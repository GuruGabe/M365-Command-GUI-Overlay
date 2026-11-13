# test_v020_more_reads.py - v0.20 (11-13-2026): 7 more READ-ONLY tasks, each run live
# before it was added (CLI 12.0.0). Checks: each task is in its section, is not
# marked destructive, builds the exact command (list / get only, --output text),
# never uses 'entra app get --save' (it writes a file), and a required box left
# empty is refused.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

SVC, SP, PP = "Service health and security", "SharePoint", "Power Platform"
QUERY = ("{displayName:displayName,appId:appId,accountEnabled:accountEnabled,"
         "appRoleAssignmentRequired:appRoleAssignmentRequired,servicePrincipalType:servicePrincipalType,"
         "publisherName:publisherName,signInAudience:signInAudience,homepage:homepage}")
EXPECT = {
    "An app registration's details": (SVC, {"app": "My App"},
        ["entra", "app", "get", "--name", "My App", "--properties",
         "displayName,appId,signInAudience,createdDateTime,publisherDomain,notes", "--output", "text"]),
    "Roles an app registration defines (app roles)": (SVC, {"app": "My App"},
        ["entra", "app", "role", "list", "--appName", "My App", "--output", "text"]),
    "An enterprise app's details": (SVC, {"app": "Some App"},
        ["entra", "enterpriseapp", "get", "--displayName", "Some App", "--query", QUERY,
         "--output", "text"]),
    "Terms in a term set": (SP, {"group": "People", "set": "Department"},
        ["spo", "term", "list", "--termGroupName", "People", "--termSetName", "Department",
         "--output", "text"]),
    "Office 365 CDN policies": (SP, {"type": "Private"},
        ["spo", "cdn", "policy", "list", "--cdnType", "Private", "--output", "text"]),
    "Solutions in an environment": (PP, {"env": "Default-1234"},
        ["pp", "solution", "list", "--environmentName", "Default-1234", "--output", "text"]),
    "Dataverse tables in an environment": (PP, {"env": "Default-1234"},
        ["pp", "dataverse", "table", "list", "--environmentName", "Default-1234", "--output", "text"]),
}
for name, (section, values, want) in EXPECT.items():
    found = [t for t in c.TASKS.get(section, []) if t["name"] == name]
    check(len(found) == 1, "%s: once in %s" % (name, section))
    if not found:
        continue
    t = found[0]
    check(not t.get("destructive"), "%s: not destructive" % name)
    _shown, argv, err = c.build_command(t, values, section)
    check(not err and argv == want, "%s: %r" % (name, argv))
    check("--save" not in argv, "%s: never --save" % name)
    for f in t["fields"]:
        if f["required"] and not f.get("default"):
            _s, _a, err = c.build_command(t, dict(values, **{f["key"]: ""}), section)
            check(bool(err), "%s: '%s' required" % (name, f["key"]))
    check(all(ord(ch) < 128 for ch in name + t["desc"] + t["template"]), "%s: ASCII only" % name)

names = [t["name"] for ts in c.TASKS.values() for t in ts]
check(len(names) == len(set(names)), "task names unique (%d)" % len(names))
check(len(names) >= 218, "218 tasks or more (%d)" % len(names))
print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
