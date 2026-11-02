# test_v015_web_team_settings.py - v0.15 (10-30-2026): 'Team settings review'
# in the browser version (m365_web.py). A real server on a free local port and
# a stand-in 'm365' that answers 'teams team list' / 'teams team get --id'.
# The workflow runs as a job, asks no question, only reads, and saves its CSV
# under DATA_DIR/Records. Nothing touches a tenant.
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

tmp = tempfile.mkdtemp(prefix="m365webteams_")
CALLS = os.path.join(tmp, "calls.jsonl")
FAKE = os.path.join(tmp, "fake_m365.py")
open(FAKE, "w").write(r'''
import sys, json, os
argv = sys.argv[1:]
open(os.environ["M365_CALLS"], "a").write(json.dumps(argv) + "\n")
TEAM = {"id": "570c6ca2-94ad-4a75-9102-5979a2d0ca00", "displayName": "Band Boosters"}
if argv[:3] == ["teams", "team", "list"]:
    print(json.dumps([TEAM]))
elif argv[:4] == ["teams", "team", "get", "--id"] and argv[4] == TEAM["id"]:
    print(json.dumps(dict(TEAM, visibility="public", isArchived=False,
        summary={"ownersCount": 0, "membersCount": 3, "guestsCount": 1},
        guestSettings={"allowCreateUpdateChannels": False, "allowDeleteChannels": True},
        funSettings={"giphyContentRating": "strict"})))
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
task = next((t for sct in tasks if sct["name"] == "Teams / M365 Groups"
             for t in sct["tasks"] if t["name"] == "Team settings review"), None)
check(task is not None and task["workflow"] == "team_settings" and "read-only" in task["plan"],
      "/api/tasks lists it with its read-only plan")

s, b = req("POST", "/api/workflow/start", {"cat": "Teams / M365 Groups", "idx": task["idx"],
                                           "values": {"team": "band boosters"}})
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
check("Band Boosters: no owner" in text and "Band Boosters: public" in text
      and "Band Boosters: 1 guest(s)" in text and "Band Boosters: guests can delete channels" in text
      and "strict" in text, "the settings and the notes reach the page")
calls = [json.loads(l) for l in open(CALLS)]
check(calls and all(c[:2] == ["teams", "team"] and c[2] in ("list", "get") for c in calls),
      "only Team reads were run (%d)" % len(calls))
records = os.path.join(tmp, "Records")
found = [os.path.join(r, f) for r, _d, fs in os.walk(records) for f in fs if f == "team-settings.csv"]
check(len(found) == 1, "team-settings.csv saved under DATA_DIR/Records")
server.shutdown()
print("FAILURES:", len(fails))
