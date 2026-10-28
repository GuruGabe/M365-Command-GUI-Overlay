# test_v012_readonly_more.py - v0.12 (10-28-2026): six read-only tasks added
# the day after the Outlook ones - Entra policies (one type, required), apps
# in a Team, the Teams app catalog, two usage reports and the organization's
# details. Checked against the CLI's docs (v11.11) and run live (read-only)
# on 10-28-2026. Builds each command - nothing runs.
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

NEW = {"Microsoft Entra policies (settings)": "Security",
       "Apps installed in a Team": "Teams / M365 Groups",
       "Teams apps in the organization's app catalog": "Teams / M365 Groups",
       "Mailboxes near their size limit (counts)": "Reports (usage)",
       "OneDrive storage used - whole organization": "Reports (usage)",
       "Organization (tenant) details": "Diagnostics"}
for name, section in NEW.items():
    cat, task = find(name)
    check(cat == section, "%s is in %s (%s)" % (name, section, cat))
    check(task is not None and not task["destructive"], "%s is read-only (no ask)" % name)

# Policies: the type is required. Without one the CLI also reads
# roleManagement, which needs Entra ID P2 - the whole command failed live.
cat, task = find("Microsoft Entra policies (settings)")
field = task["fields"][0]
check(field["required"] and "" not in field["choices"], "policy type is required (no blank choice)")
check("roleManagement" not in field["choices"], "roleManagement (needs P2) is not offered")
check(field["default"] == "authorization", "policy type defaults to authorization")
_d, argv, err = build("Microsoft Entra policies (settings)", ptype="authorization")
check(not err and argv == ["entra", "policy", "list", "--type", "authorization"],
      "policies: %s" % argv)
_d, argv, err = build("Microsoft Entra policies (settings)", ptype="")
check(bool(err), "policies: an empty type is refused (%s)" % err)

_d, argv, err = build("Apps installed in a Team", team="Grade 5 Science")
check(not err and argv == ["teams", "team", "app", "list", "--teamName", "Grade 5 Science",
                           "--output", "text"], "team apps: a name with spaces stays ONE argument")
cat, task = find("Apps installed in a Team")
check(c.picker_kind(cat, task, task["fields"][0]) == "group", "team apps: Pick... a Team")

_d, argv, err = build("Teams apps in the organization's app catalog", dist="organization")
check(not err and argv == ["teams", "app", "list", "--distributionMethod", "organization",
                           "--output", "text"], "app catalog: organization")
_d, argv, err = build("Teams apps in the organization's app catalog", dist="")
check(not err and argv == ["teams", "app", "list", "--output", "text"],
      "app catalog: blank = all (no --distributionMethod)")
cat, task = find("Teams apps in the organization's app catalog")
check(task["fields"][0]["default"] == "organization",
      "app catalog defaults to organization (the store has thousands of apps)")

for name, cmd in (("Mailboxes near their size limit (counts)",
                   ["outlook", "report", "mailboxusagequotastatusmailboxcounts"]),
                  ("OneDrive storage used - whole organization",
                   ["onedrive", "report", "usagestorage"])):
    _d, argv, err = build(name, period="D90")
    # Report commands accept only csv / json output (found live 10-26-2026).
    check(not err and argv == cmd + ["--period", "D90", "--output", "csv"], "%s: %s" % (name, argv))

_d, argv, err = build("Organization (tenant) details")
check(not err and argv[:4] == ["entra", "organization", "list", "--properties"]
      and "onPremisesLastSyncDateTime" in argv[4] and " " not in argv[4]
      and argv[-2:] == ["--output", "text"], "organization details: %s" % argv)
print("FAILURES:", len(fails))
