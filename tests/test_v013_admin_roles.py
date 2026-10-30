# test_v013_admin_roles.py - v0.13 (10-28-2026): the read-only 'Who holds
# admin roles' workflow (m365_workflows.admin_roles), driven by a fake m365
# that answers like Microsoft Graph did on a real tenant: paged role
# assignments with the principal expanded, role definitions without a few
# hidden built-in roles (read one by one), users and apps. Nothing runs.
import csv, json, os, shutil, sys, tempfile
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
GA, HD, HIDDEN = "62e90394-ga", "729827e3-hd", "88d8e3e3-hidden"

def user(n, enabled=True):
    return {"@odata.type": "#microsoft.graph.user", "id": "u%d" % n,
            "displayName": "Person %d" % n, "userPrincipalName": "p%d@contoso.com" % n,
            "accountEnabled": enabled}

APP = {"@odata.type": "#microsoft.graph.servicePrincipal", "id": "sp1",
       "displayName": "Sync app", "appId": "app-0001"}

def assignments():
    rows = [{"roleDefinitionId": GA, "directoryScopeId": "/", "principal": user(n)}
            for n in range(1, 7)]                                   # 6 Global Admins
    rows += [{"roleDefinitionId": "r%02d" % i, "directoryScopeId": "/", "principal": user(1)}
             for i in range(11)]                                   # Person 1: 12 roles
    rows.append({"roleDefinitionId": HD, "directoryScopeId": "/administrativeUnits/au1",
                 "principal": user(9, enabled=False)})              # blocked, scoped
    rows.append({"roleDefinitionId": HIDDEN, "directoryScopeId": "/", "principal": APP})
    return rows

CALLS = []
def make_run(fail_assignments=False):
    rows = assignments()
    def run(argv):
        CALLS.append(argv)
        # v0.14: the MFA registration read (tested in test_v014_admin_roles_mfa.py).
        if argv[:4] == ["entra", "user", "registrationdetails", "list"]:
            return 0, "[]"
        assert argv[0] == "request" and argv[-2:] == ["--output", "json"], argv
        url = argv[2]
        if url.startswith(G + "roleAssignments"):
            if fail_assignments:
                return 1, '{"error":"Request failed with status code 403"}'
            if "skiptoken" not in url:
                return 0, json.dumps({"value": rows[:10],
                                      "@odata.nextLink": G + "roleAssignments?$skiptoken=x"})
            return 0, json.dumps({"value": rows[10:]})
        if url == G + "roleDefinitions?$select=id,displayName":
            defs = [{"id": GA, "displayName": "Global Administrator"},
                    {"id": HD, "displayName": "Helpdesk Administrator"}]
            defs += [{"id": "r%02d" % i, "displayName": "Role %02d" % i} for i in range(11)]
            return 0, json.dumps({"value": defs})
        if url == G + "roleDefinitions/" + HIDDEN + "?$select=id,displayName":
            return 0, json.dumps({"id": HIDDEN, "displayName": "Email Verified User Creator"})
        return 1, '{"error":"unexpected %s"}' % url
    return run

base = tempfile.mkdtemp(prefix="m365roles_")
try:
    lines = []
    res = wf.admin_roles(make_run(), lines.append, lambda: False, {"apps": "Yes"}, base)
    text = "".join(lines)
    check(res["ok"] and not res["error"], "runs OK (%s)" % res["error"])
    check(res["assignments"] == 19, "every assignment over BOTH pages (%d)" % res["assignments"])
    check(sum(1 for c in CALLS if "skiptoken" in c[2]) == 1, "follows @odata.nextLink once")
    check(any(c[2].endswith(HIDDEN + "?$select=id,displayName") for c in CALLS),
          "a role missing from the list is read by its id")
    check("Email Verified User Creator" in text, "the hidden role's name is shown")
    check("Global Administrators: 6 people" in text and "fewer than five" in text,
          "6 Global Administrators -> 'fewer than five' note")
    check("Person 1 (p1@contoso.com) holds 12 roles" in text, "an account with many roles is pointed out")
    check("Person 9 (p9@contoso.com) is blocked" in text, "a blocked account that holds a role is pointed out")
    check("scope /administrativeUnits/au1" in text and "sign-in blocked" in text,
          "a scoped / blocked assignment is marked in the list")
    check(text.index("Global Administrator\n") < text.index("Helpdesk Administrator\n"),
          "Global Administrator is listed first")
    check("Sync app" in text and "[app]" in text, "apps are listed when chosen")
    check(not any(c[0] != "request" and c[:4] != ["entra", "user", "registrationdetails", "list"]
                  for c in CALLS), "only reads (m365 request GETs + registrationdetails list)")
    path = os.path.join(res["folder"], "admin-roles.csv")
    with open(path, encoding="utf-8") as fh:
        data = list(csv.reader(fh))
    check(data[0][:3] == ["role", "type", "name"] and len(data) == 20,
          "admin-roles.csv: header + 19 rows (%d)" % len(data))
    check(os.path.basename(res["folder"]).startswith("AdminRoles_tenant_"), "record folder name")

    lines = []
    res = wf.admin_roles(make_run(), lines.append, lambda: False, {"apps": "No"}, base)
    text = "".join(lines)
    check(res["assignments"] == 18 and "Sync app" not in text, "apps left out when not chosen")

    # Microsoft's advice is about people: 4 people + 1 app = no note; 1 person = 'at least two'.
    def ga_only(people, apps):
        rows = [{"roleDefinitionId": GA, "directoryScopeId": "/", "principal": user(n)}
                for n in range(people)] + \
               [{"roleDefinitionId": GA, "directoryScopeId": "/", "principal": APP}] * apps
        def run(argv):
            if "roleAssignments" in argv[2]:
                return 0, json.dumps({"value": rows})
            return 0, json.dumps({"value": [{"id": GA, "displayName": "Global Administrator"}]})
        out = []
        wf.admin_roles(run, out.append, lambda: False, {"apps": "Yes"}, base)
        return "".join(out)
    text = ga_only(4, 1)
    check("Global Administrators: 4 people + 1 app(s) / group(s)" in text
          and "recommends" not in text, "4 people + 1 app: no note (apps not counted)")
    text = ga_only(1, 0)
    check("Global Administrators: 1 person" in text and "at least two" in text,
          "1 Global Administrator -> 'at least two' note")

    lines = []
    res = wf.admin_roles(make_run(fail_assignments=True), lines.append, lambda: False, {}, base)
    text = "".join(lines)
    check(not res["ok"] and "403" in res["error"] and "RoleManagement.Read.Directory" in text,
          "a Graph error stops with the permission hint")

    lines = []
    res = wf.admin_roles(make_run(), lines.append, lambda: True, {}, base)
    check(not res["ok"], "Stop before starting -> not OK")
finally:
    shutil.rmtree(base, ignore_errors=True)
# The catalog task and its plan (desktop + browser read both).
task = next((t for t in cat.TASKS["Roles and admin units"] if t["name"] == "Who holds admin roles"), None)
check(task is not None and task["workflow"] == "admin_roles" and not task["destructive"],
      "catalog: 'Who holds admin roles' is a read-only workflow in Roles and admin units")
check("admin_roles" in cat.WORKFLOW_PLANS and "read-only" in cat.WORKFLOW_PLANS["admin_roles"],
      "catalog: its plan says read-only")
for front in ("M365GUI.py", "m365_web.py"):
    with open(os.path.join(os.path.dirname(HERE), front), encoding="utf-8") as fh:
        check("admin_roles(" in fh.read(), front + " runs the workflow")
print("FAILURES:", len(fails))
