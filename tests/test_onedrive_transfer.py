# test_onedrive_transfer.py - v0.4 (10-22-2026): 'Copy a user's OneDrive
# files to another user'. Runs M365GUI.transfer_onedrive against a FAKE m365
# (a function that answers each command the way the real CLI v11.11 does -
# response shapes from 'm365 <command> --help response'). Nothing touches
# Microsoft 365.
import os, sys, json, csv, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import M365GUI as m

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

HOST = "https://contoso-my.sharepoint.com"
SRC = HOST + "/personal/jdoe_contoso_com/"
DST = HOST + "/personal/asmith_contoso_com/"
SRC_LIB = "/personal/jdoe_contoso_com/Documents"
DST_LIB = "/personal/asmith_contoso_com/Documents"
OPERATOR = "admin@contoso.com"

class FakeM365:
    def __init__(self, admins=None, fail=(), dst_extra=0, src_files=None, no_site=()):
        # admins: site web url -> list of admin emails already there
        self.admins = admins if admins is not None else {SRC.rstrip("/"): ["jdoe@contoso.com"],
                                                         DST.rstrip("/"): ["asmith@contoso.com"]}
        self.fail = fail                    # argv words that make a command fail
        self.dst_extra = dst_extra          # files missing (-) or extra (+) after copy
        self.calls = []
        self.copied = []
        self.no_site = no_site
        self.src_files = src_files if src_files is not None else [
            (SRC_LIB + "/Report.docx", 1000), (SRC_LIB + "/Budget & Plan.xlsx", 2000),
            (SRC_LIB + "/Class (2026)/Notes.txt", 300), (SRC_LIB + "/Class (2026)/Deep/a.pdf", 4000),
            (SRC_LIB + "/Forms/AllItems.aspx", 50)]

    def opt(self, argv, name):
        return argv[argv.index(name) + 1] if name in argv else None

    def __call__(self, argv):
        self.calls.append(list(argv))
        for word in self.fail:
            if word in " ".join(argv):
                return 1, '{"error":"Request failed with status code 401"}'
        if argv[:1] == ["status"]:
            return 0, json.dumps({"connectedAs": OPERATOR, "authType": "browser"})
        if argv[:3] == ["entra", "user", "get"]:
            upn = self.opt(argv, "--userName")
            if upn in self.no_site:
                return 0, json.dumps({"userPrincipalName": upn, "mySite": None})
            site = SRC if upn.startswith("jdoe") else DST if upn.startswith("asmith") else None
            if site is None:
                return 1, '{"error":"Resource \'%s\' does not exist"}' % upn
            return 0, json.dumps({"userPrincipalName": upn, "displayName": upn.split("@")[0],
                                  "mySite": site})
        if argv[:4] == ["spo", "site", "admin", "list"]:
            # The REAL --asAdmin shape (checked live 10-22-2026): Email,
            # LoginName, Title, IsPrimaryAdmin only - and Email can be a
            # different address from the sign-in name, so only LoginName
            # ('i:0#.f|membership|<UPN>') identifies the admin.
            site = self.opt(argv, "--siteUrl")
            return 0, json.dumps([{"Email": "alias." + e, "LoginName": "i:0#.f|membership|" + e,
                                   "Title": e.split("@")[0], "IsPrimaryAdmin": i == 0}
                                  for i, e in enumerate(self.admins.get(site, []))])
        if argv[:4] == ["spo", "site", "admin", "add"]:
            self.admins.setdefault(self.opt(argv, "--siteUrl"), []).append(self.opt(argv, "--userName"))
            return 0, ""
        if argv[:4] == ["spo", "site", "admin", "remove"]:
            site = self.opt(argv, "--siteUrl")
            self.admins[site] = [e for e in self.admins.get(site, []) if e != self.opt(argv, "--userName")]
            return 0, ""
        if argv[:3] == ["spo", "file", "list"]:
            folder = self.opt(argv, "--folderUrl")
            recursive = "--recursive" in argv
            if folder.startswith(DST_LIB):
                n = len([f for f in self.src_files if "/Forms/" not in f[0]]) + self.dst_extra
                return 0, json.dumps([{"Name": "f%d" % i, "ServerRelativeUrl": folder + "/f%d" % i,
                                       "Length": 10} for i in range(max(n, 0))])
            rows = [f for f in self.src_files if f[0].startswith(folder + "/")
                    and (recursive or "/" not in f[0][len(folder) + 1:])]
            return 0, json.dumps([{"Name": p.rsplit("/", 1)[1], "ServerRelativeUrl": p, "Length": n}
                                  for p, n in rows])
        if argv[:3] == ["spo", "folder", "list"]:
            parent = self.opt(argv, "--parentFolderUrl")
            names = sorted({p[len(parent) + 1:].split("/")[0] for p, n in self.src_files
                            if p.startswith(parent + "/") and "/" in p[len(parent) + 1:]})
            return 0, json.dumps([{"Name": n, "ServerRelativeUrl": parent + "/" + n} for n in names])
        if argv[:3] == ["spo", "folder", "add"]:
            return 0, json.dumps({"Exists": True, "Name": self.opt(argv, "--name"),
                                  "ServerRelativeUrl": self.opt(argv, "--parentFolderUrl") + "/"
                                  + self.opt(argv, "--name")})
        if argv[:3] in (["spo", "folder", "copy"], ["spo", "file", "copy"]):
            self.copied.append((argv[1], self.opt(argv, "--sourceUrl"), self.opt(argv, "--targetUrl")))
            return 0, ""
        return 1, "unexpected command: " + " ".join(argv)

def go(fake, values=None, answer=True, cancel_after=None):
    out = []
    asked = []
    def confirm(text):
        asked.append(text)
        return answer
    copies = [0]
    def cancelled():
        return cancel_after is not None and len(fake.copied) >= cancel_after
    report = os.path.join(tempfile.mkdtemp(prefix="m365gui_"), "transfer.csv")
    vals = {"from": "jdoe@contoso.com", "to": "asmith@contoso.com", "folder": "",
            "access": m.TRANSFER_ACCESS_REMOVE}
    vals.update(values or {})
    result = m.transfer_onedrive(fake, out.append, confirm, cancelled, vals, report)
    return result, "".join(out), asked, report

# ---- 1. the normal run ---------------------------------------------------------
fake = FakeM365()
result, text, asked, report = go(fake)
check(result["ok"], "a normal transfer succeeds (%s)" % result.get("error"))
check(len(asked) == 1 and "4 files" in asked[0] and "jdoe@contoso.com" in asked[0]
      and "asmith@contoso.com" in asked[0], "asks ONCE, naming both people and the 4 files")
check("Forms" not in str(fake.copied), "the library's hidden Forms folder is not copied")
target = HOST + DST_LIB + "/" + m.default_transfer_folder("jdoe@contoso.com")
check(sorted(fake.copied) == sorted([
          ("file", SRC_LIB + "/Report.docx", target), ("file", SRC_LIB + "/Budget & Plan.xlsx", target),
          ("folder", SRC_LIB + "/Class (2026)", target)]),
      "top-level files and folders are each copied into the new folder (%s)" % fake.copied)
copy_cmds = [c for c in fake.calls if c[2:3] == ["copy"]]
check(all("--nameConflictBehavior" in c and c[c.index("--nameConflictBehavior") + 1] == "rename"
          for c in copy_cmds), "copies never overwrite: name conflicts are renamed")
check(all("--webUrl" in c and c[c.index("--webUrl") + 1] == SRC.rstrip("/") for c in copy_cmds),
      "copies run against the source OneDrive")
check(not any(c[:3] in (["spo", "file", "remove"], ["spo", "folder", "remove"]) for c in fake.calls),
      "nothing is ever removed from the original owner")
check(fake.admins[SRC.rstrip("/")] == ["jdoe@contoso.com"] and
      fake.admins[DST.rstrip("/")] == ["asmith@contoso.com"],
      "the temporary admin access is removed again from BOTH OneDrives")
check(result["copied"] == 3 and result["failed"] == 0, "3 items copied, 0 failed")
check(result["src_files"] == 4 and result["dst_files"] == 4, "counts checked: 4 files before and after")
check(os.path.exists(report) and len(list(csv.reader(open(report, encoding="utf-8")))) == 4,
      "a CSV record of every copy is saved (header + 3 rows)")
check(all(ord(c) < 128 for c in text), "the output is ASCII")

# ---- 2. access the operator already had is left alone ---------------------------
fake = FakeM365(admins={SRC.rstrip("/"): ["jdoe@contoso.com", OPERATOR],
                        DST.rstrip("/"): ["asmith@contoso.com"]})
result, text, asked, report = go(fake)
check(OPERATOR in fake.admins[SRC.rstrip("/")], "access the admin ALREADY had is not removed")
check(not any(c[:4] == ["spo", "site", "admin", "add"] and SRC.rstrip("/") in c for c in fake.calls),
      "no access is added where it already exists")

# ---- 3. 'keep my access' --------------------------------------------------------
fake = FakeM365()
result, text, asked, report = go(fake, {"access": m.TRANSFER_ACCESS_KEEP})
check(OPERATOR in fake.admins[DST.rstrip("/")] and OPERATOR in fake.admins[SRC.rstrip("/")],
      "'Keep my access' leaves the admin on both OneDrives")

# ---- 4. saying No at the confirmation copies nothing, still cleans up ------------
fake = FakeM365()
result, text, asked, report = go(fake, answer=False)
check(not result["ok"] and not fake.copied, "No at the confirmation: nothing copied")
check(OPERATOR not in fake.admins[SRC.rstrip("/")], "...and the temporary access is removed")

# ---- 5. refusals before anything happens -----------------------------------------
for vals, why in (({"to": "jdoe@contoso.com"}, "the same person twice"),
                  ({"from": ""}, "a blank From box"),
                  ({"to": "nobody"}, "a To box that is not an address"),
                  ({"folder": "a/b"}, "a folder name SharePoint does not allow"),
                  ({"folder": "x:y"}, "a folder name with ':'")):
    fake = FakeM365()
    result, text, asked, report = go(fake, vals)
    check(not result["ok"] and not fake.calls, "refused before running anything: " + why)

fake = FakeM365(no_site=("asmith@contoso.com",))
result, text, asked, report = go(fake)
check(not result["ok"] and "has no OneDrive yet" in text and not fake.copied,
      "a recipient whose OneDrive was never set up is explained, nothing copied")

fake = FakeM365(fail=("admin list",))
result, text, asked, report = go(fake)
check(not result["ok"] and "SharePoint" in text and not fake.copied,
      "no SharePoint admin access -> a clear message, nothing copied")

# ---- 6. a failed copy is reported and the rest carries on -------------------------
fake = FakeM365(fail=("Budget & Plan",))
result, text, asked, report = go(fake)
check(result["copied"] == 2 and result["failed"] == 1 and "FAILED" in text,
      "one failed copy is reported; the others still copy")
check(OPERATOR not in fake.admins[DST.rstrip("/")], "...and the temporary access is still removed")

# ---- 7. Stop part-way ---------------------------------------------------------------
fake = FakeM365()
result, text, asked, report = go(fake, cancel_after=1)
check(len(fake.copied) == 1 and "Stopped" in text, "Stop ends the copying after the current item")
check(OPERATOR not in fake.admins[SRC.rstrip("/")], "...and still removes the temporary access")

# ---- 8. the count check catches missing files ---------------------------------------
fake = FakeM365(dst_extra=-1)
result, text, asked, report = go(fake)
check("WARNING" in text and "3 of 4" in text, "fewer files at the destination -> a WARNING")

# ---- 9. folder names -----------------------------------------------------------------
check(m.default_transfer_folder("j.doe@contoso.com").startswith("Files from j.doe "),
      "default folder: 'Files from <name> MM-DD-YYYY'")
check(m.onedrive_paths(SRC) == (SRC.rstrip("/"), HOST, SRC_LIB), "OneDrive address -> site, host, library")

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
