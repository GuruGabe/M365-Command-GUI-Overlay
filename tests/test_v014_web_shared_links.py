# test_v014_web_shared_links.py - v0.14 (10-29-2026): 'Files shared by link in
# a folder' in the browser version (m365_web.py). A real server on a free
# local port and a stand-in 'm365' that answers 'spo file list' and
# 'spo file sharinglink list'. The workflow runs as a job, asks no question,
# only reads, and saves its CSV under DATA_DIR/Records. Nothing touches a tenant.
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

tmp = tempfile.mkdtemp(prefix="m365webshare_")
CALLS = os.path.join(tmp, "calls.jsonl")
FAKE = os.path.join(tmp, "fake_m365.py")
open(FAKE, "w").write(r'''
import sys, json, os
argv = sys.argv[1:]
open(os.environ["M365_CALLS"], "a").write(json.dumps(argv) + "\n")
if argv[:3] == ["spo", "file", "list"]:
    print(json.dumps([{"Name": "plan.docx", "UniqueId": "f1",
                       "ServerRelativeUrl": "/sites/Team/Shared Documents/plan.docx"}]))
elif argv[:4] == ["spo", "file", "sharinglink", "list"]:
    print(json.dumps([{"id": "l1", "roles": ["write"], "hasPassword": False,
                       "link": {"scope": "anonymous", "type": "edit",
                                "webUrl": "https://contoso.sharepoint.com/:w:/s/Team/SECRET"}}]))
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
task = next((t for sct in tasks if sct["name"] == "SharePoint"
             for t in sct["tasks"] if t["name"] == "Files shared by link in a folder"), None)
check(task is not None and task["workflow"] == "shared_links" and "read-only" in task["plan"],
      "/api/tasks lists it with its read-only plan")

s, b = req("POST", "/api/workflow/start", {"cat": "SharePoint", "idx": task["idx"],
                                           "values": {"url": "https://contoso.sharepoint.com/sites/Team",
                                                      "folder": "Shared Documents", "subfolders": "Yes",
                                                      "kind": "Anyone-with-the-link links only"}})
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
check("1 link(s) on 1 of 1 file(s)" in text and "EDIT" in text, "the summary and notes reach the page")
check("SECRET" not in text, "no link address on the page")
calls = [json.loads(l) for l in open(CALLS)]
check(len(calls) == 2 and calls[0][:3] == ["spo", "file", "list"]
      and calls[1][:4] == ["spo", "file", "sharinglink", "list"], "only the two list commands ran")
records = os.path.join(tmp, "Records")
found = [os.path.join(r, f) for r, _d, fs in os.walk(records) for f in fs if f == "shared-links.csv"]
check(len(found) == 1, "shared-links.csv saved under DATA_DIR/Records")
server.shutdown()
print("FAILURES:", len(fails))
