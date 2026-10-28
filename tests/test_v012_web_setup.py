# test_v012_web_setup.py - v0.12 (10-27-2026): Set up the CLI in the browser
# version (m365_web.py): GET /api/setup (Node.js, the CLI, its app ID, the
# sign-in, and the commands to paste), POST /api/setup/cli (npm as a job,
# m365 looked for again), POST /api/setup/login (sign in with a code as a
# job), the 'setup' flag on /api/status and on a failed job. A real server on
# a free local port; stand-ins for node, npm and m365. Nothing is installed
# and nothing touches a tenant.
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

tmp = tempfile.mkdtemp(prefix="m365web_setup_")
CALLS = os.path.join(tmp, "calls.jsonl")
STATE = os.path.join(tmp, "state.json")
FAKE = os.path.join(tmp, "fake_m365.py")
GUID = "028de82d-7fd9-476e-a9fd-be9714280ff3"
def state(**kw):
    json.dump(kw, open(STATE, "w"))
open(FAKE, "w").write(r'''
import sys, json, os
argv = sys.argv[1:]
open(os.environ["M365_CALLS"], "a").write(json.dumps(argv) + "\n")
st = json.load(open(os.environ["M365_STATE"]))
if argv[:1] == ["version"]:
    print('"11.11.0"')
elif argv[:1] == ["status"]:
    print(json.dumps({"connectedAs": st["who"]}) if st.get("who") else "Logged out")
elif argv[:3] == ["cli", "config", "get"]:
    print('"%s"' % st["app"] if st.get("app") else "")
elif argv[:1] == ["login"]:
    if st.get("app"):
        print("To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter the code ABCD1234")
    else:
        sys.stderr.write('Error: appId is required. TIP: use the "m365 setup" command\n')
        sys.exit(1)
elif argv[:1] == ["fail"]:
    sys.stderr.write("Error: Log in to Microsoft 365 first\n"); sys.exit(1)
elif argv[:1] == ["badinput"]:
    sys.stderr.write("Error: Resource not found\n"); sys.exit(1)
else:
    print("done")
''')
os.environ["M365_CALLS"] = CALLS
os.environ["M365_STATE"] = STATE
w.invocation = lambda argv: [sys.executable, FAKE] + list(argv)
app.DATA_DIR, app.LOG_DIR = tmp, os.path.join(tmp, "Logs")
w.UPLOAD_DIR = os.path.join(tmp, "Uploads")
NODE = os.path.join(tmp, "node.exe" if os.name == "nt" else "node")
NPM = os.path.join(tmp, "npm.cmd" if os.name == "nt" else "npm")
real_find_node, real_popen, real_run = app.find_node, w.subprocess.Popen, w.subprocess.run

class Done:
    def __init__(self, out):
        self.returncode, self.stdout, self.stderr = 0, out, ""
def fake_run(argv, **kw):
    if argv[0] == NODE and argv[1:] == ["--version"]:
        return Done("v24.11.0\n")
    return real_run(argv, **kw)
w.subprocess.run = fake_run

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

def wait(job):
    for _ in range(100):
        _s, j = req("GET", "/api/job?job=%s&since=0" % job)
        if j.get("done"):
            return j
        time.sleep(0.1)
    return j

# ---- nothing on this server -----------------------------------------------------------
w.M365_PATH = ""
app.find_node = lambda near="": ""
_s, s = req("GET", "/api/setup")
check(s["steps"] == ["node", "cli", "app", "login"], "nothing here: all four steps needed")
check(s["node_command"] or s["node_url"], "a way to install Node.js is shown (winget command or nodejs.org)")
check(s["commands"]["setup"].endswith("m365 setup")
      and s["commands"]["browser"].endswith("m365 login --authType browser")
      and s["commands"]["code"].endswith("m365 login --authType deviceCode"), "the commands to paste")
_s, r = req("POST", "/api/setup/cli", {})
check("Node.js first" in r.get("error", ""), "no Node.js: Install the CLI says install Node.js first")
_s, r = req("POST", "/api/setup/login", {})
check("CLI first" in r.get("error", ""), "no CLI: Sign in says install the CLI first")
_s, st = req("GET", "/api/status")
check(st["setup"] is True, "/api/status tells the page to open the window (m365 not found)")

# ---- Install the CLI: npm as a job -----------------------------------------------------
app.find_node = lambda near="": NODE
for path in (NODE, NPM):
    open(path, "w").close()
popen_calls = []
def fake_popen(argv, **kw):
    popen_calls.append(list(argv))
    if argv[0] == NPM:
        return real_popen([sys.executable, "-c", "print('added 1 package')"], **kw)
    return real_popen(argv, **kw)
w.subprocess.Popen = fake_popen
real_find_m365 = app.find_m365
app.find_m365 = lambda saved: os.path.join(tmp, "m365.cmd")
_s, r = req("POST", "/api/setup/cli", {})
j = wait(r["job"])
text = "".join(j["lines"])
check(popen_calls[0] == [NPM, "install", "-g", "@pnp/cli-microsoft365"], "npm install -g @pnp/cli-microsoft365")
check(j["rc"] == 0 and "added 1 package" in text and "The CLI is installed" in text,
      "the npm output, then 'installed'")
check(w.M365_PATH == os.path.join(tmp, "m365.cmd"), "m365 is looked for again afterwards")

# A failing npm: the hint, and the CLI path unchanged.
def failing_popen(argv, **kw):
    return real_popen([sys.executable, "-c", "import sys; print('npm ERR! code EACCES'); sys.exit(243)"], **kw)
w.subprocess.Popen = failing_popen
_s, r = req("POST", "/api/setup/cli", {})
j = wait(r["job"])
check(j["rc"] == 243 and "global folder" in "".join(j["lines"]), "a failed npm: exit code and the EACCES hint")
w.subprocess.Popen = real_popen
app.find_m365 = real_find_m365

# ---- the CLI is here, no app ID, nobody signed in ---------------------------------------------
state(who="", app="")
_s, s = req("GET", "/api/setup")
check(s["node_version"] == "v24.11.0" and s["cli_version"] == "11.11.0", "the Node.js and CLI versions")
check(s["steps"] == ["app", "login"] and not s["app_ok"], "no app ID, nobody signed in")
check(s["commands"]["setup"].startswith(w._shell_words([w.M365_PATH])), "the commands use this server's m365")

# Sign in with a code without an app ID -> the CLI's own error; the job is
# NOT offered the window again by the server... the page decides (once).
_s, r = req("POST", "/api/setup/login", {})
j = wait(r["job"])
check(j["rc"] == 1 and "appId is required" in "".join(j["lines"]) and j["setup"] is True,
      "no app ID: the CLI's error, and the page is told to offer Set up")

# With an app ID: the code and the web address come back in the output.
state(who="", app=GUID)
_s, s = req("GET", "/api/setup")
check(s["app_ok"] and s["steps"] == ["login"], "app ID set: only the sign-in left")
_s, r = req("POST", "/api/setup/login", {})
j = wait(r["job"])
check(j["rc"] == 0 and "devicelogin" in "".join(j["lines"]) and "ABCD1234" in "".join(j["lines"]),
      "Sign in with a code: the web address and code are shown")
check(["login", "--authType", "deviceCode"] in [json.loads(l) for l in open(CALLS)],
      "it runs 'm365 login --authType deviceCode'")

# Everything set.
state(who="admin@contoso.com", app=GUID)
_s, s = req("GET", "/api/setup")
check(s["steps"] == [], "signed in: nothing needed")
_s, st = req("GET", "/api/status")
check(st["setup"] is False, "/api/status: no window when all is set")

# ---- the 'setup' flag on a failed job -------------------------------------------------------
_s, r = req("POST", "/api/run", {"custom": "fail"})
check(wait(r["job"])["setup"] is True, "'Log in to Microsoft 365 first': the page offers Set up")
_s, r = req("POST", "/api/run", {"custom": "badinput"})
check(wait(r["job"])["setup"] is False, "another error: no offer")
_s, r = req("POST", "/api/run", {"custom": "anything"})
check(wait(r["job"])["setup"] is False, "a command that worked: no offer")

# ---- busy: never two jobs -------------------------------------------------------------------
busy = w.Job()
w.JOBS[busy.id] = busy
_s, r1 = req("POST", "/api/setup/cli", {})
_s, r2 = req("POST", "/api/setup/login", {})
check("running" in r1.get("error", "") and "running" in r2.get("error", ""), "not while a task runs")
busy.done = True

# ---- token required, the page -----------------------------------------------------------------
c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
c.request("GET", "/api/setup", headers={"Host": "127.0.0.1:%d" % PORT})
check(c.getresponse().status == 403, "no token = refused")
page = w.PAGE
check('id="setupbtn"' in page and 'id="setupdlg"' in page and "/api/setup/cli" in page
      and "/api/setup/login" in page and "offerSetup()" in page and "s.setup&&!SETUPASKED" in page,
      "the page: button, dialog, opens when needed, offer after errors")
check(all(ord(ch) < 128 for ch in page), "the page is ASCII")
server.shutdown()
app.find_node = real_find_node
w.subprocess.run = real_run
import shutil; shutil.rmtree(tmp, ignore_errors=True)
print("FAILURES:", len(fails))
