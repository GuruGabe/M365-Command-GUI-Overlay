# test_v014_sharepoint_more.py - v0.14 (10-29-2026): nine read-only tasks -
# SharePoint groups and their members, a site's lists and libraries, files in
# a folder (with and without subfolders), sharing links and sharing details
# for one file, hub sites, and one person's Teams apps. Checked against the
# CLI's --help (v11.11) and run live (read-only) on 10-29-2026. Builds each
# command - nothing runs.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def find(name):
    for cat, items in c.TASKS.items():
        for t in items:
            if t["name"] == name:
                return cat, t
    return None, None

def build(name, **values):
    cat, task = find(name)
    return c.build_command(task, values, cat)

SITE = "https://contoso.sharepoint.com/sites/Team"
NEW = {"SharePoint groups on a site": "SharePoint",
       "Members of a SharePoint group": "SharePoint",
       "Lists and libraries on a site": "SharePoint",
       "Files in a folder": "SharePoint",
       "Every file in a folder, subfolders included": "SharePoint",
       "Sharing links on a file": "SharePoint",
       "Who can open a file (sharing details)": "SharePoint",
       "Hub sites": "SharePoint",
       "Teams apps a person has installed": "Teams / M365 Groups"}
for name, section in NEW.items():
    cat, task = find(name)
    check(cat == section, "%s is in %s (%s)" % (name, section, cat))
    check(task is not None and not task["destructive"], "%s is read-only (no ask)" % name)
    verb = task["template"].split(" --")[0].split()[-1] if task else ""
    check(verb in ("list", "get"), "%s: a list/get command (%s)" % (name, verb))

_d, argv, err = build("SharePoint groups on a site", url=SITE)
check(not err and argv == ["spo", "group", "list", "--webUrl", SITE, "--output", "text"],
      "groups: %s" % argv)

_d, argv, err = build("Members of a SharePoint group", url=SITE, group="Team Members")
check(not err and argv == ["spo", "group", "member", "list", "--webUrl", SITE, "--groupName",
                           "Team Members", "--output", "text"],
      "group members: a group name with spaces stays ONE argument")
_d, argv, err = build("Members of a SharePoint group", url=SITE, group="")
check(bool(err), "group members: the group name is required (%s)" % err)

# The OData filter is one argument; hidden system lists are left out.
_d, argv, err = build("Lists and libraries on a site", url=SITE)
check(not err and argv == ["spo", "list", "list", "--webUrl", SITE, "--filter", "Hidden eq false",
                           "--output", "text"], "lists: %s" % argv)

cat, task = find("Files in a folder")
check(task["fields"][1]["default"] == "Shared Documents", "files: folder defaults to Shared Documents")
_d, argv, err = build("Files in a folder", url=SITE, folder="Shared Documents/Reports 2026")
check(not err and argv == ["spo", "file", "list", "--webUrl", SITE, "--folderUrl",
                           "Shared Documents/Reports 2026", "--output", "text"]
      and "--recursive" not in argv, "files: one folder, spaces kept, no --recursive")
_d, argv, err = build("Every file in a folder, subfolders included", url=SITE, folder="Shared Documents")
check(not err and "--recursive" in argv and argv[-2:] == ["--output", "text"],
      "every file: --recursive")

FILE = "/sites/Team/Shared Documents/report 1.docx"
_d, argv, err = build("Sharing links on a file", url=SITE, file=FILE, scope="")
check(not err and argv == ["spo", "file", "sharinglink", "list", "--webUrl", SITE, "--fileUrl", FILE,
                           "--output", "text"], "links: blank scope = all (no --scope)")
_d, argv, err = build("Sharing links on a file", url=SITE, file=FILE, scope="anonymous")
check(not err and argv[-4:] == ["--scope", "anonymous", "--output", "text"], "links: anonymous only")
cat, task = find("Sharing links on a file")
check(task["fields"][2]["choices"] == ["", "anonymous", "users", "organization"],
      "links: the CLI's three scopes + blank")

# Text and CSV output of sharinginfo are EMPTY (found live 10-29-2026) - JSON only.
_d, argv, err = build("Who can open a file (sharing details)", url=SITE, file=FILE)
check(not err and argv == ["spo", "file", "sharinginfo", "get", "--webUrl", SITE, "--fileUrl", FILE,
                           "--output", "json"], "sharing details: --output json")
cat, task = find("Who can open a file (sharing details)")
check(not c.saves_output(task), "sharing details: no Save to CSV (the CLI's CSV is empty)")

_d, argv, err = build("Hub sites")
check(not err and argv == ["spo", "hubsite", "list", "--output", "text"], "hub sites: %s" % argv)

_d, argv, err = build("Teams apps a person has installed", email="jsmith@contoso.com")
check(not err and argv == ["teams", "user", "app", "list", "--userName", "jsmith@contoso.com",
                           "--output", "text"], "user apps: %s" % argv)
cat, task = find("Teams apps a person has installed")
check(c.picker_kind(cat, task, task["fields"][0]) == "user", "user apps: Pick... a user")

# A pasted site address in curly quotes is cleaned (url is an identifier box).
_d, argv, err = build("SharePoint groups on a site", url=chr(0x201c) + SITE + chr(0x201d))
check(not err and argv[4] == SITE, "groups: curly quotes around a pasted URL are removed")
print("FAILURES:", len(fails))
