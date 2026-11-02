# test_v015_move_to_site.py - v0.15 (10-29-2026): 'Move a user's OneDrive
# files to a Team or SharePoint site' (m365_workflows.move_to_site) against a
# fake m365 whose answers have the shapes seen live (read-only) on
# 10-29-2026: spo site list GroupId '/Guid(<id>)/', spo list list with
# RootFolder/ServerRelativeUrl, spo listitem list with FSObjType '0'/'1' and
# File/Length, listitem get --withPermissions RoleAssignments. Checks: the
# boxes, Team -> site, the sharing record BEFORE the question, nothing moves
# without a yes, the move commands, the count check and the temporary access
# always taken back. Nothing runs.
import csv, json, os, shutil, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_workflows as wf
import m365_catalog as cat

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

OD = "https://contoso-my.sharepoint.com/personal/pat_contoso_com"
LIB = "/personal/pat_contoso_com/Documents"
SITE = "https://contoso.sharepoint.com/sites/Grade5"
TARGET_SRV = "/sites/Grade5/Shared Documents/Files from pat"
ITEMS = [
    {"Id": 1, "FileRef": LIB + "/Reports", "FSObjType": "1", "HasUniqueRoleAssignments": True},
    {"Id": 2, "FileRef": LIB + "/Reports/q1.xlsx", "FSObjType": "0", "HasUniqueRoleAssignments": False,
     "File": {"Length": 3000}},
    {"Id": 3, "FileRef": LIB + "/plan.docx", "FSObjType": "0", "HasUniqueRoleAssignments": True,
     "File": {"Length": 1000}},
    {"Id": 4, "FileRef": LIB + "/Forms/AllItems.aspx", "FSObjType": "0", "HasUniqueRoleAssignments": False,
     "File": {"Length": 50}},
]


def make_run(calls, teams=None, libs=None, landed=2, move_fail=False, admins=None):
    teams = teams if teams is not None else [{"id": "T-1", "displayName": "Grade 5"}]
    libs = libs if libs is not None else [
        {"Title": "Documents", "RootFolder": {"ServerRelativeUrl": "/sites/Grade5/Shared Documents"}}]
    def run(argv):
        calls.append(list(argv))
        a = argv
        if a[0] == "status":
            return 0, json.dumps({"connectedAs": "admin@contoso.com"})
        if a[:3] == ["entra", "user", "get"]:
            return 0, json.dumps({"userPrincipalName": "pat@contoso.com", "mySite": OD + "/"})
        if a[:3] == ["teams", "team", "list"]:
            return 0, json.dumps(teams)
        if a[:3] == ["spo", "site", "list"]:
            return 0, json.dumps([{"Url": "https://contoso.sharepoint.com/sites/Other", "GroupId": "/Guid(x-9)/"},
                                  {"Url": SITE, "GroupId": "/Guid(t-1)/"}])
        if a[:4] == ["spo", "site", "admin", "list"]:
            return 0, json.dumps(admins or [])
        if a[:4] in (["spo", "site", "admin", "add"], ["spo", "site", "admin", "remove"]):
            return 0, "{}"
        if a[:3] == ["spo", "list", "list"]:
            return 0, json.dumps(libs)
        if a[:3] == ["spo", "listitem", "list"]:
            return 0, json.dumps(ITEMS)
        if a[:3] == ["spo", "listitem", "get"]:
            return 0, json.dumps({"RoleAssignments": [
                {"Member": {"Title": "Lee Teacher", "LoginName": "i:0#.f|membership|lee@contoso.com"},
                 "RoleDefinitionBindings": [{"Name": "Contribute"}]}]})
        if a[:3] == ["spo", "folder", "add"]:
            return 0, json.dumps({"ServerRelativeUrl": TARGET_SRV})
        if a[:2] == ["spo", "folder"] and a[2] == "move" or a[:3] == ["spo", "file", "move"]:
            return (1, '{"error":"Access denied"}') if move_fail else (0, "{}")
        if a[:3] == ["spo", "file", "list"]:
            return 0, json.dumps([{"Name": "f%d" % i} for i in range(landed)])
        return 1, '{"error":"unexpected %s"}' % " ".join(a[:4])
    return run


def go(values, answer=True, **kw):
    calls, lines, asked = [], [], []
    base = tempfile.mkdtemp(prefix="m365move_")
    def confirm(q):
        asked.append((q, len(calls)))
        return answer
    res = wf.move_to_site(make_run(calls, **kw), lines.append, confirm, lambda: False, values, base)
    return res, calls, "".join(lines), asked, base

V = {"from": "pat@contoso.com", "team": "grade 5", "folder": "Files from pat", "access": cat.TRANSFER_ACCESS_REMOVE}

# ---- the happy path, by Team --------------------------------------------------------
res, calls, text, asked, base = go(dict(V))
moves = [c for c in calls if len(c) > 2 and c[2] == "move"]
check(res["ok"] and res["moved"] == 2 and res["failed"] == 0, "moves the 2 top-level items (%s)" % res)
check(len(asked) == 1 and not any(len(c) > 2 and c[2] == "move" for c in calls[:asked[0][1]]),
      "asks ONCE, before anything moves")
check("MOVE 2 files (3.9 KB) - 2 top-level item(s)" in asked[0][0] and "Grade5" in asked[0][0]
      and "2 item(s) were shared on their own" in asked[0][0], "the question has the counts, size and sharing")
check(not any("Forms" in " ".join(c) for c in moves), "the library's Forms pages are not moved")
fm = [c for c in moves if c[1] == "folder"][0]
f = [c for c in moves if c[1] == "file"][0]
check(fm[:8] == ["spo", "folder", "move", "--webUrl", OD, "--sourceUrl", LIB + "/Reports", "--targetUrl"]
      and fm[8] == "https://contoso.sharepoint.com" + TARGET_SRV and "rename" in fm,
      "folder move: from the OneDrive to the ABSOLUTE target URL, rename on a clash")
check("--bypassSharedLock" in f and "--bypassSharedLock" not in fm, "a file left open still moves (files only)")
check(any(c[:4] == ["spo", "site", "admin", "add"] and c[5] == OD for c in calls)
      and any(c[:4] == ["spo", "site", "admin", "add"] and c[5] == SITE for c in calls),
      "temporary access on the OneDrive and the Team site")
removed = [c[5] for c in calls if c[:4] == ["spo", "site", "admin", "remove"]]
check(sorted(removed) == sorted([OD, SITE]), "the temporary access is taken back afterwards")
with open(os.path.join(res["folder"], "sharing-before.csv"), encoding="utf-8") as fh:
    rows = list(csv.reader(fh))
check(rows[0] == ["item", "type", "who", "sign-in name", "permission"] and len(rows) == 3
      and rows[1][:3] == [LIB + "/Reports", "folder", "Lee Teacher"] and rows[2][1] == "file"
      and rows[1][4] == "Contribute", "sharing-before.csv: who and what level, for each item shared on its own")
with open(os.path.join(res["folder"], "moved.csv"), encoding="utf-8") as fh:
    check(len(list(csv.reader(fh))) == 3, "moved.csv: one row per top-level item")
check("Check: 2 of 2 files are in the new folder." in text, "counts what arrived")

# ---- No at the question: nothing moves, access still taken back -------------------
res, calls, text, asked, base = go(dict(V), answer=False)
check(not res["ok"] and "nothing was moved" in res["error"]
      and not any(len(c) > 2 and c[2] == "move" for c in calls)
      and not any(c[:3] == ["spo", "folder", "add"] for c in calls), "No: nothing is created or moved")
check(len([c for c in calls if c[:4] == ["spo", "site", "admin", "remove"]]) == 2, "No: access is still taken back")
check(os.path.isfile(os.path.join(res["folder"], "sharing-before.csv")), "No: the sharing record is still kept")

# ---- by Site URL + library; keep access; already an admin -------------------------
res, calls, text, asked, base = go({"from": "pat@contoso.com", "url": SITE + "/", "library": "shared documents",
                                    "access": cat.TRANSFER_ACCESS_KEEP},
                                   admins=[{"Email": "admin@contoso.com"}])
check(res["ok"] and not any(c[:3] == ["teams", "team", "list"] for c in calls), "Site URL: no Team lookup")
check(not any(c[:4] in (["spo", "site", "admin", "add"], ["spo", "site", "admin", "remove"]) for c in calls),
      "already a site admin: no access added or removed")
fa = [c for c in calls if c[:3] == ["spo", "folder", "add"]][0]
check(fa[fa.index("--name") + 1].startswith("Files from pat "), "default folder 'Files from <name> <date>'")

# ---- problems stop BEFORE anything changes -------------------------------------------
for values, kw, want in (
        ({"from": "pat", "team": "Grade 5"}, {}, "sign-in name"),
        ({"from": "pat@contoso.com"}, {}, "EITHER the Team box OR the Site URL"),
        ({"from": "pat@contoso.com", "team": "Grade 5", "url": SITE}, {}, "EITHER the Team box OR the Site URL"),
        ({"from": "pat@contoso.com", "url": "contoso"}, {}, "needs a site address"),
        ({"from": "pat@contoso.com", "team": "Grade 5", "folder": "a/b"}, {}, "folder name cannot contain"),
        ({"from": "pat@contoso.com", "team": "Nope"}, {}, "No Team is called 'Nope'"),
        ({"from": "pat@contoso.com", "team": "Grade 5"},
         {"teams": [{"id": "T-1", "displayName": "Grade 5"}, {"id": "T-2", "displayName": "Grade 5"}]},
         "2 Teams are called"),
        ({"from": "pat@contoso.com", "team": "Grade 5", "library": "Policies"}, {}, "has no library called 'Policies'")):
    res, calls, text, asked, base = go(values, **kw)
    check(want in res["error"] and not asked and not any(len(c) > 2 and c[2] in ("move", "add") and c[1] in ("folder", "file")
                                                         for c in calls), "stops: %s" % want)
    check(len([c for c in calls if c[:4] == ["spo", "site", "admin", "add"]]) ==
          len([c for c in calls if c[:4] == ["spo", "site", "admin", "remove"]]), "  ... and gives back any access it added")

# ---- a failed move / missing files are reported ---------------------------------------
res, calls, text, asked, base = go(dict(V), move_fail=True, landed=0)
check(not res["ok"] and res["failed"] == 2 and "FAILED" in text and "still in pat@contoso.com's OneDrive" in text,
      "a failed move is reported and not called OK")

# ---- the catalog task ---------------------------------------------------------------
task = next(t for t in cat.TASKS["OneDrive"] if t["workflow"] == "move_to_site")
check(task["destructive"] and "MOVE" in cat.WORKFLOW_PLANS["move_to_site"], "catalog: a changing (destructive) workflow")
check([f["key"] for f in task["fields"]] == ["from", "team", "url", "library", "folder", "access"],
      "catalog: From, Team, Site URL, Library, Folder, Afterwards")
check(cat.picker_kind("OneDrive", task, task["fields"][1]) == "group", "catalog: Pick... a Team")
for front in ("M365GUI.py", "m365_web.py"):
    with open(os.path.join(os.path.dirname(HERE), front), encoding="utf-8") as fh:
        check("move_to_site(" in fh.read(), front + " runs the workflow")
print("FAILURES:", len(fails))
