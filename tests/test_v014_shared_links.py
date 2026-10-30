# test_v014_shared_links.py - v0.14 (10-29-2026): 'Files shared by link in a
# folder' (m365_workflows.shared_links) against a fake m365 that answers
# 'spo file list' and 'spo file sharinglink list' like the CLI (JSON shapes
# from 'm365 spo file sharinglink list --help response' and a live read-only
# run). Checks: only reads, Forms pages skipped, --recursive / --scope
# follow the form, notes for editable / never-expiring 'anyone' links, link
# ADDRESSES never shown or saved, a failed file is reported, Stop works.
import csv, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c
import m365_workflows as wf

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

SITE = "https://contoso.sharepoint.com/sites/Team"
SECRET = "https://contoso.sharepoint.com/:w:/s/Team/SECRETLINKADDRESS"
FILES = [
    {"Name": "AllItems.aspx", "ServerRelativeUrl": "/sites/Team/Shared Documents/Forms/AllItems.aspx",
     "UniqueId": "forms-1"},
    {"Name": "plan.docx", "ServerRelativeUrl": "/sites/Team/Shared Documents/plan.docx", "UniqueId": "f1"},
    {"Name": "grades.xlsx", "ServerRelativeUrl": "/sites/Team/Shared Documents/Sub/grades.xlsx",
     "UniqueId": "f2"},
    {"Name": "quiet.pdf", "ServerRelativeUrl": "/sites/Team/Shared Documents/quiet.pdf", "UniqueId": "f3"},
    {"Name": "broken.txt", "ServerRelativeUrl": "/sites/Team/Shared Documents/broken.txt", "UniqueId": "f4"},
]
LINKS = {
    "f1": [{"id": "l1", "roles": ["write"], "hasPassword": False,
            "link": {"scope": "anonymous", "type": "edit", "webUrl": SECRET, "preventsDownload": False}},
           {"id": "l2", "roles": ["read"], "hasPassword": False,
            "grantedToIdentitiesV2": [{"user": {"displayName": "Pat", "email": "pat@contoso.com"}}],
            "link": {"scope": "users", "type": "view", "webUrl": SECRET}}],
    "f2": [{"id": "l3", "roles": ["read"], "hasPassword": True, "expirationDateTime": "2026-12-31T00:00:00Z",
            "link": {"scope": "anonymous", "type": "view", "webUrl": SECRET, "preventsDownload": True}}],
    "f3": [],
}


def make_run(calls, stop_after=None, state=None):
    def run(argv):
        calls.append(list(argv))
        if state is not None and stop_after is not None and len(calls) >= stop_after:
            state["stop"] = True
        if argv[:3] == ["spo", "file", "list"]:
            import json
            return 0, json.dumps(FILES)
        if argv[:4] == ["spo", "file", "sharinglink", "list"]:
            import json
            fid = argv[argv.index("--fileId") + 1]
            if fid == "forms-1":
                return 1, '{"error":"Resource not found for the segment"}'
            if fid == "f4":
                return 1, '{"error":"Access denied."}'
            links = LINKS[fid]
            if "--scope" in argv:
                links = [l for l in links if l["link"]["scope"] == argv[argv.index("--scope") + 1]]
            return 0, json.dumps(links)
        return 1, '{"error":"unexpected"}'
    return run


def go(values, stop_after=None):
    calls, lines, state = [], [], {"stop": False}
    tmp = tempfile.mkdtemp(prefix="m365share_")
    result = wf.shared_links(make_run(calls, stop_after, state), lines.append,
                             lambda: state["stop"], values, tmp)
    return result, calls, "".join(lines), tmp


# ---- the catalog task ----------------------------------------------------------
cat, task = next(((k, t) for k, ts in c.TASKS.items() for t in ts
                  if t["name"] == "Files shared by link in a folder"), (None, None))
check(cat == "SharePoint" and task["workflow"] == "shared_links" and not task["destructive"],
      "the task is in SharePoint, runs the shared_links workflow, read-only")
check("read-only" in c.WORKFLOW_PLANS["shared_links"], "its plan says read-only")
keys = {f["key"]: f for f in task["fields"]}
check(keys["kind"]["default"] == c.SHARE_ANYONE and keys["subfolders"]["default"] == "Yes"
      and keys["folder"]["default"] == "Shared Documents", "defaults: anyone links, subfolders, Shared Documents")

# ---- anyone links only (the default) -------------------------------------------
r, calls, text, tmp = go({"url": SITE, "folder": "Shared Documents", "subfolders": "Yes",
                          "kind": c.SHARE_ANYONE})
check(all(cl[:2] == ["spo", "file"] and cl[2] in ("list", "sharinglink") and
          (cl[2] == "list" or cl[3] == "list") for cl in calls), "only list commands were run")
check(calls[0] == ["spo", "file", "list", "--webUrl", SITE, "--folderUrl", "Shared Documents",
                   "--recursive", "--output", "json"], "file list: --recursive with subfolders")
check(not any("forms-1" in cl for cl in calls), "the Forms page is skipped")
check(all(cl[-4:-2] == ["--scope", "anonymous"] for cl in calls[1:]), "every link check has --scope anonymous")
check(r["files"] == 4 and r["links"] == 2, "4 files checked, 2 anyone links (%s)" % r)
check("1 'anyone' link(s) let whoever has the link EDIT" in text, "note: editable anyone link")
check("1 'anyone' link(s) never expire" in text, "note: anyone link without expiry")
check("COULD NOT CHECK: /sites/Team/Shared Documents/broken.txt - " in text and not r["ok"],
      "a file that cannot be checked is reported and the run is not OK")
check(SECRET not in text, "no link address on screen")
saved = os.path.join(r["folder"], "shared-links.csv")
rows = list(csv.DictReader(open(saved, encoding="utf-8")))
check(os.path.isfile(saved) and len(rows) == 3, "shared-links.csv: 2 links + 1 could-not-check row")
check(SECRET not in open(saved, encoding="utf-8").read(), "no link address in the CSV")
grades = next(x for x in rows if x["file"].endswith("grades.xlsx"))
check(grades["expires"] == "2026-12-31" and grades["password"] == "yes" and grades["blocks download"] == "yes",
      "expiry, password and blocks download are recorded")

# ---- every link, this folder only ----------------------------------------------
r, calls, text, tmp = go({"url": SITE, "folder": "/Shared Documents/", "subfolders": "No",
                          "kind": c.SHARE_ALL})
check(calls[0] == ["spo", "file", "list", "--webUrl", SITE, "--folderUrl", "Shared Documents",
                   "--output", "json"], "no --recursive; slashes around the folder trimmed")
check(not any("--scope" in cl for cl in calls), "every kind: no --scope")
check(r["links"] == 3 and "users, view" in text and "for pat@contoso.com" in text,
      "a specific-people link shows who it is for")

# ---- form checks, Stop -----------------------------------------------------------
r, calls, text, tmp = go({"url": "contoso", "folder": "Shared Documents"})
check(not calls and "needs a site address" in r["error"], "a site address is required (nothing run)")
r, calls, text, tmp = go({"url": SITE, "folder": "  "})
check(not calls and "Folder box" in r["error"], "a folder is required")
r, calls, text, tmp = go({"url": "\u201c" + SITE + "/\u201d", "folder": "Shared Documents"})
check(calls and calls[0][4] == SITE, "curly quotes and a trailing slash around the site are removed")
r, calls, text, tmp = go({"url": SITE, "folder": "Shared Documents", "kind": c.SHARE_ALL}, stop_after=2)
check("[Stopped after 1 of 4 file(s).]" in text and not r["ok"], "Stop ends the run after the current file")
print("FAILURES:", len(fails))
