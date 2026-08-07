# =============================================================================
# Script:   M365GUI.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  08-07-2026
# Modified: 08-07-2026
# Version:  0.2
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
import datetime
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog

APP_NAME = "M365GUI"
APP_VERSION = "0.2"

# =============================================================================
# SECTION: Locating the m365 CLI
# =============================================================================

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

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
    return ""

INI_PATH = os.path.join(app_dir(), "m365gui.ini")
LOG_DIR = os.path.join(app_dir(), "Logs")

# =============================================================================
# SECTION: Task catalog (all commands verified against m365 v11 --help)
#   template uses "--flag {value}" style; {placeholders} fill from the form,
#   [bracketed] parts drop when blank, bare flags (--force) are literal.
# =============================================================================

def T(name, desc, template, fields, destructive=False, workflow=""):
    return {"name": name, "desc": desc, "template": template,
            "fields": fields, "destructive": destructive, "workflow": workflow}

def F(label, key, required=True, choices=None, default=""):
    return {"label": label, "key": key, "required": required,
            "choices": choices, "default": default}

TASKS = {
 "Users (Entra ID)": [
  T("List users", "Lists all users in the directory.",
    "entra user list --output text", []),
  T("List guest users", "Lists only external / guest accounts.",
    "entra user list --type Guest --output text", []),
  T("Get user info", "Shows the details of one user, found by their UPN.",
    "entra user get --userName {email} --output text",
    [F("User (UPN) e.g. jdoe@contoso.com", "email")]),
  T("Create user",
    "Creates a new member account. Set the usage location so the account can "
    "be licensed later.",
    "entra user add --displayName {display} --userName {email} --password {password} [--usageLocation {loc}]",
    [F("Display name e.g. John Doe", "display"),
     F("User (UPN) e.g. jdoe@contoso.com", "email"),
     F("Initial password", "password"),
     F("Usage location e.g. US (optional)", "loc", False)]),
  T("Reset password",
    "Sets a new password and forces a change at next sign-in.",
    "entra user set --userName {email} --resetPassword --newPassword {password} --forceChangePasswordNextSignIn",
    [F("User (UPN)", "email"), F("New password", "password")]),
  T("Rename user (display / first / last name)",
    "Changes the user's names. The sign-in name (UPN) does not change.",
    "entra user set --userName {email} [--displayName {display}] [--firstName {first}] [--lastName {last}]",
    [F("User (UPN)", "email"), F("New display name (optional)", "display", False),
     F("New first name (optional)", "first", False),
     F("New last name (optional)", "last", False)]),
  T("Set usage location",
    "Sets the country the account is used from (required before assigning "
    "licenses).",
    "entra user set --userName {email} --usageLocation {loc}",
    [F("User (UPN)", "email"), F("Usage location e.g. US", "loc")]),
  T("Block sign-in",
    "Disables the account so the user cannot sign in; keeps the account/data.",
    "entra user set --userName {email} --accountEnabled false",
    [F("User (UPN)", "email")]),
  T("Unblock sign-in", "Re-enables a blocked account.",
    "entra user set --userName {email} --accountEnabled true",
    [F("User (UPN)", "email")]),
  T("Delete user (DESTRUCTIVE)",
    "Deletes the account (recoverable from the Entra recycle bin for 30 days).",
    "entra user remove --userName {email} --force",
    [F("User (UPN)", "email")], destructive=True),
  T("List deleted users (recycle bin)",
    "Lists users that were deleted within the last 30 days.",
    "entra user recyclebinitem list --output text", []),
  T("Restore deleted user",
    "Restores a soft-deleted user by their object id (from the recycle bin "
    "list).",
    "entra user recyclebinitem restore --id {id}",
    [F("User object id (from recycle bin list)", "id")]),
  T("Remove ALL guest users (DESTRUCTIVE)",
    "Finds every guest account, shows you the count, asks you to type DELETE, "
    "then removes them one by one. Nothing is deleted until you confirm.",
    "", [], destructive=True, workflow="remove_guests"),
 ],
 "Groups (Entra)": [
  T("List groups", "Lists all groups in the directory.",
    "entra group list --output text", []),
  T("List groups by type", "Lists only Microsoft 365 groups or security groups.",
    "entra group list --type {type} --output text",
    [F("Type", "type", choices=["microsoft365", "security"])]),
  T("Get group info", "Shows the details of one group, found by its name.",
    "entra group get --displayName {name} --output text",
    [F("Group display name", "name")]),
  T("Create group",
    "Creates a Microsoft 365 or security group.",
    "entra group add --displayName {name} --type {type} [--mailNickname {nick}] [--description {desc}]",
    [F("Group display name", "name"),
     F("Type", "type", choices=["microsoft365", "security"]),
     F("Mail nickname (M365 groups) e.g. sales (optional)", "nick", False),
     F("Description (optional)", "desc", False)]),
  T("List group members", "Lists the members of a group.",
    "entra group member list --groupName {name} --output text",
    [F("Group display name", "name")]),
  T("Add member to group", "Adds a user to a group with the chosen role.",
    "entra group member add --groupName {name} --userNames {email} --role {role}",
    [F("Group display name", "name"), F("User (UPN)", "email"),
     F("Role", "role", choices=["Member", "Owner"])]),
  T("Remove member from group (DESTRUCTIVE)", "Removes a user from a group.",
    "entra group member remove --groupName {name} --userNames {email} --force",
    [F("Group display name", "name"), F("User (UPN)", "email")],
    destructive=True),
  T("Delete group (DESTRUCTIVE)", "Deletes a group (not its members' accounts).",
    "entra group remove --displayName {name} --force",
    [F("Group display name", "name")], destructive=True),
 ],
 "Licenses": [
  T("View all licenses (tenant SKUs)",
    "Lists the license SKUs your tenant owns, with used/total counts and each "
    "SKU's id (needed for the tasks below).",
    "entra license list --output text", []),
  T("List users with a specific license",
    "Lists every user assigned a given license. Get the SKU id from 'View all "
    "licenses' (the skuId GUID).",
    "entra user list --properties \"displayName,userPrincipalName,assignedLicenses\" "
    "--query \"[?assignedLicenses[?skuId=='{skuId}']].{displayName:displayName,userPrincipalName:userPrincipalName}\" --output text",
    [F("License SKU id (GUID, from View all licenses)", "skuId")]),
  T("Assign license(s)",
    "Assigns one or more license SKUs (comma-separated ids) to a user. The "
    "user must have a usage location set.",
    "entra user license add --userName {email} --ids {ids}",
    [F("User (UPN)", "email"), F("License SKU id(s), comma-separated", "ids")]),
  T("Remove license(s) (DESTRUCTIVE)",
    "Removes one or more license SKUs from a user.",
    "entra user license remove --userName {email} --ids {ids} --force",
    [F("User (UPN)", "email"), F("License SKU id(s), comma-separated", "ids")],
    destructive=True),
 ],
 "Teams / M365 Groups": [
  T("Add member to a Team",
    "Adds a user to a Microsoft Team (M365 group) as Member or Owner.",
    "entra m365group user add --teamName {team} --userNames {email} --role {role}",
    [F("Team display name e.g. Engineering", "team"), F("User (UPN)", "email"),
     F("Role", "role", choices=["Member", "Owner"])]),
 ],
 "SharePoint": [
  T("List sites", "Lists SharePoint sites in the tenant.",
    "spo site list --output text", []),
  T("Add user to a SharePoint group",
    "Adds a user to a SharePoint group on a specific site.",
    "spo group member add --webUrl {url} --groupName {group} --userNames {email}",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url"),
     F("SharePoint group name", "group"), F("User (UPN)", "email")]),
 ],
 "Security": [
  T("Sign user out everywhere",
    "Revokes all sign-in sessions for the user - first move on a compromised "
    "account (they must sign in again).",
    "entra user session revoke --userName {email} --force",
    [F("User (UPN)", "email")], destructive=True),
  T("Sign-in activity",
    "Lists recent sign-ins for a user. REQUIRES the AuditLog.Read.All Graph "
    "permission AND a Microsoft Entra ID P1/P2 (premium) tenant - sign-in logs "
    "are a premium feature. If it fails with 'Error: [object Object]', that is "
    "the CLI hiding the real message; re-run the command with --debug (or add "
    "--verbose in Custom command) to see the actual reason.",
    "entra user signin list --userName {email} --output text",
    [F("User (UPN)", "email")]),
 ],
 "Diagnostics": [
  T("Login status", "Shows whether the CLI is signed in and to which tenant.",
    "status", []),
  T("CLI version", "Shows the CLI for Microsoft 365 version.", "version", []),
  T("Tenant ID", "Shows the tenant's directory (tenant) id.",
    "tenant id get", []),
 ],
}

# =============================================================================
# SECTION: Command building (same engine as GAMGUI)
# =============================================================================

def quote_if_needed(value):
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        return value
    if " " in value or '"' in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value

def build_command(task, values):
    template = task["template"]

    def seg_sub(match):
        segment = match.group(0)[1:-1]
        keys = re.findall(r"{(\w+)[^}]*}", segment)
        if any(values.get(k, "").strip() for k in keys):
            return segment
        return ""
    # Optional segments are flag groups like [--usageLocation {loc}]. The
    # pattern requires the segment to begin with "--" so it does NOT collide
    # with literal JMESPath brackets in a --query value, e.g.
    # [?assignedLicenses[?skuId=='...']].
    rendered = re.sub(r"\[--[^\]]*\]", seg_sub, template)

    argv, display_parts, problem = [], [], [""]

    def fill(m):
        key, fallback = m.group(1), m.group(2) or ""
        v = values.get(key, "").strip()
        if not v:
            if fallback:
                v = fallback
            else:
                problem[0] = "Missing required value: " + key
        return v

    # Split on whitespace but keep quoted "..." segments together so that
    # options like --properties "a,b,c" stay a single argument.
    for token in re.findall(r'"[^"]*"|\S+', rendered):
        filled = re.sub(r"{(\w+)(?:\|([^}]*))?}", fill, token)
        if problem[0]:
            return "", [], problem[0]
        if filled.startswith('"') and filled.endswith('"') and len(filled) > 1:
            inner = filled[1:-1]
            argv.append(inner)
            display_parts.append(quote_if_needed(inner))
        else:
            argv.append(filled)
            display_parts.append(quote_if_needed(filled))
    return " ".join(display_parts), argv, ""

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

        self._build_layout()
        self._populate_tree()
        self._preselect()
        self.after(100, self._poll_output)
        if not self.m365_path:
            self._append_output(
                "NOTE: the 'm365' CLI was not found. Install it with\n"
                "    npm i -g @pnp/cli-microsoft365\n"
                "then sign in with 'm365 login', or click 'Locate m365...'.\n")

    # ---- invocation host selection (cmd.exe / PowerShell / direct) ----------
    def _build_invocation(self, argv):
        exe = self.m365_path
        low = exe.lower()
        if os.name == "nt" and low.endswith((".cmd", ".bat")):
            return [os.environ.get("COMSPEC", "cmd.exe"), "/c", exe] + argv
        if os.name == "nt" and low.endswith(".ps1"):
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", exe] + argv
        return [exe] + argv

    # ---- layout -------------------------------------------------------------
    def _build_layout(self):
        top = ttk.Frame(self, padding=4); top.pack(side="top", fill="x")
        self.path_label = ttk.Label(top, text="m365: " + (self.m365_path or "(not found)"))
        self.path_label.pack(side="left")
        ttk.Button(top, text="Locate m365...", command=self._locate).pack(side="right")

        main = ttk.PanedWindow(self, orient="horizontal"); main.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(main, show="tree", selectmode="browse")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        main.add(self.tree, weight=1)

        right = ttk.Frame(main, padding=6); main.add(right, weight=3)
        self.desc_label = ttk.Label(right, text="Select a task on the left.",
                                    wraplength=720, justify="left")
        self.desc_label.pack(anchor="w")
        self.form_frame = ttk.Frame(right); self.form_frame.pack(fill="x", pady=6)

        pv = ttk.Frame(right); pv.pack(fill="x")
        ttk.Label(pv, text="Command preview (editable):").pack(side="left")
        ttk.Button(pv, text="Build", command=self._preview).pack(side="right")
        ttk.Button(pv, text="Copy", command=self._copy).pack(side="right")
        self.preview_box = tk.Text(right, height=3, wrap="word"); self.preview_box.pack(fill="x", pady=4)

        rb = ttk.Frame(right); rb.pack(fill="x")
        self.run_button = ttk.Button(rb, text="Run", command=self._run); self.run_button.pack(side="left")
        ttk.Button(rb, text="Stop", command=self._stop).pack(side="left", padx=4)
        ttk.Button(rb, text="Clear output", command=lambda: self.output_box.delete("1.0", "end")).pack(side="right")
        self.output_box = scrolledtext.ScrolledText(right, height=18, wrap="word"); self.output_box.pack(fill="both", expand=True, pady=4)

    def _populate_tree(self):
        for category, tasks in TASKS.items():
            parent = self.tree.insert("", "end", text=category, open=False)
            for index, task in enumerate(tasks):
                self.tree.insert(parent, "end", text=task["name"], values=(category, index))
        self.tree.insert("", "end", text="Custom command", values=("__custom__", 0))

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
        self.current_task = TASKS[vals[0]][int(vals[1])]
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
                if field["choices"]: var.set(field["choices"][0])
            else:
                w = ttk.Entry(self.form_frame, textvariable=var, width=62)
            w.grid(row=row, column=1, sticky="we", pady=2, padx=6)
            self.field_vars.append((field["key"], var))
        self.form_frame.columnconfigure(1, weight=1)
        self._preview()

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
            self.preview_box.insert("1.0", "Workflow: list guests -> confirm (type "
                                    "DELETE) -> remove each. Click Run to start.")
            return
        display, argv, err = build_command(self.current_task, self._collect())
        self.preview_box.delete("1.0", "end")
        if err:
            self.generated_display = None; self.generated_argv = None
            self.preview_box.insert("1.0", "(" + err + ")")
        else:
            self.generated_display = "m365 " + display; self.generated_argv = argv
            self.preview_box.insert("1.0", self.generated_display)

    def _copy(self):
        self.clipboard_clear(); self.clipboard_append(self.preview_box.get("1.0", "end").strip())

    # ---- execution ----------------------------------------------------------
    def _run(self):
        if self.running_proc is not None:
            messagebox.showinfo(APP_NAME, "A command is already running."); return
        if not self.m365_path:
            messagebox.showerror(APP_NAME, "m365 CLI not found. Install it or click Locate m365."); return
        if self.current_task and self.current_task.get("workflow") == "remove_guests":
            self._run_remove_guests(); return

        command_text = self.preview_box.get("1.0", "end").strip()
        if command_text.startswith("("):
            self._preview(); command_text = self.preview_box.get("1.0", "end").strip()
        if not command_text or command_text.startswith("("):
            messagebox.showerror(APP_NAME, "Fill in the required fields first."); return

        if command_text == getattr(self, "generated_display", None):
            argv = list(self.generated_argv)
        else:
            s = command_text
            if s.lower().startswith("m365 "): s = s[5:]
            argv = [a[1:-1] if a.startswith('"') and a.endswith('"') else a
                    for a in re.findall(r'"[^"]*"|\S+', s)]
        if not argv: return

        if self.current_task and self.current_task["destructive"]:
            if not messagebox.askyesno(APP_NAME + " - CONFIRM",
                    "This makes a change or deletes data:\n\n" + command_text + "\n\nAre you sure?"):
                return

        self._append_output("\n> " + command_text + "\n")
        self.run_button.config(state="disabled")

        def worker():
            try:
                proc = subprocess.Popen(self._build_invocation(argv),
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace")
                self.running_proc = proc
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
        proc = subprocess.Popen(self._build_invocation(argv), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace")
        self.running_proc = proc
        out = proc.stdout.read()
        proc.wait(); self.running_proc = None
        return proc.returncode, out

    def _ask_confirm(self, summary):
        event = threading.Event(); result = {"ok": False}
        self.output_queue.put(("confirm", summary, event, result))
        event.wait(); return result["ok"]

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
            if not self.config_parser.has_section(APP_NAME.lower()):
                self.config_parser.add_section(APP_NAME.lower())
            self.config_parser.set(APP_NAME.lower(), "m365_path", path)
            with open(INI_PATH, "w", encoding="utf-8") as h:
                self.config_parser.write(h)


if __name__ == "__main__":
    M365Gui().mainloop()
