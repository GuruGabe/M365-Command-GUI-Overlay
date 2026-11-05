# test_v016_web_power_platform.py - v0.16 (11-02-2026): 'Power Automate flows
# and Power Apps review' in the browser version (m365_web.py). A real server
# on a free local port and a stand-in 'm365' that answers the environment,
# flow, app and directoryObjects reads. The workflow runs as a job, asks no
# question, only reads, and saves its CSV under DATA_DIR/Records. Nothing
# touches a tenant.
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

tmp = tempfile.mkdtemp(prefix="m365webpower_")
CALLS = os.path.join(tmp, "calls.jsonl")
FAKE = os.path.join(tmp, "fake_m365.py")
open(FAKE, "w").write(r'''
import sys, json, os
argv = sys.argv[1:]
open(os.environ["M365_CALLS"], "a").write(json.dumps(argv) + "\n")
ENV = "Default-11111111-2222-3333-4444-555555555555"
CREATOR = "aaaaaaaa-0000-0000-0000-000000000009"
if argv[:3] == ["flow", "environment", "list"]:
    print(json.dumps([{"name": ENV, "properties": {"displayName": "Contoso (default)"}}]))
elif argv[:2] == ["flow", "list"] and argv[3] == ENV and "--asAdmin" in argv:
    print(json.dumps([{"name": "f1", "properties": {"displayName": "Send to Dropbox",
        "state": "Started", "creator": {"objectId": CREATOR, "userType": "ActiveDirectory"}}}]))
elif argv[:2] == ["flow", "get"] and argv[3] == "f1" and "--asAdmin" in argv:
    print(json.dumps({"name": "f1", "triggers": "Recurrence", "actions": "Http",
        "properties": {"connectionReferences": {"d": {"apiName": "dropbox", "displayName": "Dropbox"}}}}))
elif argv[:3] == ["pa", "app", "list"] and "--asAdmin" in argv:
    print("[]")
elif argv[:2] == ["request", "--url"] and argv[2].endswith("/directoryObjects/" + CREATOR):
    print('{"error":"Request failed with status code 404"}'); sys.exit(1)
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
task = next((t for sct in tasks if sct["name"] == "Power Platform"
             for t in sct["tasks"] if t["name"] == "Power Automate flows and Power Apps review"), None)
check(task is not None and task["workflow"] == "power_platform" and "read-only" in task["plan"],
      "/api/tasks lists it with its read-only plan")

s, b = req("POST", "/api/workflow/start", {"cat": "Power Platform", "idx": task["idx"],
                                           "values": {"details": w.cat.POWER_DETAILS_FULL}})
check(s == 200 and "job" in b, "the workflow starts as a job (%s)" % b)
lines, since, st, asked = [], 0, {"done": False}, False
end = time.time() + 60
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
check("can send data outside Microsoft 365: Dropbox" in text
      and "calls web addresses directly (HTTP)" in text
      and "deleted or unknown - and it is still ON" in text,
      "the flow and its notes reach the page")
calls = [json.loads(l) for l in open(CALLS)]
check(calls and all(c[:2] in (["flow", "environment"], ["flow", "list"], ["flow", "get"],
                              ["pa", "app"], ["request", "--url"]) for c in calls)
      and not any("--method" in c for c in calls), "only reads were run (%d)" % len(calls))
records = os.path.join(tmp, "Records")
found = [os.path.join(r, f) for r, _d, fs in os.walk(records) for f in fs if f == "power-platform.csv"]
check(len(found) == 1, "power-platform.csv saved under DATA_DIR/Records")
server.shutdown()
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
