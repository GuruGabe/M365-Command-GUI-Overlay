# =============================================================================
# Script:   M365GUI.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  08-07-2026
# Modified: 10-22-2026
# Version:  0.4
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
import urllib.parse
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
APP_VERSION = "0.5"

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

# The 'Afterwards' choices of the OneDrive copy (see transfer_onedrive).
TRANSFER_ACCESS_REMOVE = "Remove my temporary access when done"
TRANSFER_ACCESS_KEEP = "Keep my access to both OneDrives"

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
 "OneDrive": [
  T("Find a user's OneDrive address",
    "Shows the web address of a user's OneDrive (empty if their OneDrive has "
    "never been set up - it is created the first time they open it).",
    "entra user get --userName {email} --properties userPrincipalName,mySite --output text",
    [F("User (UPN)", "email")]),
  T("Copy a user's OneDrive files to another user",
    "For a person who is leaving: copies EVERYTHING in their OneDrive into a "
    "new folder in another person's OneDrive (e.g. their manager). Nothing "
    "is removed from the original owner, and files with the same name are "
    "renamed, never overwritten. Shows the file count and asks before "
    "copying; afterwards counts the files that arrived and saves a CSV "
    "record in the Logs folder. You need to be a SharePoint or Global "
    "administrator: M365GUI gives you access to both OneDrives for the copy "
    "and takes it away again afterwards (unless you choose to keep it).",
    "", [F("From: whose files (UPN) e.g. jdoe@contoso.com", "from"),
         F("To: who gets a copy (UPN) e.g. manager@contoso.com", "to"),
         F("Folder name in their OneDrive (optional - default 'Files from <name> <date>')",
           "folder", False),
         F("Afterwards", "access", choices=[TRANSFER_ACCESS_REMOVE, TRANSFER_ACCESS_KEEP])],
    workflow="onedrive_transfer"),
 ],
 "Diagnostics": [
  T("Login status", "Shows whether the CLI is signed in and to which tenant.",
    "status", []),
  T("CLI version", "Shows the CLI for Microsoft 365 version.", "version", []),
  T("Tenant ID", "Shows the tenant's directory (tenant) id.",
    "tenant id get", []),
 ],
}

# What the preview box says for a guided workflow (it runs several commands).
WORKFLOW_PLANS = {
    "remove_guests": "Workflow: list guests -> confirm (type DELETE) -> remove each. "
                     "Click Run to start.",
    "onedrive_transfer": "Workflow: find both OneDrives -> give you temporary access -> "
                         "count the files -> ask you -> copy into the new folder -> "
                         "count what arrived -> remove the temporary access. Click Run "
                         "to start.",
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
# SECTION: OneDrive transfer - copy one user's OneDrive files to another user
#   (v0.4). Copies; never removes anything from the original owner. Built
#   only from commands checked with 'm365 <command> --help' on CLI v11.11.
#   The signed-in admin needs site collection admin rights on BOTH OneDrives
#   to read and write them: M365GUI adds them for the run (SharePoint admin
#   center, --asAdmin) and removes again only what it added.
# =============================================================================

BAD_FOLDER_CHARS = set('"*:<>?/\\|')

def parse_json(text):
    # m365 prints JSON, sometimes after a line of plain text. Read from the
    # first [ or {. None when there is no JSON.
    text = (text or "").strip()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                return json.loads(text[i:])
            except ValueError:
                return None
    return None

def onedrive_paths(my_site):
    # A OneDrive address (Graph 'mySite', e.g. https://contoso-my.sharepoint
    # .com/personal/jdoe_contoso_com/) -> (site URL, host, server-relative
    # path of its document library). The library's URL is always
    # 'Documents', whatever language the OneDrive shows it in.
    web = my_site.strip().rstrip("/")
    parts = urllib.parse.urlsplit(web)
    return web, parts.scheme + "://" + parts.netloc, parts.path + "/Documents"

def default_transfer_folder(src_upn):
    # The folder the files land in, in the recipient's OneDrive.
    return "Files from %s %s" % (src_upn.split("@")[0],
                                 datetime.date.today().strftime("%m-%d-%Y"))

def size_text(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "bytes" else ("%.1f %s" % (n, unit))
        n /= 1024.0

def _is_site_admin(admins, upn):
    upn = upn.lower()
    return any((a.get("Email") or "").lower() == upn
               or (a.get("LoginName") or "").lower().endswith("|" + upn) for a in admins)

def transfer_onedrive(run, out, confirm, cancelled, values, report_path):
    # run(argv) -> (returncode, text): one m365 command.
    # out(text): progress for the window and the log.
    # confirm(text) -> True/False: the one question before anything is copied.
    # cancelled() -> True after Stop.
    # report_path: where the CSV record of every copy is written.
    # Returns a summary dict (ok, error, copied, failed, src_files, dst_files).
    result = {"ok": False, "error": "", "copied": 0, "failed": 0,
              "src_files": 0, "dst_files": 0}
    src_upn = (values.get("from") or "").strip()
    dst_upn = (values.get("to") or "").strip()
    folder = (values.get("folder") or "").strip() or default_transfer_folder(src_upn)
    keep_access = values.get("access") == TRANSFER_ACCESS_KEEP

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    # ---- 1. check the boxes before running anything ----------------------------
    for label, upn in (("From", src_upn), ("To", dst_upn)):
        if "@" not in upn or " " in upn:
            return stop("The %s box needs a sign-in name (UPN) such as jdoe@contoso.com." % label)
    if src_upn.lower() == dst_upn.lower():
        return stop("From and To are the same person - nothing to copy.")
    if BAD_FOLDER_CHARS & set(folder) or folder.endswith("."):
        return stop('The folder name cannot contain " * : < > ? / \\ | or end with a period.')

    out("\n===== COPY ONEDRIVE FILES: %s -> %s =====\n" % (src_upn, dst_upn))
    rc, text = run(["status", "--output", "json"])
    operator = (parse_json(text) or {}).get("connectedAs", "") if rc == 0 else ""
    if not operator:
        return stop("m365 is not signed in. Run 'm365 login' first.")

    # ---- 2. find both OneDrives -------------------------------------------------
    sites = {}
    for upn in (src_upn, dst_upn):
        rc, text = run(["entra", "user", "get", "--userName", upn,
                        "--properties", "userPrincipalName,mySite", "--output", "json"])
        info = parse_json(text) if rc == 0 else None
        if not isinstance(info, dict):
            return stop("Could not find %s: %s" % (upn, text.strip()[:300]))
        if not info.get("mySite"):
            return stop("%s has no OneDrive yet - it is created the first time they open "
                        "OneDrive (or when an admin pre-provisions it)." % upn)
        sites[upn] = onedrive_paths(info["mySite"])
    src_web, src_host, src_lib = sites[src_upn]
    dst_web, dst_host, dst_lib = sites[dst_upn]
    out("From: %s\nTo:   %s\n" % (src_web, dst_web))

    added = []                                    # sites where WE added access
    try:
        # ---- 3. access: site collection admin on both, for this run --------------
        for web in (src_web, dst_web):
            rc, text = run(["spo", "site", "admin", "list", "--siteUrl", web, "--asAdmin",
                            "--output", "json"])
            admins = parse_json(text) if rc == 0 else None
            if not isinstance(admins, list):
                return stop("Could not read who can manage %s: %s\nCopying needs a SharePoint "
                            "administrator (or Global administrator) signed in to m365, with "
                            "SharePoint access for the CLI's sign-in." % (web, text.strip()[:300]))
            if not _is_site_admin(admins, operator):
                rc, text = run(["spo", "site", "admin", "add", "--siteUrl", web,
                                "--userName", operator, "--asAdmin", "--output", "json"])
                if rc != 0:
                    return stop("Could not give %s access to %s: %s" % (operator, web, text.strip()[:300]))
                added.append(web)
                out("Gave %s temporary access to %s\n" % (operator, web))

        # ---- 4. what is there to copy --------------------------------------------
        hidden = src_lib + "/Forms"               # the library's own page files
        out("Counting %s's files - on a large OneDrive this can take 10 minutes or "
            "more...\n" % src_upn)
        rc, text = run(["spo", "file", "list", "--webUrl", src_web, "--folderUrl", src_lib,
                        "--recursive", "--fields", "Name,ServerRelativeUrl,Length",
                        "--output", "json"])
        every = parse_json(text) if rc == 0 else None
        if not isinstance(every, list):
            return stop("Could not list %s's files: %s" % (src_upn, text.strip()[:300]))
        every = [f for f in every
                 if not (f.get("ServerRelativeUrl") or "").startswith(hidden + "/")]
        result["src_files"] = len(every)
        total = sum(int(f.get("Length") or 0) for f in every)
        rc, text = run(["spo", "folder", "list", "--webUrl", src_web, "--parentFolderUrl", src_lib,
                        "--fields", "Name,ServerRelativeUrl", "--output", "json"])
        folders = parse_json(text) if rc == 0 else None
        rc2, text2 = run(["spo", "file", "list", "--webUrl", src_web, "--folderUrl", src_lib,
                          "--fields", "Name,ServerRelativeUrl", "--output", "json"])
        files = parse_json(text2) if rc2 == 0 else None
        if not isinstance(folders, list) or not isinstance(files, list):
            return stop("Could not list the top of %s's OneDrive: %s" % (src_upn, (text + text2).strip()[:300]))
        folders = [f for f in folders if f.get("Name") != "Forms"]
        items = ([("folder", f["ServerRelativeUrl"]) for f in folders] +
                 [("file", f["ServerRelativeUrl"]) for f in files])
        if not items:
            return stop("%s's OneDrive is empty - nothing to copy." % src_upn)

        question = ("Copy %d files (%s) in %d folders and %d loose files\n"
                    "FROM %s's OneDrive\nTO a new folder '%s' in %s's OneDrive?\n\n"
                    "Nothing is removed from %s. Files with the same name are renamed, "
                    "never overwritten." % (len(every), size_text(total), len(folders), len(files),
                                            src_upn, folder, dst_upn, src_upn))
        out(question + "\n")
        if not confirm(question):
            return stop("Canceled - nothing was copied.")

        # ---- 5. the destination folder, then copy --------------------------------
        rc, text = run(["spo", "folder", "add", "--webUrl", dst_web, "--parentFolderUrl", dst_lib,
                        "--name", folder, "--output", "json"])
        made = parse_json(text) if rc == 0 else None
        if not isinstance(made, dict):
            return stop("Could not create the folder '%s' in %s's OneDrive: %s"
                        % (folder, dst_upn, text.strip()[:300]))
        target_srv = made.get("ServerRelativeUrl") or (dst_lib + "/" + folder)
        target = dst_host + target_srv
        out("Copying into %s ...\n" % target)
        rows = [["type", "source", "result", "detail"]]
        for kind, source in items:
            if cancelled():
                out("[Stopped - the rest was not copied.]\n")
                break
            argv = ["spo", kind, "copy", "--webUrl", src_web, "--sourceUrl", source,
                    "--targetUrl", target, "--nameConflictBehavior", "rename"]
            if kind == "file":
                argv.append("--bypassSharedLock")   # a file left open still copies
            rc, text = run(argv + ["--output", "json"])
            name = source[len(src_lib) + 1:]
            if rc == 0:
                result["copied"] += 1
                out("  OK      %s %s\n" % (kind, name))
                rows.append([kind, source, "copied", ""])
            else:
                result["failed"] += 1
                detail = " ".join(text.split())[:200]
                out("  FAILED  %s %s - %s\n" % (kind, name, detail))
                rows.append([kind, source, "FAILED", detail])
        try:
            with open(report_path, "w", newline="", encoding="utf-8") as h:
                csv.writer(h).writerows(rows)
            out("Record of every copy: %s\n" % report_path)
        except OSError as exc:
            out("Could not save the record %s: %s\n" % (report_path, exc))

        # ---- 6. check: count the files that arrived -------------------------------
        out("Counting the files that arrived...\n")
        rc, text = run(["spo", "file", "list", "--webUrl", dst_web, "--folderUrl", target_srv,
                        "--recursive", "--fields", "Name,ServerRelativeUrl,Length", "--output", "json"])
        landed = parse_json(text) if rc == 0 else None
        if isinstance(landed, list):
            result["dst_files"] = len(landed)
            out("Check: %d of %d files are in the new folder (%s of %s).\n"
                % (len(landed), len(every), size_text(sum(int(f.get("Length") or 0) for f in landed)),
                   size_text(total)))
            if len(landed) < len(every):
                out("WARNING: some files did not arrive - see FAILED lines above, or run the "
                    "copy again into a new folder for the rest.\n")
        else:
            out("Could not count the copied files: %s\n" % text.strip()[:300])
        result["ok"] = result["failed"] == 0 and not cancelled()
        out("\n===== DONE: %d copied, %d failed =====\n" % (result["copied"], result["failed"]))
        return result
    finally:
        # ---- 7. take back only the access this run added --------------------------
        if keep_access:
            for web in added:
                out("Your access to %s was KEPT (as chosen).\n" % web)
        else:
            for web in added:
                rc, text = run(["spo", "site", "admin", "remove", "--siteUrl", web,
                                "--userName", operator, "--asAdmin", "--force", "--output", "json"])
                out(("Removed your temporary access to %s\n" % web) if rc == 0 else
                    ("COULD NOT remove your access to %s - remove it in the SharePoint admin "
                     "center: %s\n" % (web, text.strip()[:200])))

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

        self._build_layout()
        self._build_menu()
        self._populate_tree()
        self._preselect()
        self.after(100, self._poll_output)
        self.after(1500, self._startup_checks)
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
            self.preview_box.insert("1.0", WORKFLOW_PLANS[self.current_task["workflow"]])
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
        if self.current_task and self.current_task.get("workflow") == "onedrive_transfer":
            self._run_onedrive_transfer(); return

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
                                        text=True, encoding="utf-8", errors="replace",
                                        stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
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
