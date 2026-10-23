# =============================================================================
# Script:   m365_workflows.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  10-23-2026 (moved out of M365GUI.py, v0.6)
# Modified: 10-23-2026
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
import urllib.parse

from m365_catalog import TRANSFER_ACCESS_KEEP, clean_identifier

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
