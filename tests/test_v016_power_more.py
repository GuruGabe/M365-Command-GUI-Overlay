# test_v016_power_more.py - v0.16 (11-02-2026): five more read-only tasks,
# each command run live first (flow owner list, flow run list, flow
# recyclebinitem list, spo contenttype list; pa app permission list against
# the CLI's docs - the tenant has no Power Apps). Pins the commands, the
# optional parts and the 'Invalid UUID' note (the CLI's strict id check
# refused 2 of 6 real flow ids live). Nothing runs.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def task(cat, name):
    found = [t for t in c.TASKS[cat] if t["name"] == name]
    check(len(found) == 1, "%s > %s exists once" % (cat, name))
    return found[0] if found else None

def build(t, values, cat):
    _d, argv, err = c.build_command(t, values, cat)
    return err or argv

ENV = "Default-11111111-2222-3333-4444-555555555555"
FLOW = "a4b7eb86-66d0-4a43-874c-891b9e4ceabf"
P = "Power Platform"

t = task(P, "Owners of a flow")
check(build(t, {"env": ENV, "flow": FLOW}, P) ==
      ["flow", "owner", "list", "--environmentName", ENV, "--flowName", FLOW, "--asAdmin",
       "--output", "text"], "owners: flow owner list --asAdmin")
check("Invalid UUID" in t["desc"] and not t["destructive"], "owners: explains 'Invalid UUID'")

t = task(P, "Run history of a flow")
check(build(t, {"env": ENV, "flow": FLOW, "status": ""}, P) ==
      ["flow", "run", "list", "--environmentName", ENV, "--flowName", FLOW, "--asAdmin",
       "--output", "text"], "runs: blank status = every run")
argv = build(t, {"env": ENV, "flow": FLOW, "status": "Failed"}, P)
check(argv[argv.index("--status") + 1] == "Failed", "runs: only failed runs")
status = [f for f in t["fields"] if f["key"] == "status"][0]
check(status["choices"] == ["", "Failed", "Succeeded", "Running", "Cancelled"] and not status["required"],
      "runs: the status values the CLI accepts, may be blank")
check("Invalid UUID" in t["desc"], "runs: explains 'Invalid UUID'")

t = task(P, "Deleted flows (can be restored for 21 days)")
check(build(t, {"env": ENV}, P) ==
      ["flow", "recyclebinitem", "list", "--environmentName", ENV, "--output", "text"],
      "deleted flows: flow recyclebinitem list")

t = task(P, "Who can use a Power App")
check(build(t, {"app": FLOW, "env": ENV, "role": ""}, P) ==
      ["pa", "app", "permission", "list", "--appName", FLOW, "--environmentName", ENV, "--asAdmin",
       "--output", "text"], "app permissions: --environmentName always given with --asAdmin")
argv = build(t, {"app": FLOW, "env": ENV, "role": "CanView"}, P)
check(argv[argv.index("--roleName") + 1] == "CanView", "app permissions: one role")

S = "SharePoint"
t = task(S, "Content types on a site")
url = "https://contoso.sharepoint.com/sites/Team"
check(build(t, {"url": url, "category": ""}, S) ==
      ["spo", "contenttype", "list", "--webUrl", url, "--output", "text"], "content types: all")
argv = build(t, {"url": url, "category": "Document Content Types"}, S)
check(argv[argv.index("--category") + 1] == "Document Content Types", "content types: one group")
names = [x["name"] for x in c.TASKS[S]]
check(names.index("Content types on a site") + 1 == names.index("Items in a list"),
      "content types sits before Items in a list")

# All five are reads: nothing destructive, no workflow, ASCII text.
for cat, name in [(P, "Owners of a flow"), (P, "Run history of a flow"),
                  (P, "Deleted flows (can be restored for 21 days)"), (P, "Who can use a Power App"),
                  (S, "Content types on a site")]:
    t = [x for x in c.TASKS[cat] if x["name"] == name][0]
    check(not t["destructive"] and not t["workflow"] and t["desc"].isascii(),
          "%s: read-only, plain task, ASCII" % name)
# (0.16 later added 7 more - test_v016_org_reads.py checks the total)
check(sum(len(v) for v in c.TASKS.values()) >= 180, "at least 180 tasks")
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
