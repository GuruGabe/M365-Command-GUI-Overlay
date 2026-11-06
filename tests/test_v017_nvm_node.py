# test_v017_nvm_node.py - v0.17 (11-06-2026): Node.js through nvm with no
# version chosen. nvm's stand-in node.exe (seen live 11-06-2026 on Windows)
# exits 1, prints nothing on stdout and this on stderr:
#   No active Node.js version is configured. Run `nvm install <version>` then `nvm use <version>`.
# The CLI cannot start either (m365.cmd runs that node). 0.16 showed
# "Installed: Node.js ?" and "Signed in as: (unknown - ...)" and did not open
# Set up the CLI. Checks the facts, the "Signed in as" text, the window's
# reason and Node.js line (no Tk window), and GET /api/setup in the browser
# version (a real local server). Fakes only; nothing is installed.
import os, sys, json, types, tempfile, threading, http.client
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_setup as s
import M365GUI as m
import m365_web as w

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

NVM = ("No active Node.js version is configured. Run `nvm install <version>` then "
       "`nvm use <version>`.")

# ---- 1. the facts ------------------------------------------------------------------------
check(s.node_not_ready(NVM) and s.node_not_ready("Error\n" + NVM + "\n"), "nvm's answer is recognized")
check(not s.node_not_ready("v24.11.1") and not s.node_not_ready("") and not s.node_not_ready(None),
      "a real node version (or nothing) is not")
check("nvm install <version>" in s.NODE_NOT_READY and "nvm use <version>" in s.NODE_NOT_READY
      and "install Node.js" in s.NODE_NOT_READY, "the advice: nvm install / nvm use, or install Node.js")

# ---- 2. "Signed in as" and opening the window by itself ------------------------------------
line = m.account_text("m365.cmd", lambda argv: (1, NVM + "\n"))
check("Node.js is not ready" in line and "nvm" in line, "Signed in as: Node.js is not ready (nvm) - got %r" % line)
check(s.needs_window(line), "Set up the CLI opens by itself for it")
check(not s.signed_in(line), "and it is not a signed-in account")
check("Node.js is not installed" in m.account_text("m365.cmd", lambda a: (1, "'node' is not recognized as an internal or external command")),
      "no Node.js at all: still 'Node.js is not installed'")
reasons = []
fake = types.SimpleNamespace(_open_setup=lambda reason: reasons.append(reason))
m.M365Gui._auto_open_setup(fake, line)
check(reasons == [s.NODE_NOT_READY], "the window says why: nvm has no version chosen")
reasons.clear()
fake = types.SimpleNamespace(_open_setup=lambda reason: reasons.append(reason))
m.M365Gui._auto_open_setup(fake, "Signed in as: (Node.js is not installed - m365 cannot run)")
check(reasons and "Node.js is not installed" in reasons[0], "no Node.js: the old reason, unchanged")

# ---- 3. the window's step lines (no Tk: _setup_show on a stand-in) -------------------------
shown = {}
fake = types.SimpleNamespace(
    _setup_set=lambda key, text: shown.__setitem__(key, text),
    account_label=types.SimpleNamespace(cget=lambda k: line),
    _after_task=lambda argv: None)
NODE = r"C:\ProgramData\nvm\.nodejs\node.exe"
m.M365Gui._setup_show(fake, NODE, "", "C:\\npm\\m365.cmd", "", False, line, s.NODE_NOT_READY)
check(shown["node"].startswith("Found " + NODE + ", but it did not answer.") and "nvm use" in shown["node"],
      "step 1: found nvm's node.exe, it did not answer, what to do")
check("install Node.js first" in shown["cli"], "step 2: the CLI did not answer (install Node.js first)")
shown.clear()
m.M365Gui._setup_show(fake, NODE, "v24.11.1", "C:\\npm\\m365.cmd", "11.11.0", False, line)
check(shown["node"].startswith("Installed: Node.js v24.11.1"), "a working node: 'Installed' as before")
src = open(os.path.join(os.path.dirname(HERE), "M365GUI.py"), encoding="utf-8").read()
check("account, node_note))" in src and "m365_setup.node_not_ready((answer.stdout" in src,
      "the window's check reads node's stderr too and passes the note on")

# ---- 4. the browser version: GET /api/setup -------------------------------------------------
tmp = tempfile.mkdtemp(prefix="m365_v017_nvm_")
m.DATA_DIR, m.LOG_DIR = tmp, os.path.join(tmp, "Logs")
w.UPLOAD_DIR = os.path.join(tmp, "Uploads")
FAKE_NODE = os.path.join(tmp, "node.exe")
open(FAKE_NODE, "w").close()
real_run, real_find_node = w.subprocess.run, m.find_node
answer = {"rc": 1, "out": "", "err": NVM + "\n"}
def fake_run(argv, **kw):
    if argv[0] == FAKE_NODE and argv[1:] == ["--version"]:
        return types.SimpleNamespace(returncode=answer["rc"], stdout=answer["out"], stderr=answer["err"])
    return real_run(argv, **kw)
w.subprocess.run = fake_run
m.find_node = lambda near="": FAKE_NODE
w.M365_PATH = ""
server = w.make_server(0)
PORT = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()

def get(path):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request("GET", path, headers={"Host": "127.0.0.1:%d" % PORT, "X-M365Web-Token": w.SESSION_TOKEN})
    r = c.getresponse()
    return json.loads(r.read())

try:
    st = get("/api/setup")
    check(st["node_note"] == s.NODE_NOT_READY and st["node_version"] == "", "browser: the nvm note, no version")
    check(st["steps"][:1] == ["node"], "browser: step 1 (Node.js) is still needed")
    answer.update(rc=0, out="v24.11.1\n", err="")
    st = get("/api/setup")
    check(st["node_note"] == "" and st["node_version"] == "v24.11.1" and "node" not in st["steps"],
          "browser: a working node -> no note, step 1 done")
    page = w.PAGE if hasattr(w, "PAGE") else open(os.path.join(os.path.dirname(HERE), "m365_web.py"), encoding="utf-8").read()
    check('s.node_note?"Found "+s.node+", but it did not answer. "+s.node_note' in page
          and 's.node&&!s.node_note?"":' in page, "browser page: shows the note and the install help")
finally:
    server.shutdown()
    w.subprocess.run, m.find_node = real_run, real_find_node

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
