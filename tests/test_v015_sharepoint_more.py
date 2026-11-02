# test_v015_sharepoint_more.py - v0.15 (10-30-2026): six read-only SharePoint
# tasks - a site's owners / members / visitors, people and groups added to a
# site, permission levels, version history settings, earlier versions of a
# file and sharing links on a folder. Checked against the CLI's --help
# (v11.11) and run live (read-only) on 10-30-2026. Builds each command -
# nothing runs.
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
NEW = ["Owners, members and visitors of a site", "People and groups added to a site",
       "Permission levels on a site", "Version history settings of a site",
       "Earlier versions of a file", "Sharing links on a folder"]
for name in NEW:
    cat, task = find(name)
    check(cat == "SharePoint", "%s is in SharePoint (%s)" % (name, cat))
    check(task is not None and not task["destructive"], "%s is read-only (no ask)" % name)
    verb = task["template"].split(" --")[0].split()[-1] if task else ""
    check(verb in ("list", "get"), "%s: a list/get command (%s)" % (name, verb))
    check(task["desc"].isascii() and task["template"].endswith("--output text"), "%s: ASCII, text output" % name)

_d, argv, err = build("Owners, members and visitors of a site", url=SITE, role="")
check(not err and argv == ["spo", "site", "membership", "list", "--siteUrl", SITE, "--output", "text"],
      "membership: blank role = all (%s)" % argv)
_d, argv, err = build("Owners, members and visitors of a site", url=SITE, role="Owner")
check(not err and argv[-4:] == ["--role", "Owner", "--output", "text"], "membership: owners only")
cat, task = find("Owners, members and visitors of a site")
check(task["fields"][1]["choices"] == ["", "Owner", "Member", "Visitor"], "membership: the CLI's three roles + blank")

for name, verb in (("People and groups added to a site", ["spo", "user", "list", "--webUrl"]),
                   ("Permission levels on a site", ["spo", "roledefinition", "list", "--webUrl"]),
                   ("Version history settings of a site", ["spo", "site", "versionpolicy", "get", "--siteUrl"])):
    _d, argv, err = build(name, url=SITE)
    check(not err and argv == verb + [SITE, "--output", "text"], "%s: %s" % (name, argv))
    cat, task = find(name)
    check("open the site" in task["desc"], "%s: says you must be able to open the site" % name)

FILE = "/sites/Team/Shared Documents/report 1.docx"
_d, argv, err = build("Earlier versions of a file", url=SITE, file=FILE)
check(not err and argv == ["spo", "file", "version", "list", "--webUrl", SITE, "--fileUrl", FILE,
                           "--output", "text"], "versions: a path with spaces stays ONE argument")
_d, argv, err = build("Earlier versions of a file", url=SITE, file="")
check(bool(err), "versions: the file is required (%s)" % err)

FOLDER = "/sites/Team/Shared Documents/Projects 2026"
_d, argv, err = build("Sharing links on a folder", url=SITE, folder=FOLDER, scope="")
check(not err and argv == ["spo", "folder", "sharinglink", "list", "--webUrl", SITE, "--folderUrl", FOLDER,
                           "--output", "text"], "folder links: blank scope = all (no --scope)")
_d, argv, err = build("Sharing links on a folder", url=SITE, folder=FOLDER, scope="anonymous")
check(not err and argv[-4:] == ["--scope", "anonymous", "--output", "text"], "folder links: anonymous only")

# Pages / navigation / list items (live 10-30-2026 on the root site).
for name in ("Pages on a site", "Navigation links on a site", "Items in a list"):
    cat, task = find(name)
    check(cat == "SharePoint" and not task["destructive"], "%s: SharePoint, read-only" % name)
_d, argv, err = build("Pages on a site", url=SITE)
check(not err and argv == ["spo", "page", "list", "--webUrl", SITE, "--query",
                           "[].{Title:Title,FileName:FileName,Url:Url,Modified:Modified}", "--output", "text"],
      "pages: the JMESPath query is ONE argument and not taken for a box (%s)" % argv)
cat, task = find("Navigation links on a site")
check(task["fields"][1]["default"] == "QuickLaunch" and task["fields"][1]["choices"] == ["QuickLaunch", "TopNavigationBar"],
      "navigation: the CLI's two menus, left menu first")
_d, argv, err = build("Navigation links on a site", url=SITE, location="TopNavigationBar")
check(not err and argv == ["spo", "navigation", "node", "list", "--webUrl", SITE, "--location", "TopNavigationBar",
                           "--output", "text"], "navigation: %s" % argv)
_d, argv, err = build("Items in a list", url=SITE, list="Site Pages", fields="")
check(not err and argv == ["spo", "listitem", "list", "--webUrl", SITE, "--listTitle", "Site Pages", "--output", "text"],
      "list items: no columns = no --fields; a name with a space stays ONE argument")
_d, argv, err = build("Items in a list", url=SITE, list="Announcements", fields="Id,Title,Modified")
check(not err and argv[-4:] == ["--fields", "Id,Title,Modified", "--output", "text"], "list items: chosen columns")
_d, argv, err = build("Items in a list", url=SITE, list="", fields="")
check(bool(err), "list items: the list name is required (%s)" % err)

# CLI v11.11 prints 'spo externaluser list' only when SharePoint's
# TotalUserCount > 0; live 10-30-2026 SharePoint sent people with a count of 0,
# so nothing at all was shown. The task says so and points to the guest list.
ext = [t for items in c.TASKS.values() for t in items if t["template"].startswith("spo externaluser list")]
check(len(ext) == 1 and "List guest users" in ext[0]["desc"] and "v11.11" in ext[0]["desc"],
      "external users: warns that the CLI may hide the list and points to 'List guest users'")
# 11-02-2026: the maintainers fixed it (#7674, closed 10-31) in the CLI 12.0 beta.
check("fixed in CLI 12.0" in ext[0]["desc"], "external users: says the CLI 12.0 fix")
check(find("List guest users")[1] is not None, "external users: the task it points to exists")
print("FAILURES:", len(fails))
