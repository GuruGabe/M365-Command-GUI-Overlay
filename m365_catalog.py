# =============================================================================
# Script:   m365_catalog.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  10-23-2026 (moved out of M365GUI.py, v0.6)
# Modified: 10-23-2026
#
# Purpose:
#   M365GUI's task catalog (every form: its m365 command template and boxes)
#   and the command builder that turns a filled-in form into the argument
#   list m365 runs. No window code here - like GAMGUI's gam_catalog.py.
# =============================================================================

import re

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

def build_command(task, values, category=""):
    # v0.6: pasted curly quotes / invisible characters in address and ID
    # boxes are removed first (clean_identifier_values, as in GAMGUI 2.93).
    values = clean_identifier_values(task, values, category)
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
# SECTION: Finding tasks - search box, Favorites and Recent (v0.6, as GAMGUI)
# =============================================================================

def is_identifier_field(category, task, field):
    # True for a box that holds an address / ID (cleaned before building).
    if field["key"] in NEVER_CLEAN_KEYS or field.get("choices") is not None:
        return False
    return field["key"] in IDENTIFIER_KEYS or bool(picker_kind(category, task, field))

def _clean_item(item):
    # The spaces before an item stay (they follow a comma), but not a
    # non-breaking space (chr 0xA0) - that is pasted junk wherever it sits.
    lead = item[:len(item) - len(item.lstrip())].replace(chr(0xa0), "")
    core = item.strip().replace("\u00a0", " ").strip()
    while len(core) >= 2 and core[0] in _WRAP_QUOTES and core[-1] in _WRAP_QUOTES:
        core = core[1:-1].strip()
    return lead + core

def clean_identifier(value):
    # Drops invisible zero-width characters anywhere; then, for each comma-
    # separated item, non-breaking spaces at its ends and quotes (straight or
    # curly) wrapped around the whole item. Separators and inner text stay.
    text = _ZERO_WIDTH.sub("", str(value or ""))
    return re.sub(r"[^,]+", lambda m: _clean_item(m.group(0)), text)

def clean_identifier_values(task, values, category=""):
    # The form's values with every identifier box cleaned (see above).
    out = dict(values)
    for field in (task or {}).get("fields", []):
        key = field["key"]
        if key in out and isinstance(out[key], str) and is_identifier_field(category, task, field):
            out[key] = clean_identifier(out[key])
    return out

# ---- "Save results to" (v0.6, as GAMGUI's Screen / CSV file choice) ----------
SAVE_CHOICES = ["Screen", "CSV file", "JSON file"]
SAVE_FORMATS = {"CSV file": "csv", "JSON file": "json"}

def saves_output(task):
    # A task that prints a list or details ('--output text' in its
    # template) can send them to a file instead.
    return not task.get("workflow") and "--output text" in task.get("template", "")

def with_output_format(argv, fmt):
    # The same command with its --output value changed (added if missing);
    # the CLI itself writes the CSV / JSON (m365 global option --output).
    argv = list(argv)
    for i, arg in enumerate(argv[:-1]):
        if arg in ("--output", "-o"):
            argv[i + 1] = fmt
            return argv
    return argv + ["--output", fmt]

def dropdown_start(field):
    # What a dropdown starts on (GAMGUI 2.91's rule): its default when that
    # is one of the choices, else the first choice.
    choices = field.get("choices") or []
    default = field.get("default") or ""
    return default if default in choices else (choices[0] if choices else default)

# ---- "Run for each CSV row" (v0.6, as GAMGUI's bulk runs) ---------------------
# The m365 CLI has no CSV loop (GAM has 'gam csv'), so M365GUI runs the task
# once per row itself. Each form box takes its value from a CSV column or
# from the form.
FORM_VALUE = "(the value in the form)"

def bulk_available(task):
    # Ordinary command tasks with at least one box; not the guided workflows.
    return bool(task.get("template")) and not task.get("workflow") and bool(task.get("fields"))

def bulk_guess_column(field, headers):
    # The column a box most likely reads from: its key, or a column named
    # like it (userPrincipalName for a UPN box...). FORM_VALUE when unsure.
    lowered = {h.lower(): h for h in headers}
    wanted = [field["key"].lower()]
    if field["key"] in USER_PICK_KEYS:
        wanted += ["userprincipalname", "upn", "email", "mail", "user"]
    if field["key"] in ("name", "team", "group"):
        wanted += ["displayname", "groupname", "group", "name"]
    if field["key"] == "id":
        wanted += ["id", "objectid"]
    for w in wanted:
        if w in lowered:
            return lowered[w]
    return FORM_VALUE

def bulk_plan(task, category, form_values, mapping, rows):
    # One entry per CSV row: (row number, argv, error). mapping[key] is a
    # column name or FORM_VALUE. Row numbers count the header as row 1, as
    # a spreadsheet shows them.
    plan = []
    for number, row in enumerate(rows, start=2):
        values = dict(form_values)
        for key, column in mapping.items():
            if column != FORM_VALUE:
                values[key] = (row.get(column) or "").strip()
        _display, argv, err = build_command(task, values, category)
        plan.append((number, argv, err))
    return plan

# ---- "Save as script" (v0.6, as GAMGUI) ---------------------------------------
# PowerShell (.ps1) and bash (.sh) only: both can quote ANY value safely
# (single quotes). A .bat would go through cmd.exe, which treats & | < > ^ %
# inside a value as commands - the problem M365GUI 0.4 removed.

def ps_quote(arg):
    # PowerShell single-quoted string: nothing inside is special except ',
    # which is doubled.
    return "'" + str(arg).replace("'", "''") + "'"

def sh_quote(arg):
    # bash single-quoted string; a ' is closed, escaped and reopened.
    return "'" + str(arg).replace("'", "'\\''") + "'"

def script_text(argv, kind, task_name, app_version, date_text):
    # The whole script for one m365 command. kind: "ps1" or "sh".
    title = (task_name or "Custom command").replace("\r", " ").replace("\n", " ")
    if kind == "ps1":
        # Windows PowerShell 5.1 drops a double quote INSIDE a value it hands
        # to a program (checked 10-23-2026: 'a "HQ"' arrived as 'a HQ');
        # PowerShell 7.3+ passes values exactly when told to ('Standard').
        # So the script refuses to run such a value under 5.1 instead of
        # silently changing it.
        return ("# %s - saved from M365GUI %s on %s\r\n"
                "# Runs one CLI for Microsoft 365 command. Needs m365 installed and signed in\r\n"
                "# ('m365 login'). Run: powershell -ExecutionPolicy Bypass -File <this file>\r\n"
                "$ErrorActionPreference = 'Stop'\r\n"
                "$arguments = @(%s)\r\n"
                "if ($PSVersionTable.PSVersion -lt [version]'7.3' -and ($arguments -match '\"')) {\r\n"
                "    Write-Error ('A value contains a double quote, which Windows PowerShell 5.1 cannot pass ' +\r\n"
                "                 'to m365 unchanged. Run this script with PowerShell 7 (pwsh) instead.')\r\n"
                "    exit 1\r\n"
                "}\r\n"
                "$PSNativeCommandArgumentPassing = 'Standard'\r\n"
                "& m365 @arguments\r\n"
                "if ($LASTEXITCODE -ne 0) { Write-Error ('m365 failed with exit code ' + $LASTEXITCODE); exit $LASTEXITCODE }\r\n"
                % (title, app_version, date_text, ", ".join(ps_quote(a) for a in argv)))
    return ("#!/usr/bin/env bash\n"
            "# %s - saved from M365GUI %s on %s\n"
            "# Runs one CLI for Microsoft 365 command. Needs m365 installed and signed in\n"
            "# ('m365 login'). Run: bash <this file>\n"
            "set -euo pipefail\n"
            "m365 %s\n" % (title, app_version, date_text, " ".join(sh_quote(a) for a in argv)))

def task_key(category, name):
    # How Favorites / Recent remember a task: "<section>|<task name>".
    return category + "|" + name

def find_task(key):
    # (category, index) of a remembered task, or None if it no longer exists
    # (renamed or removed in a newer version - then it is quietly dropped).
    category, _sep, name = (key or "").partition("|")
    for index, task in enumerate(TASKS.get(category, [])):
        if task["name"] == name:
            return category, index
    return None

def task_matches(category, task, needle):
    # The search box rule (GAMGUI's): every WORD typed must appear somewhere
    # in the section name, the task name or its description, any case.
    if not needle.strip():
        return True
    text = (category + " " + task["name"] + " " + task["desc"]).lower()
    return all(word in text for word in needle.lower().split())


# =============================================================================
# SECTION: Pick... lists for users and groups (v0.6, as GAMGUI)
#   'entra user list' turns any extra --<property> <text> option into a Graph
#   "starts with" filter (CLI v11.11 user-list.js / its docs), so the user
#   list is searched on the server - a tenant can have thousands of users.
#   'entra group list' has no such filter: groups are loaded once and
#   searched here.
# =============================================================================

USER_PICK_KEYS = {"email", "from", "to"}         # boxes that take a user's UPN

# Pasted look-alike characters (v0.6, from GAMGUI 2.93 - GAM issue #1623): an
# address or ID pasted from Word, Outlook or a web page often carries curly
# quotes or an invisible zero-width space, and Microsoft 365 then answers
# "does not exist" for an account that does exist. Only ADDRESS / ID boxes
# are cleaned; passwords, names and descriptions keep every character. The
# preview shows the cleaned command.
IDENTIFIER_KEYS = {"email", "from", "to", "id", "ids", "skuId", "team", "url", "loc"}
NEVER_CLEAN_KEYS = {"password", "display", "first", "last", "desc", "folder", "nick"}
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WRAP_QUOTES = "\"'\u201c\u201d\u201e\u2018\u2019\u201a\u00ab\u00bb"

def picker_kind(category, task, field):
    # "user", "group" or None - which Pick... list a form box gets. A
    # 'Create ...' task names something NEW, so it gets no list.
    if field.get("choices") is not None or task["name"].startswith("Create"):
        return None
    if field["key"] in USER_PICK_KEYS:
        return "user"
    if field["key"] == "team" or (category == "Groups (Entra)" and field["key"] == "name"):
        return "group"
    return None

def user_search_commands(text):
    # The m365 commands that find users whose display name OR sign-in name
    # starts with what was typed (two Graph filters; results are merged).
    text = (text or "").strip()
    if not text:
        return []
    props = ["--properties", "displayName,userPrincipalName", "--output", "json"]
    return [["entra", "user", "list", "--displayName", text] + props,
            ["entra", "user", "list", "--userPrincipalName", text] + props]

def people_choices(lists):
    # Several 'entra user list' JSON results -> sorted, de-duplicated
    # [(label, upn)] for the list box.
    seen, out = set(), []
    for items in lists:
        for item in items or []:
            upn = (item or {}).get("userPrincipalName")
            if upn and upn.lower() not in seen:
                seen.add(upn.lower())
                out.append(("%s  <%s>" % (item.get("displayName") or upn, upn), upn))
    return sorted(out, key=lambda pair: pair[0].lower())

GROUP_LIST_COMMAND = ["entra", "group", "list", "--properties", "displayName,mail",
                      "--output", "json"]

def group_choices(groups, text):
    # All groups -> [(label, display name)] whose name or address CONTAINS
    # every word typed (blank = all).
    words = (text or "").lower().split()
    out = []
    for g in groups or []:
        name = (g or {}).get("displayName") or ""
        label = name + ("  <%s>" % g["mail"] if g.get("mail") else "")
        if name and all(w in label.lower() for w in words):
            out.append((label, name))
    return sorted(out, key=lambda pair: pair[0].lower())
