# test_v014_admin_roles_mfa.py - v0.14 (10-29-2026): 'Who holds admin roles'
# also reads whether each person with a role registered an MFA method
# ('entra user registrationdetails list --userIds', at most 20 ids per call;
# needs AuditLog.Read.All - checked live 10-29-2026). A fake m365 answers.
# Checks: batches of 20, people only (no apps), Global Administrators
# without MFA first, other admins after, the CSV columns, and a failed MFA
# read is a NOTE - the role list still finishes. Nothing runs.
import csv, json, os, shutil, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_workflows as wf

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

G = wf.GRAPH_ROLES
GA, HD = "ga-id", "hd-id"

def user(n):
    return {"@odata.type": "#microsoft.graph.user", "id": "u%d" % n, "displayName": "Person %d" % n,
            "userPrincipalName": "p%d@contoso.com" % n, "accountEnabled": True}

APP = {"@odata.type": "#microsoft.graph.servicePrincipal", "id": "sp1", "displayName": "Sync app",
       "appId": "app-0001"}
# 3 Global Admins (u1-u3), 22 Helpdesk Admins (u10-u31) and one app.
ROWS = [{"roleDefinitionId": GA, "directoryScopeId": "/", "principal": user(n)} for n in (1, 2, 3)]
ROWS += [{"roleDefinitionId": HD, "directoryScopeId": "/", "principal": user(n)} for n in range(10, 32)]
ROWS.append({"roleDefinitionId": HD, "directoryScopeId": "/", "principal": APP})
NO_MFA = {"u2", "u15"}


def make_run(calls, mfa_fails=False):
    def run(argv):
        calls.append(argv)
        if argv[:4] == ["entra", "user", "registrationdetails", "list"]:
            if mfa_fails:
                return 1, '{"error":"Request failed with status code 403"}'
            ids = argv[argv.index("--userIds") + 1].split(",")
            return 0, json.dumps([{"id": i, "isMfaRegistered": i not in NO_MFA,
                                   "methodsRegistered": [] if i in NO_MFA else ["microsoftAuthenticatorPush"]}
                                  for i in ids])
        url = argv[2]
        if url.startswith(G + "roleAssignments"):
            return 0, json.dumps({"value": ROWS})
        if url.startswith(G + "roleDefinitions"):
            return 0, json.dumps({"value": [{"id": GA, "displayName": "Global Administrator"},
                                            {"id": HD, "displayName": "Helpdesk Administrator"}]})
        return 1, '{"error":"unexpected"}'
    return run


base = tempfile.mkdtemp(prefix="m365mfa_")
try:
    calls, lines = [], []
    res = wf.admin_roles(make_run(calls), lines.append, lambda: False, {"apps": "Yes"}, base)
    text = "".join(lines)
    mfa_calls = [c for c in calls if c[:4] == ["entra", "user", "registrationdetails", "list"]]
    ids = [c[c.index("--userIds") + 1].split(",") for c in mfa_calls]
    check(res["ok"] and len(mfa_calls) == 2 and [len(x) for x in ids] == [20, 5],
          "25 people read in batches of 20 + 5 (%s)" % [len(x) for x in ids])
    check(not any("sp1" in x for x in ids), "apps are not looked up (MFA is for people)")
    check(all(c[c.index("--properties") + 1] == "id,isMfaRegistered,methodsRegistered" for c in mfa_calls),
          "only the three needed properties are asked for")
    ga_note = "NOTE: Global Administrator Person 2 (p2@contoso.com) has NO MFA method registered - fix this first."
    hd_note = "NOTE: Person 15 (p15@contoso.com) holds an admin role and has NO MFA method registered."
    check(ga_note in text and hd_note in text, "both people without MFA are pointed out")
    check(text.index(ga_note) < text.index(hd_note), "the Global Administrator comes first")
    check(text.count("has NO MFA method registered") == 2, "nobody else is pointed out")
    check("Person 2  <p2@contoso.com>  [no MFA]" in text, "the list marks 'no MFA'")
    with open(os.path.join(res["folder"], "admin-roles.csv"), encoding="utf-8") as fh:
        data = list(csv.DictReader(fh))
    p2 = next(r for r in data if r["name"] == "Person 2")
    p1 = next(r for r in data if r["name"] == "Person 1")
    app = next(r for r in data if r["name"] == "Sync app")
    check(p2["MFA registered"] == "NO" and p1["MFA registered"] == "yes"
          and p1["MFA methods"] == "microsoftAuthenticatorPush" and app["MFA registered"] == "",
          "CSV: MFA registered yes / NO, methods, blank for apps")

    calls, lines = [], []
    res = wf.admin_roles(make_run(calls, mfa_fails=True), lines.append, lambda: False, {"apps": "Yes"}, base)
    text = "".join(lines)
    check(res["ok"] and "MFA registration could not be read" in text and "AuditLog.Read.All" in text
          and "Helpdesk Administrator" in text, "a failed MFA read is a NOTE; the role list still finishes")
    check("has NO MFA method registered" not in text, "unknown MFA is never shown as 'no MFA'")
finally:
    shutil.rmtree(base, ignore_errors=True)
print("FAILURES:", len(fails))
