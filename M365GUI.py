# =============================================================================
# Script:   M365GUI.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  08-07-2026
# Modified: 10-23-2026
# Version:  0.8
#
# Purpose:
#   A graphical front-end for the CLI for Microsoft 365 (the "m365" command) -
#   the Microsoft-world counterpart to GAMGUI. Pick a task, fill in a form, see
#   the exact m365 command, run it, read the output.
#
#   CLI for Microsoft 365: https://pnp.github.io/cli-microsoft365/
#
# Command accuracy:
#   Every command in the catalog below was verified against a real m365 v11
#   install with `m365 <command> --help`. Options change between CLI versions;
#   if a command is rejected, check `m365 <command> --help`.
#
# Requirements:
#   - Python 3.10+ with tkinter (standard library only)
#   - CLI for Microsoft 365 installed and signed in:
#       npm i -g @pnp/cli-microsoft365   then   m365 login
# =============================================================================

import os
import sys
import shutil
import subprocess
import threading
import queue
import re
import json
import csv
import datetime
import configparser
import hashlib                 # SHA-256 check of update downloads
import tempfile
import webbrowser
import urllib.request          # the update check (GitHub's public release API)
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog

import m365_update             # macOS / Linux updater + What's new (from GAMGUI)

APP_NAME = "M365GUI"
APP_VERSION = "0.8"

# GitHub repo that publishes M365GUI releases, and the API endpoint used by
# the built-in update check. The check only READS this public endpoint.
UPDATE_REPO = "GuruGabe/M365-Command-GUI-Overlay"
UPDATE_API_URL = "https://api.github.com/repos/" + UPDATE_REPO + "/releases/latest"
UPDATE_RELEASES_URL = "https://github.com/" + UPDATE_REPO + "/releases/latest"

# =============================================================================
# SECTION: Locating the m365 CLI and M365GUI's own folders
# =============================================================================

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def resource_path(name):
    # A file shipped INSIDE the built app (PyInstaller --add-data puts it in
    # sys._MEIPASS, e.g. CHANGELOG.txt for What's new), or next to
    # M365GUI.py when running from source.
    return os.path.join(getattr(sys, "_MEIPASS", None) or app_dir(), name)

def common_m365_locations():
    # Where npm puts the 'm365' command. A Mac app opened from Finder or the
    # Dock does NOT get the Terminal's PATH, so 'm365' can work in Terminal
    # yet be invisible here - these are checked after the PATH.
    home = os.path.expanduser("~")
    if os.name == "nt":
        return [os.path.join(os.environ.get("APPDATA") or "", "npm", "m365.cmd")]
    return ["/usr/local/bin/m365", "/opt/homebrew/bin/m365", "/usr/bin/m365",
            os.path.join(home, ".npm-global", "bin", "m365"),
            os.path.join(home, ".local", "bin", "m365")]

def find_m365(saved_path):
    # The CLI installs (via npm) as wrapper scripts. Prefer m365.cmd on Windows
    # (simplest to launch); npm also creates m365.ps1 (nvm setups) and an
    # extensionless script.
    if saved_path and os.path.isfile(saved_path):
        return saved_path
    for name in ("m365.cmd", "m365.exe", "m365.ps1", "m365"):
        candidate = os.path.join(app_dir(), name)
        if os.path.isfile(candidate):
            return candidate
    for name in ("m365.cmd", "m365.exe", "m365.ps1", "m365"):
        hit = shutil.which(name)
        if hit:
            return hit
    for candidate in common_m365_locations():
        if os.path.isfile(candidate):
            return candidate
    return ""

def find_node(near=""):
    # Node.js, which runs the CLI: next to the m365 wrapper (some npm
    # installs), on the PATH, then where its installers put it (a Mac app
    # started from Finder has no Terminal PATH).
    names = ("node.exe",) if os.name == "nt" else ("node",)
    for name in names:
        if near and os.path.isfile(os.path.join(near, name)):
            return os.path.join(near, name)
    hit = shutil.which("node")
    if hit:
        return hit
    if os.name == "nt":
        candidates = [os.path.join(os.environ.get("ProgramFiles") or r"C:\Program Files",
                                   "nodejs", "node.exe")]
    else:
        candidates = ["/usr/local/bin/node", "/opt/homebrew/bin/node", "/usr/bin/node"]
    return next((c for c in candidates if os.path.isfile(c)), "")

def _is_writable(path):
    # True only if a file can really be CREATED in 'path'. os.access(W_OK)
    # is unreliable on Windows (it reports Program Files as writable).
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".m365gui_write_test")
        with open(probe, "w") as handle:
            handle.write("")
        os.remove(probe)
        return True
    except Exception:
        return False

def data_dir():
    # Where M365GUI keeps m365gui.ini and Logs (v0.5, same rules as GAMGUI):
    #   macOS app      ~/Library/Application Support/M365GUI (never inside
    #                  the signed .app - writing there breaks its signature,
    #                  and an update replaces the bundle)
    #   portable copy  next to the app, so everything travels together
    #   installed copy (Program Files / /opt - not writable for the user)
    #                  %LOCALAPPDATA%\M365GUI or ~/.local/share/M365GUI
    base = app_dir()
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        target = m365_update.mac_data_dir()
    elif _is_writable(base):
        return base
    elif os.name == "nt":
        target = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                              "M365GUI")
    else:
        target = os.path.join(os.environ.get("XDG_DATA_HOME")
                              or os.path.join(os.path.expanduser("~"), ".local", "share"),
                              "M365GUI")
    try:
        os.makedirs(target, exist_ok=True)
    except Exception:
        pass
    return target

def _same_path(a, b):
    # True if two paths are the same folder (ignoring case and a trailing
    # slash). Used to tell whether THIS copy is the Setup.exe install.
    if not a or not b:
        return False
    try:
        na = os.path.normcase(os.path.normpath(a)).rstrip("\\/")
        nb = os.path.normcase(os.path.normpath(b)).rstrip("\\/")
        return na == nb
    except Exception:
        return False

def registry_exe_install():
    # The Setup.exe install record installer\m365gui.iss writes to
    # HKLM\SOFTWARE\M365GUI (Version + InstallLocation): a dict or None.
    # Windows only; any failure means "no installed copy found".
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except Exception:
        return None
    for subkey in (r"SOFTWARE\M365GUI", r"SOFTWARE\WOW6432Node\M365GUI"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                values = {}
                for name, field in (("InstallLocation", "location"), ("Version", "version")):
                    try:
                        values[field] = str(winreg.QueryValueEx(key, name)[0])
                    except OSError:
                        values[field] = ""
                if values["location"] or values["version"]:
                    return values
        except OSError:
            continue
    return None

# No console window flashing up for each command (the built app has none).
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CLI_SCRIPT = os.path.join("node_modules", "@pnp", "cli-microsoft365", "dist", "index.js")
CMD_SPECIAL = set('&|<>^%!"\r\n')

def build_invocation(exe, argv):
    # The program list that runs one m365 command. v0.4: npm's m365.cmd /
    # m365.ps1 wrappers only start "node <npm>\node_modules\@pnp\
    # cli-microsoft365\dist\index.js <args>", so M365GUI starts that itself -
    # NO shell. Through cmd.exe, a value such as a folder named 'Q&A' was
    # split at the '&' and the rest RAN AS A COMMAND (checked 10-22-2026).
    # v0.5: on macOS / Linux npm's 'm365' is a LINK to that index.js (it
    # starts with '#!/usr/bin/env node', which fails in a Mac app started
    # from Finder - no Terminal PATH), so follow the link and start node
    # ourselves there too.
    folder = os.path.dirname(exe)
    script = os.path.join(folder, CLI_SCRIPT)
    real = os.path.realpath(exe)
    if not os.path.isfile(script) and real.replace("\\", "/").endswith(
            "/@pnp/cli-microsoft365/dist/index.js"):
        script = real
    if os.path.isfile(script):
        node = find_node(folder)
        if node:
            return [node, script] + list(argv)
    low = exe.lower()
    if os.name == "nt" and low.endswith((".cmd", ".bat")):
        # Fallback for an unusual install: cmd.exe, but never with a value
        # cmd.exe would treat as part of a command.
        bad = [a for a in argv if CMD_SPECIAL & set(a)]
        if bad:
            raise ValueError("This value cannot be passed safely through m365.cmd "
                             "(it contains one of & | < > ^ % ! \"): " + bad[0])
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", exe] + list(argv)
    if os.name == "nt" and low.endswith(".ps1"):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", exe] + list(argv)
    return [exe] + list(argv)

DATA_DIR = data_dir()
INI_PATH = os.path.join(DATA_DIR, "m365gui.ini")
LOG_DIR = os.path.join(DATA_DIR, "Logs")
# Favorites and Recent tasks (v0.6) - their own small JSON file, as in GAMGUI
# (task names can hold characters the .ini reader treats specially).
TASKLISTS_PATH = os.path.join(DATA_DIR, "m365gui_tasklists.json")
# Records the guided workflows keep (v0.8): hand-off records, incident evidence.
RECORDS_DIR = os.path.join(DATA_DIR, "Records")
RECENT_MAX = 10

def save_results(path, text):
    # Writes a command's CSV / JSON output to the chosen file and returns the
    # line for the output window (never raises).
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except OSError as exc:
        return "Could not save the results to %s: %s\n" % (path, exc)
    rows = text.count("\n")
    return "Saved to %s (%d line%s).\n" % (path, rows, "" if rows == 1 else "s")

def account_text(m365_path, run):
    # The top bar's "Signed in as" text, from 'm365 status' (run(argv) ->
    # (returncode, output)). Never raises.
    if not m365_path:
        return "Signed in as: (m365 not found)"
    try:
        rc, out = run(["status", "--output", "json"])
    except Exception as exc:
        return "Signed in as: (could not check: %s)" % exc
    start = out.find("{")
    try:
        info = json.loads(out[start:]) if start >= 0 else {}
    except ValueError:
        info = {}
    who = info.get("connectedAs") if isinstance(info, dict) else None
    if who:
        return "Signed in as: " + who
    if "logged out" in out.lower() or "not logged" in out.lower():
        return "Signed in as: nobody - run 'm365 login'"
    if "node" in out.lower() and ("not recognized" in out.lower() or "not found" in out.lower()):
        return "Signed in as: (Node.js is not installed - m365 cannot run)"
    return "Signed in as: (unknown - " + (" ".join(out.split())[:60] or "no answer") + ")"

# The task catalog and the guided workflows live in their own modules (v0.6,
# like GAMGUI). These names are re-exported here: the tests and older code
# use them as M365GUI.<name>.
from m365_catalog import (T, F, TRANSFER_ACCESS_REMOVE, TRANSFER_ACCESS_KEEP,
                          TASKS, WORKFLOW_PLANS, quote_if_needed, build_command,
                          task_key, find_task, task_matches, picker_kind,
                          user_search_commands, people_choices, GROUP_LIST_COMMAND,
                          group_choices, SAVE_CHOICES, SAVE_FORMATS, saves_output,
                          with_output_format, dropdown_start, FORM_VALUE,
                          bulk_available, bulk_guess_column, bulk_plan, script_text)
from m365_workflows import (BAD_FOLDER_CHARS, parse_json, onedrive_paths,
                            default_transfer_folder, size_text, transfer_onedrive,
                            staff_handoff, compromised_response, COMPROMISED_NEXT_STEPS)

def random_password(length=16):
    # A new password for a compromised account: letters, digits and symbols
    # (at least one of each kind, as Microsoft 365's password rules want),
    # from the 'secrets' module (made for passwords, not 'random').
    import secrets
    import string
    # No % or ^ (cmd.exe treats them specially, should m365 ever be started
    # through m365.cmd) and no quotes.
    kinds = [string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$*-_=+?"]
    chars = [secrets.choice(k) for k in kinds]
    pool = "".join(kinds)
    chars += [secrets.choice(pool) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)

# =============================================================================
# SECTION: Main window
# =============================================================================

class M365Gui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME + " " + APP_VERSION
                   + " - CLI for Microsoft 365 Front-End")
        self.geometry("1120x740")
        self.minsize(900, 600)

        self.config_parser = configparser.ConfigParser()
        self.config_parser.read(INI_PATH)
        saved = self.config_parser.get(APP_NAME.lower(), "m365_path", fallback="")
        self.m365_path = find_m365(saved)

        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        self.log_path = os.path.join(LOG_DIR, "M365GUI_" + stamp + ".log")

        self.output_queue = queue.Queue()
        self.running_proc = None
        self.workflow_cancel = False
        self.field_vars = []
        self.current_task = None
        # v0.5 (as in GAMGUI): check GitHub for a newer M365GUI at startup,
        # and show What's new once after an update. Both can be switched off
        # in the Help menu (saved in m365gui.ini).
        self.check_updates = self._setting("check_updates", "true") == "true"
        self.show_whats_new = self._setting("show_whats_new", "true") == "true"
        self._update_in_progress = False
        self.favorites, self.recent = self._load_tasklists()
        self._group_cache = None             # the Pick... group list, loaded once

        self._build_layout()
        self._build_menu()
        self._populate_tree()
        self._preselect()
        self.after(100, self._poll_output)
        self.after(1500, self._startup_checks)
        self._refresh_account()
        if not self.m365_path:
            self._append_output(
                "NOTE: the 'm365' CLI was not found. Install it with\n"
                "    npm i -g @pnp/cli-microsoft365\n"
                "then sign in with 'm365 login', or click 'Locate m365...'.\n")

    # ---- how m365 is started (see build_invocation: node directly) ----------
    def _build_invocation(self, argv):
        return build_invocation(self.m365_path, argv)

    # ---- layout -------------------------------------------------------------
    def _build_layout(self):
        top = ttk.Frame(self, padding=4); top.pack(side="top", fill="x")
        self.path_label = ttk.Label(top, text="m365: " + (self.m365_path or "(not found)"))
        self.path_label.pack(side="left")
        ttk.Button(top, text="Locate m365...", command=self._locate).pack(side="right")
        # v0.6 (GAMGUI's "signs in as" line): which account m365 is signed in
        # as, checked in the background at startup. Click it to check again.
        self.account_label = ttk.Label(top, text="Signed in as: (checking...)",
                                       cursor="hand2")
        self.account_label.pack(side="right", padx=12)
        self.account_label.bind("<Button-1>", lambda _e: self._refresh_account())

        main = ttk.PanedWindow(self, orient="horizontal"); main.pack(fill="both", expand=True)
        left = ttk.Frame(main)
        # Search box: every word typed must appear in the section, task name
        # or description (m365_catalog.task_matches). Esc clears it.
        search_row = ttk.Frame(left); search_row.pack(fill="x", pady=(0, 4))
        ttk.Label(search_row, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.search_entry.bind("<Escape>", lambda _e: self.search_var.set(""))
        self.search_var.trace_add("write", lambda *_: self._populate_tree())
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        # Right-click (Ctrl-click on a Mac) a task: add to / remove from Favorites.
        for event in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.tree.bind(event, self._tree_menu)
        main.add(left, weight=1)

        right = ttk.Frame(main, padding=6); main.add(right, weight=3)
        self.desc_label = ttk.Label(right, text="Select a task on the left.",
                                    wraplength=720, justify="left")
        self.desc_label.pack(anchor="w")
        self.form_frame = ttk.Frame(right); self.form_frame.pack(fill="x", pady=6)

        pv = ttk.Frame(right); pv.pack(fill="x")
        ttk.Label(pv, text="Command preview (editable):").pack(side="left")
        ttk.Button(pv, text="Build", command=self._preview).pack(side="right")
        ttk.Button(pv, text="Copy", command=self._copy).pack(side="right")
        ttk.Button(pv, text="Save as script...", command=self._save_script).pack(side="right", padx=4)
        self.preview_box = tk.Text(right, height=3, wrap="word"); self.preview_box.pack(fill="x", pady=4)

        rb = ttk.Frame(right); rb.pack(fill="x")
        self.run_button = ttk.Button(rb, text="Run", command=self._run); self.run_button.pack(side="left")
        ttk.Button(rb, text="Stop", command=self._stop).pack(side="left", padx=4)
        # v0.6: run the open task once per row of a CSV file (as GAMGUI).
        self.bulk_button = ttk.Button(rb, text="Run for each CSV row...", command=self._bulk_dialog)
        self.bulk_button.pack(side="left", padx=4)
        ttk.Button(rb, text="Clear output", command=lambda: self.output_box.delete("1.0", "end")).pack(side="right")
        self.output_box = scrolledtext.ScrolledText(right, height=18, wrap="word"); self.output_box.pack(fill="both", expand=True, pady=4)

    def _populate_tree(self):
        # (Re)draws the task list: Favorites and Recent at the top, then every
        # section. With search words, only matching tasks show, sections open.
        needle = self.search_var.get().strip() if hasattr(self, "search_var") else ""
        self.tree.delete(*self.tree.get_children(""))
        for title, keys in (("Favorites", self.favorites), ("Recent", self.recent)):
            found = [(k, find_task(k)) for k in keys]
            found = [(k, hit) for k, hit in found if hit and
                     task_matches(hit[0], TASKS[hit[0]][hit[1]], needle)]
            if found:
                parent = self.tree.insert("", "end", text=title, open=True)
                for _key, (category, index) in found:
                    self.tree.insert(parent, "end", text=TASKS[category][index]["name"],
                                     values=(category, index))
        for category, tasks in TASKS.items():
            shown = [(i, t) for i, t in enumerate(tasks) if task_matches(category, t, needle)]
            if not shown:
                continue
            parent = self.tree.insert("", "end", text=category, open=bool(needle))
            for index, task in shown:
                self.tree.insert(parent, "end", text=task["name"], values=(category, index))
        if not needle or task_matches("", {"name": "Custom command", "desc": "any m365 command"}, needle):
            self.tree.insert("", "end", text="Custom command", values=("__custom__", 0))

    # ---- Favorites and Recent (v0.6, as GAMGUI: m365gui_tasklists.json) -----
    def _load_tasklists(self):
        try:
            with open(TASKLISTS_PATH, encoding="utf-8") as handle:
                data = json.load(handle)
            favorites = [k for k in data.get("favorites", []) if isinstance(k, str)]
            recent = [k for k in data.get("recent", []) if isinstance(k, str)]
        except (OSError, ValueError, AttributeError):
            favorites, recent = [], []
        return favorites, recent[:RECENT_MAX]

    def _save_tasklists(self):
        try:
            with open(TASKLISTS_PATH, "w", encoding="utf-8") as handle:
                json.dump({"favorites": self.favorites, "recent": self.recent}, handle, indent=1)
        except OSError as exc:
            self._log("Could not save Favorites/Recent: " + str(exc))

    def _remember_recent(self):
        # The task just run moves to the top of Recent (at most RECENT_MAX).
        task = self.current_task
        if not task:
            return
        key = next((task_key(c, t["name"]) for c, ts in TASKS.items() for t in ts if t is task), None)
        if not key:
            return
        self.recent = [key] + [k for k in self.recent if k != key][:RECENT_MAX - 1]
        self._save_tasklists()
        self._refresh_special_nodes()

    def _refresh_special_nodes(self):
        # Redraws the list but keeps the selected task selected.
        selected = self.tree.selection()
        values = self.tree.item(selected[0], "values") if selected else None
        self._populate_tree()
        if values:
            for parent in self.tree.get_children(""):
                if self.tree.item(parent, "text") in ("Favorites", "Recent"):
                    continue
                for child in self.tree.get_children(parent):
                    if tuple(self.tree.item(child, "values")) == tuple(values):
                        self.tree.selection_set(child)
                        self.tree.see(child)
                        return

    def _tree_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        values = self.tree.item(item, "values")
        if not values or values[0] == "__custom__":
            return
        key = task_key(values[0], TASKS[values[0]][int(values[1])]["name"])
        menu = tk.Menu(self, tearoff=0)
        if key in self.favorites:
            menu.add_command(label="Remove from Favorites", command=lambda: self._toggle_favorite(key))
        else:
            menu.add_command(label="Add to Favorites", command=lambda: self._toggle_favorite(key))
        menu.tk_popup(event.x_root, event.y_root)

    def _toggle_favorite(self, key):
        if key in self.favorites:
            self.favorites.remove(key)
        else:
            self.favorites.append(key)
        self._save_tasklists()
        self._refresh_special_nodes()

    # ---- Staff hand-off / compromised account (v0.8) --------------------------
    def _run_record_workflow(self, name):
        # The two workflows that keep a record folder in RECORDS_DIR. They ask
        # their one question through _ask_yesno; the new password (compromised)
        # goes to _show_secret on the window's thread - never to the output.
        self.workflow_cancel = False
        self.run_button.config(state="disabled")
        values = self._collect()

        def show_secret(title, secret):
            self.output_queue.put(lambda: self._show_secret(title, secret))
            self.output_queue.put("(The new password is in its own window - it is not "
                                  "shown here or saved in any log.)\n")

        def worker():
            try:
                os.makedirs(RECORDS_DIR, exist_ok=True)
                if name == "staff_handoff":
                    staff_handoff(self._capture, self.output_queue.put, self._ask_yesno,
                                  lambda: self.workflow_cancel, values, RECORDS_DIR)
                else:
                    compromised_response(self._capture, self.output_queue.put, self._ask_yesno,
                                         lambda: self.workflow_cancel, values, RECORDS_DIR,
                                         show_secret, random_password)
            except Exception as exc:
                self.output_queue.put("WORKFLOW ERROR: " + str(exc) + "\n")
            finally:
                self.running_proc = None
                self.output_queue.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def _show_secret(self, title, secret):
        # A small window with the secret in a read-only box and a Copy button.
        # Deliberately NOT _append_output: that writes to the session log.
        win = tk.Toplevel(self)
        win.title(APP_NAME + " - New password")
        win.transient(self)
        ttk.Label(win, text=title, padding=8, wraplength=460).pack(anchor="w")
        # The text goes straight into the box: a StringVar made here would be
        # garbage-collected when this method returns and the box would show
        # EMPTY (found by tests/test_v08_workflows.py) - a reset password
        # nobody ever saw.
        box = ttk.Entry(win, width=40, font=("Consolas", 12))
        box.insert(0, secret)
        box.configure(state="readonly")
        box.pack(padx=8, fill="x")
        row = ttk.Frame(win, padding=8); row.pack(fill="x")

        def copy():
            self.clipboard_clear()
            self.clipboard_append(secret)
        ttk.Button(row, text="Copy", command=copy).pack(side="left")
        ttk.Button(row, text="Close", command=win.destroy).pack(side="right")
        self._secret_window = win              # the tests reach the window through this

    # ---- Run for each CSV row (v0.6) ----------------------------------------
    def _bulk_dialog(self):
        # Choose a CSV file, say which column fills each box (or the form's
        # value), optionally only the first N rows, then run.
        task = self.current_task
        if not task or not bulk_available(task):
            messagebox.showinfo(APP_NAME, "Open an ordinary task first (not Custom command "
                                "or a guided workflow) - it then runs once per CSV row.")
            return
        if self.running_proc is not None:
            messagebox.showinfo(APP_NAME, "A command is already running.")
            return
        win = tk.Toplevel(self)
        win.title(APP_NAME + " - Run for each CSV row: " + task["name"])
        win.transient(self)
        frame = ttk.Frame(win, padding=8); frame.pack(fill="both", expand=True)
        path_var = tk.StringVar()
        ttk.Label(frame, text="CSV file (first row = column names):").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=path_var, width=56).grid(row=0, column=1, sticky="we", padx=4)
        maps = {}
        state = {"headers": [], "rows": []}
        grid = ttk.Frame(frame); grid.grid(row=2, column=0, columnspan=3, sticky="we", pady=8)
        note = ttk.Label(frame, text="Choose a CSV file.", wraplength=620, justify="left")
        note.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        def load(path):
            try:
                with open(path, encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    state["rows"] = [r for r in reader]
                    state["headers"] = list(reader.fieldnames or [])
            except (OSError, csv.Error, UnicodeDecodeError) as exc:
                note.config(text="Could not read the file: " + str(exc))
                return
            for child in grid.winfo_children():
                child.destroy()
            maps.clear()
            choices = [FORM_VALUE] + state["headers"]
            for row, field in enumerate(task["fields"]):
                ttk.Label(grid, text=field["label"]).grid(row=row, column=0, sticky="w", pady=1)
                var = tk.StringVar(value=bulk_guess_column(field, state["headers"]))
                ttk.Combobox(grid, textvariable=var, values=choices, state="readonly",
                             width=34).grid(row=row, column=1, sticky="w", padx=6, pady=1)
                maps[field["key"]] = var
            note.config(text="%d data row(s), columns: %s" % (len(state["rows"]),
                                                              ", ".join(state["headers"])))

        def browse():
            path = filedialog.askopenfilename(parent=win, title="CSV file",
                                              filetypes=[("CSV file", "*.csv"), ("All files", "*.*")])
            if path:
                path_var.set(path)
                load(path)
        ttk.Button(frame, text="Browse...", command=browse).grid(row=0, column=2)
        limit_var = tk.StringVar()
        bottom = ttk.Frame(frame); bottom.grid(row=3, column=0, columnspan=3, sticky="we")
        ttk.Label(bottom, text="Test run - only the first").pack(side="left")
        ttk.Entry(bottom, textvariable=limit_var, width=5).pack(side="left", padx=4)
        ttk.Label(bottom, text="rows (blank = every row)").pack(side="left")

        def plan():
            if not state["rows"]:
                if path_var.get().strip():
                    load(path_var.get().strip())
                if not state["rows"]:
                    messagebox.showerror(APP_NAME, "Choose a CSV file with at least one data row.",
                                         parent=win)
                    return None
            limit = limit_var.get().strip()
            if limit and (not limit.isdigit() or int(limit) < 1):
                messagebox.showerror(APP_NAME, "Test rows must be a whole number of 1 or more.",
                                     parent=win)
                return None
            rows = state["rows"][:int(limit)] if limit else state["rows"]
            steps = bulk_plan(task, self.current_category, self._collect(),
                              {k: v.get() for k, v in maps.items()}, rows)
            bad = [(n, err) for n, _argv, err in steps if err]
            if bad:
                messagebox.showerror(APP_NAME, "%d row(s) cannot be run - fix the CSV (or the "
                                     "column choices) first:\n\n" % len(bad)
                                     + "\n".join("row %d: %s" % b for b in bad[:8]), parent=win)
                return None
            return steps

        def first():
            steps = plan()
            if steps:
                messagebox.showinfo(APP_NAME, "Row %d runs:\n\nm365 %s\n\n(%d row(s) in all)"
                                    % (steps[0][0], " ".join(quote_if_needed(a) for a in steps[0][1]),
                                       len(steps)), parent=win)

        def go():
            steps = plan()
            if not steps:
                return
            if task["destructive"] and not messagebox.askyesno(
                    APP_NAME + " - CONFIRM", "This makes a change or deletes data, once per "
                    "row - %d row(s).\n\nFirst row:\nm365 %s\n\nAre you sure?"
                    % (len(steps), " ".join(quote_if_needed(a) for a in steps[0][1])), parent=win):
                return
            win.destroy()
            self._run_bulk(task, steps, path_var.get().strip())
        buttons = ttk.Frame(frame); buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Show the first row's command", command=first).pack(side="left")
        ttk.Button(buttons, text="Run", command=go).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="left")
        frame.columnconfigure(1, weight=1)
        self._bulk_window = win               # the tests reach the dialog through this

    def _run_bulk(self, task, steps, source):
        # One m365 command per row, in order, on a worker thread. Stop ends it
        # after the current row. A CSV record of every row goes to Logs.
        self.workflow_cancel = False
        self.run_button.config(state="disabled")
        self._remember_recent()
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        record = os.path.join(LOG_DIR, "Bulk_%s_%s.csv" % (re.sub(r"[^A-Za-z0-9]+", "-",
                                                                  task["name"]).strip("-"), stamp))

        def worker():
            done = failed = 0
            rows = [["csv row", "result", "command", "detail"]]
            try:
                self.output_queue.put("\n===== %s - once per row of %s (%d row(s)) =====\n"
                                      % (task["name"], source, len(steps)))
                for number, argv, _err in steps:
                    if self.workflow_cancel:
                        self.output_queue.put("[Stopped - the remaining rows were not run.]\n")
                        break
                    shown = "m365 " + " ".join(quote_if_needed(a) for a in argv)
                    rc, out = self._capture(argv)
                    detail = " ".join(out.split())[:200]
                    if rc == 0:
                        done += 1
                        self.output_queue.put("  row %d OK      %s\n" % (number, shown))
                    else:
                        failed += 1
                        self.output_queue.put("  row %d FAILED  %s\n          %s\n" % (number, shown, detail))
                    rows.append([number, "OK" if rc == 0 else "FAILED", shown, detail])
                try:
                    os.makedirs(LOG_DIR, exist_ok=True)
                    with open(record, "w", newline="", encoding="utf-8") as handle:
                        csv.writer(handle).writerows(rows)
                    self.output_queue.put("Record of every row: %s\n" % record)
                except OSError as exc:
                    self.output_queue.put("Could not save the record: %s\n" % exc)
                self.output_queue.put("===== DONE: %d OK, %d failed =====\n" % (done, failed))
            except Exception as exc:
                self.output_queue.put("BULK RUN ERROR: " + str(exc) + "\n")
            finally:
                self.running_proc = None
                self.output_queue.put(None)
        threading.Thread(target=worker, daemon=True).start()

    # ---- Pick... lists (v0.6) -------------------------------------------------
    def _pick(self, kind, var):
        # A small window: type the start of a name or address, pick from the
        # list, OK fills the box. Users are searched on the server (thousands
        # in a tenant); groups are loaded once per session.
        if not self.m365_path:
            messagebox.showerror(APP_NAME, "m365 CLI not found. Install it or click Locate m365.")
            return
        win = tk.Toplevel(self)
        win.title(APP_NAME + " - Pick a " + kind)
        win.transient(self)
        win.geometry("560x420")
        row = ttk.Frame(win, padding=6); row.pack(fill="x")
        ttk.Label(row, text=("Name or address starts with:" if kind == "user"
                             else "Name or address contains:")).pack(side="left")
        text = tk.StringVar(value=var.get().strip())
        entry = ttk.Entry(row, textvariable=text); entry.pack(side="left", fill="x", expand=True, padx=4)
        status = ttk.Label(win, text="", padding=(6, 0)); status.pack(anchor="w")
        box = tk.Listbox(win, activestyle="dotbox"); box.pack(fill="both", expand=True, padx=6, pady=4)
        values = []

        def show(choices, note):
            if not win.winfo_exists():
                return
            box.delete(0, "end")
            values[:] = [value for _label, value in choices]
            for label, _value in choices:
                box.insert("end", label)
            status.config(text=note)

        def search(*_):
            if kind == "group":
                if self._group_cache is None:
                    return                  # still loading; shown when it arrives
                found = group_choices(self._group_cache, text.get())
                show(found, "%d group(s)" % len(found))
                return
            commands = user_search_commands(text.get())
            if not commands:
                show([], "Type the start of a name or address, then press Enter.")
                return
            status.config(text="Searching...")

            def work():
                results = []
                for argv in commands:
                    rc, out = self._quiet_run(argv, timeout=120)
                    data = parse_json(out) if rc == 0 else None
                    if not isinstance(data, list):
                        note = "Could not search: " + " ".join(out.split())[:120]
                        self.output_queue.put(lambda: show([], note))
                        return
                    results.append(data)
                found = people_choices(results)
                self.output_queue.put(lambda: show(found, "%d user(s)" % len(found)))
            threading.Thread(target=work, daemon=True).start()

        def choose(*_):
            pick = box.curselection()
            if pick:
                var.set(values[pick[0]])
                win.destroy()

        buttons = ttk.Frame(win, padding=6); buttons.pack(fill="x")
        ttk.Button(buttons, text="OK", command=choose).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=4)
        if kind == "user":
            ttk.Button(row, text="Search", command=search).pack(side="left")
            entry.bind("<Return>", search)
        else:
            text.trace_add("write", search)
        box.bind("<Double-Button-1>", choose)
        entry.focus_set()
        if kind == "group" and self._group_cache is None:
            status.config(text="Loading the groups (once per session)...")

            def load():
                rc, out = self._quiet_run(GROUP_LIST_COMMAND, timeout=300)
                data = parse_json(out) if rc == 0 else None
                if isinstance(data, list):
                    self._group_cache = data
                    self.output_queue.put(search)
                else:
                    note = "Could not load the groups: " + " ".join(out.split())[:120]
                    self.output_queue.put(lambda: show([], note))
            threading.Thread(target=load, daemon=True).start()
        else:
            search()

    # ---- "Signed in as" (v0.6) ----------------------------------------------
    def _refresh_account(self):
        self.account_label.config(text="Signed in as: (checking...)")
        threading.Thread(target=self._account_worker, daemon=True).start()

    def _account_worker(self):
        # OFF the UI thread: 'm365 status'. Never touches running_proc, so a
        # task can run at the same time.
        text = account_text(self.m365_path, self._quiet_run)
        self.output_queue.put(lambda: self.account_label.config(text=text))

    def _quiet_run(self, argv, timeout=60):
        # One m365 command for the window's own checks: (returncode, output).
        try:
            r = subprocess.run(self._build_invocation(argv), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout,
                               stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except Exception as exc:
            return 1, str(exc)

    def _preselect(self):
        for parent in self.tree.get_children(""):
            self.tree.item(parent, open=True)
            for child in self.tree.get_children(parent):
                if self.tree.item(child, "text") == "Create user":
                    self.tree.selection_set(child); self.tree.see(child)
                    self._on_select(None); return
            kids = self.tree.get_children(parent)
            if kids:
                self.tree.selection_set(kids[0]); self._on_select(None)
            return

    def _on_select(self, _e):
        item = self.tree.selection()
        if not item: return
        vals = self.tree.item(item[0], "values")
        if not vals: return
        if vals[0] == "__custom__": self._show_custom(); return
        task = TASKS[vals[0]][int(vals[1])]
        if task is self.current_task:
            # Already open (e.g. the list was redrawn after a run and the
            # same task re-selected): keep the boxes as they are - redrawing
            # the form would wipe what was typed.
            return
        self.current_category = vals[0]
        self.current_task = task
        self._show_form(self.current_task)

    def _clear_form(self):
        for c in self.form_frame.winfo_children(): c.destroy()
        self.field_vars = []

    def _show_form(self, task):
        self._clear_form()
        self.desc_label.config(text=task["name"] + ": " + task["desc"])
        for row, field in enumerate(task["fields"]):
            label = field["label"] + (" *" if field["required"] else "")
            ttk.Label(self.form_frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=field["default"])
            if field["choices"] is not None:
                w = ttk.Combobox(self.form_frame, textvariable=var, values=field["choices"], state="readonly", width=40)
                var.set(dropdown_start(field))   # v0.6: the default, not always the first
            else:
                w = ttk.Entry(self.form_frame, textvariable=var, width=62)
            w.grid(row=row, column=1, sticky="we", pady=2, padx=6)
            # v0.6: a Pick... list for boxes that take a user or a group.
            kind = picker_kind(getattr(self, "current_category", ""), task, field)
            if kind:
                ttk.Button(self.form_frame, text="Pick...",
                           command=lambda k=kind, v=var: self._pick(k, v)).grid(
                               row=row, column=2, sticky="w", pady=2)
            self.field_vars.append((field["key"], var))
        # v0.6 "Save results to": a list task can send its results to a CSV
        # or JSON file instead of the window (the CLI writes the format).
        self.save_var = tk.StringVar(value="Screen")
        self.save_path_var = tk.StringVar(value="")
        if saves_output(task):
            row = len(task["fields"])
            ttk.Label(self.form_frame, text="Save results to").grid(row=row, column=0, sticky="w", pady=2)
            line = ttk.Frame(self.form_frame)
            line.grid(row=row, column=1, sticky="we", pady=2, padx=6)
            ttk.Combobox(line, textvariable=self.save_var, values=SAVE_CHOICES, state="readonly",
                         width=12).pack(side="left")
            path_entry = ttk.Entry(line, textvariable=self.save_path_var)
            path_entry.pack(side="left", fill="x", expand=True, padx=4)
            browse = ttk.Button(self.form_frame, text="Browse...", command=self._browse_save)
            browse.grid(row=row, column=2, sticky="w", pady=2)

            def show_path(*_):
                state = "disabled" if self.save_var.get() == "Screen" else "normal"
                path_entry.configure(state=state)
                browse.configure(state=state)
            self.save_var.trace_add("write", show_path)
            show_path()
        self.form_frame.columnconfigure(1, weight=1)
        self._preview()

    def _browse_save(self):
        fmt = SAVE_FORMATS.get(self.save_var.get(), "csv")
        path = filedialog.asksaveasfilename(
            title="Save results to", defaultextension="." + fmt,
            filetypes=[(fmt.upper() + " file", "*." + fmt), ("All files", "*.*")])
        if path:
            self.save_path_var.set(path)

    def _show_custom(self):
        self._clear_form(); self.current_task = None
        self.desc_label.config(text="Custom command: type ANY m365 command below "
                               "(without the leading 'm365') and press Run. "
                               "Reference: https://pnp.github.io/cli-microsoft365/")
        self.preview_box.delete("1.0", "end")

    def _collect(self): return {k: v.get() for k, v in self.field_vars}

    def _preview(self):
        if not self.current_task: return
        if self.current_task.get("workflow"):
            self.preview_box.delete("1.0", "end")
            self.preview_box.insert("1.0", WORKFLOW_PLANS[self.current_task["workflow"]])
            return
        display, argv, err = build_command(self.current_task, self._collect(),
                                           getattr(self, "current_category", ""))
        self.preview_box.delete("1.0", "end")
        if err:
            self.generated_display = None; self.generated_argv = None
            self.preview_box.insert("1.0", "(" + err + ")")
        else:
            self.generated_display = "m365 " + display; self.generated_argv = argv
            self.preview_box.insert("1.0", self.generated_display)

    def _copy(self):
        self.clipboard_clear(); self.clipboard_append(self.preview_box.get("1.0", "end").strip())

    def _preview_argv(self):
        # The command in the preview box as (text, argv) - the built command,
        # or the box's own text if it was edited. None (after telling the
        # person) when there is nothing runnable.
        command_text = self.preview_box.get("1.0", "end").strip()
        if command_text.startswith("("):
            self._preview(); command_text = self.preview_box.get("1.0", "end").strip()
        if not command_text or command_text.startswith("("):
            messagebox.showerror(APP_NAME, "Fill in the required fields first.")
            return None
        if command_text == getattr(self, "generated_display", None):
            argv = list(self.generated_argv)
        else:
            s = command_text
            if s.lower().startswith("m365 "): s = s[5:]
            argv = [a[1:-1] if a.startswith('"') and a.endswith('"') else a
                    for a in re.findall(r'"[^"]*"|\S+', s)]
        return (command_text, argv) if argv else None

    def _save_script(self):
        # v0.6 (as GAMGUI): the previewed command as a PowerShell (.ps1) or
        # bash (.sh) script, to run later or on a schedule.
        if self.current_task and self.current_task.get("workflow"):
            messagebox.showinfo(APP_NAME, "A guided workflow runs several commands with checks "
                                "in between, so it cannot be saved as one script.")
            return
        got = self._preview_argv()
        if not got:
            return
        _text, argv = got
        default = "ps1" if os.name == "nt" else "sh"
        name = re.sub(r"[^A-Za-z0-9]+", "-", (self.current_task or {}).get("name", "m365-command")).strip("-")
        path = filedialog.asksaveasfilename(
            title="Save as script", initialfile=name + "." + default, defaultextension="." + default,
            filetypes=[("PowerShell script", "*.ps1"), ("bash script", "*.sh")])
        if not path:
            return
        kind = "sh" if path.lower().endswith(".sh") else "ps1"
        text = script_text(argv, kind, (self.current_task or {}).get("name"), APP_VERSION,
                           datetime.date.today().strftime("%m-%d-%Y"))
        try:
            with open(path, "w", encoding="ascii" if text.isascii() else "utf-8", newline="") as h:
                h.write(text)
            if kind == "sh" and os.name != "nt":
                os.chmod(path, 0o755)
        except OSError as exc:
            messagebox.showerror(APP_NAME, "Could not save the script:\n" + str(exc))
            return
        self._append_output("Saved the command as a script: " + path + "\n")

    # ---- execution ----------------------------------------------------------
    def _run(self):
        if self.running_proc is not None:
            messagebox.showinfo(APP_NAME, "A command is already running."); return
        if not self.m365_path:
            messagebox.showerror(APP_NAME, "m365 CLI not found. Install it or click Locate m365."); return
        if self.current_task and self.current_task.get("workflow"):
            self._remember_recent()
        if self.current_task and self.current_task.get("workflow") == "remove_guests":
            self._run_remove_guests(); return
        if self.current_task and self.current_task.get("workflow") == "onedrive_transfer":
            self._run_onedrive_transfer(); return
        if self.current_task and self.current_task.get("workflow") in ("staff_handoff", "compromised"):
            self._run_record_workflow(self.current_task["workflow"]); return

        got = self._preview_argv()
        if not got:
            return
        command_text, argv = got

        if self.current_task and self.current_task["destructive"]:
            if not messagebox.askyesno(APP_NAME + " - CONFIRM",
                    "This makes a change or deletes data:\n\n" + command_text + "\n\nAre you sure?"):
                return

        # v0.6 "Save results to" a file: the CLI writes CSV / JSON itself.
        save_to = ""
        if self.current_task and saves_output(self.current_task) \
                and self.save_var.get() in SAVE_FORMATS:
            save_to = self.save_path_var.get().strip()
            if not save_to:
                messagebox.showerror(APP_NAME, "Choose the file to save the results to "
                                     "(Browse...), or set 'Save results to' back to Screen.")
                return
            argv = with_output_format(argv, SAVE_FORMATS[self.save_var.get()])
            command_text = "m365 " + " ".join(quote_if_needed(a) for a in argv)

        self._append_output("\n> " + command_text + "\n")
        if save_to:
            self._append_output("(saving the results to " + save_to + ")\n")
        self.run_button.config(state="disabled")
        self._remember_recent()

        def worker():
            try:
                proc = subprocess.Popen(self._build_invocation(argv),
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace",
                                        stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
                self.running_proc = proc
                if save_to:
                    # Collected, then written only if the command worked - an
                    # error message must not end up in the CSV / JSON file.
                    text = proc.stdout.read()
                    proc.wait()
                    if proc.returncode == 0:
                        self.output_queue.put(save_results(save_to, text))
                    else:
                        self.output_queue.put(text)
                else:
                    for line in proc.stdout:
                        self.output_queue.put(line)
                proc.wait()
                if proc.returncode != 0:
                    self.output_queue.put(
                        "\n[exit code %d]  Tip: if the error is unclear (m365 "
                        "sometimes shows 'Error: [object Object]'), re-run the "
                        "command in Custom command with --debug added to see "
                        "the real message.\n" % proc.returncode)
                else:
                    self.output_queue.put("\n[exit code 0]\n")
            except Exception as exc:
                self.output_queue.put("ERROR: " + str(exc) + "\n")
            finally:
                self.running_proc = None
                self.output_queue.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def _capture(self, argv):
        # Run one m365 command and return (returncode, text). Used by workflows.
        # A value that cannot be passed safely (see build_invocation) comes
        # back as a failed command instead of stopping the workflow.
        try:
            proc = subprocess.Popen(self._build_invocation(argv), stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                    errors="replace", stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        except (OSError, ValueError) as exc:
            return 1, str(exc)
        self.running_proc = proc
        out = proc.stdout.read()
        proc.wait(); self.running_proc = None
        return proc.returncode, out

    def _ask_confirm(self, summary):
        event = threading.Event(); result = {"ok": False}
        self.output_queue.put(("confirm", summary, event, result))
        event.wait(); return result["ok"]

    def _ask_yesno(self, summary):
        # A plain Yes/No question from a workflow thread (answered on the
        # window's thread in _poll_output).
        event = threading.Event(); result = {"ok": False}
        self.output_queue.put(("yesno", summary, event, result))
        event.wait(); return result["ok"]

    def _run_onedrive_transfer(self):
        # 'Copy a user's OneDrive files to another user' - see transfer_onedrive.
        self.workflow_cancel = False
        self.run_button.config(state="disabled")
        values = self._collect()
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        who = re.sub(r"[^A-Za-z0-9._-]", "_", (values.get("from") or "").split("@")[0])
        report = os.path.join(LOG_DIR, "OneDrive-Copy_%s_%s.csv" % (who, stamp))

        def worker():
            try:
                transfer_onedrive(self._capture, self.output_queue.put, self._ask_yesno,
                                  lambda: self.workflow_cancel, values, report)
            except Exception as exc:
                self.output_queue.put("WORKFLOW ERROR: " + str(exc) + "\n")
            finally:
                self.running_proc = None
                self.output_queue.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def _run_remove_guests(self):
        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            try:
                self.output_queue.put("\n===== REMOVE ALL GUEST USERS =====\n"
                                      "Step 1: finding guest accounts...\n")
                rc, out = self._capture(["entra", "user", "list", "--type", "Guest",
                                         "--properties", "id,displayName,userPrincipalName",
                                         "--output", "json"])
                if rc != 0:
                    self.output_queue.put("Could not list guests (rc=%d):\n%s\n" % (rc, out)); return
                try:
                    guests = json.loads(out) if out.strip() else []
                except ValueError:
                    self.output_queue.put("Could not parse the guest list. Raw output:\n" + out + "\n"); return
                if not guests:
                    self.output_queue.put("No guest accounts found. Nothing to do.\n"); return
                for g in guests:
                    self.output_queue.put("  - %s (%s)\n" % (g.get("displayName", "?"),
                                                             g.get("userPrincipalName", "?")))
                if not self._ask_confirm(str(len(guests)) + " guest account(s) will be "
                                         "DELETED (recoverable 30 days)."):
                    self.output_queue.put("\n[canceled - nothing deleted]\n"); return
                self.output_queue.put("\nStep 2: removing...\n")
                removed = 0
                for g in guests:
                    if self.workflow_cancel:
                        self.output_queue.put("[stopped by user]\n"); break
                    gid = g.get("id")
                    rc, out = self._capture(["entra", "user", "remove", "--id", gid, "--force"])
                    ok = "OK" if rc == 0 else "FAILED (rc=%d)" % rc
                    self.output_queue.put("  %s %s %s\n" % (ok, g.get("userPrincipalName", gid),
                                                           "" if rc == 0 else out.strip()[:80]))
                    if rc == 0: removed += 1
                self.output_queue.put("\n===== DONE: removed %d of %d =====\n" % (removed, len(guests)))
            except Exception as exc:
                self.output_queue.put("WORKFLOW ERROR: " + str(exc) + "\n")
            finally:
                self.running_proc = None
                self.output_queue.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def _stop(self):
        self.workflow_cancel = True
        proc = self.running_proc
        if proc is None: return
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            else:
                proc.kill()
            self._append_output("\n[stopped by user]\n")
        except Exception as exc:
            self._append_output("\n[stop failed: " + str(exc) + "]\n")

    def _poll_output(self):
        try:
            while True:
                try:
                    line = self.output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    self.run_button.config(state="normal")
                elif callable(line):
                    line()                      # UI work handed over from a thread
                elif isinstance(line, tuple) and line[0] == "yesno":
                    _tag, summary, event, result = line
                    try:
                        result["ok"] = messagebox.askyesno(APP_NAME + " - CONFIRM", summary,
                                                           parent=self)
                    finally:
                        event.set()
                elif isinstance(line, tuple) and line[0] == "confirm":
                    _tag, summary, event, result = line
                    try:
                        ans = simpledialog.askstring(APP_NAME + " - CONFIRM DELETE",
                                summary + "\n\nType DELETE to proceed (anything else cancels):",
                                parent=self)
                        result["ok"] = (ans == "DELETE")
                    finally:
                        event.set()
                else:
                    self._append_output(line)
        except Exception as exc:
            try: self._append_output("\n[poll error: " + str(exc) + "]\n")
            except Exception: pass
        finally:
            self.after(100, self._poll_output)

    def _append_output(self, text):
        self.output_box.insert("end", text); self.output_box.see("end")
        try:
            with open(self.log_path, "a", encoding="utf-8") as h: h.write(text)
        except OSError:
            pass

    def _locate(self):
        path = filedialog.askopenfilename(title="Locate m365",
                filetypes=[("m365 CLI", "m365.cmd;m365.exe;m365.ps1;m365"), ("All files", "*.*")])
        if path:
            self.m365_path = path
            self.path_label.config(text="m365: " + path)
            self._refresh_account()
            if not self.config_parser.has_section(APP_NAME.lower()):
                self.config_parser.add_section(APP_NAME.lower())
            self.config_parser.set(APP_NAME.lower(), "m365_path", path)
            with open(INI_PATH, "w", encoding="utf-8") as h:
                self.config_parser.write(h)

    # ---- settings in m365gui.ini --------------------------------------------
    def _setting(self, name, default=""):
        return self.config_parser.get(APP_NAME.lower(), name, fallback=default)

    def _save_setting(self, name, value):
        try:
            if not self.config_parser.has_section(APP_NAME.lower()):
                self.config_parser.add_section(APP_NAME.lower())
            self.config_parser.set(APP_NAME.lower(), name, value)
            with open(INI_PATH, "w", encoding="utf-8") as h:
                self.config_parser.write(h)
        except Exception:
            pass                        # a read-only ini must not break the app

    def _log(self, text):
        # A line for the session log only (not the output box).
        try:
            with open(self.log_path, "a", encoding="utf-8") as h:
                h.write("[" + datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
                        + "] " + text + "\n")
        except OSError:
            pass

    # ---- Help menu: updates, What's new, About (v0.5, as in GAMGUI) ----------
    def _build_menu(self):
        bar = tk.Menu(self)
        helpm = tk.Menu(bar, tearoff=0)
        helpm.add_command(label="Check for updates now",
                          command=lambda: self._check_updates_async(False))
        self.check_updates_var = tk.BooleanVar(value=self.check_updates)
        helpm.add_checkbutton(label="Check for updates at startup",
                              variable=self.check_updates_var,
                              command=self._toggle_check_updates)
        self.whats_new_var = tk.BooleanVar(value=self.show_whats_new)
        helpm.add_checkbutton(label="Show What's new after an update",
                              variable=self.whats_new_var,
                              command=self._toggle_whats_new)
        helpm.add_command(label="What's new", command=lambda: self._show_whats_new(None))
        helpm.add_separator()
        helpm.add_command(label="Releases page (all versions)",
                          command=lambda: webbrowser.open(UPDATE_RELEASES_URL))
        helpm.add_command(label="About " + APP_NAME, command=self._show_about)
        bar.add_cascade(label="Help", menu=helpm)
        self.config(menu=bar)

    def _toggle_check_updates(self):
        self.check_updates = bool(self.check_updates_var.get())
        self._save_setting("check_updates", "true" if self.check_updates else "false")

    def _toggle_whats_new(self):
        self.show_whats_new = bool(self.whats_new_var.get())
        self._save_setting("show_whats_new", "true" if self.show_whats_new else "false")

    def _show_about(self):
        messagebox.showinfo("About " + APP_NAME,
                            APP_NAME + " " + APP_VERSION + "\n\nA graphical front-end "
                            "for the CLI for Microsoft 365.\n" + UPDATE_RELEASES_URL)

    def _startup_checks(self):
        # Once, shortly after the window opens: What's new (if this copy was
        # just updated), then the silent update check.
        self._maybe_show_whats_new()
        if self.check_updates:
            self._check_updates_async(True)

    def _maybe_show_whats_new(self):
        # The version that last ran is kept in m365gui.ini. A first run just
        # records it; a NEWER version than last time shows What's new once.
        last = self._setting("last_version", "")
        self._save_setting("last_version", APP_VERSION)
        if (last and self.show_whats_new
                and self._version_tuple(APP_VERSION) > self._version_tuple(last)):
            self._log("Updated from " + last + " to " + APP_VERSION + " - showing what's new.")
            self._show_whats_new(last)

    def _show_whats_new(self, since):
        # since=None (Help menu): the five newest versions.
        try:
            with open(resource_path("CHANGELOG.txt"), encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            text = ""
        entries = m365_update.changelog_since(text, since or "0", APP_VERSION)
        if since is None:
            entries = entries[:5]
        win = tk.Toplevel(self)
        win.title(APP_NAME + " - What's new" + (" since " + since if since else ""))
        win.transient(self)
        win.geometry("820x560")
        box = scrolledtext.ScrolledText(win, wrap="word", width=100, height=30)
        box.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        box.insert("1.0", m365_update.format_whats_new(entries) if entries else
                   "The list of changes is not available in this copy. See the "
                   "Releases page for every version's notes.")
        box.configure(state="disabled")
        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="All releases on GitHub",
                   command=lambda: webbrowser.open(UPDATE_RELEASES_URL)).pack(side="left")
        ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right")
        ttk.Checkbutton(buttons, text="Show this after every update",
                        variable=self.whats_new_var,
                        command=self._toggle_whats_new).pack(side="right", padx=(0, 12))

    def _version_tuple(self, text):
        # "0.10" > "0.9": compare versions as numbers, not text.
        parts = []
        for piece in (text or "").strip().lstrip("vV").split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts) if parts else (0,)

    def _check_updates_async(self, auto):
        # On a background thread so a slow network never freezes the window.
        # auto=True is the silent startup check (says nothing unless there is
        # an update); False is the menu item (always answers).
        if self._update_in_progress:
            return
        threading.Thread(target=self._check_updates_worker, args=(auto,), daemon=True).start()

    def _check_updates_worker(self, auto):
        tag, err = "", ""
        try:
            request = urllib.request.Request(
                UPDATE_API_URL, headers={"User-Agent": "M365GUI-Updater",
                                         "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(request, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
            tag = str(data.get("tag_name", "")).strip()
            if not tag:
                err = "GitHub did not return a release tag."
        except Exception as exc:
            err = str(exc)
        self.output_queue.put(lambda: self._on_update_check_result(tag, err, auto))

    def _on_update_check_result(self, tag, err, auto):
        if err or not tag:
            if not auto:
                messagebox.showwarning(APP_NAME + " - Update check",
                                       "Could not check for updates:\n" + (err or "unknown error"))
            self._log("Update check failed: " + (err or "no tag"))
            return
        if self._version_tuple(tag) > self._version_tuple(APP_VERSION):
            self._prompt_update(tag)
        else:
            self._log("Update check: up to date (" + APP_VERSION + ").")
            if not auto:
                messagebox.showinfo(APP_NAME + " - Update check",
                                    "You are on the latest version (" + APP_VERSION + ").")

    def _prompt_update(self, tag):
        # M365GUI never updates without this explicit yes.
        self._log("Update available: " + APP_VERSION + " -> " + tag)
        if messagebox.askyesno(
                APP_NAME + " - Update available",
                "A newer version of " + APP_NAME + " is available.\n\n"
                "    Installed: " + APP_VERSION + "\n    Latest:    " + tag + "\n\n"
                "Update now? " + APP_NAME + " will close, update itself, and reopen "
                "when it is done."):
            self._do_self_update(tag)

    def _do_self_update(self, tag):
        # Windows: the bundled updatem365gui.ps1 (Setup.exe install -> re-runs
        # the new Setup.exe, elevated; portable copy -> the zip). macOS /
        # Linux: m365_update. Both only install a download whose SHA-256
        # matches the release notes.
        if self._update_in_progress or self.running_proc is not None:
            if self.running_proc is not None:
                messagebox.showinfo(APP_NAME, "A command is running - update after it finishes.")
            return
        if sys.platform != "win32":
            self._self_update_posix(tag)
            return
        appdir = app_dir()
        updater = os.path.join(appdir, "updatem365gui.ps1")
        if not getattr(sys, "frozen", False) or not os.path.isfile(updater):
            webbrowser.open(UPDATE_RELEASES_URL)
            messagebox.showinfo(APP_NAME, "This copy cannot update itself (it runs from "
                                "source, or the updater is missing), so the Releases "
                                "page has been opened in your browser instead.")
            return
        # Is THIS copy the registered Setup.exe install? Decided from the
        # registry (an admin can often write to Program Files, so a write
        # test would wrongly call it portable).
        reg = registry_exe_install()
        installed = bool(reg and _same_path(appdir, reg.get("location", "")))
        try:
            if installed:
                # Elevated (UAC) so it can re-run Setup.exe; the installer's
                # /CLOSEAPPLICATIONS closes this window itself.
                import ctypes
                params = ('-ExecutionPolicy Bypass -NoProfile -File "' + updater
                          + '" -InstallType exe -Launch')
                rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe",
                                                         params, None, 1)
                if int(rc) <= 32:
                    messagebox.showwarning(
                        APP_NAME, "The update needs administrator approval and it was "
                        "not granted, so nothing was changed. Try again and choose Yes "
                        "at the Windows prompt, or update by hand from:\n" + UPDATE_RELEASES_URL)
                    return
            else:
                # Portable copy: the updater waits for this window to close,
                # then replaces the files (keeping m365gui.ini and Logs).
                inner = ("Start-Sleep -Seconds 3; & '" + updater.replace("'", "''")
                         + "' -InstallType zip -InstallRoot '" + appdir.replace("'", "''")
                         + "' -Launch")
                subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile",
                                  "-Command", inner],
                                 creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Could not start the updater:\n" + str(exc)
                                 + "\n\nYou can update by hand from:\n" + UPDATE_RELEASES_URL)
            return
        self._update_in_progress = True
        self._log("Self-update launched (" + APP_VERSION + " -> " + tag
                  + (", installer" if installed else ", portable") + ").")
        self.destroy()

    def _self_update_posix(self, tag):
        # macOS / Linux: how was THIS copy installed? Then download + verify
        # the matching release file on a background thread.
        import platform
        kind, target = m365_update.install_kind(
            platform.system(), sys.executable, getattr(sys, "frozen", False),
            lambda path: os.access(path, os.W_OK))
        if kind in ("source", "unknown"):
            webbrowser.open(UPDATE_RELEASES_URL)
            messagebox.showinfo(APP_NAME, (
                "This copy is running from source code" if kind == "source" else
                "M365GUI cannot replace itself here (its folder is not writable by "
                "your account)") + ", so the Releases page has been opened in your "
                "browser instead.")
            return
        tool = None
        if kind == "linux-package":
            tool = next((t for t in ("apt", "dnf", "yum", "zypper") if shutil.which(t)), "rpm")
        name = m365_update.asset_name(kind, tag, tool)
        self._update_in_progress = True
        self._append_output("\n===== UPDATING TO " + tag + " =====\nDownloading " + name + " ...\n")
        threading.Thread(target=self._posix_update_worker,
                         args=(tag, kind, target, name, tool), daemon=True).start()

    def _posix_update_worker(self, tag, kind, target, name, tool):
        # OFF the UI thread: download, check the SHA-256 against the release
        # notes, unpack, write the swap script. Nothing M365GUI runs from is
        # touched here - the script does that after M365GUI closes.
        say = self.output_queue.put
        try:
            request = urllib.request.Request(
                UPDATE_API_URL, headers={"User-Agent": "M365GUI-Updater",
                                         "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            if str(data.get("tag_name", "")).strip() != tag:
                raise RuntimeError("the latest release changed while updating - please try again")
            want = m365_update.published_sha256(data.get("body", ""), name)
            if not want:
                raise RuntimeError("the release notes do not list a SHA-256 for " + name
                                   + " yet (they are added right after each build) - "
                                   "please try again later")
            url = next((a.get("browser_download_url") for a in data.get("assets", [])
                        if a.get("name") == name), None)
            if not url:
                raise RuntimeError(name + " is not attached to release " + tag)
            if kind == "linux-package":
                work = None
                folder = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, name)
            else:
                work = tempfile.mkdtemp(prefix="m365gui-update-")
                path = os.path.join(work, name)
            digest = hashlib.sha256()
            with urllib.request.urlopen(urllib.request.Request(
                    url, headers={"User-Agent": "M365GUI-Updater"}), timeout=60) as resp, \
                    open(path, "wb") as out:
                size = int(resp.headers.get("Content-Length") or 0)
                done, shown = 0, 0
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if size and done * 10 // size > shown:
                        shown = done * 10 // size
                        say("  %d%%\n" % (shown * 10))
            if digest.hexdigest().upper() != want:
                os.remove(path)
                raise RuntimeError("the download does NOT match the SHA-256 in the "
                                   "release notes, so it was deleted")
            say("SHA-256 matches the release notes.\n")
            if kind == "linux-package":
                self.output_queue.put(lambda: self._posix_update_package_done(tool, path))
                return
            new_root = os.path.join(work, "new")
            os.makedirs(new_root)
            log = os.path.join(LOG_DIR, "m365gui-update.log")
            if kind == "mac-app":
                # ditto (Apple's tool) keeps the app's links and signature.
                if subprocess.run(["ditto", "-x", "-k", path, new_root]).returncode:
                    raise RuntimeError("could not unpack " + name)
                new_item = next((os.path.join(dirpath, d)
                                 for dirpath, dirs, _files in os.walk(new_root)
                                 for d in dirs if d == "M365GUI.app"), None)
                if not new_item:
                    raise RuntimeError(name + " does not contain M365GUI.app")
                script = m365_update.mac_update_script(
                    os.getpid(), target, new_item, app_dir(), DATA_DIR, work, log, APP_VERSION)
            else:
                m365_update.safe_extract_tar(path, new_root)
                new_item = os.path.join(new_root, "M365GUI")
                if not os.path.isfile(os.path.join(new_item, "M365GUI")):
                    raise RuntimeError(name + " does not contain M365GUI/M365GUI")
                script = m365_update.linux_update_script(
                    os.getpid(), target, new_item, work, log, APP_VERSION)
            script_path = os.path.join(work, "update.sh")
            with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(script)
            os.chmod(script_path, 0o700)
            self.output_queue.put(lambda: self._posix_update_launch(script_path, tag))
        except Exception as exc:
            message = str(exc)
            self.output_queue.put(lambda: self._posix_update_failed(message))

    def _posix_update_launch(self, script_path, tag):
        # The swap script runs in its own session (it outlives M365GUI).
        self._log("Self-update launched (" + APP_VERSION + " -> " + tag + ", "
                  + sys.platform + ").")
        subprocess.Popen(["/bin/bash", script_path], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
        self.destroy()

    def _posix_update_failed(self, message):
        self._update_in_progress = False
        self._log("Self-update failed: " + message)
        if messagebox.askyesno(APP_NAME + " - Update", "The update did not run - " + message
                               + ".\n\nNothing was changed. Open the Releases page to "
                               "download it yourself?"):
            webbrowser.open(UPDATE_RELEASES_URL)

    def _posix_update_package_done(self, tool, path):
        # .deb / .rpm installs live in /opt (root-owned): M365GUI never asks
        # for root itself - it hands the admin the one command to run.
        self._update_in_progress = False
        command = m365_update.package_command(tool, path)
        self.clipboard_clear()
        self.clipboard_append(command)
        self._append_output("Downloaded and verified: " + path + "\nInstall it with "
                            "(copied to the clipboard):\n  " + command + "\n")
        messagebox.showinfo(
            APP_NAME + " - Update downloaded",
            "The new version was downloaded and its SHA-256 matches the release notes:\n"
            + path + "\n\nThis copy was installed as a package, so installing needs your "
            "password. In a terminal, run (already copied to the clipboard):\n\n"
            + command + "\n\nThen reopen M365GUI.")


if __name__ == "__main__":
    M365Gui().mainloop()
