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
import os
import urllib.parse

from m365_catalog import TRANSFER_ACCESS_KEEP, TRANSFER_ACCESS_REMOVE, clean_identifier

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
        steps.do("Set an automatic reply",
                 ["outlook", "mailbox", "settings", "set", "--userName", leaver,
                  "--autoReplyStatus", "alwaysEnabled", "--autoReplyInternalMessage", reply,
                  "--autoReplyExternalMessage", reply, "--autoReplyExternalAudience", "all"])
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
