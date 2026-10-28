# test_v011_web_connections.py - v0.11 (10-26-2026): the Connection list in the
# browser version (m365_web.py). A real server on a free local port; a stand-in
# 'm365' keeps the active connection in a file. Nothing touches a tenant.
import os, sys, json, time, tempfile, threading, http.client
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_web as w
import M365GUI as app

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

tmp = tempfile.mkdtemp(prefix="m365web_conn_")
CALLS = os.path.join(tmp, "calls.jsonl")
ACTIVE = os.path.join(tmp, "active.txt")
FAKE = os.path.join(tmp, "fake_m365.py")
GUID1 = "028de82d-7fd9-476e-a9fd-be9714280ff3"
open(ACTIVE, "w").write(GUID1)
open(FAKE, "w").write(r'''
import sys, json, os, time
argv = sys.argv[1:]
open(os.environ["M365_CALLS"], "a").write(json.dumps(argv) + "\n")
active = open(os.environ["M365_ACTIVE"]).read()
G = "028de82d-7fd9-476e-a9fd-be9714280ff3"
if argv[:1] == ["status"]:
    print(json.dumps({"connectedAs": "alexw@contoso.com" if active == G else "admin@fabrikam.com"}))
elif argv[:2] == ["connection", "list"]:
    print(json.dumps([{"name": G, "connectedAs": "alexw@contoso.com", "authType": "browser", "active": active == G},
                      {"name": "fabrikam", "connectedAs": "admin@fabrikam.com", "authType": "deviceCode",
                       "active": active == "fabrikam"}]))
elif argv[:2] == ["connection", "use"]:
    open(os.environ["M365_ACTIVE"], "w").write(argv[3])
elif argv[:3] == ["entra", "group", "list"]:
    print(json.dumps([{"displayName": "Sales", "mail": "sales@contoso.com"}]))
elif argv[:1] == ["slow"]:
    time.sleep(3); print("done")
else:
    print("done")
''')
os.environ["M365_CALLS"] = CALLS
os.environ["M365_ACTIVE"] = ACTIVE
w.invocation = lambda argv: [sys.executable, FAKE] + list(argv)
w.M365_PATH = "m365"
app.DATA_DIR, app.LOG_DIR = tmp, os.path.join(tmp, "Logs")
w.UPLOAD_DIR = os.path.join(tmp, "Uploads")
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

def calls():
    return [json.loads(l) for l in open(CALLS)] if os.path.exists(CALLS) else []

def uses():
    return [a for a in calls() if a[:2] == ["connection", "use"]]

# ---- status lists the connections ---------------------------------------------------------
s, st = req("GET", "/api/status")
check(st["account"] == "Signed in as: alexw@contoso.com", "status: signed in as the active one")
check(st["connections"] == [{"label": "alexw@contoso.com  [028de82d]", "name": GUID1, "active": True},
                            {"label": "admin@fabrikam.com  [fabrikam]", "name": "fabrikam", "active": False}],
      "status lists both connections, the active one marked")

# ---- the page has the list ------------------------------------------------------------------
c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
c.request("GET", "/", headers={"Host": "127.0.0.1:%d" % PORT})
page = c.getresponse().read().decode("utf-8")
check('id="conn"' in page and "/api/connection/use" in page and "refreshAcct" in page,
      "the page has the Connection list and switches through /api/connection/use")

# ---- tasks say which ones change the connection -----------------------------------------------
s, tasks = req("GET", "/api/tasks")
diag = {t["name"]: t for sct in tasks if sct["name"] == "Diagnostics" for t in sct["tasks"]}
check(diag["Switch to another connection"]["conn"] and diag["Sign out"]["conn"]
      and diag["Sign in another account (adds a connection)"]["conn"],
      "switch / sign in / sign out are marked: the page reads the account again after them")
check(not diag["List saved connections (accounts / tenants)"]["conn"] and not diag["CLI version"]["conn"],
      "listing and other tasks are not")
check(diag["Rename a connection"]["fields"][0]["picker"] == "connection", "the connection box gets Pick...")

# ---- Pick... ---------------------------------------------------------------------------------
s, r = req("POST", "/api/pick", {"kind": "connection", "text": ""})
check(r.get("choices") == [["alexw@contoso.com  [028de82d]", GUID1], ["admin@fabrikam.com  [fabrikam]", "fabrikam"]],
      "Pick... lists the connections (label, name)")
s, r = req("POST", "/api/pick", {"kind": "connection", "text": "fabr"})
check([v for _l, v in r.get("choices", [])] == ["fabrikam"], "typing narrows the list")

# ---- switching -------------------------------------------------------------------------------
req("POST", "/api/pick", {"kind": "group", "text": ""})
check(w.GROUP_CACHE["groups"] is not None, "(the group list is loaded)")
s, r = req("POST", "/api/connection/use", {"name": "nosuch"})
check(r.get("error") == "Unknown connection." and not uses(), "a name the CLI did not list is refused, nothing run")
s, r = req("POST", "/api/connection/use", {"name": "fabrikam; logout"})
check(r.get("error") == "Unknown connection." and not uses(), "an odd value is refused, nothing run")
s, r = req("POST", "/api/connection/use", {"name": "fabrikam"})
check(r.get("ok") is True and uses() == [["connection", "use", "--name", "fabrikam"]], "switches with 'connection use'")
check(w.GROUP_CACHE["groups"] is None, "the old tenant's group list is forgotten")
s, st = req("GET", "/api/status")
check(st["account"] == "Signed in as: admin@fabrikam.com", "status now shows the new account")

# Busy: a running job blocks a switch.
s, r = req("POST", "/api/run", {"custom": "slow", "confirmed": True})
time.sleep(0.5)
s, r2 = req("POST", "/api/connection/use", {"name": GUID1})
check("task is running" in (r2.get("error") or "") and len(uses()) == 1, "no switch while a task runs")
end = time.time() + 15
while time.time() < end and not w.JOBS[r["job"]].done:
    time.sleep(0.2)

# A task run that switches also forgets the group list.
req("POST", "/api/pick", {"kind": "group", "text": ""})
s, r = req("POST", "/api/run", {"cat": "Diagnostics",
                                "idx": [t["name"] for t in app.TASKS["Diagnostics"]].index("Switch to another connection"),
                                "values": {"connection": GUID1}})
end = time.time() + 15
while time.time() < end and not w.JOBS[r["job"]].done:
    time.sleep(0.2)
check(uses()[-1] == ["connection", "use", "--name", GUID1], "the Switch task runs 'connection use'")
check(w.GROUP_CACHE["groups"] is None, "after it, the group list is forgotten too")
server.shutdown()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
