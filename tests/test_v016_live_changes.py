# test_v016_live_changes.py - v0.16 (11-02-2026): the second live run of the
# tasks that CHANGE things, on throwaway objects only (a new user made and
# permanently deleted, throwaway Teams and groups). Worked as built: Create
# user, Block / Unblock sign-in, Sign user out everywhere, Delete user,
# Restore deleted user, Permanently delete a user from the recycle bin,
# Create a Team, Add / Delete a channel, Archive / Unarchive a Team, Delete a
# Team. Found and fixed:
#  - Create group (microsoft365) was refused without --visibility although
#    the CLI docs say it defaults to Public -> a 'Who can see and join it' box.
#  - Restore a deleted Microsoft 365 group took only a name; two deleted
#    groups with one name -> 'Multiple groups ... found' -> it takes the id.
#  - Signed in as yourself, the CLI refuses another person's mailbox settings
#    ('... only if CLI is authenticated in app-only mode'), and another
#    person's calendars answer 'Access is denied' -> the tasks and the staff
#    hand-off say so (and what to do instead).
# This file pins those commands and texts - nothing runs.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c
import m365_workflows as wf

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def task(cat, name):
    return [t for t in c.TASKS[cat] if t["name"] == name][0]

def build(cat, name, values):
    t = task(cat, name)
    _d, argv, err = c.build_command(t, values, cat)
    return t, (err or argv)

# ---- Create group: visibility -------------------------------------------------------
t, argv = build("Groups (Entra)", "Create group", {"name": "Band", "type": "microsoft365", "vis": "Private"})
check(argv[:6] == ["entra", "group", "add", "--displayName", "Band", "--type"]
      and argv[argv.index("--visibility") + 1] == "Private",
      "a Microsoft 365 group is created with --visibility (%s)" % argv)
_t, argv = build("Groups (Entra)", "Create group", {"name": "Lab", "type": "security"})
check("--visibility" not in argv, "a security group: no --visibility when the box is blank")
vis = [f for f in t["fields"] if f["key"] == "vis"][0]
check(vis["choices"] == ["", "Private", "Public", "HiddenMembership"] and not vis["required"],
      "the box offers Private / Public / HiddenMembership and may be blank")
check("needs 'Who can see" in t["desc"] and "blank for a security group" in t["desc"],
      "the description says when it is needed")

# ---- Restore a deleted Microsoft 365 group: name OR id -------------------------
gid = "a359444b-a94b-4a8a-ad56-cf66c4b03a40"
t, argv = build("Teams / M365 Groups", "Restore a deleted Microsoft 365 group", {"id": gid})
check(argv == ["entra", "m365group", "recyclebinitem", "restore", "--id", gid],
      "restore by id (live 11-02-2026)")
_t, argv = build("Teams / M365 Groups", "Restore a deleted Microsoft 365 group", {"deleted": "Band"})
check(argv == ["entra", "m365group", "recyclebinitem", "restore", "--displayName", "Band"],
      "restore by name still works")
check("run it again with the id" in t["desc"], "the description says what to do when two have that name")

# ---- another person's mailbox: app-only -------------------------------------------
for name in ["A user's mailbox settings", "Turn on automatic replies (until turned off)",
             "Turn on automatic replies for dates (scheduled)", "Turn off automatic replies"]:
    check("app-only" in task("Outlook", name)["desc"], "%s: says it needs an app-only sign-in" % name)
for name in ["A user's calendars", "A user's calendar events"]:
    check("Access is denied" in task("Outlook", name)["desc"], "%s: explains 'Access is denied'" % name)
check("Full Access" in task("Outlook", "Messages in a user's mail folder")["desc"],
      "mail folder: says Full Access is needed")
handoff = task("Users (Entra ID)", "Staff hand-off - someone is leaving")
check(any(f["key"] == "autoreply" and "app-only" in f["label"] for f in handoff["fields"]),
      "staff hand-off: the automatic reply choice says it needs an app-only sign-in")
check(all(task(cat, n)["desc"].isascii() for cat, n in
          [("Outlook", "Turn off automatic replies"), ("Groups (Entra)", "Create group")]),
      "the new texts are ASCII")

# ---- the staff hand-off says what to do when the reply cannot be set ---------------
calls, lines = [], []
def fake_run(argv):
    calls.append(argv)
    if argv[:4] == ["outlook", "mailbox", "settings", "set"]:
        return 1, ('{"error":"You can update mailbox settings of other users only if CLI is '
                   'authenticated in app-only mode"}')
    if argv[:3] == ["entra", "user", "get"]:
        return 0, '{"id": "u1", "displayName": "Leaver", "userPrincipalName": "leaver@example.com"}'
    return 0, "[]"
import tempfile
values = {"leaver": "leaver@example.com", "manager": "", "block": "No", "signout": "No",
          "copy": "No", "autoreply": "Yes", "reply": "Gone", "groups": "No", "licenses": "No"}
try:
    wf.staff_handoff(fake_run, lines.append, lambda q: True, lambda: False, values,
                     tempfile.mkdtemp(prefix="m365handoff_"))
except Exception as exc:                       # the signature is pinned by older tests
    lines.append("CRASH %r" % exc)
text = "".join(lines)
check("FAILED  Set an automatic reply" in text and "Exchange admin center" in text
      and "CRASH" not in text, "staff hand-off: a refused reply step says to use the Exchange admin center")

# ---- Archive read-only: Microsoft's reason when the Team's site is not ready -------
check("site url is not available" in task("Teams / M365 Groups",
                                            "Archive a Team and make its files read-only")["desc"],
      "read-only archive: explains the BadRequest seen live (the Team's site was not ready)")

# ---- Lock a site: SharePoint Online refuses NoAdditions --------------------------
lock = task("SharePoint", "Lock a site or make it read-only")
check([f for f in lock["fields"] if f["key"] == "lock"][0]["choices"] == ["ReadOnly", "NoAccess", "Unlock"]
      and "NoAdditions" not in lock["desc"],
      "lock a site: only the states SharePoint Online accepts (live: NoAdditions refused)")

# ---- administrative units: the new Remove task ------------------------------------
t, argv = build("Roles and admin units", "Remove a user from an administrative unit (DESTRUCTIVE)",
                {"au": "North Campus", "email": "a@example.com"})
check(argv == ["entra", "administrativeunit", "member", "remove", "--administrativeUnitName",
               "North Campus", "--userName", "a@example.com", "--force"] and t["destructive"],
      "remove a user from an administrative unit (live 11-02-2026)")
names = [x["name"] for x in c.TASKS["Roles and admin units"]]
check(names.index("Remove a user from an administrative unit (DESTRUCTIVE)")
      == names.index("Add a user to an administrative unit") + 1, "it sits right after Add")

LIVE_OK = [("Users (Entra ID)", "Create user", {"display": "A", "email": "a@example.com", "password": "x"}),
           ("Users (Entra ID)", "Block sign-in", {"email": "a@example.com"}),
           ("Users (Entra ID)", "Unblock sign-in", {"email": "a@example.com"}),
           ("Security", "Sign user out everywhere", {"email": "a@example.com"}),
           ("Users (Entra ID)", "Delete user (DESTRUCTIVE)", {"email": "a@example.com"}),
           ("Users (Entra ID)", "Restore deleted user", {"id": "u1"}),
           ("Users (Entra ID)", "Permanently delete a user from the recycle bin (DESTRUCTIVE)", {"id": "u1"}),
           ("Teams / M365 Groups", "Create a Team", {"newteam": "T", "desc": "d"}),
           ("Teams / M365 Groups", "Add a channel to a Team", {"team": "T", "channel": "C", "ctype": "standard"}),
           ("Teams / M365 Groups", "Delete a channel (DESTRUCTIVE)", {"team": "T", "channel": "C"}),
           ("Teams / M365 Groups", "Archive a Team", {"team": "T"}),
           ("Teams / M365 Groups", "Unarchive a Team", {"team": "T"}),
           ("Teams / M365 Groups", "Delete a Team (DESTRUCTIVE)", {"team": "T"}),
           # SharePoint, on throwaway sites (all OK; NoAdditions removed above)
           ("SharePoint", "Create a communication site", {"title": "S", "url": "https://x/sites/s"}),
           ("SharePoint", "Create a team site", {"title": "S", "alias": "s"}),
           ("SharePoint", "Add a site collection admin", {"url": "https://x/sites/s", "email": "a@example.com"}),
           ("SharePoint", "Remove a site collection admin (DESTRUCTIVE)",
            {"url": "https://x/sites/s", "email": "a@example.com"}),
           ("SharePoint", "Add user to a SharePoint group",
            {"url": "https://x/sites/s", "group": "S Members", "email": "a@example.com"}),
           ("SharePoint", "Lock a site or make it read-only", {"url": "https://x/sites/s", "lock": "ReadOnly"}),
           ("SharePoint", "Change who a site can be shared with",
            {"url": "https://x/sites/s", "share": "ExistingExternalUserSharingOnly"}),
           ("SharePoint", "Restore everything in a site's recycle bin", {"url": "https://x/sites/s"}),
           ("SharePoint", "Delete a site (DESTRUCTIVE)", {"url": "https://x/sites/s"}),
           ("SharePoint", "Restore a deleted site", {"url": "https://x/sites/s"})]
for cat, name, values in LIVE_OK:
    _t, argv = build(cat, name, values)
    check(isinstance(argv, list), "%s: still builds (live-tested 11-02-2026)" % name)
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
