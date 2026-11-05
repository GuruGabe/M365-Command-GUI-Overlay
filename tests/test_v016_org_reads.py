# test_v016_org_reads.py - v0.16 (11-02-2026): seven organization-wide,
# read-only tasks, each command run live first (spo app list, spo tenant
# applicationcustomizer list, spo site apppermission list, pp tenant
# settings list with a --query of plain names, pp copilot list --asAdmin,
# pp gateway list, entra agent list). Pins the commands - nothing runs.
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

S, P, H = "SharePoint", "Power Platform", "Service health and security"
ENV = "Default-11111111-2222-3333-4444-555555555555"
URL = "https://contoso.sharepoint.com/sites/Team"

check(build(S, "Apps in the SharePoint app catalog", {}) == ["spo", "app", "list", "--output", "text"],
      "app catalog: spo app list")
check(build(S, "Extensions added to every site", {}) ==
      ["spo", "tenant", "applicationcustomizer", "list", "--output", "text"],
      "tenant-wide extensions: spo tenant applicationcustomizer list")
check(build(S, "Apps given access to a site", {"url": URL}) ==
      ["spo", "site", "apppermission", "list", "--siteUrl", URL, "--output", "text"],
      "site app permissions: --siteUrl")
check(build(P, "Copilot Studio agents in an environment", {"env": ENV}) ==
      ["pp", "copilot", "list", "--environmentName", ENV, "--asAdmin", "--output", "text"],
      "Copilot Studio agents: --asAdmin")
check(build(P, "On-premises data gateways", {}) == ["pp", "gateway", "list", "--output", "text"],
      "gateways: pp gateway list")
check(build(H, "AI agent identities (Entra Agent ID)", {}) == ["entra", "agent", "list", "--output", "text"],
      "agent identities: entra agent list")

# The tenant settings query: one argv value, plain names -> the API's paths
# (the exact string ran live 11-02-2026).
argv = build(P, "Power Platform tenant settings", {})
check(argv[:4] == ["pp", "tenant", "settings", "list"] and argv[-2:] == ["--output", "text"],
      "tenant settings: pp tenant settings list ... --output text")
query = argv[argv.index("--query") + 1] if "--query" in argv else ""
pairs = dict(p.split(":", 1) for p in query.strip("{}").split(","))
check(query.startswith("{") and query.endswith("}") and len(pairs) == 9, "tenant settings: 9 named values")
check(pairs.get("OnlyAdminsCreateEnvironments") == "disableEnvironmentCreationByNonAdminUsers"
      and pairs.get("OnlyAdminsCreateDeveloperEnvironments") ==
      "powerPlatform.governance.disableDeveloperEnvironmentCreationByNonAdminUsers"
      and pairs.get("GuestsCanMakeApps") == "powerPlatform.powerApps.enableGuestsToMake"
      and pairs.get("AppsCannotBeSharedWithEveryone") == "powerPlatform.powerApps.disableShareWithEveryone",
      "tenant settings: names match what each value means")
check(" " not in query and '"' not in query, "tenant settings: no spaces or quotes inside the query")

names = [x["name"] for x in c.TASKS[S]]
i = names.index("Apps in the SharePoint app catalog")
check(names[i + 1:i + 3] == ["Extensions added to every site", "Apps given access to a site"],
      "the three SharePoint tasks sit together")
for cat, name in [(S, "Apps in the SharePoint app catalog"), (S, "Extensions added to every site"),
                  (S, "Apps given access to a site"), (P, "Power Platform tenant settings"),
                  (P, "Copilot Studio agents in an environment"), (P, "On-premises data gateways"),
                  (H, "AI agent identities (Entra Agent ID)")]:
    t = task(cat, name)
    check(not t["destructive"] and not t["workflow"] and t["desc"].isascii(),
          "%s: read-only, plain task, ASCII" % name)
check(sum(len(v) for v in c.TASKS.values()) >= 187, "at least 187 tasks (more follow - test_v016_org_reads2.py)")
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
