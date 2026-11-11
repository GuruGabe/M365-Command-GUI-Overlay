# test_v019_more_reads.py - v0.19 (11-10-2026): 15 more READ-ONLY tasks, each
# run live before it was added (CLI 12.0.0), and the note on 'Invite a guest'.
# Checks: each task is in its section, is not marked destructive, builds the
# exact command (list / get only, with --output text), and a required box
# left empty is refused.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

SP, ROLES, SVC = "SharePoint", "Roles and admin units", "Service health and security"
# name -> (section, values, expected argv)
EXPECT = {
    "Term store groups (managed metadata)": (SP, {}, "spo term group list --output text"),
    "Term sets in a term group": (SP, {"group": "People"},
                                  "spo term set list --termGroupName People --output text"),
    "Site designs": (SP, {}, "spo sitedesign list --output text"),
    "Site scripts": (SP, {}, "spo sitescript list --output text"),
    "Custom themes": (SP, {}, "spo theme list --output text"),
    "Are SharePoint's default themes hidden?": (SP, {}, "spo hidedefaultthemes get --output text"),
    "Office 365 CDN on or off": (SP, {"type": "Private"}, "spo cdn get --type Private --output text"),
    "Office 365 CDN origins": (SP, {"type": "Public"},
                               "spo cdn origin list --type Public --output text"),
    "Tenant app catalog address": (SP, {}, "spo tenant appcatalogurl get --output text"),
    "Organization assets libraries": (SP, {}, "spo orgassetslibrary list --output text"),
    "Brand center settings": (SP, {}, "spo brandcenter settings list --output text"),
    "What an admin role can do": (ROLES, {"role": "Helpdesk Administrator"}, None),
    "Group setting templates": (SVC, {}, "entra groupsettingtemplate list --output text"),
    "Multi-tenant organization": (SVC, {}, "entra multitenant get --output text"),
    "Retention event types": (SVC, {}, "purview retentioneventtype list --output text"),
}
for name, (section, values, want) in EXPECT.items():
    found = [t for t in c.TASKS.get(section, []) if t["name"] == name]
    check(len(found) == 1, "%s: once in %s" % (name, section))
    if not found:
        continue
    t = found[0]
    check(not t.get("destructive"), "%s: not destructive" % name)
    _shown, argv, err = c.build_command(t, values, section)
    check(not err, "%s: builds (%s)" % (name, err))
    words = [a for a in argv if not a.startswith("-")]
    check(argv[-2:] == ["--output", "text"], "%s: --output text" % name)
    check(any(w in ("list", "get") for w in words[:5]), "%s: a list / get command" % name)
    if want:
        check(argv == want.split(), "%s: %s" % (name, want))

# the role task: the name with a space stays one argument; the query lists permissions
t = [t for t in c.TASKS[ROLES] if t["name"] == "What an admin role can do"][0]
_s, argv, err = c.build_command(t, {"role": "Helpdesk Administrator"}, ROLES)
check(argv == ["entra", "roledefinition", "get", "--displayName", "Helpdesk Administrator",
               "--query", "rolePermissions[].allowedResourceActions[]", "--output", "text"],
      "role permissions command: %r" % argv)
_s, argv, err = c.build_command(t, {"role": ""}, ROLES)
check(bool(err), "role name required")
t = [t for t in c.TASKS[SP] if t["name"] == "Term sets in a term group"][0]
_s, argv, err = c.build_command(t, {"group": ""}, SP)
check(bool(err), "term group name required")

# no task name used twice anywhere
names = [t["name"] for ts in c.TASKS.values() for t in ts]
check(len(names) == len(set(names)), "task names unique (%d)" % len(names))
check(len(names) >= 211, "211 tasks or more (%d)" % len(names))

# Invite a guest explains the 'not allowed' answer
t = [t for t in c.TASKS["Users (Entra ID)"] if t["name"] == "Invite a guest (external user)"][0]
check("Guest invitations not allowed for your company" in t["desc"]
      and "External collaboration settings" in t["desc"], "Invite a guest: the note")

# ASCII only in the new text
for name in list(EXPECT) + ["Invite a guest (external user)"]:
    t = [t for ts in c.TASKS.values() for t in ts if t["name"] == name][0]
    blob = name + t["desc"] + t["template"]
    check(all(ord(ch) < 128 for ch in blob), "%s: ASCII only" % name)

print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
