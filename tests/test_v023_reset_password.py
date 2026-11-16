# test_v023_reset_password.py - v0.23 (11-16-2026): Reset password.
#   - 'Require a password change at next sign-in' is a Yes/No box, default No; Yes adds
#     the bare --forceChangePasswordNextSignIn switch (it takes no value).
#   - A blank password box gets a random password for a single run (desktop and
#     browser): handed over once, kept out of the session log, and the desktop box is
#     emptied again so the next Run makes a new one. A CSV run still needs a password.
# A stand-in m365 runs; nothing touches a tenant.
import os, sys, json, time, tempfile, threading, http.client
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

SEC = "Users (Entra ID)"
reset = [t for t in c.TASKS[SEC] if t["name"] == "Reset password"][0]
keys = [f["key"] for f in reset["fields"]]
check(keys == ["email", "password", "force"], "boxes: user, password, change at next sign-in (%r)" % keys)
force = reset["fields"][2]
check(force["choices"] == ["No", "Yes"] and force["default"] == "No", "the change is a Yes/No choice, default No")
check(not reset["fields"][1]["required"] and reset.get("random_key") == "password",
      "the password box may be left blank (random)")
check(not reset["destructive"], "not marked destructive (as before)")
BASE = ["entra", "user", "set", "--userName", "a@contoso.com", "--resetPassword", "--newPassword", "P1!x"]
for value, want in (("No", BASE), ("", BASE), ("Yes", BASE + ["--forceChangePasswordNextSignIn"])):
    _d, argv, err = c.build_command(reset, {"email": "a@contoso.com", "password": "P1!x", "force": value}, SEC)
    check(not err and argv == want, "force %r -> %r" % (value, argv))
_d, _a, err = c.build_command(reset, {"email": "a@contoso.com", "password": "", "force": "No"}, SEC)
check(err == "Missing required value: password", "build_command itself never invents a password (CSV rows need one)")
others = [t["name"] for ts in c.TASKS.values() for t in ts if t.get("random_key") and t is not reset]
# v0.24: Create user makes random passwords too (test_v024_create_user.py).
check(others in ([], ["Create user"]), "only Reset password / Create user make random passwords (%r)" % others)
comp = [t for t in c.TASKS["Security"] if t["name"] == "Compromised account response"][0]
check(comp["workflow"] == "compromised", "the compromised-account workflow is unchanged")
check(all(ord(ch) < 128 for ch in reset["desc"] + reset["template"]), "ASCII only")

# ---- the desktop window (hidden), with a stand-in m365 ------------------------------------
import M365GUI as m
tmp = tempfile.mkdtemp(prefix="m365gui_reset_")
m.INI_PATH, m.TASKLISTS_PATH = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "t.json")
m.LOG_DIR = os.path.join(tmp, "Logs")
m.find_m365 = lambda saved: "m365"
m.M365Gui._startup_checks = lambda self: None
m.M365Gui._refresh_account = lambda self: None
m.messagebox.askyesno = lambda *a, **k: True
RANDOM = "Rnd!Secret-123abc"
m.random_password = lambda length=16: RANDOM
app = m.M365Gui()
app.withdraw()
app.update()
ran, shown = [], []
app._build_invocation = lambda argv: (ran.append(list(argv)), [sys.executable, "-c", "print('ok')"])[1]
app._capture = lambda argv: (0, "")
app._show_secret = lambda title, secret: shown.append((title, secret))

def wait_done():
    end = time.time() + 60
    while time.time() < end:
        app.update()
        if str(app.run_button.cget("state")) == "normal" and app.running_proc is None:
            break
        time.sleep(0.05)
    app.update()

for parent in app.tree.get_children(""):
    for child in app.tree.get_children(parent):
        if app.tree.item(child, "text") == "Reset password":
            app.tree.selection_set(child)
app.update()
fields = dict(app.field_vars)
check(fields["force"].get() == "No", "the window opens the task with No")
fields["email"].set("a@contoso.com")
fields["password"].set("")
app._preview()
app._run()
wait_done()
check(ran and ran[-1][-2:] == ["--newPassword", RANDOM] and "--forceChangePasswordNextSignIn" not in ran[-1],
      "blank password: the random one is set, no change forced (%r)" % (ran[-1:] if ran else None))
check(len(shown) == 1 and shown[0][1] == RANDOM and "a@contoso.com" in shown[0][0],
      "the random password is shown once, with the user's name")
check(fields["password"].get() == "", "the box is emptied again (the next Run makes a new one)")
log = open(app.log_path, encoding="utf-8").read()
check(RANDOM not in log and "--newPassword ********" in log, "the session log masks it")

fields["password"].set("Typed Pass9!")
fields["force"].set("Yes")
app._preview()
app._run()
wait_done()
check(ran[-1][-3:] == ["--newPassword", "Typed Pass9!", "--forceChangePasswordNextSignIn"],
      "a typed password is used as typed; Yes adds the switch")
check(len(shown) == 1 and fields["password"].get() == "Typed Pass9!",
      "a typed password: no window, the box keeps it")
app.destroy()

# ---- the browser version, with a stand-in m365 -------------------------------------------
import m365_web as w
CALLS = os.path.join(tmp, "calls.jsonl")
FAKE = os.path.join(tmp, "fake_m365.py")
with open(FAKE, "w") as h:
    h.write("import sys, json, os\n"
            "open(os.environ['M365_CALLS'], 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "print('done')\n")
os.environ["M365_CALLS"] = CALLS
w.invocation = lambda argv: [sys.executable, FAKE] + list(argv)
w.M365_PATH = "m365"
m.DATA_DIR, m.LOG_DIR = tmp, os.path.join(tmp, "Logs")
WEB_RANDOM = "Zq9!webSecret-77"
w.app.random_password = lambda length=16: WEB_RANDOM
server = w.make_server(0)
PORT = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()

def req(method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    headers = {"Host": "127.0.0.1:%d" % PORT, "X-M365Web-Token": w.SESSION_TOKEN}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    return json.loads(r.read())

def follow(job):
    secrets_seen, since = [], 0
    end = time.time() + 30
    while time.time() < end:
        st = req("GET", "/api/job?job=%s&since=%d" % (job, since))
        since = st["next"]
        if st.get("secret"):
            secrets_seen.append(st["secret"]["value"])
        if st["done"]:
            return st, secrets_seen
        time.sleep(0.1)
    return {"done": False}, secrets_seen

def calls():
    return [json.loads(l) for l in open(CALLS)] if os.path.exists(CALLS) else []

tasks = req("GET", "/api/tasks")
idx = None
for sct in tasks if isinstance(tasks, list) else tasks.get("sections", []):
    if sct["name"] == SEC:
        idx = [t["idx"] for t in sct["tasks"] if t["name"] == "Reset password"][0]
check(idx is not None, "the browser lists Reset password")
b = req("POST", "/api/run", {"cat": SEC, "idx": idx, "values": {"email": "b@contoso.com", "password": "", "force": "No"}})
st, seen = follow(b.get("job"))
check(st.get("rc") == 0 and calls()[-1][-2:] == ["--newPassword", WEB_RANDOM],
      "browser, blank password: the random one is set (%r)" % (calls()[-1:],))
check(seen == [WEB_RANDOM], "browser: the random password is handed to the page once")
b = req("POST", "/api/run", {"cat": SEC, "idx": idx, "values": {"email": "b@contoso.com", "password": "Typed9!x",
                                                               "force": "Yes"}})
st, seen = follow(b.get("job"))
check(calls()[-1][-3:] == ["--newPassword", "Typed9!x", "--forceChangePasswordNextSignIn"] and seen == [],
      "browser, typed password + Yes: as typed, the switch added, nothing handed over")
server.shutdown()

print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
