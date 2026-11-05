# =============================================================================
# Script:   m365_workflows.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  10-23-2026 (moved out of M365GUI.py, v0.6)
# Modified: 11-02-2026 (v0.16: Power Automate flows and Power Apps review - read-only)
#
# Purpose:
#   M365GUI's guided workflows - tasks that run several m365 commands in a
#   row with checks in between (like GAMGUI's gam_workflows.py). Each one
#   takes run / out / confirm / cancelled functions, so the window (and
#   the tests, with a fake m365) can drive it.
# =============================================================================

import csv
import datetime
import json
import os
import urllib.parse

from m365_catalog import (SHARE_ANYONE, TRANSFER_ACCESS_KEEP, TRANSFER_ACCESS_REMOVE,
                          POWER_DETAILS_FULL, clean_identifier)

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
    # v0.6: pasted curly quotes / invisible characters removed (as the forms do).
    src_upn = clean_identifier(values.get("from") or "").strip()
    dst_upn = clean_identifier(values.get("to") or "").strip()
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
# SECTION: shared pieces of the guided workflows (v0.8)
# =============================================================================

YES, NO = "Yes", "No"

def _record_dir(base, kind, upn):
    # A new folder for one run's records: <base>/<kind>_<name>_<MM-DD-YYYY_HH-MM-SS>.
    stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
    name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in upn.split("@")[0])
    folder = os.path.join(base, "%s_%s_%s" % (kind, name, stamp))
    os.makedirs(folder, exist_ok=True)
    return folder

def _save(folder, name, text, out):
    # One evidence / record file; a failure is reported, never raised.
    try:
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="") as h:
            h.write(text)
        return True
    except OSError as exc:
        out("Could not save %s: %s\n" % (name, exc))
        return False

def _check_upn(label, upn):
    if "@" not in upn or " " in upn:
        return "The %s box needs a sign-in name (UPN) such as jdoe@contoso.com." % label
    return ""

class _Steps:
    # Runs one m365 command as a named step, shows OK / FAILED and keeps a
    # row for steps.csv. A failed step never stops the rest.
    def __init__(self, run, out):
        self.run, self.out, self.rows = run, out, [["step", "result", "detail"]]

    def do(self, label, argv, hide=()):
        rc, text = self.run(argv)
        detail = " ".join(text.split())[:300]
        for secret in hide:                     # never write a password anywhere
            detail = detail.replace(secret, "********")
        self.rows.append([label, "OK" if rc == 0 else "FAILED", detail if rc else ""])
        self.out(("  OK      %s\n" % label) if rc == 0 else
                 ("  FAILED  %s - %s\n" % (label, detail)))
        return rc, text

    def note(self, label, result, detail=""):
        self.rows.append([label, result, detail])

    def csv_text(self):
        import io
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(self.rows)
        return buf.getvalue()

# =============================================================================
# SECTION: Move a user's OneDrive files to a Team / SharePoint site (v0.15,
#   10-29-2026) - the Microsoft counterpart of GAMGUI's Move to Shared Drive.
#   A Team's files live in its SharePoint site's document library, so the
#   files MOVE there (they leave the OneDrive), into a new folder. Before
#   anything moves: a record of every item that has its OWN permissions
#   (who and what level - 'spo listitem get --withPermissions'), because
#   sharing does not carry over to another site, and one question. Built
#   from commands checked read-only on 10-29-2026: the Team -> site match
#   (spo site list GroupId '/Guid(<id>)/' = the Team id; Graph
#   groups/{id}/sites/root and 'm365group get --withSiteUrl' were refused),
#   'spo listitem list --fields FileRef,FSObjType,HasUniqueRoleAssignments'
#   (6,455 items in 36 s), the library root folder via 'spo list list
#   --properties Title,RootFolder/ServerRelativeUrl'. The MOVE itself
#   ('spo folder|file move' to an absolute URL on another host) still needs
#   its live test on throwaway accounts.
# =============================================================================

MOVE_DEFAULT_LIBRARY = "Documents"   # a Team site's library (its folder is 'Shared Documents')

def _guid(value):
    # SharePoint shows a group id as '/Guid(<id>)/'; Teams as plain '<id>'.
    text = (value or "").strip().lower()
    if text.startswith("/guid(") and text.endswith(")/"):
        text = text[6:-2]
    return text

def _find_team_site(run, team_name):
    # (site URL, error) for a Team's display name.
    rc, text = run(["teams", "team", "list", "--output", "json"])
    teams = parse_json(text) if rc == 0 else None
    if not isinstance(teams, list):
        return "", "Could not list the Teams: " + " ".join((text or "").split())[:300]
    found = [t for t in teams if (t.get("displayName") or "").strip().lower() == team_name.lower()]
    if not found:
        return "", "No Team is called '%s'." % team_name
    if len(found) > 1:
        return "", ("%d Teams are called '%s' - type the site address in the Site URL box "
                    "instead." % (len(found), team_name))
    rc, text = run(["spo", "site", "list", "--output", "json"])
    sites = parse_json(text) if rc == 0 else None
    if not isinstance(sites, list):
        return "", "Could not list the SharePoint sites: " + " ".join((text or "").split())[:300]
    for s in sites:
        if _guid(s.get("GroupId")) == (found[0].get("id") or "").lower() and s.get("Url"):
            return s["Url"].rstrip("/"), ""
    return "", "Could not find the SharePoint site of the Team '%s'." % team_name

def _find_library(run, site, library):
    # The server-relative folder of a document library, found by its title
    # or the last part of its address. (folder, error).
    rc, text = run(["spo", "list", "list", "--webUrl", site, "--filter",
                    "BaseTemplate eq 101 and Hidden eq false", "--properties",
                    "Title,RootFolder/ServerRelativeUrl", "--output", "json"])
    libs = parse_json(text) if rc == 0 else None
    if not isinstance(libs, list):
        return "", "Could not list the libraries of %s: %s" % (site, " ".join((text or "").split())[:300])
    want = library.strip().strip("/").lower()
    for lib in libs:
        root = ((lib.get("RootFolder") or {}).get("ServerRelativeUrl") or "").rstrip("/")
        if want in ((lib.get("Title") or "").lower(), root.split("/")[-1].lower()):
            return root, ""
    names = ", ".join(sorted(l.get("Title") or "?" for l in libs))
    return "", "%s has no library called '%s' (it has: %s)." % (site, library, names or "none")

def _permission_rows(run, web, item):
    # CSV rows for one item that has its own permissions: who and what level.
    rc, text = run(["spo", "listitem", "get", "--webUrl", web, "--listTitle", "Documents", "--id",
                    str(item.get("Id")), "--withPermissions", "--output", "json"])
    data = parse_json(text) if rc == 0 else None
    path = item.get("FileRef") or ""
    kind = "folder" if str(item.get("FSObjType")) == "1" else "file"
    if not isinstance(data, dict):
        return [[path, kind, "COULD NOT READ", "", " ".join((text or "").split())[:200]]]
    rows = []
    for ra in data.get("RoleAssignments") or []:
        member = ra.get("Member") or {}
        levels = ", ".join(b.get("Name") or "" for b in ra.get("RoleDefinitionBindings") or [])
        rows.append([path, kind, member.get("Title") or "", member.get("LoginName") or "", levels])
    return rows or [[path, kind, "(nobody listed)", "", ""]]

def move_to_site(run, out, confirm, cancelled, values, records_base):
    # run / out / confirm / cancelled as in transfer_onedrive. Returns a
    # summary dict (ok, error, folder, moved, failed, src_files, dst_files).
    result = {"ok": False, "error": "", "folder": "", "moved": 0, "failed": 0,
              "src_files": 0, "dst_files": 0}
    src_upn = clean_identifier(values.get("from") or "").strip()
    team = (values.get("team") or "").strip()
    site = clean_identifier(values.get("url") or "").strip().rstrip("/")
    library = (values.get("library") or "").strip() or MOVE_DEFAULT_LIBRARY
    folder = (values.get("folder") or "").strip() or default_transfer_folder(src_upn)
    keep_access = values.get("access") == TRANSFER_ACCESS_KEEP

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    # ---- 1. check the boxes before running anything ----------------------------
    problem = _check_upn("From", src_upn)
    if problem:
        return stop(problem)
    if bool(team) == bool(site):
        return stop("Fill in EITHER the Team box OR the Site URL box (not both).")
    if site and not site.lower().startswith("https://"):
        return stop("The Site URL box needs a site address such as "
                    "https://contoso.sharepoint.com/sites/Team.")
    if BAD_FOLDER_CHARS & set(folder) or folder.endswith("."):
        return stop('The folder name cannot contain " * : < > ? / \\ | or end with a period.')

    out("\n===== MOVE ONEDRIVE FILES TO A SHARED LIBRARY: %s =====\n" % src_upn)
    rc, text = run(["status", "--output", "json"])
    operator = (parse_json(text) or {}).get("connectedAs", "") if rc == 0 else ""
    if not operator:
        return stop("m365 is not signed in. Run 'm365 login' first.")

    # ---- 2. the OneDrive and the destination ------------------------------------
    rc, text = run(["entra", "user", "get", "--userName", src_upn,
                    "--properties", "userPrincipalName,mySite", "--output", "json"])
    info = parse_json(text) if rc == 0 else None
    if not isinstance(info, dict):
        return stop("Could not find %s: %s" % (src_upn, text.strip()[:300]))
    if not info.get("mySite"):
        return stop("%s has no OneDrive - nothing to move." % src_upn)
    src_web, src_host, src_lib = onedrive_paths(info["mySite"])
    if team:
        site, err = _find_team_site(run, team)
        if err:
            return stop(err)
    dst_host = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(site))
    out("From: %s\nTo:   %s (library '%s')\n" % (src_web, site, library))

    records = _record_dir(records_base, "MoveToSite", src_upn)
    result["folder"] = records
    added = []                                    # sites where WE added access
    try:
        # ---- 3. access: site collection admin on both, for this run --------------
        for web in (src_web, site):
            rc, text = run(["spo", "site", "admin", "list", "--siteUrl", web, "--asAdmin",
                            "--output", "json"])
            admins = parse_json(text) if rc == 0 else None
            if not isinstance(admins, list):
                return stop("Could not read who can manage %s: %s\nMoving needs a SharePoint "
                            "administrator (or Global administrator) signed in to m365." %
                            (web, text.strip()[:300]))
            if not _is_site_admin(admins, operator):
                rc, text = run(["spo", "site", "admin", "add", "--siteUrl", web,
                                "--userName", operator, "--asAdmin", "--output", "json"])
                if rc != 0:
                    return stop("Could not give %s access to %s: %s" % (operator, web, text.strip()[:300]))
                added.append(web)
                out("Gave %s temporary access to %s\n" % (operator, web))

        dst_lib, err = _find_library(run, site, library)
        if err:
            return stop(err)

        # ---- 4. what is there, and who it is shared with ---------------------------
        hidden = src_lib + "/Forms"
        out("Listing %s's OneDrive - on a large OneDrive this can take a few minutes...\n" % src_upn)
        rc, text = run(["spo", "listitem", "list", "--webUrl", src_web, "--listTitle", "Documents",
                        # 'File/Length' (File_x0020_Size does not exist here - live 10-29-2026)
                        "--fields", "Id,FileRef,FSObjType,HasUniqueRoleAssignments,File/Length",
                        "--output", "json"])
        every = parse_json(text) if rc == 0 else None
        if not isinstance(every, list):
            return stop("Could not list %s's OneDrive: %s" % (src_upn, text.strip()[:300]))
        every = [i for i in every if not (i.get("FileRef") or "").startswith(hidden + "/")]
        files = [i for i in every if str(i.get("FSObjType")) != "1"]
        result["src_files"] = len(files)
        total = sum(int((i.get("File") or {}).get("Length") or 0) for i in files)
        top = [i for i in every if (i.get("FileRef") or "").rsplit("/", 1)[0] == src_lib
               and (i.get("FileRef") or "") != hidden]
        if not top:
            return stop("%s's OneDrive is empty - nothing to move." % src_upn)
        unique = [i for i in every if i.get("HasUniqueRoleAssignments")]
        out("Saving who has access to the %d item(s) shared on their own...\n" % len(unique))
        perm_rows = [["item", "type", "who", "sign-in name", "permission"]]
        for item in unique:
            if cancelled():
                return stop("[Stopped - nothing was moved.]")
            perm_rows.extend(_permission_rows(run, src_web, item))
        import io
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(perm_rows)
        if not _save(records, "sharing-before.csv", buf.getvalue(), out):
            return stop("Could not save the sharing record - nothing was moved.")

        question = ("MOVE %d files (%s) - %d top-level item(s)\nFROM %s's OneDrive\n"
                    "TO a new folder '%s' in %s (library '%s')?\n\nThe files will no longer be "
                    "in %s's OneDrive. %d item(s) were shared on their own - who had access is "
                    "saved in sharing-before.csv; check the sharing in the new place after the "
                    "move. Files with the same name are renamed, never overwritten."
                    % (len(files), size_text(total), len(top), src_upn, folder, site, library,
                       src_upn, len(unique)))
        out(question + "\n")
        if not confirm(question):
            return stop("Canceled - nothing was moved.")

        # ---- 5. the destination folder, then move each top-level item -----------
        rc, text = run(["spo", "folder", "add", "--webUrl", site, "--parentFolderUrl", dst_lib,
                        "--name", folder, "--output", "json"])
        made = parse_json(text) if rc == 0 else None
        if not isinstance(made, dict):
            return stop("Could not create the folder '%s' in %s: %s" % (folder, site, text.strip()[:300]))
        target_srv = made.get("ServerRelativeUrl") or (dst_lib + "/" + folder)
        target = dst_host + target_srv
        out("Moving into %s ...\n" % target)
        rows = [["type", "source", "result", "detail"]]
        for item in top:
            if cancelled():
                out("[Stopped - the rest was not moved.]\n")
                break
            kind = "folder" if str(item.get("FSObjType")) == "1" else "file"
            source = item["FileRef"]
            argv = ["spo", kind, "move", "--webUrl", src_web, "--sourceUrl", source,
                    "--targetUrl", target, "--nameConflictBehavior", "rename"]
            if kind == "file":
                argv.append("--bypassSharedLock")   # a file left open still moves
            rc, text = run(argv + ["--output", "json"])
            name = source[len(src_lib) + 1:]
            if rc == 0:
                result["moved"] += 1
                out("  OK      %s %s\n" % (kind, name))
                rows.append([kind, source, "moved", ""])
            else:
                result["failed"] += 1
                detail = " ".join(text.split())[:200]
                out("  FAILED  %s %s - %s\n" % (kind, name, detail))
                rows.append([kind, source, "FAILED", detail])
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        _save(records, "moved.csv", buf.getvalue(), out)

        # ---- 6. check: the files in the new folder, and what is left ---------------
        out("Counting the files that arrived...\n")
        rc, text = run(["spo", "file", "list", "--webUrl", site, "--folderUrl", target_srv,
                        "--recursive", "--fields", "Name,ServerRelativeUrl,Length", "--output", "json"])
        landed = parse_json(text) if rc == 0 else None
        if isinstance(landed, list):
            result["dst_files"] = len(landed)
            out("Check: %d of %d files are in the new folder.\n" % (len(landed), len(files)))
            if len(landed) < len(files):
                out("WARNING: some files did not arrive - see FAILED lines above; what was not "
                    "moved is still in %s's OneDrive.\n" % src_upn)
        else:
            out("Could not count the moved files: %s\n" % text.strip()[:300])
        result["ok"] = (result["failed"] == 0 and not cancelled()
                        and result["dst_files"] >= len(files))
        out("\n===== DONE: %d moved, %d failed. Records: %s =====\n"
            % (result["moved"], result["failed"], records))
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
# SECTION: Staff hand-off - someone is leaving (v0.8, like GAMGUI's hand-off)
#   Order matters: a record of what they had FIRST, then lock the account,
#   copy their files while the license (and so the OneDrive) still exists,
#   and only then take groups / licenses away - each step chosen on the
#   form. A record folder keeps what was there before and what was done.
# =============================================================================

def staff_handoff(run, out, confirm, cancelled, values, records_base):
    result = {"ok": False, "error": "", "folder": ""}
    leaver = clean_identifier(values.get("leaver") or "").strip()
    manager = clean_identifier(values.get("manager") or "").strip()
    pick = {k: values.get(k) == YES for k in
            ("block", "signout", "copy", "autoreply", "groups", "licenses")}
    reply = (values.get("reply") or "").strip()

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    problem = _check_upn("leaver", leaver)
    if not problem and (pick["copy"] or manager):
        problem = _check_upn("manager", manager)
    if problem:
        return stop(problem)
    if manager and manager.lower() == leaver.lower():
        return stop("The leaver and the manager are the same person.")
    if pick["autoreply"] and not reply:
        return stop("Type the automatic reply message, or set 'Set an automatic reply' to No.")
    if not any(pick.values()):
        return stop("Nothing to do - choose Yes for at least one step.")

    chosen = [label for key, label in (
        ("block", "block sign-in"), ("signout", "sign them out everywhere"),
        ("copy", "copy their OneDrive files to " + (manager or "the manager")),
        ("autoreply", "set an automatic reply"), ("groups", "remove them from every group"),
        ("licenses", "REMOVE THEIR LICENSES (their mailbox is deleted 30 days later)"))
        if pick[key]]
    question = ("Staff hand-off for %s:\n\n- %s\n\nA record of their groups and licenses is "
                "saved first. Go ahead?" % (leaver, "\n- ".join(chosen)))
    out("\n===== STAFF HAND-OFF: %s =====\n" % leaver)
    rc, text = run(["entra", "user", "get", "--userName", leaver, "--withManager",
                    "--output", "json"])
    user = parse_json(text) if rc == 0 else None
    if not isinstance(user, dict):
        return stop("Could not find %s: %s" % (leaver, text.strip()[:300]))
    if not confirm(question):
        return stop("Canceled - nothing was changed.")

    folder = _record_dir(records_base, "Handoff", leaver)
    result["folder"] = folder
    steps = _Steps(run, out)
    # ---- 1. the record: who they are, their groups and licenses -------------
    _save(folder, "user.json", json.dumps(user, indent=2), out)
    rc, text = run(["entra", "user", "groupmembership", "list", "--userName", leaver,
                    "--output", "json"])
    groups = parse_json(text) if rc == 0 else None
    groups = groups if isinstance(groups, list) else []
    _save(folder, "groups-before.json", json.dumps(groups, indent=2), out)
    rc, text = run(["entra", "user", "license", "list", "--userName", leaver, "--output", "json"])
    licenses = parse_json(text) if rc == 0 else None
    licenses = licenses if isinstance(licenses, list) else []
    _save(folder, "licenses-before.json", json.dumps(licenses, indent=2), out)
    out("Record saved: %d group(s), %d license(s) -> %s\n" % (len(groups), len(licenses), folder))

    # ---- 2. lock the account -------------------------------------------------
    if pick["block"] and not cancelled():
        steps.do("Block sign-in", ["entra", "user", "set", "--userName", leaver,
                                   "--accountEnabled", "false"])
    if pick["signout"] and not cancelled():
        steps.do("Sign out everywhere", ["entra", "user", "session", "revoke",
                                         "--userName", leaver, "--force"])
    # ---- 3. files, while the license still exists ------------------------------
    if pick["copy"] and not cancelled():
        out("\n--- Copy OneDrive files to %s ---\n" % manager)
        copy = transfer_onedrive(run, out, confirm, cancelled,
                                 {"from": leaver, "to": manager, "folder": "",
                                  "access": TRANSFER_ACCESS_REMOVE},
                                 os.path.join(folder, "onedrive-copy.csv"))
        steps.note("Copy OneDrive files", "OK" if copy["ok"] else "FAILED",
                   copy.get("error") or "%d copied, %d failed" % (copy["copied"], copy["failed"]))
    if pick["autoreply"] and not cancelled():
        rc, text = steps.do("Set an automatic reply",
                            ["outlook", "mailbox", "settings", "set", "--userName", leaver,
                             "--autoReplyStatus", "alwaysEnabled", "--autoReplyInternalMessage",
                             reply, "--autoReplyExternalMessage", reply,
                             "--autoReplyExternalAudience", "all"])
        if rc and "app-only" in (text or ""):
            # Live 11-02-2026: signed in as yourself, the CLI cannot change
            # another person's mailbox settings.
            out("          Signed in as yourself, Microsoft lets you set only your own "
                "automatic reply. Set it in the Exchange admin center on their mailbox "
                "(the other steps are not affected).\n")
    # ---- 4. take access away -----------------------------------------------------
    if pick["groups"] and not cancelled():
        for g in groups:
            if cancelled():
                break
            if (g.get("@odata.type") or "#microsoft.graph.group") != "#microsoft.graph.group" \
                    or not g.get("id"):
                continue                     # directory roles etc. are not groups
            steps.do("Remove from group %s" % (g.get("displayName") or g["id"]),
                     ["entra", "group", "member", "remove", "--groupId", g["id"],
                      "--userNames", leaver, "--force"])
    if pick["licenses"] and not cancelled():
        ids = [l.get("skuId") for l in licenses if l.get("skuId")]
        if ids:
            steps.do("Remove %d license(s)" % len(ids),
                     ["entra", "user", "license", "remove", "--userName", leaver,
                      "--ids", ",".join(ids), "--force"])
        else:
            steps.note("Remove licenses", "OK", "they had none")
    if cancelled():
        out("[Stopped - the remaining steps were not run.]\n")
        steps.note("Stopped", "STOPPED", "the remaining steps were not run")
    _save(folder, "steps.csv", steps.csv_text(), out)
    failed = sum(1 for r in steps.rows[1:] if r[1] != "OK")
    result["ok"] = failed == 0 and not cancelled()
    out("\n===== DONE: %d step(s), %d not OK. Record: %s =====\n"
        % (len(steps.rows) - 1, failed, folder))
    return result

# =============================================================================
# SECTION: Compromised account response (v0.8, like GAMGUI's)
#   Contain first (block, sign out, new password), then save evidence. The
#   new password is shown ONCE through show_secret - never in the output
#   window or any log file.
# =============================================================================

COMPROMISED_NEXT_STEPS = """STEPS M365GUI CANNOT DO - DO THESE NEXT

1. Talk to the user in person or by phone - not by email (the attacker may
   still be reading it).
2. Exchange admin center > the mailbox: look for inbox rules that forward,
   delete or move mail, and for forwarding (SMTP forwarding, delegates).
   Remove anything the user did not set up.
3. Entra admin center > the user > Authentication methods: remove any phone
   number, authenticator app or security key the user does not recognize.
   Then have them register MFA again.
4. Check what was sent: Exchange message trace / the Sent Items folder, for
   phishing sent to others in the organization. Warn the recipients.
5. Entra admin center > Enterprise applications > User consent: remove apps
   the user consented to that they do not recognize.
6. Look at the saved sign-ins (signins.json): note the IP addresses and
   countries that were not the user; block them in Conditional Access if
   they are attackers.
7. When the account is clean: unblock sign-in (Users > Unblock sign-in) and
   give the user the new password in person.
8. Keep this folder as the incident record.
"""

def compromised_response(run, out, confirm, cancelled, values, records_base, show_secret,
                         make_password):
    result = {"ok": False, "error": "", "folder": ""}
    upn = clean_identifier(values.get("email") or "").strip()
    pick = {k: values.get(k) == YES for k in ("block", "signout", "password")}

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    problem = _check_upn("user", upn)
    if problem:
        return stop(problem)
    chosen = [label for key, label in (("block", "block sign-in"),
                                       ("signout", "sign them out everywhere"),
                                       ("password", "set a new random password"))
              if pick[key]]
    question = ("Compromised account response for %s:\n\n- %s\n- save evidence (sign-ins, MFA "
                "methods, groups, licenses)\n\nGo ahead?" % (upn, "\n- ".join(chosen) or "(no changes)"))
    out("\n===== COMPROMISED ACCOUNT: %s =====\n" % upn)
    rc, text = run(["entra", "user", "get", "--userName", upn, "--withManager", "--output", "json"])
    user = parse_json(text) if rc == 0 else None
    if not isinstance(user, dict):
        return stop("Could not find %s: %s" % (upn, text.strip()[:300]))
    if not confirm(question):
        return stop("Canceled - nothing was changed.")
    folder = _record_dir(records_base, "Compromised", upn)
    result["folder"] = folder
    steps = _Steps(run, out)
    # ---- 1. contain ------------------------------------------------------------
    if pick["block"] and not cancelled():
        steps.do("Block sign-in", ["entra", "user", "set", "--userName", upn, "--accountEnabled", "false"])
    if pick["signout"] and not cancelled():
        steps.do("Sign out everywhere", ["entra", "user", "session", "revoke", "--userName", upn, "--force"])
    if pick["password"] and not cancelled():
        password = make_password()
        rc, _text = steps.do("Set a new random password",
                             ["entra", "user", "set", "--userName", upn, "--resetPassword",
                              "--newPassword", password, "--forceChangePasswordNextSignIn"],
                             hide=(password,))
        if rc == 0:
            show_secret("New password for %s (shown only now - it is not saved anywhere):"
                        % upn, password)
    # ---- 2. evidence ----------------------------------------------------------------
    out("Saving evidence...\n")
    _save(folder, "user.json", json.dumps(user, indent=2), out)
    for name, argv in (
            ("signins.json", ["entra", "user", "signin", "list", "--userName", upn, "--output", "json"]),
            ("mfa-methods.json", ["entra", "user", "registrationdetails", "list",
                                  "--userPrincipalNames", upn, "--output", "json"]),
            ("groups.json", ["entra", "user", "groupmembership", "list", "--userName", upn,
                             "--output", "json"]),
            ("licenses.json", ["entra", "user", "license", "list", "--userName", upn,
                               "--output", "json"])):
        if cancelled():
            break
        rc, text = steps.do("Evidence: " + name, argv)
        _save(folder, name, text if rc == 0 else json.dumps({"error": text.strip()[:2000]}), out)
    _save(folder, "NEXT-STEPS.txt", COMPROMISED_NEXT_STEPS, out)
    _save(folder, "steps.csv", steps.csv_text(), out)
    out("\n" + COMPROMISED_NEXT_STEPS + "\n")
    failed = sum(1 for r in steps.rows[1:] if r[1] != "OK")
    result["ok"] = failed == 0 and not cancelled()
    out("===== DONE: %d step(s), %d not OK. Evidence: %s =====\n"
        % (len(steps.rows) - 1, failed, folder))
    return result

# =============================================================================
# SECTION: Remove ALL guest users (v0.2; moved here from the window in v0.9 so
#   the browser version runs the same steps). confirm_delete(summary) must
#   only return True when the person TYPED the word DELETE.
# =============================================================================

def remove_all_guests(run, out, confirm_delete, cancelled):
    result = {"ok": False, "removed": 0, "found": 0}
    out("\n===== REMOVE ALL GUEST USERS =====\nStep 1: finding guest accounts...\n")
    rc, text = run(["entra", "user", "list", "--type", "Guest",
                    "--properties", "id,displayName,userPrincipalName", "--output", "json"])
    if rc != 0:
        out("Could not list guests (rc=%d):\n%s\n" % (rc, text))
        return result
    guests = parse_json(text) if text.strip() else []
    if not isinstance(guests, list):
        out("Could not read the guest list. Raw output:\n" + text + "\n")
        return result
    result["found"] = len(guests)
    if not guests:
        out("No guest accounts found. Nothing to do.\n")
        result["ok"] = True
        return result
    for g in guests:
        out("  - %s (%s)\n" % (g.get("displayName", "?"), g.get("userPrincipalName", "?")))
    if not confirm_delete(str(len(guests)) + " guest account(s) will be DELETED (recoverable 30 days)."):
        out("\n[canceled - nothing deleted]\n")
        return result
    out("\nStep 2: removing...\n")
    for g in guests:
        if cancelled():
            out("[stopped by user]\n")
            break
        gid = g.get("id")
        rc, text = run(["entra", "user", "remove", "--id", gid, "--force"])
        out("  %s %s %s\n" % ("OK" if rc == 0 else "FAILED (rc=%d)" % rc,
                              g.get("userPrincipalName", gid), "" if rc == 0 else text.strip()[:80]))
        if rc == 0:
            result["removed"] += 1
    out("\n===== DONE: removed %d of %d =====\n" % (result["removed"], len(guests)))
    result["ok"] = result["removed"] == len(guests)
    return result

# =============================================================================
# SECTION: Who holds admin roles (v0.13, 10-28-2026) - read-only.
#   'entra pim role assignment list' needs Microsoft Entra ID P2, so this
#   reads Microsoft Graph through 'm365 request' instead (works on every
#   tenant, checked live 10-28-2026):
#     roleManagement/directory/roleAssignments?$expand=principal
#   (only ONE $expand is allowed there - adding roleDefinition answers 400),
#   then the role names from roleDefinitions. A few built-in roles (e.g.
#   'Email Verified User Creator') are missing from that list but can be
#   read one at a time by id. 'm365 request' does not follow
#   @odata.nextLink, so every list is paged here. Changes nothing.
# =============================================================================

GRAPH_ROLES = "https://graph.microsoft.com/v1.0/roleManagement/directory/"
ROLES_GLOBAL_ADMIN = "Global Administrator"
ROLES_MANY = 10         # an account with this many roles or more is pointed out
ROLES_MAX_PAGES = 200   # a guard: never page forever if Graph keeps answering

def _graph_pages(run, url, cancelled):
    # Every item of a Graph list, following @odata.nextLink.
    # Returns (items, error text or "").
    items, pages = [], 0
    while url and not cancelled():
        pages += 1
        if pages > ROLES_MAX_PAGES:
            return items, "stopped after %d pages" % ROLES_MAX_PAGES
        rc, text = run(["request", "--url", url, "--output", "json"])
        data = parse_json(text) if rc == 0 else None
        if not isinstance(data, dict):
            return items, " ".join((text or "").split())[:300] or "no answer"
        items.extend(v for v in data.get("value") or [] if isinstance(v, dict))
        url = data.get("@odata.nextLink") or ""
    return items, ""

def _principal_row(principal):
    # (kind, display name, sign-in name / app id, enabled text) of the
    # account, group or app that holds a role.
    p = principal or {}
    kind = (p.get("@odata.type") or "").replace("#microsoft.graph.", "") or "unknown"
    kinds = {"user": "user", "servicePrincipal": "app", "group": "group"}
    ident = p.get("userPrincipalName") or p.get("appId") or p.get("mail") or p.get("id") or ""
    enabled = p.get("accountEnabled")
    return (kinds.get(kind, kind), p.get("displayName") or ident or "(unknown)", ident,
            "" if enabled is None else ("yes" if enabled else "NO"))

MFA_BATCH = 20          # 'registrationdetails list --userIds' takes at most 20 ids

def _mfa_status(run, user_ids, cancelled):
    # v0.14: {user object id: (registered True/False, "method, method")} for the
    # role holders, read 20 at a time with 'entra user registrationdetails list'
    # (Graph's userRegistrationDetails - needs AuditLog.Read.All and, per
    # Microsoft, Entra ID P1 or P2; checked live 10-29-2026). Returns
    # (dict, error text or "").
    found = {}
    for i in range(0, len(user_ids), MFA_BATCH):
        if cancelled():
            break
        rc, text = run(["entra", "user", "registrationdetails", "list", "--userIds",
                        ",".join(user_ids[i:i + MFA_BATCH]), "--properties",
                        "id,isMfaRegistered,methodsRegistered", "--output", "json"])
        data = parse_json(text) if rc == 0 else None
        if not isinstance(data, list):
            return found, " ".join((text or "").split())[:300] or "no answer"
        for d in data:
            if isinstance(d, dict) and d.get("id"):
                found[d["id"]] = (bool(d.get("isMfaRegistered")),
                                  ", ".join(d.get("methodsRegistered") or []))
    return found, ""

ROLES_IDLE_DAYS = 90     # default: point out people idle this long
ROLES_GRAPH_USERS = "https://graph.microsoft.com/v1.0/users/"

def _signin_date(activity):
    # The newest sign-in Microsoft recorded (successful first, else the
    # newest interactive / non-interactive one) as a date, or None.
    a = activity or {}
    when = a.get("lastSuccessfulSignInDateTime") or max(
        [x for x in (a.get("lastSignInDateTime"), a.get("lastNonInteractiveSignInDateTime")) if x] or [""])
    try:
        return datetime.datetime.strptime(when[:10], "%Y-%m-%d").date() if when else None
    except ValueError:
        return None

def _last_signins(run, user_ids, cancelled):
    # v0.14: {user object id: date or None} from Graph users/{id}?$select=
    # signInActivity (needs AuditLog.Read.All and Entra ID P1 or P2; checked
    # live 10-29-2026). If the FIRST read fails it is almost always a missing
    # permission, so the reads stop; a later failure skips only that account
    # (live: one account answered an empty body while eight others read
    # fine). Returns (dict, error text or "").
    found, skipped = {}, 0
    for uid in user_ids:
        if cancelled():
            break
        rc, text = run(["request", "--url", ROLES_GRAPH_USERS + uid + "?$select=signInActivity",
                        "--output", "json"])
        one = parse_json(text) if rc == 0 else None
        if not isinstance(one, dict) or "error" in one:
            if not found and not skipped:
                return found, " ".join((text or "").split())[:300] or "no answer"
            skipped += 1
            continue
        found[uid] = _signin_date(one.get("signInActivity"))
    return found, ("%d account(s) gave no answer - their last sign-in is left blank" % skipped
                   if skipped else "")

def admin_roles(run, out, cancelled, values, records_base):
    result = {"ok": False, "error": "", "folder": "", "assignments": 0}
    try:
        idle_days = max(1, min(3650, int(str(values.get("days") or ROLES_IDLE_DAYS).strip())))
    except ValueError:
        idle_days = ROLES_IDLE_DAYS
    with_apps = values.get("apps", YES) == YES

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    out("\n===== WHO HOLDS ADMIN ROLES =====\nReading role assignments...\n")
    assignments, err = _graph_pages(run, GRAPH_ROLES + "roleAssignments?$expand=principal",
                                    cancelled)
    if err:
        return stop("Could not read the role assignments: " + err +
                    "\n(The signed-in account needs RoleManagement.Read.Directory or "
                    "Directory.Read.All.)")
    if cancelled():
        return stop("[Stopped.]")
    out("Reading role names...\n")
    defs, err = _graph_pages(run, GRAPH_ROLES + "roleDefinitions?$select=id,displayName",
                             cancelled)
    names = {d.get("id"): d.get("displayName") for d in defs if d.get("id")}
    for rid in sorted({a.get("roleDefinitionId") for a in assignments} - set(names)):
        if cancelled() or not rid:
            continue
        rc, text = run(["request", "--url", GRAPH_ROLES + "roleDefinitions/" + rid +
                        "?$select=id,displayName", "--output", "json"])
        one = parse_json(text) if rc == 0 else None
        names[rid] = (one or {}).get("displayName") if isinstance(one, dict) else None
        names[rid] = names[rid] or ("role " + rid)

    rows = []
    for a in assignments:
        kind, name, ident, enabled = _principal_row(a.get("principal"))
        if kind == "app" and not with_apps:
            continue
        scope = a.get("directoryScopeId") or "/"
        rows.append({"role": names.get(a.get("roleDefinitionId")) or "(unknown role)",
                     "kind": kind, "name": name, "id": ident, "enabled": enabled,
                     "scope": "whole organization" if scope == "/" else scope,
                     "key": ((a.get("principal") or {}).get("id") or ident)})
    rows.sort(key=lambda r: (r["role"] != ROLES_GLOBAL_ADMIN, r["role"].lower(),
                             r["name"].lower()))
    result["assignments"] = len(rows)

    # v0.14: has each person with a role registered an MFA method?
    people = sorted({r["key"] for r in rows if r["kind"] == "user" and r["key"]})
    mfa, mfa_err = ({}, "")
    if people and not cancelled():
        out("Reading MFA registration for %d account(s)...\n" % len(people))
        mfa, mfa_err = _mfa_status(run, people, cancelled)
    for r in rows:
        got = mfa.get(r["key"]) if r["kind"] == "user" else None
        r["mfa"] = "" if got is None else ("yes" if got[0] else "NO")
        r["methods"] = "" if got is None else got[1]

    # v0.14: when did each person with a role last sign in?
    seen, seen_err = ({}, "")
    if people and not cancelled():
        out("Reading the last sign-in of %d account(s)...\n" % len(people))
        seen, seen_err = _last_signins(run, people, cancelled)
    today = datetime.date.today()
    for r in rows:
        if r["kind"] != "user" or r["key"] not in seen:
            r["last"], r["idle"] = "", None
        elif seen[r["key"]] is None:
            r["last"], r["idle"] = "never (or not recorded)", -1
        else:
            r["last"], r["idle"] = seen[r["key"]].strftime("%m-%d-%Y"), (today - seen[r["key"]]).days

    # ---- summary: the things worth a second look --------------------------------
    holders = {}
    for r in rows:
        holders.setdefault(r["key"], []).append(r)
    users = [k for k, rs in holders.items() if rs[0]["kind"] == "user"]
    gas = [r for r in rows if r["role"] == ROLES_GLOBAL_ADMIN]
    out("\n%d role assignment(s): %d account(s)%s.\n"
        % (len(rows), len(users),
           "" if not with_apps else ", %d app(s)" % sum(
               1 for rs in holders.values() if rs[0]["kind"] == "app")))
    # People and apps are counted apart: Microsoft's advice (fewer than five,
    # at least two) is about people. A live tenant had 4 people + 1 app.
    ga_people = sum(1 for r in gas if r["kind"] == "user")
    ga_other = len(gas) - ga_people
    out("Global Administrators: %d %s%s" % (ga_people, "person" if ga_people == 1 else "people",
                                            (" + %d app(s) / group(s)" % ga_other) if ga_other else ""))
    if ga_people > 4:
        out("  - Microsoft recommends fewer than five.")
    elif ga_people < 2:
        out("  - Microsoft recommends at least two (so one is left if the other is locked out).")
    out("\n")
    many = sorted(((len(rs), rs[0]) for rs in holders.values() if len(rs) >= ROLES_MANY),
                  key=lambda pair: -pair[0])
    for n, r in many:
        out("NOTE: %s (%s) holds %d roles - most people need one or two; a Global "
            "Administrator already has every permission.\n" % (r["name"], r["id"], n))
    off = sorted({(r["name"], r["id"]) for r in rows if r["enabled"] == "NO"})
    for name, ident in off:
        out("NOTE: %s (%s) is blocked from signing in but still holds a role - remove the "
            "role if the account is no longer used.\n" % (name, ident))
    # v0.14: no MFA method registered - Global Administrators first.
    if mfa_err:
        out("NOTE: MFA registration could not be read (needs the AuditLog.Read.All "
            "permission and Microsoft Entra ID P1 or P2): %s\n" % mfa_err)
    no_mfa_ga = sorted({(r["name"], r["id"]) for r in gas if r["mfa"] == "NO"})
    no_mfa_other = sorted({(r["name"], r["id"]) for r in rows if r["mfa"] == "NO"} - set(no_mfa_ga))
    for name, ident in no_mfa_ga:
        out("NOTE: Global Administrator %s (%s) has NO MFA method registered - fix this "
            "first.\n" % (name, ident))
    for name, ident in no_mfa_other:
        out("NOTE: %s (%s) holds an admin role and has NO MFA method registered.\n"
            % (name, ident))
    # v0.14: people with a role who have not signed in for idle_days (or never).
    if seen_err and not seen:
        out("NOTE: last sign-ins could not be read (needs the AuditLog.Read.All "
            "permission and Microsoft Entra ID P1 or P2): %s\n" % seen_err)
    elif seen_err:
        out("NOTE: some last sign-ins could not be read: %s.\n" % seen_err)
    idle = {}
    for r in rows:
        if r["idle"] is not None and (r["idle"] < 0 or r["idle"] >= idle_days):
            idle[(r["name"], r["id"])] = (r["idle"], r["last"])
    for (name, ident), (days, last) in sorted(idle.items(), key=lambda kv: -(kv[1][0] if kv[1][0] >= 0 else 10 ** 6)):
        out("NOTE: %s (%s) holds an admin role and %s - remove the role or block the "
            "account if it is no longer used.\n"
            % (name, ident, "has never signed in (or it was not recorded)" if days < 0 else
               "has not signed in for %d days (last %s)" % (days, last)))

    # ---- the list, by role ---------------------------------------------------------
    current = None
    for r in rows:
        if r["role"] != current:
            current = r["role"]
            out("\n%s\n" % current)
        extra = [x for x in (r["kind"] if r["kind"] != "user" else "",
                             "sign-in blocked" if r["enabled"] == "NO" else "",
                             "no MFA" if r["mfa"] == "NO" else "",
                             "never signed in" if r["idle"] == -1 else
                             ("idle %d days" % r["idle"]) if r["idle"] is not None and r["idle"] >= idle_days else "",
                             "" if r["scope"] == "whole organization" else "scope " + r["scope"])
                 if x]
        out("  %s  <%s>%s\n" % (r["name"], r["id"], ("  [" + ", ".join(extra) + "]") if extra else ""))

    # ---- the record ------------------------------------------------------------------
    import io
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["role", "type", "name", "sign-in name or app id", "sign-in enabled", "scope",
                     "MFA registered", "MFA methods", "last sign-in"])
    for r in rows:
        writer.writerow([r["role"], r["kind"], r["name"], r["id"], r["enabled"], r["scope"],
                         r["mfa"], r["methods"], r["last"]])
    folder = _record_dir(records_base, "AdminRoles", "tenant")
    result["folder"] = folder
    _save(folder, "admin-roles.csv", buf.getvalue(), out)
    result["ok"] = not cancelled()
    out("\n===== DONE: %d assignment(s). Saved: %s =====\n"
        % (len(rows), os.path.join(folder, "admin-roles.csv")))
    return result

# =============================================================================
# SECTION: Conditional Access review (v0.14, 10-29-2026) - read-only.
#   Reads every Conditional Access policy from Microsoft Graph
#   (identity/conditionalAccess/policies, through 'm365 request'), the admin
#   role names (directoryRoleTemplates) and the names of the users and
#   groups a policy includes or excludes (one GET each), then describes each
#   policy in plain words and points out gaps: no policy that is ON requires
#   MFA for everyone / for Global Administrators, nothing blocks legacy
#   authentication, and who is excluded from policies that are ON. Needs
#   Policy.Read.All. Changes nothing. Checked live 10-29-2026.
# =============================================================================

GRAPH = "https://graph.microsoft.com/v1.0/"
GA_ROLE_TEMPLATE = "62e90394-69f5-4237-9190-012177145e10"   # Global Administrator
CA_STATES = {"enabled": "ON", "disabled": "off",
             "enabledForReportingButNotEnforced": "report-only (not enforced)"}
CA_CONTROLS = {"mfa": "MFA", "block": "BLOCK access", "compliantDevice": "a compliant device",
               "domainJoinedDevice": "a hybrid-joined device", "approvedApplication": "an approved app",
               "compliantApplication": "an app protection policy", "passwordChange": "a password change"}
CA_CLIENTS = {"exchangeActiveSync": "Exchange ActiveSync", "other": "other old clients",
              "browser": "browser", "mobileAppsAndDesktopClients": "mobile and desktop apps"}
CA_SPECIAL_USERS = {"All": "everyone", "None": "nobody", "GuestsOrExternalUsers": "guests"}
LEGACY_CLIENTS = {"exchangeActiveSync", "other"}

def _ca_requires(policy):
    # True when the policy asks for MFA (the MFA control or an authentication strength).
    grant = policy.get("grantControls") or {}
    return "mfa" in (grant.get("builtInControls") or []) or bool(grant.get("authenticationStrength"))

def _ca_blocks(policy):
    return "block" in ((policy.get("grantControls") or {}).get("builtInControls") or [])

def _ca_users(policy):
    return (policy.get("conditions") or {}).get("users") or {}

def _ca_grant_text(policy):
    grant = policy.get("grantControls") or {}
    parts = [CA_CONTROLS.get(c, c) for c in grant.get("builtInControls") or []]
    strength = (grant.get("authenticationStrength") or {}).get("displayName")
    if strength:
        parts.append("authentication strength '%s'" % strength)
    if grant.get("termsOfUse"):
        parts.append("terms of use")
    if not parts:
        return "nothing (session settings only)" if policy.get("sessionControls") else "nothing"
    if len(parts) > 1:
        return ("all of: " if grant.get("operator") == "AND" else "any of: ") + ", ".join(parts)
    return parts[0]

def _ca_conditions_text(policy):
    cond = policy.get("conditions") or {}
    bits = []
    clients = cond.get("clientAppTypes") or ["all"]
    # All four client types listed one by one is the same as 'all' (seen live).
    if "all" not in clients and not set(CA_CLIENTS) <= set(clients):
        bits.append("only " + " / ".join(CA_CLIENTS.get(c, c) for c in clients))
    if cond.get("locations"):
        bits.append("only some locations")
    if cond.get("platforms"):
        bits.append("only some device platforms")
    if cond.get("devices"):
        bits.append("a device filter")
    for key, label in (("signInRiskLevels", "sign-in risk"), ("userRiskLevels", "user risk")):
        if cond.get(key):
            bits.append("%s %s" % (label, "/".join(cond[key])))
    return ", ".join(bits)

def _ca_apps_text(policy):
    apps = (policy.get("conditions") or {}).get("applications") or {}
    inc = apps.get("includeApplications") or []
    text = "all apps" if "All" in inc else ("Office 365" if inc == ["Office365"] else
                                             "%d app(s)" % len(inc) if inc else "no apps")
    if apps.get("excludeApplications"):
        text += " except %d app(s)" % len(apps["excludeApplications"])
    return text

def conditional_access(run, out, cancelled, values, records_base):
    result = {"ok": False, "error": "", "folder": "", "policies": 0}

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    out("\n===== CONDITIONAL ACCESS REVIEW =====\nReading the policies...\n")
    policies, err = _graph_pages(run, GRAPH + "identity/conditionalAccess/policies", cancelled)
    if err:
        return stop("Could not read the Conditional Access policies: " + err +
                    "\n(The signed-in account needs Policy.Read.All. Conditional Access needs "
                    "Microsoft Entra ID P1 or P2.)")
    if cancelled():
        return stop("[Stopped.]")
    result["policies"] = len(policies)
    if not policies:
        out("\nThere are no Conditional Access policies.\n")

    # ---- names for the role, user and group ids the policies use -------------------
    roles, rerr = _graph_pages(run, GRAPH + "directoryRoleTemplates?$select=id,displayName", cancelled)
    names = {r.get("id"): r.get("displayName") for r in roles if r.get("id")}
    wanted = {"users": set(), "groups": set()}
    for p in policies:
        u = _ca_users(p)
        for side in ("include", "exclude"):
            wanted["users"].update(x for x in u.get(side + "Users") or [] if x not in CA_SPECIAL_USERS)
            wanted["groups"].update(u.get(side + "Groups") or [])
    for kind, select in (("users", "displayName,userPrincipalName"), ("groups", "displayName")):
        for oid in sorted(wanted[kind]):
            if cancelled():
                return stop("[Stopped.]")
            rc, text = run(["request", "--url", GRAPH + kind + "/" + oid + "?$select=" + select,
                            "--output", "json"])
            one = parse_json(text) if rc == 0 else None
            if isinstance(one, dict) and one.get("displayName"):
                upn = one.get("userPrincipalName")
                names[oid] = one["displayName"] + (" <%s>" % upn if upn else "")
            else:
                names[oid] = "(deleted or unknown %s %s)" % (kind[:-1], oid)

    def who(u, side):
        parts = [CA_SPECIAL_USERS.get(x) or names.get(x, x) for x in u.get(side + "Users") or []]
        parts += ["group " + names.get(g, g) for g in u.get(side + "Groups") or []]
        r = u.get(side + "Roles") or []
        if r:
            ga = " (incl. Global Administrator)" if GA_ROLE_TEMPLATE in r else ""
            parts.append(("role " + (names.get(r[0]) or r[0])) if len(r) == 1 else
                         "%d admin roles%s" % (len(r), ga))
        if u.get(side + "GuestsOrExternalUsers"):
            parts.append("guests / external users")
        return parts

    # ---- each policy in plain words ------------------------------------------------
    rows = []
    for p in sorted(policies, key=lambda x: (x.get("state") != "enabled", (x.get("displayName") or "").lower())):
        u = _ca_users(p)
        rows.append({"policy": p.get("displayName") or p.get("id") or "(no name)",
                     "state": CA_STATES.get(p.get("state"), p.get("state") or ""),
                     "requires": _ca_grant_text(p), "applies to": ", ".join(who(u, "include")) or "nobody",
                     "excludes": ", ".join(who(u, "exclude")), "apps": _ca_apps_text(p),
                     "conditions": _ca_conditions_text(p)})
    for r in rows:
        out("\n%s  [%s]\n  requires: %s\n  applies to: %s%s\n  apps: %s%s\n"
            % (r["policy"], r["state"], r["requires"], r["applies to"],
               ("\n  excludes: " + r["excludes"]) if r["excludes"] else "", r["apps"],
               ("\n  only when: " + r["conditions"]) if r["conditions"] else ""))

    # ---- what is worth a second look ------------------------------------------------
    on = [p for p in policies if p.get("state") == "enabled"]
    out("\n%d policy(ies): %d ON, %d report-only, %d off.\n"
        % (len(policies), len(on),
           sum(1 for p in policies if p.get("state") == "enabledForReportingButNotEnforced"),
           sum(1 for p in policies if p.get("state") == "disabled")))
    # Only policies that cover ALL apps count here - a one-app policy leaves the
    # account open everywhere else.
    mfa_on = [p for p in on if _ca_requires(p) and "All" in (((p.get("conditions") or {})
              .get("applications") or {}).get("includeApplications") or [])]
    if not any("All" in (_ca_users(p).get("includeUsers") or []) for p in mfa_on):
        out("NOTE: no policy that is ON requires MFA for everyone on all apps.\n")
    if not any("All" in (_ca_users(p).get("includeUsers") or []) or
               GA_ROLE_TEMPLATE in (_ca_users(p).get("includeRoles") or []) for p in mfa_on):
        out("NOTE: no policy that is ON requires MFA for Global Administrators on all apps - "
            "add one first.\n")
    legacy = [p for p in on if _ca_blocks(p) and
              LEGACY_CLIENTS <= set((p.get("conditions") or {}).get("clientAppTypes") or [])
              and "All" in (_ca_users(p).get("includeUsers") or [])]
    if not legacy:
        out("NOTE: no policy that is ON blocks legacy authentication (old mail apps that cannot "
            "do MFA) for everyone.\n")
    excluded = {}
    for p in on:
        if not (_ca_requires(p) or _ca_blocks(p)):
            continue
        u = _ca_users(p)
        for oid in [x for x in u.get("excludeUsers") or [] if x not in CA_SPECIAL_USERS] + \
                   (u.get("excludeGroups") or []):
            excluded.setdefault(oid, []).append(p.get("displayName") or p.get("id"))
    for oid, pols in sorted(excluded.items(), key=lambda kv: -len(kv[1])):
        kind = "group " if oid in wanted["groups"] else ""
        out("NOTE: %s%s is excluded from %d MFA / block policy(ies) that are ON (%s) - make sure "
            "that is on purpose (an emergency 'break-glass' account is the usual reason).\n"
            % (kind, names.get(oid, oid), len(pols), "; ".join(pols)))
    if rerr:
        out("NOTE: admin role names could not be read (%s) - roles are shown by id.\n" % rerr)

    # ---- the record ------------------------------------------------------------------
    import io
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    columns = ["policy", "state", "requires", "applies to", "excludes", "apps", "conditions"]
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r[c] for c in columns])
    folder = _record_dir(records_base, "ConditionalAccess", "tenant")
    result["folder"] = folder
    _save(folder, "conditional-access.csv", buf.getvalue(), out)
    result["ok"] = not cancelled()
    out("\n===== DONE: %d policy(ies). Saved: %s =====\n"
        % (len(rows), os.path.join(folder, "conditional-access.csv")))
    return result

# =============================================================================
# SECTION: Files shared by link in a folder (v0.14, 10-29-2026) - read-only.
#   'spo file list' (with --recursive for subfolders) gives the files; then
#   'spo file sharinglink list --fileId' gives each file's links (with
#   --scope anonymous for 'anyone' links only). A library's Forms folder
#   holds SharePoint's own .aspx pages - the sharing commands fail on them
#   (found live 10-29-2026), so they are skipped. The link ADDRESSES are
#   never shown or saved: whoever has an 'anyone' link can open the file.
#   Changes nothing.
# =============================================================================

SHARE_MAX_FILES = 2000   # one command per file - a guard for huge libraries
SHARE_PROGRESS = 25      # a progress line every this many files

def _link_row(path, link):
    # One CSV / screen row for one sharing link of one file.
    info = link.get("link") or {}
    people = []
    for ident in link.get("grantedToIdentitiesV2") or link.get("grantedToIdentities") or []:
        user = (ident or {}).get("user") or (ident or {}).get("siteUser") or {}
        who = user.get("email") or user.get("displayName")
        if who and who not in people:
            people.append(who)
    expires = (link.get("expirationDateTime") or "")[:10]
    return {"file": path,
            "scope": info.get("scope") or link.get("scope") or "unknown",
            "type": info.get("type") or "",
            "roles": ",".join(link.get("roles") or []),
            "expires": expires,
            "password": "yes" if link.get("hasPassword") else "no",
            "blocks download": "yes" if info.get("preventsDownload") else "no",
            "people": "; ".join(people)}

def _can_edit(row):
    return row["type"] == "edit" or "write" in row["roles"].split(",")

def shared_links(run, out, cancelled, values, records_base):
    result = {"ok": False, "error": "", "folder": "", "files": 0, "links": 0}
    site = clean_identifier(values.get("url") or "").strip().rstrip("/")
    folder = (values.get("folder") or "").strip().strip("/")
    deep = values.get("subfolders", YES) == YES
    anyone_only = values.get("kind", SHARE_ANYONE) == SHARE_ANYONE

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    if not site.lower().startswith("https://"):
        return stop("The Site URL box needs a site address such as "
                    "https://contoso.sharepoint.com/sites/Team.")
    if not folder:
        return stop("The Folder box needs a folder, e.g. Shared Documents.")

    out("\n===== FILES SHARED BY LINK =====\nSite: %s\nFolder: %s%s\nLinks: %s\n"
        % (site, folder, " (and its subfolders)" if deep else "",
           "anyone with the link only" if anyone_only else "every kind"))
    out("Listing the files...\n")
    rc, text = run(["spo", "file", "list", "--webUrl", site, "--folderUrl", folder] +
                   (["--recursive"] if deep else []) + ["--output", "json"])
    files = parse_json(text) if rc == 0 else None
    if not isinstance(files, list):
        return stop("Could not list the files: " +
                    (" ".join((text or "").split())[:300] or "no answer"))
    files = [f for f in files if isinstance(f, dict) and f.get("UniqueId")
             and "/forms/" not in (f.get("ServerRelativeUrl") or "").lower()]
    if len(files) > SHARE_MAX_FILES:
        out("NOTE: %d files - only the first %d are checked. Choose a smaller folder for the "
            "rest.\n" % (len(files), SHARE_MAX_FILES))
        files = files[:SHARE_MAX_FILES]
    out("%d file(s) to check.\n" % len(files))

    rows, failed, checked = [], [], 0
    for f in files:
        if cancelled():
            break
        path = f.get("ServerRelativeUrl") or f.get("Name") or f["UniqueId"]
        rc, text = run(["spo", "file", "sharinglink", "list", "--webUrl", site,
                        "--fileId", f["UniqueId"]] +
                       (["--scope", "anonymous"] if anyone_only else []) + ["--output", "json"])
        links = parse_json(text) if rc == 0 else None
        checked += 1
        if not isinstance(links, list):
            failed.append((path, " ".join((text or "").split())[:200] or "no answer"))
        else:
            rows.extend(_link_row(path, link) for link in links if isinstance(link, dict))
        if checked % SHARE_PROGRESS == 0 and checked < len(files):
            out("  ... %d of %d checked\n" % (checked, len(files)))
    result["files"], result["links"] = checked, len(rows)
    if cancelled():
        out("\n[Stopped after %d of %d file(s).]\n" % (checked, len(files)))

    # ---- summary: the things worth a second look --------------------------------
    by_scope = {}
    for r in rows:
        by_scope[r["scope"]] = by_scope.get(r["scope"], 0) + 1
    shared_files = len({r["file"] for r in rows})
    out("\n%d link(s) on %d of %d file(s)%s.\n"
        % (len(rows), shared_files, checked,
           (" (" + ", ".join("%s %d" % (k, v) for k, v in sorted(by_scope.items())) + ")")
           if by_scope else ""))
    anyone = [r for r in rows if r["scope"] == "anonymous"]
    edit_anyone = [r for r in anyone if _can_edit(r)]
    forever = [r for r in anyone if not r["expires"]]
    if edit_anyone:
        out("NOTE: %d 'anyone' link(s) let whoever has the link EDIT the file.\n" % len(edit_anyone))
    if forever:
        out("NOTE: %d 'anyone' link(s) never expire.\n" % len(forever))
    if failed:
        out("NOTE: %d file(s) could not be checked (listed at the end).\n" % len(failed))

    # ---- the list, by file ---------------------------------------------------------
    current = None
    for r in rows:
        if r["file"] != current:
            current = r["file"]
            out("\n%s\n" % current)
        bits = [r["scope"], r["type"] or r["roles"] or "?",
                ("expires " + r["expires"]) if r["expires"] else "no expiry"]
        if r["password"] == "yes":
            bits.append("password")
        if r["people"]:
            bits.append("for " + r["people"])
        out("  " + ", ".join(bits) + "\n")
    for path, why in failed:
        out("\nCOULD NOT CHECK: %s - %s\n" % (path, why))

    # ---- the record ------------------------------------------------------------------
    import io
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    columns = ["file", "scope", "type", "roles", "expires", "password", "blocks download", "people"]
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r[c] for c in columns])
    for path, why in failed:
        writer.writerow([path, "COULD NOT CHECK", "", "", "", "", "", why])
    name = site.split("/")[-1] or "site"
    folder_out = _record_dir(records_base, "SharedLinks", name)
    result["folder"] = folder_out
    _save(folder_out, "shared-links.csv", buf.getvalue(), out)
    result["ok"] = not cancelled() and not failed
    out("\n===== DONE: %d file(s) checked, %d link(s). Saved: %s =====\n"
        % (checked, len(rows), os.path.join(folder_out, "shared-links.csv")))
    return result

# =============================================================================
# SECTION: Team settings review (v0.15, read-only) - for one Team, or every
#   Team when the box is left blank: who can see it, whether it is archived,
#   how many owners / members / guests it has, and its guest, member,
#   messaging and fun settings. 'teams team get --id' answers all of it in
#   one call (run live, read-only, 10-30-2026: guestSettings, memberSettings,
#   messagingSettings, funSettings, discoverySettings, visibility,
#   isArchived and summary.ownersCount / membersCount / guestsCount). Nothing
#   is changed; team-settings.csv is saved in the Records folder.
# =============================================================================

TEAM_SETTINGS_AREAS = [("guestSettings", "Guests"), ("memberSettings", "Members"),
                       ("messagingSettings", "Messaging"), ("funSettings", "Fun stuff"),
                       ("discoverySettings", "Discovery")]
TEAM_SETTING_NAMES = {
    ("guestSettings", "allowCreateUpdateChannels"): "Guests can create and edit channels",
    ("guestSettings", "allowDeleteChannels"): "Guests can delete channels",
    ("memberSettings", "allowAddRemoveApps"): "Members can add and remove apps",
    ("memberSettings", "allowCreatePrivateChannels"): "Members can create private channels",
    ("memberSettings", "allowCreateUpdateChannels"): "Members can create and edit channels",
    ("memberSettings", "allowCreateUpdateRemoveConnectors"): "Members can add, edit and remove connectors",
    ("memberSettings", "allowCreateUpdateRemoveTabs"): "Members can add, edit and remove tabs",
    ("memberSettings", "allowDeleteChannels"): "Members can delete channels",
    ("messagingSettings", "allowChannelMentions"): "@channel mentions allowed",
    ("messagingSettings", "allowOwnerDeleteMessages"): "Owners can delete anyone's messages",
    ("messagingSettings", "allowTeamMentions"): "@team mentions allowed",
    ("messagingSettings", "allowUserDeleteMessages"): "People can delete their own messages",
    ("messagingSettings", "allowUserEditMessages"): "People can edit their own messages",
    ("funSettings", "allowCustomMemes"): "Custom memes allowed",
    ("funSettings", "allowGiphy"): "Giphy (animated pictures) allowed",
    ("funSettings", "allowStickersAndMemes"): "Stickers and memes allowed",
    ("funSettings", "giphyContentRating"): "Giphy content rating",
    ("discoverySettings", "showInTeamsSearchAndSuggestions"): "Shown in Teams search and suggestions",
}
# Settings worth a second look when they are ON (true) - both are OFF by
# default. 'Members can delete channels' is ON by default in every Team (all
# three on the live run), so it is shown but not pointed out.
TEAM_SETTING_NOTES = {
    ("guestSettings", "allowCreateUpdateChannels"): "guests can create and edit channels",
    ("guestSettings", "allowDeleteChannels"): "guests can delete channels",
}

def _looks_like_id(text):
    # A Team / group id: 36 characters of hex digits and dashes.
    return len(text) == 36 and all(ch in "0123456789abcdefABCDEF-" for ch in text)

def _setting_text(value):
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None:
        return "(not set)"
    return str(value)

def _team_rows(team):
    # One Team's 'teams team get' JSON -> [(area, setting, value, raw)] in
    # the order they are shown.
    summary = team.get("summary") if isinstance(team.get("summary"), dict) else {}
    rows = [("General", "Who can find and join it (visibility)", _setting_text(team.get("visibility")),
             team.get("visibility")),
            ("General", "Archived (read-only)", _setting_text(team.get("isArchived")),
             team.get("isArchived")),
            ("General", "Owners", _setting_text(summary.get("ownersCount")), summary.get("ownersCount")),
            ("General", "Members", _setting_text(summary.get("membersCount")), summary.get("membersCount")),
            ("General", "Guests", _setting_text(summary.get("guestsCount")), summary.get("guestsCount"))]
    for area, area_label in TEAM_SETTINGS_AREAS:
        got = team.get(area)
        if not isinstance(got, dict):
            continue
        for key in sorted(got):
            rows.append((area_label, TEAM_SETTING_NAMES.get((area, key), key),
                         _setting_text(got[key]), got[key]))
    return rows

def _team_notes(team):
    # The plain-words notes for one Team (things worth a second look).
    notes = []
    summary = team.get("summary") if isinstance(team.get("summary"), dict) else {}
    if summary.get("ownersCount") == 0 and not team.get("isArchived"):
        notes.append("no owner - nobody can manage its members or settings")
    if (team.get("visibility") or "").lower() == "public":
        notes.append("public - anyone in the organization can find and join it")
    if summary.get("guestsCount"):
        notes.append("%s guest(s)" % summary.get("guestsCount"))
    for (area, key), text in sorted(TEAM_SETTING_NOTES.items()):
        if isinstance(team.get(area), dict) and team[area].get(key) is True:
            notes.append(text)
    return notes

def team_settings(run, out, cancelled, values, records_base):
    result = {"ok": False, "error": "", "folder": "", "teams": 0, "notes": 0}
    wanted = clean_identifier(values.get("team") or "").strip()

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    out("\n===== TEAM SETTINGS REVIEW: %s =====\n"
        % (("'%s'" % wanted) if wanted else "every Team"))
    out("Listing the Teams...\n")
    rc, text = run(["teams", "team", "list", "--output", "json"])
    teams = parse_json(text) if rc == 0 else None
    if not isinstance(teams, list):
        return stop("Could not list the Teams: " +
                    (" ".join((text or "").split())[:300] or "no answer"))
    teams = [t for t in teams if isinstance(t, dict) and t.get("id")]
    if wanted:
        if _looks_like_id(wanted):
            teams = [t for t in teams if t["id"].lower() == wanted.lower()]
        else:
            teams = [t for t in teams
                     if (t.get("displayName") or "").strip().lower() == wanted.lower()]
        if not teams:
            return stop("No Team is called '%s'. (Leave the box blank for every Team.)" % wanted)
        if len(teams) > 1:
            out("NOTE: %d Teams are called '%s' - each one is shown, with its id.\n"
                % (len(teams), wanted))
    teams.sort(key=lambda t: (t.get("displayName") or "").lower())
    out("%d Team(s) to read.\n" % len(teams))

    rows, notes, failed, done = [], [], [], 0
    for listed in teams:
        if cancelled():
            break
        name = listed.get("displayName") or listed["id"]
        rc, text = run(["teams", "team", "get", "--id", listed["id"], "--output", "json"])
        team = parse_json(text) if rc == 0 else None
        if not isinstance(team, dict):
            why = " ".join((text or "").split())[:200] or "no answer"
            failed.append((name, listed["id"], why))
            out("\n%s  (id %s)\n  COULD NOT READ - %s\n" % (name, listed["id"], why))
            continue
        done += 1
        out("\n%s  (id %s)\n" % (name, listed["id"]))
        area_now = ""
        for area_label, setting, shown, _raw in _team_rows(team):
            if area_label != area_now:
                area_now = area_label
                out("  %s:\n" % area_label)
            out("    %-46s %s\n" % (setting, shown))
            rows.append({"team": name, "id": listed["id"], "area": area_label,
                         "setting": setting, "value": shown})
        for n in _team_notes(team):
            notes.append("%s: %s" % (name, n))
    result["teams"], result["notes"] = done, len(notes)
    if cancelled():
        out("\n[Stopped after %d of %d Team(s).]\n" % (done + len(failed), len(teams)))

    # ---- summary: the things worth a second look --------------------------------
    out("\n%d Team(s) read.\n" % done)
    if notes:
        out("Worth a second look:\n")
        for n in notes:
            out("  - %s\n" % n)
    elif done:
        out("Nothing to point out: every Team has an owner, none is public or has guests, "
            "and none lets guests create, edit or delete channels.\n")

    # ---- the record ------------------------------------------------------------------
    import io
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    columns = ["team", "id", "area", "setting", "value"]
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r[c] for c in columns])
    for name, ident, why in failed:
        writer.writerow([name, ident, "", "COULD NOT READ", why])
    folder_out = _record_dir(records_base, "TeamSettings", wanted or "all-teams")
    result["folder"] = folder_out
    _save(folder_out, "team-settings.csv", buf.getvalue(), out)
    result["ok"] = not cancelled() and not failed
    out("\n===== DONE: %d Team(s), %d note(s). Saved: %s =====\n"
        % (done, len(notes), os.path.join(folder_out, "team-settings.csv")))
    return result

# =============================================================================
# SECTION: Power Automate flows and Power Apps review (v0.16, read-only)
#   Every Power Platform environment -> every flow and every app in it, read
#   as an administrator ('flow list --asAdmin', 'pa app list --asAdmin'), who
#   made each one and - unless skipped - each flow's trigger, actions and
#   connectors ('flow get --asAdmin'). Run live, read-only, 11-02-2026: one
#   environment, six flows, no apps. A flow's creator can be a person, an app
#   (service principal) or a Dataverse system account that is not in the
#   directory at all, so each creator is looked up as a directoryObject (the
#   live run had an app and a system account; a 404 for a person's id means
#   the account was deleted). Nothing is changed; power-platform.csv is saved
#   in the Records folder.
# =============================================================================

# Connectors (by API name, without 'shared_') that can send data outside
# Microsoft 365 - a flow or app that uses one is pointed out.
POWER_OUTSIDE_CONNECTORS = {
    "gmail": "Gmail", "googledrive": "Google Drive", "googlesheet": "Google Sheets",
    "googlecalendar": "Google Calendar", "googletasks": "Google Tasks", "dropbox": "Dropbox",
    "box": "Box", "onedrive": "OneDrive (personal)", "outlook": "Outlook.com (personal)",
    "ftp": "FTP", "sftp": "SFTP", "sftpwithssh": "SFTP", "smtp": "SMTP", "slack": "Slack",
    "twitter": "X (Twitter)", "webcontents": "HTTP with Microsoft Entra ID",
}
# Creator types that are not directory accounts (live: Dataverse system flows).
POWER_SYSTEM_TYPES = {"DataverseSystemUser": "system account (Dataverse)"}
# 'flow get' writes each trigger as type[-kind] (CLI flow-get.js); plain words.
POWER_TRIGGERS = {
    "Recurrence": "on a schedule",
    "OpenApiConnectionWebhook": "when something happens in a connected service",
    "OpenApiConnection": "checks a connected service now and then",
    "ApiConnectionWebhook": "when something happens in a connected service",
    "ApiConnection": "checks a connected service now and then",
    "Request": "when someone calls its web address",
    "Request-Http": "when someone calls its web address",
    "Request-Button": "by hand (a button)",
    "Request-PowerApp": "from a Power App",
    "Request-PowerAppV2": "from a Power App",
    "Request-VirtualAgent": "from a Copilot agent / chatbot",
    "Request-Skills": "from a Copilot agent / chatbot",
}

def _power_trigger_text(trigger):
    # 'Recurrence, Request-Button' -> 'on a schedule (Recurrence); by hand ...'
    parts = [t.strip() for t in (trigger or "").split(",") if t.strip()]
    return "; ".join("%s (%s)" % (POWER_TRIGGERS[t], t) if t in POWER_TRIGGERS else t
                     for t in parts)

def _power_connectors(refs):
    # A flow's or app's connectionReferences -> [(api name, display name)].
    items = refs.values() if isinstance(refs, dict) else (refs if isinstance(refs, list) else [])
    found = []
    for ref in items:
        if not isinstance(ref, dict):
            continue
        api = (ref.get("apiName") or (ref.get("id") or "").rstrip("/").split("/")[-1]).lower()
        if api.startswith("shared_"):
            api = api[len("shared_"):]
        pair = (api, ref.get("displayName") or api)
        if api and pair not in found:
            found.append(pair)
    return found

def _power_who(run, cache, account):
    # A creator / owner -> (name shown, kind). kind is user, guest, app,
    # system, deleted or unknown. Each id is looked up once.
    acct = account if isinstance(account, dict) else {}
    if acct.get("userType") in POWER_SYSTEM_TYPES:
        return POWER_SYSTEM_TYPES[acct["userType"]], "system"
    oid = acct.get("objectId") or acct.get("id") or ""
    if not oid:
        return "(not recorded)", "unknown"
    if oid in cache:
        return cache[oid]
    rc, text = run(["request", "--url", GRAPH + "directoryObjects/" + oid, "--output", "json"])
    one = parse_json(text) if rc == 0 else None
    if isinstance(one, dict) and one.get("@odata.type"):
        kind = one["@odata.type"].replace("#microsoft.graph.", "")
        name = one.get("displayName") or oid
        if kind == "user":
            upn = one.get("userPrincipalName") or one.get("mail") or ""
            got = (name + (" <%s>" % upn if upn else ""),
                   "guest" if "#EXT#" in upn.upper() else "user")
        elif kind == "servicePrincipal":
            got = ("app: " + name, "app")
        else:
            got = ("%s (%s)" % (name, kind), kind)
    elif "404" in (text or "") or "NotFound" in (text or ""):
        got = ("(deleted or unknown account %s)" % oid, "deleted")
    else:
        got = ("(could not look up %s)" % oid, "unknown")
    cache[oid] = got
    return got

def _power_notes(on, who_kind, connectors, trigger, actions, suspension):
    # The plain-words notes for one flow or app (things worth a second look).
    notes = []
    if who_kind == "guest":
        notes.append("made by a guest")
    if who_kind == "deleted":
        notes.append("the account that made it is deleted or unknown" +
                     (" - and it is still ON" if on else ""))
    outside = sorted({POWER_OUTSIDE_CONNECTORS[a] for a, _n in connectors
                      if a in POWER_OUTSIDE_CONNECTORS})
    if outside:
        notes.append("can send data outside Microsoft 365: " + ", ".join(outside))
    if any(t.strip() in ("Request", "Request-Http") for t in (trigger or "").split(",")):
        notes.append("starts when someone calls its web address")
    if any(a.strip().lower().startswith("http") for a in (actions or "").split(",")):
        notes.append("calls web addresses directly (HTTP)")
    if suspension and str(suspension) not in ("None", "none"):
        notes.append("suspended by Microsoft (%s)" % suspension)
    return notes

def power_platform(run, out, cancelled, values, records_base):
    result = {"ok": False, "error": "", "folder": "", "flows": 0, "apps": 0, "notes": 0}
    details = (values.get("details") or POWER_DETAILS_FULL) == POWER_DETAILS_FULL

    def stop(message):
        result["error"] = message
        out("\n" + message + "\n")
        return result

    def why(text):
        return " ".join((text or "").split())[:200] or "no answer"

    out("\n===== POWER AUTOMATE FLOWS AND POWER APPS REVIEW =====\n")
    out("Listing the Power Platform environments...\n")
    rc, text = run(["flow", "environment", "list", "--output", "json"])
    envs = parse_json(text) if rc == 0 else None
    if not isinstance(envs, list):
        return stop("Could not list the Power Platform environments (you need to be a Power "
                    "Platform or Global administrator): " + why(text))
    envs = [e for e in envs if isinstance(e, dict) and e.get("name")]
    out("%d environment(s).\n" % len(envs))

    rows, notes, failed, cache = [], [], [], {}
    for env in envs:
        if cancelled():
            break
        props = env.get("properties") if isinstance(env.get("properties"), dict) else {}
        label = props.get("displayName") or env["name"]
        out("\n=== Environment: %s ===\n" % label)

        # ---- flows -------------------------------------------------------------------
        rc, text = run(["flow", "list", "--environmentName", env["name"], "--asAdmin",
                        "--output", "json"])
        flows = parse_json(text) if rc == 0 else None
        if not isinstance(flows, list):
            failed.append((label, "flows", why(text)))
            out("  COULD NOT LIST THE FLOWS - %s\n" % why(text))
            flows = []
        flows = [f for f in flows if isinstance(f, dict) and f.get("name")]
        out("  Flows: %d\n" % len(flows))
        for flow in sorted(flows, key=lambda f: ((f.get("properties") or {}).get("displayName")
                                                 or f["name"]).lower()):
            if cancelled():
                break
            p = flow.get("properties") if isinstance(flow.get("properties"), dict) else {}
            name = p.get("displayName") or flow["name"]
            state = p.get("state") or ""
            who, who_kind = _power_who(run, cache, p.get("creator"))
            trigger, actions, connectors = "", "", []
            if details:
                rc, text = run(["flow", "get", "--name", flow["name"], "--environmentName",
                                env["name"], "--asAdmin", "--output", "json"])
                got = parse_json(text) if rc == 0 else None
                if isinstance(got, dict):
                    trigger = got.get("triggers") or ""
                    actions = got.get("actions") or ""
                    connectors = _power_connectors((got.get("properties") or {})
                                                   .get("connectionReferences"))
                else:
                    failed.append((label, name, why(text)))
                    out("    (could not read its details - %s)\n" % why(text))
            these = _power_notes(state.lower() == "started", who_kind, connectors, trigger,
                                 actions, p.get("flowSuspensionReason"))
            result["flows"] += 1
            out("\n  FLOW  %s  [%s]\n" % (name, "ON" if state.lower() == "started" else
                                         (state or "unknown").lower()))
            out("    Made by:        %s\n" % who)
            out("    Last changed:   %s\n" % (p.get("lastModifiedTime") or "")[:10])
            if details:
                out("    Starts:         %s\n" % (_power_trigger_text(trigger) or "(none listed)"))
                out("    Connectors:     %s\n" % (", ".join(n for _a, n in connectors) or "(none)"))
            for n in these:
                notes.append("%s / flow '%s': %s" % (label, name, n))
            rows.append({"environment": label, "kind": "flow", "name": name, "id": flow["name"],
                         "state": state, "made_by": who, "made_by_kind": who_kind,
                         "created": p.get("createdTime") or "",
                         "last_changed": p.get("lastModifiedTime") or "",
                         "trigger": trigger, "connectors": "; ".join(n for _a, n in connectors),
                         "notes": "; ".join(these)})

        # ---- apps --------------------------------------------------------------------
        if cancelled():
            break
        rc, text = run(["pa", "app", "list", "--environmentName", env["name"], "--asAdmin",
                        "--output", "json"])
        apps = parse_json(text) if rc == 0 else None
        if not isinstance(apps, list):
            failed.append((label, "apps", why(text)))
            out("\n  COULD NOT LIST THE APPS - %s\n" % why(text))
            apps = []
        apps = [a for a in apps if isinstance(a, dict) and a.get("name")]
        out("\n  Apps: %d\n" % len(apps))
        for app in sorted(apps, key=lambda a: ((a.get("properties") or {}).get("displayName")
                                               or a["name"]).lower()):
            if cancelled():
                break
            p = app.get("properties") if isinstance(app.get("properties"), dict) else {}
            name = p.get("displayName") or app["name"]
            owner = p.get("owner") if isinstance(p.get("owner"), dict) else {}
            if owner.get("displayName") and (owner.get("email") or owner.get("userPrincipalName")):
                upn = owner.get("userPrincipalName") or owner.get("email")
                who = "%s <%s>" % (owner["displayName"], upn)
                who_kind = "guest" if "#EXT#" in upn.upper() else "user"
            else:
                who, who_kind = _power_who(run, cache, owner)
            connectors = _power_connectors(p.get("connectionReferences"))
            these = _power_notes(True, who_kind, connectors, "", "", None)
            shared = p.get("sharedUsersCount")
            result["apps"] += 1
            out("\n  APP   %s  [%s]\n" % (name, p.get("appType") or "app"))
            out("    Owner:          %s\n" % who)
            out("    Last changed:   %s\n" % (p.get("lastModifiedTime") or "")[:10])
            if shared is not None:
                out("    Shared with:    %s people, %s group(s)\n"
                    % (shared, p.get("sharedGroupsCount", 0)))
            out("    Connectors:     %s\n" % (", ".join(n for _a, n in connectors) or "(none)"))
            for n in these:
                notes.append("%s / app '%s': %s" % (label, name, n))
            rows.append({"environment": label, "kind": "app", "name": name, "id": app["name"],
                         "state": p.get("appType") or "", "made_by": who,
                         "made_by_kind": who_kind, "created": p.get("createdTime") or "",
                         "last_changed": p.get("lastModifiedTime") or "", "trigger": "",
                         "connectors": "; ".join(n for _a, n in connectors),
                         "notes": "; ".join(these)})
    result["notes"] = len(notes)
    if cancelled():
        out("\n[Stopped.]\n")

    # ---- summary: the things worth a second look ----------------------------------
    out("\n%d flow(s) and %d app(s) in %d environment(s).\n"
        % (result["flows"], result["apps"], len(envs)))
    if not details:
        out("(Each flow's trigger and connectors were skipped, so flows that send data "
            "outside Microsoft 365 or call web addresses are not pointed out.)\n")
    if notes:
        out("Worth a second look:\n")
        for n in notes:
            out("  - %s\n" % n)
    elif rows:
        out("Nothing to point out.\n")

    # ---- the record ------------------------------------------------------------------
    import io
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    columns = ["environment", "kind", "name", "id", "state", "made_by", "made_by_kind",
               "created", "last_changed", "trigger", "connectors", "notes"]
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r[c] for c in columns])
    for env_label, what, reason in failed:
        writer.writerow([env_label, "", what, "", "COULD NOT READ", "", "", "", "", "", "", reason])
    folder_out = _record_dir(records_base, "PowerPlatform", "all-environments")
    result["folder"] = folder_out
    _save(folder_out, "power-platform.csv", buf.getvalue(), out)
    result["ok"] = not cancelled() and not failed
    out("\n===== DONE: %d flow(s), %d app(s), %d note(s). Saved: %s =====\n"
        % (result["flows"], result["apps"], len(notes),
           os.path.join(folder_out, "power-platform.csv")))
    return result
