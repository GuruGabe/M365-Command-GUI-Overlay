# test_v014_admin_roles_signin.py - v0.14 (10-29-2026): 'Who holds admin
# roles' also reads each role holder's last sign-in (Graph users/{id}?$select=
# signInActivity - needs AuditLog.Read.All; checked live 10-29-2026) and
# points out people idle for the chosen days (90 by default) or who never
# signed in. A fake m365 answers. Nothing runs.
import csv, datetime, json, os, shutil, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_workflows as wf
import m365_catalog as cat

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

G = wf.GRAPH_ROLES
GA = "ga-id"
TODAY = datetime.date.today()
def ago(days):
    return (TODAY - datetime.timedelta(days=days)).strftime("%Y-%m-%dT10:00:00Z")

def user(n):
    return {"@odata.type": "#microsoft.graph.user", "id": "u%d" % n, "displayName": "Person %d" % n,
            "userPrincipalName": "p%d@contoso.com" % n, "accountEnabled": True}

ROWS = [{"roleDefinitionId": GA, "directoryScopeId": "/", "principal": user(n)} for n in (1, 2, 3, 4)]
ROWS.append({"roleDefinitionId": GA, "directoryScopeId": "/", "principal": {
    "@odata.type": "#microsoft.graph.servicePrincipal", "id": "sp1", "displayName": "Sync app", "appId": "a1"}})
ACTIVITY = {"u1": {"lastSuccessfulSignInDateTime": ago(3)},
            "u2": {"lastSuccessfulSignInDateTime": ago(200)},
            "u3": None,                                                     # never / not recorded
            "u4": {"lastSignInDateTime": ago(120), "lastNonInteractiveSignInDateTime": ago(10)}}


def make_run(calls, fail_signins=False):
    def run(argv):
        calls.append(argv)
        if argv[:4] == ["entra", "user", "registrationdetails", "list"]:
            return 0, "[]"
        url = argv[2]
        if url.startswith(G + "roleAssignments"):
            return 0, json.dumps({"value": ROWS})
        if url.startswith(G + "roleDefinitions"):
            return 0, json.dumps({"value": [{"id": GA, "displayName": "Global Administrator"}]})
        if url.startswith(wf.ROLES_GRAPH_USERS):
            if fail_signins:
                return 1, '{"error":"Request failed with status code 403"}'
            uid = url[len(wf.ROLES_GRAPH_USERS):].split("?")[0]
            return 0, json.dumps({"id": uid, "signInActivity": ACTIVITY[uid]})
        return 1, '{"error":"unexpected"}'
    return run


base = tempfile.mkdtemp(prefix="m365signin_")
try:
    calls, lines = [], []
    res = wf.admin_roles(make_run(calls), lines.append, lambda: False, {"apps": "Yes", "days": "90"}, base)
    text = "".join(lines)
    reads = [c[2] for c in calls if c[0] == "request" and c[2].startswith(wf.ROLES_GRAPH_USERS)]
    check(res["ok"] and len(reads) == 4 and all(u.endswith("?$select=signInActivity") for u in reads),
          "one signInActivity read per PERSON (not the app) (%d)" % len(reads))
    check("Person 2 (p2@contoso.com) holds an admin role and has not signed in for 200 days" in text,
          "idle 200 days is pointed out")
    check("Person 3 (p3@contoso.com) holds an admin role and has never signed in" in text,
          "never signed in is pointed out")
    check("Person 1 (p1@contoso.com) holds an admin role and has not" not in text
          and "Person 4 (p4@contoso.com) holds an admin role and has not" not in text,
          "recent sign-ins (3 days; 10 days non-interactive) are not pointed out")
    check(text.index("Person 3 (p3@contoso.com) holds an admin role and has never") <
          text.index("Person 2 (p2@contoso.com) holds an admin role and has not"),
          "never-signed-in comes before the longest idle")
    check("[idle 200 days]" in text and "[never signed in]" in text, "the list marks idle / never")
    with open(os.path.join(res["folder"], "admin-roles.csv"), encoding="utf-8") as fh:
        data = {r["name"]: r for r in csv.DictReader(fh)}
    check(data["Person 2"]["last sign-in"] == (TODAY - datetime.timedelta(days=200)).strftime("%m-%d-%Y")
          and data["Person 3"]["last sign-in"].startswith("never") and data["Sync app"]["last sign-in"] == "",
          "CSV: last sign-in as MM-DD-YYYY, 'never', blank for apps")

    calls, lines = [], []
    wf.admin_roles(make_run(calls), lines.append, lambda: False, {"apps": "No", "days": "5"}, base)
    text = "".join(lines)
    check("Person 1 (p1@contoso.com) holds an admin role and has not" not in text
          and "Person 4 (p4@contoso.com) holds an admin role and has not signed in for 10 days" in text,
          "the days box is used (5): 10 days idle is pointed out, 3 is not")

    calls, lines = [], []
    res = wf.admin_roles(make_run(calls, fail_signins=True), lines.append, lambda: False, {"days": "x"}, base)
    text = "".join(lines)
    reads = [c for c in calls if c[0] == "request" and c[2].startswith(wf.ROLES_GRAPH_USERS)]
    check(res["ok"] and len(reads) == 1 and "last sign-ins could not be read" in text
          and "AuditLog.Read.All" in text, "a failed read stops after the first one, as a NOTE")
    check("has not signed in" not in text and "never signed in" not in text,
          "unknown sign-ins are never shown as idle")
    # Live 10-29-2026: one account answered an EMPTY body while the others read
    # fine - skip that one, keep reading the rest.
    def flaky(calls):
        inner = make_run(calls)
        def run(argv):
            if argv[0] == "request" and argv[2].startswith(wf.ROLES_GRAPH_USERS + "u2?"):
                calls.append(argv)
                return 0, '""'
            return inner(argv)
        return run
    calls, lines = [], []
    wf.admin_roles(flaky(calls), lines.append, lambda: False, {"days": "90"}, base)
    text = "".join(lines)
    reads = [c for c in calls if c[0] == "request" and c[2].startswith(wf.ROLES_GRAPH_USERS)]
    check(len(reads) == 4 and "some last sign-ins could not be read: 1 account(s) gave no answer" in text
          and "Person 3 (p3@contoso.com) holds an admin role and has never signed in" in text
          and "Person 2 (p2@contoso.com) holds an admin role and has not" not in text,
          "one empty answer is skipped; the other accounts are still read")
finally:
    shutil.rmtree(base, ignore_errors=True)

task = next(t for t in cat.TASKS["Roles and admin units"] if t["name"] == "Who holds admin roles")
days = [f for f in task["fields"] if f["key"] == "days"]
check(days and days[0]["default"] == "90" and not days[0]["required"], "catalog: optional days box, 90 by default")
print("FAILURES:", len(fails))
