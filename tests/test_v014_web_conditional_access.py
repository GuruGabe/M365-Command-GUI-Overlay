# test_v014_web_conditional_access.py - v0.14 (10-29-2026): 'Conditional
# Access review' in the browser version (m365_web.py). A real server on a
# free local port and a stand-in 'm365' that answers 'request --url' like
# Microsoft Graph. The workflow runs as a job, asks no question, only reads,
# and saves its CSV under DATA_DIR/Records. Nothing touches a tenant.
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

tmp = tempfile.mkdtemp(prefix="m365webca_")
CALLS = os.path.join(tmp, "calls.jsonl")
FAKE = os.path.join(tmp, "fake_m365.py")
open(FAKE, "w").write(r'''
import sys, json, os
argv = sys.argv[1:]
open(os.environ["M365_CALLS"], "a").write(json.dumps(argv) + "\n")
G = "https://graph.microsoft.com/v1.0/"
url = argv[2] if argv[:2] == ["request", "--url"] else ""
if url == G + "identity/conditionalAccess/policies":
    print(json.dumps({"value": [{"id": "p1", "displayName": "Helpdesk MFA", "state": "enabled",
        "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
        "conditions": {"users": {"includeRoles": ["729827e3-9c14-49f7-bb1b-9608f156bbb8"]},
                       "clientAppTypes": ["all"], "applications": {"includeApplications": ["All"]}}}]}))
elif url.startswith(G + "directoryRoleTemplates"):
    print(json.dumps({"value": [{"id": "729827e3-9c14-49f7-bb1b-9608f156bbb8",
                                 "displayName": "Helpdesk Administrator"}]}))
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
task = next((t for sct in tasks if sct["name"] == "Security"
             for t in sct["tasks"] if t["name"] == "Conditional Access review"), None)
check(task is not None and task["workflow"] == "conditional_access" and "read-only" in task["plan"],
      "/api/tasks lists it with its read-only plan")

s, b = req("POST", "/api/workflow/start", {"cat": "Security", "idx": task["idx"], "values": {}})
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
check("Helpdesk MFA  [ON]" in text and "role Helpdesk Administrator" in text
      and "no policy that is ON requires MFA for Global Administrators" in text,
      "the policy and the gap notes reach the page")
calls = [json.loads(l) for l in open(CALLS)]
check(calls and all(c[:2] == ["request", "--url"] for c in calls), "only Graph reads were run (%d)" % len(calls))
records = os.path.join(tmp, "Records")
found = [os.path.join(r, f) for r, _d, fs in os.walk(records) for f in fs if f == "conditional-access.csv"]
check(len(found) == 1, "conditional-access.csv saved under DATA_DIR/Records")
server.shutdown()
print("FAILURES:", len(fails))
