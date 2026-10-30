# test_v014_apps_settings.py - v0.14 (10-29-2026): six read-only tasks in
# Service health and security - app-only permissions granted to an app, app
# registrations, the permissions an app registration asks for, group
# settings, the usage-report privacy setting and the pronouns setting.
# Checked against the CLI's --help (v11.11) and run live (read-only) on
# 10-29-2026. Builds each command - nothing runs.
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

NEW = ["App-only permissions granted to an app", "App registrations made in the organization",
       "Permissions an app registration asks for", "Group settings for the organization",
       "Are names hidden in usage reports?", "Pronouns setting"]
for name in NEW:
    cat, task = find(name)
    check(cat == "Service health and security", "%s is in Service health and security (%s)" % (name, cat))
    check(task is not None and not task["destructive"], "%s is read-only (no ask)" % name)
    verb = task["template"].split(" --")[0].split()[-1] if task else ""
    check(verb in ("list", "get"), "%s: a list/get command (%s)" % (name, verb))
    check(task is not None and c.saves_output(task), "%s: can be saved to CSV / JSON" % name)

_d, argv, err = build("App-only permissions granted to an app", app="Contoso HR Sync")
check(not err and argv == ["entra", "approleassignment", "list", "--appDisplayName", "Contoso HR Sync",
                           "--output", "text"], "app-only: a name with spaces stays ONE argument")
_d, argv, err = build("App-only permissions granted to an app", app="")
check(bool(err), "app-only: the app name is required")

_d, argv, err = build("App registrations made in the organization")
check(not err and argv == ["entra", "app", "list", "--properties",
                           "displayName,appId,createdDateTime,signInAudience", "--output", "text"],
      "app registrations: --properties is one argument without quotes")

cat, task = find("Permissions an app registration asks for")
check(task["fields"][1]["choices"] == ["all", "application", "delegated"] and task["fields"][1]["default"] == "all",
      "app permissions: the CLI's three types, all by default")
_d, argv, err = build("Permissions an app registration asks for", app="Grade Sync", ptype="application")
check(not err and argv == ["entra", "app", "permission", "list", "--appName", "Grade Sync", "--type",
                           "application", "--output", "text"], "app permissions: %s" % argv)

for name, cmd in (("Group settings for the organization", ["entra", "groupsetting", "list"]),
                  ("Are names hidden in usage reports?", ["tenant", "report", "settings", "get"]),
                  ("Pronouns setting", ["tenant", "people", "pronouns", "get"])):
    _d, argv, err = build(name)
    check(not err and argv == cmd + ["--output", "text"], "%s: %s" % (name, argv))
print("FAILURES:", len(fails))
