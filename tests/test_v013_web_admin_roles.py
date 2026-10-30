# test_v013_web_admin_roles.py - v0.13 (10-28-2026): 'Who holds admin roles'
# in the browser version (m365_web.py). A real server on a free local port
# and a stand-in 'm365' that answers 'request --url ...' like Microsoft
# Graph. The workflow runs as a job, asks no question, only reads, and saves
# its CSV under DATA_DIR/Records. Nothing touches a tenant.
import os, sys, json, time, tempfile, threading, http.client
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import m365_web as w
import M365GUI as app

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

tmp = tempfile.mkdtemp(prefix="m365webroles_")
CALLS = os.path.join(tmp, "calls.jsonl")
FAKE = os.path.join(tmp, "fake_m365.py")
open(FAKE, "w").write(r'''
import sys, json, os
argv = sys.argv[1:]
open(os.environ["M365_CALLS"], "a").write(json.dumps(argv) + "\n")
G = "https://graph.microsoft.com/v1.0/roleManagement/directory/"
url = argv[2] if argv[:2] == ["request", "--url"] else ""
if argv[:4] == ["entra", "user", "registrationdetails", "list"]:     # v0.14: MFA read
    print(json.dumps([{"id": "u1", "isMfaRegistered": True, "methodsRegistered": ["microsoftAuthenticatorPush"]},
                      {"id": "u2", "isMfaRegistered": False, "methodsRegistered": []}]))
elif url.startswith(G + "roleAssignments"):
    print(json.dumps({"value": [
        {"roleDefinitionId": "ga", "directoryScopeId": "/", "principal": {
            "@odata.type": "#microsoft.graph.user", "id": "u1", "displayName": "Pat Admin",
            "userPrincipalName": "pat@contoso.com", "accountEnabled": True}},
        {"roleDefinitionId": "ga", "directoryScopeId": "/", "principal": {
            "@odata.type": "#microsoft.graph.user", "id": "u2", "displayName": "Lee Admin",
            "userPrincipalName": "lee@contoso.com", "accountEnabled": True}}]}))
elif url.startswith(G + "roleDefinitions"):
    print(json.dumps({"value": [{"id": "ga", "displayName": "Global Administrator"}]}))
else:
    print('{"error":"unexpected"}'); sys.exit(1)
''')
os.environ["M365_CALLS"] = CALLS
w.invocation = lambda argv: [sys.executable, FAKE] + list(argv)
w.M365_PATH = "m365"
app.DATA_DIR, app.LOG_DIR = tmp, os.path.join(tmp, "Logs")

server = w.make_server(0)
PORT = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()

def req(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    headers = {"Host": "127.0.0.1:%d" % PORT, "X-M365Web-Token": w.SESSION_TOKEN}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    c.request(method, path, body=data, headers=headers)
    r = c.getresponse()
    return r.status, json.loads(r.read())

s, tasks = req("GET", "/api/tasks")
task = next((t for sct in tasks if sct["name"] == "Roles and admin units"
             for t in sct["tasks"] if t["name"] == "Who holds admin roles"), None)
check(task is not None and task["workflow"] == "admin_roles" and "read-only" in task["plan"],
      "/api/tasks lists it with its read-only plan")

s, b = req("POST", "/api/workflow/start", {"cat": "Roles and admin units", "idx": task["idx"],
                                           "values": {"apps": "Yes"}})
check(s == 200 and "job" in b, "the workflow starts as a job (%s)" % b)
lines, since, st, asked = [], 0, {"done": False}, False
end = time.time() + 30
while time.time() < end:
    _s, st = req("GET", "/api/job?job=%s&since=%d" % (b["job"], since))
    lines += st["lines"]
    since = st["next"]
    asked = asked or bool(st.get("question"))
    if st["done"]:
        break
    time.sleep(0.1)
text = "".join(lines)
check(st["done"], "the job finishes")
check(not asked, "it asks no question (read-only)")
check("Global Administrators: 2 people" in text and "Pat Admin  <pat@contoso.com>" in text,
      "the list and the summary reach the page")
calls = [json.loads(l) for l in open(CALLS)]
check(calls and all(c[0] == "request" or c[:4] == ["entra", "user", "registrationdetails", "list"]
                    for c in calls), "only reads were run (%d)" % len(calls))
check("Global Administrator Lee Admin (lee@contoso.com) has NO MFA method registered" in text,
      "v0.14: a Global Administrator without MFA reaches the page")
records = os.path.join(tmp, "Records")
found = [os.path.join(r, f) for r, _d, fs in os.walk(records) for f in fs if f == "admin-roles.csv"]
check(len(found) == 1, "admin-roles.csv saved under DATA_DIR/Records")
server.shutdown()
print("FAILURES:", len(fails))
