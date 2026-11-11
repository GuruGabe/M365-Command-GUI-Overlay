# test_v016_org_reads2.py - v0.16 (11-02-2026): seven more organization-wide,
# read-only tasks, each command run live first (planner tenant settings
# list, spo tenant commandset list, spo site appcatalog list, spo homesite
# list, spo orgnewssite list, pa connector list, pp managementapp list).
# Pins the commands and the 'only the ones you can use' connector note.
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
    return found[0] if found else {"template": "", "fields": [], "desc": "", "destructive": True,
                                   "workflow": "", "name": name}

def build(cat, name, values):
    _d, argv, err = c.build_command(task(cat, name), values, cat)
    return err or argv

S, P, PL = "SharePoint", "Power Platform", "Planner"
ENV = "Default-11111111-2222-3333-4444-555555555555"
TEXT = ["--output", "text"]
EXPECT = [
    (PL, "Planner settings for the organization", {}, ["planner", "tenant", "settings", "list"] + TEXT),
    (S, "List buttons added for everyone (tenant-wide command sets)", {},
     ["spo", "tenant", "commandset", "list"] + TEXT),
    (S, "Sites with their own app catalog", {}, ["spo", "site", "appcatalog", "list"] + TEXT),
    (S, "Home sites", {}, ["spo", "homesite", "list"] + TEXT),
    (S, "Organization news sites", {}, ["spo", "orgnewssite", "list"] + TEXT),
    (P, "Custom connectors in an environment", {"env": ENV},
     ["pa", "connector", "list", "--environmentName", ENV] + TEXT),
    (P, "Apps allowed to manage Power Platform", {}, ["pp", "managementapp", "list"] + TEXT),
]
for cat, name, values, argv in EXPECT:
    check(build(cat, name, values) == argv, "%s: %s" % (name, " ".join(argv[:4])))
    t = task(cat, name)
    check(not t["destructive"] and not t["workflow"] and t["desc"].isascii(),
          "%s: read-only, plain task, ASCII" % name)

check("only the ones YOU can use" in task(P, "Custom connectors in an environment")["desc"],
      "custom connectors: says the CLI only lists the ones you can use")
check("SharePoint or Global" in task(S, "Organization news sites")["desc"],
      "org news sites: says who can run it (CLI docs)")
names = [x["name"] for x in c.TASKS[S]]
check(names.index("Home sites") == names.index("Hub sites") + 1
      and names.index("Organization news sites") == names.index("Hub sites") + 2,
      "home and news sites follow Hub sites")
check(names[-1] != "Planner settings for the organization"
      and c.TASKS[PL][-1]["name"] == "Planner settings for the organization", "Planner settings ends Planner")
# 0.19: + 2 (agent blueprints) -> 196.
check(sum(len(v) for v in c.TASKS.values()) >= 194, "at least the 194 tasks of 0.16")
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
