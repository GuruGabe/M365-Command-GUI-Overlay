#!/usr/bin/env python3
# =============================================================================
# Script:   m365_web.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  10-23-2026 (M365GUI 0.9)
# Modified: 10-23-2026
#
# Purpose:
#   A BROWSER version of M365GUI (like GAMGUI's gam_web.py), for a computer
#   with no desktop - e.g. Azure Cloud Shell or a server reached over SSH -
#   or for anyone who prefers a browser. It uses M365GUI's own catalog,
#   command builder, safe m365 runner and guided workflows, so both
#   versions behave the same. Standard library only.
#
# Usage:
#   python3 m365_web.py              # then open http://127.0.0.1:8080
#   PORT=8081 python3 m365_web.py    # another port
#
# Security (the same three defenses as GAMGUI's browser version):
#   1. It listens on 127.0.0.1 only - not on the network.
#   2. Every /api/ call must carry a random session token that only this
#      server's own page knows (header X-M365Web-Token), so another web page
#      open in the same browser cannot run commands. POST bodies must be
#      JSON (no "simple" cross-site requests).
#   3. The Host header must be localhost / 127.0.0.1 or a name listed in
#      M365WEB_ALLOWED_HOSTS (comma separated) - this defeats DNS rebinding.
#   The server builds every command itself from the form values (a page
#   cannot send its own command line except through Custom command), and
#   refuses a destructive task the page did not confirm. It runs YOUR m365
#   with YOUR sign-in and stores no credentials. A new password from the
#   compromised-account workflow is shown once in its own window and never
#   written to the output or a log.
# =============================================================================

import base64
import csv
import datetime
import hmac
import http.server
import io
import json
import os
import platform              # v0.12: which Node.js install to offer
import re
import shlex                 # v0.12: setup commands to paste
import secrets
import subprocess
import sys
import threading
import time
import types
import urllib.parse
import uuid

# --- Import M365GUI for its DATA and LOGIC only (never opens a window) -------
# M365GUI is a tkinter app; a headless server may not have tkinter. Stub it
# so the import works - only the catalog, builder and runner are used.
try:
    import tkinter  # noqa: F401
except Exception:
    class _Stub:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, _n):
            return _Stub

        def __call__(self, *a, **k):
            return _Stub()

    _tk = types.ModuleType("tkinter")
    for _name in ("Tk", "Toplevel", "StringVar", "BooleanVar", "Text", "Frame", "Menu", "Listbox"):
        setattr(_tk, _name, _Stub)
    sys.modules["tkinter"] = _tk
    for _sub in ("ttk", "messagebox", "filedialog", "scrolledtext", "simpledialog"):
        _m = types.ModuleType("tkinter." + _sub)
        _m.__getattr__ = lambda _name: _Stub
        sys.modules["tkinter." + _sub] = _m
        setattr(_tk, _sub, _m)

import M365GUI as app          # noqa: E402
import m365_catalog as cat     # noqa: E402
import m365_workflows as wf    # noqa: E402
import m365_setup              # noqa: E402  (v0.12: Set up the CLI)

PORT = int(os.environ.get("PORT", "8080"))
SESSION_TOKEN = secrets.token_urlsafe(32)
MAX_BODY = 1024 * 1024                      # 1 MB: far more than any form
MAX_UPLOAD = 10 * 1024 * 1024               # a CSV for Run for each CSV row
UPLOAD_DAYS = 7                             # uploaded CSVs are deleted after this
EXTRA_HOSTS = {h.strip().lower() for h in
               os.environ.get("M365WEB_ALLOWED_HOSTS", "").split(",") if h.strip()}
M365_PATH = app.find_m365(os.environ.get("M365_PATH", ""))
UPLOAD_DIR = os.path.join(app.DATA_DIR, "Uploads")


def host_allowed(host_header):
    # True when the request's Host header (minus any :port) is one we serve.
    host = (host_header or "").strip().lower()
    if host.startswith("["):                 # IPv6 literal like [::1]:8080
        host = host.split("]")[0] + "]"
    elif host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    return host in ("127.0.0.1", "localhost", "[::1]") or host in EXTRA_HOSTS


# =============================================================================
# SECTION: running m365 (the desktop's safe runner - node directly, no shell)
# =============================================================================

def invocation(argv):
    return app.build_invocation(M365_PATH, argv)


def capture(argv, timeout=None):
    # One m365 command, run to the end: (returncode, output). Never raises.
    try:
        r = subprocess.run(invocation(argv), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=timeout,
                           creationflags=app.NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as exc:
        return 1, str(exc)


# =============================================================================
# SECTION: jobs - everything that runs is a job the page polls
# =============================================================================

JOBS = {}
JOBS_LOCK = threading.Lock()


class Job:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.lines = []
        self.done = False
        self.rc = None
        self.question = None                # {"text", "typed"} while waiting
        self._answer = None
        self._event = threading.Event()
        self.secret = None                  # {"title", "value"} until the page fetched it
        self.file = None                    # (path, download name)
        self.proc = None
        self.cancel = False
        self.lock = threading.Lock()

    def out(self, text):
        with self.lock:
            self.lines.append(str(text))

    def ask(self, text, typed=False):
        # Waits until the page answers (or Stop). typed=True: the page makes
        # the person type DELETE, and the server checks the word itself.
        self._answer = None
        self._event.clear()
        self.question = {"text": text, "typed": typed}
        while not self._event.wait(0.5):
            if self.cancel:
                break
        self.question = None
        return bool(self._answer)

    def answer(self, ok, typed=""):
        if self.question is None:
            return False
        self._answer = (typed == "DELETE") if self.question["typed"] else bool(ok)
        self._event.set()
        return True

    def cancelled(self):
        return self.cancel

    def stop(self):
        self.cancel = True
        self._event.set()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   capture_output=True, creationflags=app.NO_WINDOW)
                else:
                    proc.kill()
            except Exception:
                pass


def start_job(target):
    job = Job()
    with JOBS_LOCK:
        JOBS[job.id] = job

    def runner():
        try:
            target(job)
        except Exception as exc:
            job.out("ERROR: %s\n" % exc)
        finally:
            job.proc = None
            job.done = True
    threading.Thread(target=runner, daemon=True).start()
    return job


def run_command(job, argv, save_fmt=None, save_name="results"):
    # One command, its output streamed into the job. save_fmt "csv"/"json":
    # the output becomes a download instead (only if the command worked - an
    # error is shown, never saved into the file).
    if save_fmt:
        argv = cat.with_output_format(argv, save_fmt)
    job.out("> m365 %s\n" % " ".join(cat.quote_if_needed(a) for a in argv))
    try:
        proc = subprocess.Popen(invocation(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                stdin=subprocess.DEVNULL, creationflags=app.NO_WINDOW)
    except (OSError, ValueError) as exc:
        job.out("ERROR: %s\n" % exc)
        job.rc = 1
        return
    job.proc = proc
    if save_fmt:
        text = proc.stdout.read()
        proc.wait()
        if proc.returncode == 0:
            folder = os.path.join(app.LOG_DIR, "Downloads")
            os.makedirs(folder, exist_ok=True)
            name = "%s_%s.%s" % (re.sub(r"[^A-Za-z0-9]+", "-", save_name).strip("-") or "results",
                                 datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S"), save_fmt)
            path = os.path.join(folder, name)
            with open(path, "w", encoding="utf-8", newline="") as h:
                h.write(text)
            job.file = (path, name)
            job.out("Results ready (%d lines) - click Download.\n" % text.count("\n"))
        else:
            job.out(text)
    else:
        for line in proc.stdout:
            job.out(line)
        proc.wait()
    job.rc = proc.returncode
    job.out("\n[exit code %d]\n" % proc.returncode)
    if cat.changes_connection(argv):
        GROUP_CACHE["groups"] = None         # v0.11: may be another tenant now


# =============================================================================
# SECTION: the API
# =============================================================================

def task_at(data):
    try:
        return data["cat"], cat.TASKS[data["cat"]][int(data["idx"])]
    except (KeyError, ValueError, IndexError, TypeError):
        return None, None


def tasks_json():
    out = []
    for section, tasks in cat.TASKS.items():
        items = []
        for idx, t in enumerate(tasks):
            items.append({
                "idx": idx, "name": t["name"], "desc": t["desc"], "destructive": t["destructive"],
                "workflow": t["workflow"], "saves": cat.saves_output(t), "bulk": cat.bulk_available(t),
                "key": cat.task_key(section, t["name"]),
                "plan": cat.WORKFLOW_PLANS.get(t["workflow"], ""),
                # v0.11: the page reads "Signed in as" and the connections again after it
                "conn": cat.changes_connection(t["template"].split()),
                "fields": [{"label": f["label"], "key": f["key"], "required": f["required"],
                            "choices": f["choices"], "start": cat.dropdown_start(f) if f["choices"] else f["default"],
                            "picker": cat.picker_kind(section, t, f)} for f in t["fields"]]})
        out.append({"name": section, "tasks": items})
    return out


GROUP_CACHE = {"groups": None}


def api_pick(data):
    kind, text = data.get("kind"), str(data.get("text") or "")
    if kind == "user":
        lists = []
        for argv in cat.user_search_commands(text):
            rc, out = capture(argv, timeout=120)
            items = wf.parse_json(out) if rc == 0 else None
            if not isinstance(items, list):
                return {"error": "Could not search: " + " ".join(out.split())[:200]}
            lists.append(items)
        return {"choices": cat.people_choices(lists)}
    if kind == "group":
        if GROUP_CACHE["groups"] is None or data.get("refresh"):
            rc, out = capture(cat.GROUP_LIST_COMMAND, timeout=300)
            items = wf.parse_json(out) if rc == 0 else None
            if not isinstance(items, list):
                return {"error": "Could not load the groups: " + " ".join(out.split())[:200]}
            GROUP_CACHE["groups"] = items
        return {"choices": cat.group_choices(GROUP_CACHE["groups"], text)}
    if kind == "connection":
        choices, err = list_connections()
        if err:
            return {"error": err}
        words = text.lower().split()
        return {"choices": [[label, name] for label, name, _a in choices
                            if all(w in (label + " " + name).lower() for w in words)]}
    return {"error": "unknown list"}


# ---- connections (v0.11, like the desktop's Connection list) -----------------
def list_connections():
    # -> ([(label, name, active)], error text or "")
    if not M365_PATH:
        return [], "The m365 CLI was not found on this computer."
    rc, out = capture(cat.CONNECTION_LIST_COMMAND, timeout=60)
    items = wf.parse_json(out) if rc == 0 else None
    if not isinstance(items, list):
        return [], "Could not list the connections: " + " ".join(out.split())[:200]
    return cat.connection_choices(items), ""


def api_connection_use(data):
    # Only a name the CLI itself listed is accepted, and not while a job
    # runs (its next commands would run as another account).
    name = str(data.get("name") or "")
    with JOBS_LOCK:
        busy = any(not job.done for job in JOBS.values())
    if busy:
        return {"error": "A task is running. Switch the connection when it has finished (or click Stop)."}
    choices, err = list_connections()
    if err:
        return {"error": err}
    if name not in [n for _label, n, _a in choices]:
        return {"error": "Unknown connection."}
    rc, out = capture(cat.connection_use_command(name), timeout=60)
    if rc != 0:
        return {"error": "Could not switch: " + " ".join(out.split())[:200]}
    GROUP_CACHE["groups"] = None
    return {"ok": True}


def api_run(data):
    if not M365_PATH:
        return {"error": "The m365 CLI was not found on this computer."}
    if data.get("custom") is not None:
        text = str(data["custom"]).strip()
        if text.lower().startswith("m365 "):
            text = text[5:]
        argv = [a[1:-1] if a.startswith('"') and a.endswith('"') and len(a) > 1 else a
                for a in re.findall(r'"[^"]*"|\S+', text)]
        if not argv:
            return {"error": "Type a command."}
        return {"job": start_job(lambda job: run_command(job, argv)).id}
    section, task = task_at(data)
    if not task or task["workflow"]:
        return {"error": "Unknown task."}
    _display, argv, err = cat.build_command(task, data.get("values") or {}, section)
    if err:
        return {"error": err}
    if task["destructive"] and not data.get("confirmed"):
        return {"error": "This task changes or deletes data - confirm it first."}
    fmt = cat.SAVE_FORMATS.get(data.get("save") or "") if cat.saves_output(task) else None
    return {"job": start_job(lambda job: run_command(job, argv, fmt, task["name"])).id}


def api_workflow(data):
    if not M365_PATH:
        return {"error": "The m365 CLI was not found on this computer."}
    section, task = task_at(data)
    if not task or not task["workflow"]:
        return {"error": "Unknown workflow."}
    values = dict(data.get("values") or {})
    name = task["workflow"]
    records = os.path.join(app.DATA_DIR, "Records")

    def target(job):
        os.makedirs(app.LOG_DIR, exist_ok=True)
        if name == "remove_guests":
            wf.remove_all_guests(capture, job.out, lambda q: job.ask(q, typed=True), job.cancelled)
        elif name == "onedrive_transfer":
            stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
            who = re.sub(r"[^A-Za-z0-9._-]", "_", (values.get("from") or "").split("@")[0])
            wf.transfer_onedrive(capture, job.out, job.ask, job.cancelled, values,
                                 os.path.join(app.LOG_DIR, "OneDrive-Copy_%s_%s.csv" % (who, stamp)))
        elif name == "staff_handoff":
            os.makedirs(records, exist_ok=True)
            wf.staff_handoff(capture, job.out, job.ask, job.cancelled, values, records)
        elif name == "compromised":
            os.makedirs(records, exist_ok=True)

            def show_secret(title, secret):
                job.secret = {"title": title, "value": secret}
                job.out("(The new password is in its own window - it is not shown here or "
                        "saved in any log.)\n")
            wf.compromised_response(capture, job.out, job.ask, job.cancelled, values, records,
                                    show_secret, app.random_password)
        else:
            job.out("Unknown workflow.\n")
    return {"job": start_job(target).id}


def api_job(job_id, since):
    job = JOBS.get(job_id)
    if not job:
        return {"error": "unknown job"}
    with job.lock:
        lines = job.lines[since:]
        nxt = len(job.lines)
    secret, job.secret = job.secret, None   # handed over ONCE, then forgotten
    # v0.12: a sign-in / app problem -> the page offers Set up the CLI.
    setup = bool(job.done and job.rc not in (0, None)
                 and m365_setup.setup_can_fix("".join(job.lines[-200:])))
    return {"lines": lines, "next": nxt, "done": job.done, "rc": job.rc,
            "question": job.question, "secret": secret, "file": bool(job.file),
            "setup": setup}


def clean_uploads():
    # Uploaded CSVs are kept UPLOAD_DAYS days (re-runs), then deleted.
    try:
        cutoff = time.time() - UPLOAD_DAYS * 86400
        for name in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, name)
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
    except OSError:
        pass


def api_upload(data):
    name = os.path.basename(str(data.get("name") or "upload.csv"))
    try:
        raw = base64.b64decode(str(data.get("data") or ""), validate=True)
    except (ValueError, TypeError):
        return {"error": "The file could not be read."}
    if len(raw) > MAX_UPLOAD:
        return {"error": "The file is larger than %d MB." % (MAX_UPLOAD // 1048576)}
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:] or "upload.csv"
    path = os.path.join(UPLOAD_DIR, uuid.uuid4().hex[:8] + "_" + safe)
    with open(path, "wb") as h:
        h.write(raw)
    clean_uploads()
    return {"path": path}


def _read_csv(path):
    # Only files this server stored (Uploads) can be read - a page cannot
    # name any other file on the computer.
    real = os.path.realpath(path or "")
    if not real.startswith(os.path.realpath(UPLOAD_DIR) + os.sep) or not os.path.isfile(real):
        raise ValueError("Upload the CSV file first.")
    with open(real, encoding="utf-8-sig", newline="") as h:
        reader = csv.DictReader(h)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def api_bulk_columns(data):
    section, task = task_at(data)
    if not task or not cat.bulk_available(task):
        return {"error": "This task cannot run per CSV row."}
    try:
        headers, rows = _read_csv(data.get("path"))
    except (ValueError, OSError, csv.Error, UnicodeDecodeError) as exc:
        return {"error": str(exc)}
    return {"headers": headers, "rows": len(rows), "form": cat.FORM_VALUE,
            "guess": {f["key"]: cat.bulk_guess_column(f, headers) for f in task["fields"]}}


def api_bulk_start(data):
    section, task = task_at(data)
    if not task or not cat.bulk_available(task):
        return {"error": "This task cannot run per CSV row."}
    try:
        _headers, rows = _read_csv(data.get("path"))
    except (ValueError, OSError, csv.Error, UnicodeDecodeError) as exc:
        return {"error": str(exc)}
    limit = str(data.get("limit") or "").strip()
    if limit and (not limit.isdigit() or int(limit) < 1):
        return {"error": "Test rows must be a whole number of 1 or more."}
    rows = rows[:int(limit)] if limit else rows
    if not rows:
        return {"error": "The CSV file has no data rows."}
    steps = cat.bulk_plan(task, section, data.get("values") or {}, data.get("mapping") or {}, rows)
    bad = [(n, e) for n, _a, e in steps if e]
    if bad:
        return {"error": "%d row(s) cannot be run:\n" % len(bad)
                + "\n".join("row %d: %s" % b for b in bad[:8])}
    first = "m365 " + " ".join(cat.quote_if_needed(a) for a in steps[0][1])
    if data.get("preview"):
        return {"first": first, "count": len(steps)}
    if task["destructive"] and not data.get("confirmed"):
        return {"error": "This task changes or deletes data - confirm it first.",
                "first": first, "count": len(steps)}

    def target(job):
        ok = failed = 0
        job.out("===== %s - once per CSV row (%d row(s)) =====\n" % (task["name"], len(steps)))
        for number, argv, _e in steps:
            if job.cancel:
                job.out("[Stopped - the remaining rows were not run.]\n")
                break
            rc, out = capture(argv)
            shown = "m365 " + " ".join(cat.quote_if_needed(a) for a in argv)
            if rc == 0:
                ok += 1
                job.out("  row %d OK      %s\n" % (number, shown))
            else:
                failed += 1
                job.out("  row %d FAILED  %s\n          %s\n" % (number, shown, " ".join(out.split())[:200]))
        job.out("===== DONE: %d OK, %d failed =====\n" % (ok, failed))
    return {"job": start_job(target).id}


def api_status():
    account = app.account_text(M365_PATH, lambda a: capture(a, timeout=60))
    choices = list_connections()[0] if M365_PATH else []
    return {"version": app.APP_VERSION, "m365": M365_PATH, "account": account,
            "setup": m365_setup.needs_window(account),          # v0.12
            "connections": [{"label": label, "name": name, "active": active}
                            for label, name, active in choices]}


# ---- Set up the CLI (v0.12, the desktop's Settings > Set up the CLI) ----------
# What this server still needs (Node.js, the CLI, the CLI's app ID, a
# sign-in), Install the CLI (npm, a job), and Sign in with a code (a job: the
# CLI prints a code and a web address; the person signs in in their own
# browser). Installing Node.js (winget shows a license to accept), 'm365
# setup' (a wizard that asks questions) and the browser sign-in need a
# terminal, so the page shows their commands to paste into one on THIS
# server.
def _busy():
    with JOBS_LOCK:
        return any(not job.done for job in JOBS.values())


def _node():
    return app.find_node(os.path.dirname(M365_PATH) if M365_PATH else "")


def _shell_words(words):
    # Words as one line to paste into this server's terminal.
    if os.name == "nt":
        return " ".join('"%s"' % w if (" " in w or not w) else w for w in words)
    return " ".join(shlex.quote(w) for w in words)


def api_setup():
    node = _node()
    node_version = ""
    if node:
        try:
            node_version = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL, creationflags=app.NO_WINDOW).stdout.strip()
        except Exception:
            node_version = ""
    account = app.account_text(M365_PATH, lambda a: capture(a, timeout=60))
    cli_version, app_ok = "", False
    if M365_PATH and node:
        rc, out = capture(["version"], timeout=60)
        found = re.search(r"\d+\.\d+\.\d+", out or "")
        cli_version = found.group(0) if rc == 0 and found else ""
        rc, out = capture(m365_setup.CLIENT_ID_COMMAND, timeout=60)
        app_ok = m365_setup.app_id_set(rc, out)
    kind, how = m365_setup.node_install_plan(platform.system())
    m365 = M365_PATH or "m365"
    return {"node": node, "node_version": node_version, "m365": M365_PATH,
            "cli_version": cli_version, "app_ok": app_ok, "account": account,
            "steps": m365_setup.needed_steps(bool(node), bool(M365_PATH), app_ok, account),
            "node_command": _shell_words(how) if kind == "winget" else "",
            "node_url": how if kind == "download" else "",
            "npm_command": _shell_words(m365_setup.npm_install_command(
                m365_setup.find_npm(node) or "npm")),
            "commands": {"setup": _shell_words([m365] + m365_setup.SETUP_COMMAND),
                         "browser": _shell_words([m365] + m365_setup.login_command("browser")),
                         "code": _shell_words([m365] + m365_setup.login_command("deviceCode"))}}


def api_setup_install_cli():
    # 'npm install -g @pnp/cli-microsoft365' as a job; m365 is looked for again.
    if _busy():
        return {"error": "A task is running - install the CLI when it has finished."}
    node = _node()
    npm = m365_setup.find_npm(node)
    if not node or not npm:
        return {"error": "Install Node.js first (step 1) - npm, which installs the CLI, comes with it."}
    command = m365_setup.npm_install_command(npm)

    def target(job):
        global M365_PATH
        job.out("===== INSTALL THE CLI FOR MICROSOFT 365 =====\n> %s\n" % _shell_words(command))
        lines = []
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    stdin=subprocess.DEVNULL, creationflags=app.NO_WINDOW)
        except (OSError, ValueError) as exc:
            job.out("ERROR: %s\n" % exc)
            job.rc = 1
            return
        job.proc = proc
        for line in proc.stdout:
            job.out(line)
            lines.append(line)
            del lines[:-200]
        proc.wait()
        job.rc = proc.returncode
        if proc.returncode == 0:
            M365_PATH = app.find_m365("") or M365_PATH
            job.out("\nThe CLI is installed%s.\n" % ((" (" + M365_PATH + ")") if M365_PATH else ""))
        else:
            hint = m365_setup.npm_failure_hint("".join(lines))
            job.out("\nnpm stopped with exit code %d.%s\n" % (proc.returncode, (" " + hint) if hint else ""))
    return {"job": start_job(target).id}


def api_setup_login():
    # 'm365 login --authType deviceCode' as a job: the CLI prints the web
    # address and code; the person signs in in their own browser.
    if not M365_PATH:
        return {"error": "Install the CLI first (step 2)."}
    if _busy():
        return {"error": "A task is running - sign in when it has finished."}
    argv = m365_setup.login_command("deviceCode")
    return {"job": start_job(lambda job: run_command(job, argv)).id}


# =============================================================================
# SECTION: the HTTP server
# =============================================================================

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "M365Web"

    def log_message(self, fmt, *args):
        pass                                 # quiet: no request lines on the console

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else (
            json.dumps(body).encode("utf-8") if not isinstance(body, str) else body.encode("utf-8"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self, api):
        if not host_allowed(self.headers.get("Host")):
            self._send(403, {"error": "host not allowed"})
            return False
        if api and not hmac.compare_digest(self.headers.get("X-M365Web-Token", ""), SESSION_TOKEN):
            self._send(403, {"error": "missing or wrong token"})
            return False
        return True

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        api = url.path.startswith("/api/")
        if not self._allowed(api):
            return
        query = urllib.parse.parse_qs(url.query)
        if url.path == "/":
            self._send(200, PAGE.replace("__TOKEN__", SESSION_TOKEN).replace("__VERSION__", app.APP_VERSION),
                       "text/html; charset=utf-8",
                       {"Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; "
                                                   "style-src 'unsafe-inline'; connect-src 'self'"})
        elif url.path == "/api/tasks":
            self._send(200, tasks_json())
        elif url.path == "/api/status":
            self._send(200, api_status())
        elif url.path == "/api/setup":                          # v0.12
            self._send(200, api_setup())
        elif url.path == "/api/job":
            try:
                since = int((query.get("since") or ["0"])[0])
            except ValueError:
                since = 0
            self._send(200, api_job((query.get("job") or [""])[0], since))
        elif url.path == "/api/job/file":
            job = JOBS.get((query.get("job") or [""])[0])
            if not job or not job.file:
                self._send(404, {"error": "no file"})
                return
            path, name = job.file
            with open(path, "rb") as h:
                data = h.read()
            self._send(200, data, "application/octet-stream",
                       {"Content-Disposition": 'attachment; filename="%s"' % name})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        if not self._allowed(True):
            return
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._send(415, {"error": "JSON only"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        limit = MAX_UPLOAD * 2 if url.path == "/api/bulk/upload" else MAX_BODY
        if length < 0 or length > limit:
            self._send(413, {"error": "request too large"})
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            self._send(400, {"error": "bad JSON"})
            return
        routes = {
            "/api/build": lambda: dict(zip(("display", "argv", "error"),
                                           cat.build_command(task_at(data)[1], data.get("values") or {},
                                                             task_at(data)[0]))) if task_at(data)[1]
                         else {"error": "Unknown task."},
            "/api/run": lambda: api_run(data),
            "/api/workflow/start": lambda: api_workflow(data),
            "/api/pick": lambda: api_pick(data),
            "/api/connection/use": lambda: api_connection_use(data),
            "/api/setup/cli": api_setup_install_cli,                 # v0.12
            "/api/setup/login": api_setup_login,                     # v0.12
            "/api/job/answer": lambda: {"ok": bool(JOBS.get(data.get("job")) and
                                                   JOBS[data["job"]].answer(data.get("ok"), str(data.get("typed") or "")))},
            "/api/job/stop": lambda: (JOBS[data["job"]].stop() or {"ok": True}) if data.get("job") in JOBS
                             else {"error": "unknown job"},
            "/api/bulk/upload": lambda: api_upload(data),
            "/api/bulk/columns": lambda: api_bulk_columns(data),
            "/api/bulk/start": lambda: api_bulk_start(data),
        }
        handler = routes.get(url.path)
        if not handler:
            self._send(404, {"error": "not found"})
            return
        self._send(200, handler())


def make_server(port=PORT):
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)


# =============================================================================
# SECTION: the page (one file: HTML + CSS + JavaScript, no outside files)
# =============================================================================

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>M365GUI __VERSION__ (browser)</title>
<style>
:root{--bg:#fff;--fg:#1b1b1b;--muted:#5f6368;--line:#d0d7de;--accent:#0b57d0;--bad:#b3261e;--panel:#f6f8fa}
@media (prefers-color-scheme: dark){:root{--bg:#1e1f22;--fg:#e6e6e6;--muted:#a0a4a8;--line:#3a3d41;--accent:#8ab4f8;--bad:#f28b82;--panel:#2a2c30}}
*{box-sizing:border-box} body{margin:0;font:14px/1.4 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}
header{display:flex;gap:16px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
header b{font-size:15px} #acct{color:var(--muted)}
main{display:flex;min-height:calc(100vh - 44px)} nav{width:320px;border-right:1px solid var(--line);padding:8px;overflow:auto;max-height:calc(100vh - 44px)}
section{flex:1;padding:12px 16px;min-width:0}
nav input{width:100%;padding:6px;margin-bottom:6px} nav details{margin:2px 0} nav summary{cursor:pointer;font-weight:600}
nav a{display:block;padding:2px 6px 2px 14px;color:var(--fg);text-decoration:none;border-radius:4px;cursor:pointer}
nav a:hover,nav a.on{background:var(--panel)} nav a.bad{color:var(--bad)}
label{display:block;margin-top:8px;font-weight:600} input,select,textarea,button{font:inherit}
input[type=text],select,textarea{width:100%;max-width:640px;padding:6px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg)}
.row{display:flex;gap:6px;align-items:center;max-width:720px} .row input{flex:1}
button{padding:6px 12px;border:1px solid var(--line);border-radius:4px;background:var(--panel);color:var(--fg);cursor:pointer}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)} button:disabled{opacity:.5;cursor:default}
pre{background:var(--panel);border:1px solid var(--line);padding:8px;border-radius:4px;white-space:pre-wrap;word-break:break-word;max-height:55vh;overflow:auto}
#desc{color:var(--muted);max-width:820px} .bar{display:flex;gap:8px;margin:10px 0;flex-wrap:wrap}
dialog{border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);max-width:620px;width:92%}
dialog select{height:220px} .note{color:var(--muted);font-size:13px}
@media (max-width:760px){main{display:block} nav{width:auto;max-height:none;border-right:0;border-bottom:1px solid var(--line)}}
</style></head><body>
<header><b>M365GUI __VERSION__</b><span id="acct">Signed in as: (checking...)</span>
<label for="conn" style="margin:0;font-weight:normal">Connection:</label><select id="conn" style="width:auto;max-width:360px"></select>
<button id="setupbtn">Set up the CLI...</button></header>
<main><nav><input id="q" type="text" placeholder="Search tasks..." aria-label="Search tasks"><div id="tree"></div></nav>
<section><h3 id="title">Select a task on the left.</h3><div id="desc"></div><div id="form"></div>
<div id="previewbox"><label>Command preview</label><pre id="preview"></pre></div>
<div class="bar"><button class="primary" id="run">Run</button><button id="stop" disabled>Stop</button>
<button id="bulk">Run for each CSV row...</button><button id="dl" style="display:none">Download results</button>
<button id="fav">Add to Favorites</button><button id="clear">Clear output</button></div>
<pre id="out"></pre></section></main>
<dialog id="pickdlg"><h4 id="picktitle">Pick</h4><div class="row"><input id="picktext" type="text"><button id="picksearch">Search</button></div>
<p id="picknote" class="note"></p><select id="picklist" size="10" style="width:100%"></select>
<div class="bar"><button class="primary" id="pickok">OK</button><button id="pickcancel">Cancel</button></div></dialog>
<dialog id="askdlg"><p id="asktext" style="white-space:pre-wrap"></p><div id="asktyped" style="display:none">
<label>Type DELETE to go ahead</label><input id="askword" type="text"></div>
<div class="bar"><button class="primary" id="askyes">Yes</button><button id="askno">No</button></div></dialog>
<dialog id="secretdlg"><p id="secrettitle"></p><input id="secretvalue" type="text" readonly style="font-family:Consolas,monospace;font-size:16px">
<div class="bar"><button id="secretcopy">Copy</button><button class="primary" id="secretclose">Close</button></div></dialog>
<dialog id="bulkdlg"><h4>Run for each CSV row</h4><p class="note">The CSV's first row must be the column names. Each box takes a column or the form's value.</p>
<input id="bulkfile" type="file" accept=".csv,text/csv"><div id="bulkmap"></div>
<label>Test run - only the first ... rows (blank = every row)</label><input id="bulklimit" type="text" style="max-width:120px">
<p id="bulknote" class="note"></p><div class="bar"><button id="bulkfirst">Show the first row's command</button>
<button class="primary" id="bulkgo">Run</button><button id="bulkcancel">Cancel</button></div></dialog>
<dialog id="setupdlg" style="max-width:760px"><h4>Set up the CLI for Microsoft 365</h4><p id="setupwhy" class="note"></p><div id="setupbody">Checking this server...</div>
<div class="bar"><button id="setupcheck">Check again</button><button class="primary" id="setupclose">Close</button></div></dialog>
<script>
const TOKEN="__TOKEN__"; const $=id=>document.getElementById(id);
let SECTIONS=[], CUR=null, JOB=null, SINCE=0, BULKPATH="";
function store(k,v){try{if(v===undefined)return JSON.parse(localStorage.getItem(k)||"[]");localStorage.setItem(k,JSON.stringify(v))}catch(e){return []}}
async function getj(u){const r=await fetch(u,{headers:{"X-M365Web-Token":TOKEN}});return r.json()}
async function api(u,b){const r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json","X-M365Web-Token":TOKEN},body:JSON.stringify(b||{})});return r.json()}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function out(t){const o=$("out");o.textContent+=t;o.scrollTop=o.scrollHeight}
function findTask(key){for(const s of SECTIONS)for(const t of s.tasks)if(t.key===key)return [s.name,t];return null}
function matches(sec,t,q){const text=(sec+" "+t.name+" "+t.desc).toLowerCase();return q.toLowerCase().split(/\s+/).filter(Boolean).every(w=>text.includes(w))}
function link(sec,t){const a=document.createElement("a");a.textContent=t.name;if(t.destructive)a.className="bad";
  a.onclick=()=>openTask(sec,t);if(CUR&&CUR.t.key===t.key)a.classList.add("on");return a}
function drawTree(){const q=$("q").value.trim(),tree=$("tree");tree.innerHTML="";
  for(const [title,keys] of [["Favorites",store("m365web.fav")],["Recent",store("m365web.recent")]]){
    const hits=keys.map(findTask).filter(x=>x&&(!q||matches(x[0],x[1],q)));if(!hits.length)continue;
    const d=document.createElement("details");d.open=true;d.innerHTML="<summary>"+title+"</summary>";hits.forEach(([s,t])=>d.appendChild(link(s,t)));tree.appendChild(d)}
  for(const s of SECTIONS){const hits=s.tasks.filter(t=>!q||matches(s.name,t,q));if(!hits.length)continue;
    const d=document.createElement("details");d.open=!!q;d.innerHTML="<summary>"+esc(s.name)+"</summary>";hits.forEach(t=>d.appendChild(link(s.name,t)));tree.appendChild(d)}
  const c=document.createElement("a");c.textContent="Custom command";c.onclick=openCustom;tree.appendChild(c)}
function values(){const v={};document.querySelectorAll("#form [data-key]").forEach(e=>v[e.dataset.key]=e.value);return v}
function openTask(sec,t){CUR={sec:sec,t:t};$("title").textContent=t.name;$("desc").textContent=t.desc;
  const f=$("form");f.innerHTML="";
  for(const fl of t.fields){const lab=document.createElement("label");lab.textContent=fl.label+(fl.required?" *":"");f.appendChild(lab);
    let el;if(fl.choices){el=document.createElement("select");fl.choices.forEach(c=>{const o=document.createElement("option");o.value=c;o.textContent=c||"(blank)";el.appendChild(o)});el.value=fl.start}
    else{el=document.createElement("input");el.type="text";el.value=fl.start||""}
    el.dataset.key=fl.key;el.id="f_"+fl.key;lab.htmlFor=el.id;el.oninput=el.onchange=build;
    if(fl.picker){const r=document.createElement("div");r.className="row";r.appendChild(el);const b=document.createElement("button");b.textContent="Pick...";b.onclick=()=>pick(fl.picker,el);r.appendChild(b);f.appendChild(r)}else f.appendChild(el)}
  if(t.saves){const lab=document.createElement("label");lab.textContent="Save results to";lab.htmlFor="save";f.appendChild(lab);
    const s=document.createElement("select");s.id="save";["Screen","CSV file","JSON file"].forEach(c=>{const o=document.createElement("option");o.textContent=c;s.appendChild(o)});f.appendChild(s)}
  $("bulk").style.display=t.bulk?"":"none";$("fav").style.display="";
  $("fav").textContent=store("m365web.fav").includes(t.key)?"Remove from Favorites":"Add to Favorites";
  $("previewbox").style.display="";$("dl").style.display="none";drawTree();build()}
function openCustom(){CUR={custom:true};$("title").textContent="Custom command";$("desc").textContent="Type any m365 command (without the leading 'm365') and press Run. Reference: https://pnp.github.io/cli-microsoft365/";
  $("form").innerHTML='<label for="custom">Command</label><input id="custom" type="text" placeholder="e.g. entra user list --type Guest">';$("previewbox").style.display="none";$("bulk").style.display="none";$("fav").style.display="none";drawTree()}
let BSEQ=0;async function build(){if(!CUR||CUR.custom)return;if(CUR.t.workflow){$("preview").textContent=CUR.t.plan;return}
  const seq=++BSEQ,r=await api("/api/build",{cat:CUR.sec,idx:CUR.t.idx,values:values()});if(seq!==BSEQ)return;
  $("preview").textContent=r.error?"("+r.error+")":"m365 "+r.display}
function remember(){if(!CUR||CUR.custom)return;const r=store("m365web.recent").filter(k=>k!==CUR.t.key);r.unshift(CUR.t.key);store("m365web.recent",r.slice(0,10));drawTree()}
async function run(){if(JOB)return;let r;
  if(CUR&&CUR.custom){r=await api("/api/run",{custom:$("custom").value,confirmed:true})}
  else if(!CUR){return}
  else if(CUR.t.workflow){r=await api("/api/workflow/start",{cat:CUR.sec,idx:CUR.t.idx,values:values()})}
  else{const ok=!CUR.t.destructive||confirm("This changes or deletes data:\n\n"+$("preview").textContent+"\n\nAre you sure?");if(!ok)return;
    r=await api("/api/run",{cat:CUR.sec,idx:CUR.t.idx,values:values(),confirmed:ok,save:($("save")||{}).value})}
  if(r.error){out("\n("+r.error+")\n");return}remember();follow(r.job)}
async function follow(id){JOB=id;SINCE=0;$("run").disabled=true;$("stop").disabled=false;$("dl").style.display="none";out("\n");
  while(JOB===id){const s=await getj("/api/job?job="+encodeURIComponent(id)+"&since="+SINCE);
    if(s.error){out("("+s.error+")\n");break}
    if(s.lines.length)out(s.lines.join(""));SINCE=s.next;
    if(s.secret)showSecret(s.secret);
    if(s.question&&!$("askdlg").open)ask(id,s.question);
    if(s.done){FOLLOWRC=s.rc;if(s.file){$("dl").style.display="";$("dl").onclick=()=>download(id)}if(s.setup)offerSetup();break}
    await new Promise(r=>setTimeout(r,500))}
  JOB=null;$("run").disabled=false;$("stop").disabled=true;
  if(CUR&&(CUR.custom?/^(m365\s+)?(login|logout|connection\s+(use|set|remove))\b/i.test($("custom").value.trim()):CUR.t.conn))refreshAcct()}
let CONNS=[];
async function refreshAcct(){$("acct").textContent="Signed in as: (checking...)";const s=await getj("/api/status");$("acct").textContent=s.account;
  if(s.setup&&!SETUPASKED){SETUPASKED=true;showSetup("Something the CLI needs is missing on this server.")}
  CONNS=s.connections||[];const c=$("conn");c.innerHTML="";
  CONNS.forEach(x=>{const o=document.createElement("option");o.value=x.name;o.textContent=x.label;if(x.active)o.selected=true;c.appendChild(o)})}
async function switchConn(){const c=$("conn"),now=CONNS.find(x=>x.active);if(now&&c.value===now.name)return;
  if(JOB){out("\n(A task is running. Switch the connection when it has finished, or click Stop.)\n");if(now)c.value=now.name;return}
  $("acct").textContent="Signed in as: (switching...)";const r=await api("/api/connection/use",{name:c.value});
  out(r.error?"\n(Could not switch: "+r.error+")\n":"\nSwitched to the connection "+c.options[c.selectedIndex].textContent+" - every command now runs as that account.\n");refreshAcct()}
// v0.12: Set up the CLI - what this server still needs (GET /api/setup).
// Install the CLI and Sign in with a code run here as jobs (their output in
// the output box); installing Node.js, 'm365 setup' and the browser sign-in
// ask questions, so the dialog shows their commands to paste into a terminal
// on the server. Opens by itself once when something is missing, and is
// offered once after a sign-in error.
let SETUPASKED=false,FOLLOWRC=null;
function offerSetup(){if(SETUPASKED||$("setupdlg").open)return;SETUPASKED=true;
  if(confirm("This looks like a sign-in or CLI app problem. Open Set up the CLI to fix it?"))showSetup("")}
async function showSetup(why){$("setupwhy").textContent=why||"";$("setupbody").textContent="Checking this server...";
  if(!$("setupdlg").open)$("setupdlg").showModal();
  const s=await getj("/api/setup");
  const box=(title,state,more)=>"<label>"+esc(title)+"</label><div>"+esc(state)+"</div>"+(more||"");
  const cmd=t=>"<pre style=\"user-select:all;margin:4px 0\">"+esc(t)+"</pre>";
  let h=box("1. Node.js (the CLI runs on it)",s.node?"Installed: "+(s.node_version||"?")+" ("+s.node+")":"Not found on this server.",
    s.node?"":(s.node_command?"<p class=\"note\">Paste into a terminal on this server (winget shows Node.js's license and asks for administrator approval):</p>"+cmd(s.node_command)
      :"<p class=\"note\">Install the LTS version from <a href=\""+esc(s.node_url)+"\" target=\"_blank\" rel=\"noopener\">"+esc(s.node_url)+"</a> on this server.</p>"));
  h+=box("2. The CLI for Microsoft 365",s.m365?(s.cli_version?"Installed: "+s.cli_version+" ("+s.m365+")":"Found "+s.m365+", but it did not answer."):"Not found on this server.",
    "<div class=\"bar\"><button id=\"setupcli\">"+(s.m365?"Update the CLI":"Install the CLI")+"</button></div><p class=\"note\">Runs: "+esc(s.npm_command)+"</p>");
  h+=box("3. The CLI's own app (m365 setup)",s.app_ok?"Set.":"Not set yet - the CLI needs an Entra app before anyone can sign in.",
    "<p class=\"note\">A wizard that asks questions (create an app registration - a Global admin consents - or use an existing one). Paste into a terminal on this server:</p>"+cmd(s.commands.setup));
  h+=box("4. Sign in",s.account,
    "<div class=\"bar\"><button id=\"setupcode\">Sign in with a code</button></div><p class=\"note\">Shows a web address and a code in the output box; sign in there in your own browser. Or sign in with a browser on the server, in a terminal:</p>"+cmd(s.commands.browser));
  $("setupbody").innerHTML=h;
  const job=async(path)=>{const r=await api(path,{});if(r.error){alert(r.error);return}$("setupdlg").close();FOLLOWRC=null;await follow(r.job);refreshAcct();
    if(FOLLOWRC===0)showSetup("Done - here is what is still needed, if anything.")};   // a failure stays readable in the output box
  $("setupcli").onclick=()=>{if(confirm("Install (or update) the CLI for Microsoft 365 on this server?\n\n"+s.npm_command+"\n\nnpm downloads it from the npm registry. It takes a minute or two."))job("/api/setup/cli")};
  $("setupcode").onclick=()=>job("/api/setup/login")}
function ask(id,q){$("asktext").textContent=q.text;$("asktyped").style.display=q.typed?"":"none";$("askword").value="";
  $("askyes").onclick=async()=>{$("askdlg").close();await api("/api/job/answer",{job:id,ok:true,typed:$("askword").value})};
  $("askno").onclick=async()=>{$("askdlg").close();await api("/api/job/answer",{job:id,ok:false})};$("askdlg").showModal()}
function showSecret(s){$("secrettitle").textContent=s.title;$("secretvalue").value=s.value;
  $("secretcopy").onclick=()=>navigator.clipboard&&navigator.clipboard.writeText(s.value);
  $("secretclose").onclick=()=>{$("secretvalue").value="";$("secretdlg").close()};$("secretdlg").showModal()}
async function download(id){const r=await fetch("/api/job/file?job="+encodeURIComponent(id),{headers:{"X-M365Web-Token":TOKEN}});
  const name=(r.headers.get("Content-Disposition")||"").split('filename="')[1]||"results";const b=await r.blob();
  const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download=name.replace(/"$/,"");a.click();URL.revokeObjectURL(a.href)}
let PICKEL=null,PICKKIND="";
function pick(kind,el){PICKEL=el;PICKKIND=kind;$("picktitle").textContent="Pick a "+kind;$("picktext").value=el.value;$("picklist").innerHTML="";
  $("picknote").textContent=kind==="user"?"Type the start of a name or address, then Search.":kind==="connection"?"Loading the saved connections...":"Loading the groups (once)...";$("pickdlg").showModal();if(kind!=="user")pickSearch()}
async function pickSearch(){const r=await api("/api/pick",{kind:PICKKIND,text:$("picktext").value});const l=$("picklist");l.innerHTML="";
  if(r.error){$("picknote").textContent=r.error;return}
  r.choices.forEach(([label,value])=>{const o=document.createElement("option");o.textContent=label;o.value=value;l.appendChild(o)});
  $("picknote").textContent=r.choices.length+" found"}
async function bulkOpen(){if(!CUR||CUR.custom||!CUR.t.bulk)return;BULKPATH="";$("bulkmap").innerHTML="";$("bulknote").textContent="";$("bulkfile").value="";$("bulkdlg").showModal()}
function bulkMapping(){const m={};document.querySelectorAll("#bulkmap select").forEach(s=>m[s.dataset.key]=s.value);return m}
async function bulkRead(){const f=$("bulkfile").files[0];if(!f)return;const rd=new FileReader();
  rd.onload=async()=>{const up=await api("/api/bulk/upload",{name:f.name,data:String(rd.result).split(",").pop()});
    if(up.error){$("bulknote").textContent=up.error;return}BULKPATH=up.path;
    const c=await api("/api/bulk/columns",{cat:CUR.sec,idx:CUR.t.idx,path:BULKPATH});if(c.error){$("bulknote").textContent=c.error;return}
    const m=$("bulkmap");m.innerHTML="";for(const fl of CUR.t.fields){const lab=document.createElement("label");lab.textContent=fl.label;m.appendChild(lab);
      const s=document.createElement("select");s.dataset.key=fl.key;[c.form].concat(c.headers).forEach(h=>{const o=document.createElement("option");o.textContent=h;s.appendChild(o)});
      s.value=c.guess[fl.key];m.appendChild(s)}
    $("bulknote").textContent=c.rows+" data row(s), columns: "+c.headers.join(", ")};rd.readAsDataURL(f)}
async function bulkStart(preview){const body={cat:CUR.sec,idx:CUR.t.idx,path:BULKPATH,mapping:bulkMapping(),values:values(),limit:$("bulklimit").value,preview:preview};
  let r=await api("/api/bulk/start",body);
  if(!preview&&r.error&&r.first){if(!confirm("This changes or deletes data, once per row - "+r.count+" row(s).\n\nFirst row:\n"+r.first+"\n\nAre you sure?"))return;
    body.confirmed=true;r=await api("/api/bulk/start",body)}
  if(r.error){$("bulknote").textContent=r.error;return}
  if(preview){$("bulknote").textContent="First row runs: "+r.first+" ("+r.count+" row(s) in all)";return}
  $("bulkdlg").close();remember();follow(r.job)}
$("q").oninput=drawTree;$("run").onclick=run;$("stop").onclick=()=>JOB&&api("/api/job/stop",{job:JOB});
$("clear").onclick=()=>$("out").textContent="";$("bulk").onclick=bulkOpen;$("bulkfile").onchange=bulkRead;
$("bulkfirst").onclick=()=>bulkStart(true);$("bulkgo").onclick=()=>bulkStart(false);$("bulkcancel").onclick=()=>$("bulkdlg").close();
$("picksearch").onclick=pickSearch;$("picktext").onkeydown=e=>{if(e.key==="Enter")pickSearch()};$("picktext").oninput=()=>{if(PICKKIND!=="user")pickSearch()};
$("pickok").onclick=()=>{const v=$("picklist").value;if(v){PICKEL.value=v;build()}$("pickdlg").close()};$("picklist").ondblclick=$("pickok").onclick;
$("pickcancel").onclick=()=>$("pickdlg").close();
$("fav").onclick=()=>{if(!CUR||CUR.custom)return;let f=store("m365web.fav");f=f.includes(CUR.t.key)?f.filter(k=>k!==CUR.t.key):f.concat([CUR.t.key]);store("m365web.fav",f);openTask(CUR.sec,CUR.t)};
$("acct").onclick=refreshAcct;$("conn").onchange=switchConn;
$("setupbtn").onclick=()=>showSetup("");$("setupcheck").onclick=()=>showSetup("");$("setupclose").onclick=()=>$("setupdlg").close();
(async()=>{SECTIONS=await getj("/api/tasks");drawTree();refreshAcct()})();
</script></body></html>
"""


def main():
    clean_uploads()
    server = make_server(PORT)
    print("M365GUI %s (browser) - open http://127.0.0.1:%d   (Ctrl+C to stop)" % (app.APP_VERSION, PORT))
    if not M365_PATH:
        print("NOTE: the 'm365' CLI was not found. Install it: npm i -g @pnp/cli-microsoft365")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
