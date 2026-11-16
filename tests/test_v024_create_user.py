# test_v024_create_user.py - v0.24 (11-16-2026): Create user gets what Reset password
# got in 0.23 - blank password = a random one shown once (desktop and browser),
# 'Require a password change at first sign-in' Yes / No (default No, Yes = the bare
# switch) - plus two read-only SharePoint tasks. A stand-in m365; nothing touches a
# tenant.
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
create = [t for t in c.TASKS[SEC] if t["name"] == "Create user"][0]
keys = [f["key"] for f in create["fields"]]
check(keys == ["display", "email", "password", "loc", "force"], "boxes (%r)" % keys)
force = create["fields"][4]
check(force["choices"] == c.YES_NO and force["default"] == "No", "the change is Yes / No, default No")
check(create.get("random_key") == "password" and not create["fields"][2]["required"],
      "the password box may be left blank (random)")
BASE = ["entra", "user", "add", "--displayName", "Pat Smith", "--userName", "p@contoso.com",
        "--password", "P1!x"]
for value, want in (("No", BASE), ("", BASE), ("Yes", BASE + ["--forceChangePasswordNextSignIn"])):
    _d, argv, err = c.build_command(create, {"display": "Pat Smith", "email": "p@contoso.com",
                                             "password": "P1!x", "force": value}, SEC)
    check(not err and argv == want, "force %r -> %r" % (value, argv))
_d, argv, err = c.build_command(create, {"display": "Pat Smith", "email": "p@contoso.com",
                                         "password": "P1!x", "loc": "US", "force": "Yes"}, SEC)
check(argv[-3:] == ["--usageLocation", "US", "--forceChangePasswordNextSignIn"][-3:] or
      argv == BASE + ["--usageLocation", "US", "--forceChangePasswordNextSignIn"], "with a usage location")
_d, _a, err = c.build_command(create, {"display": "Pat", "email": "p@contoso.com", "password": ""}, SEC)
check(err == "Missing required value: password",
      "build_command never leaves --password out (the CLI would make one and print it)")
names = sorted(t["name"] for ts in c.TASKS.values() for t in ts if t.get("random_key"))
check(names == ["Create user", "Reset password"], "random passwords: Create user and Reset password (%r)" % names)

URL = "https://contoso.sharepoint.com/sites/Team"
for name, want in (("Retention labels available on a site", ["spo", "web", "retentionlabel", "list"]),
                   ("Web parts available on a site", ["spo", "web", "clientsidewebpart", "list"])):
    found = [t for t in c.TASKS["SharePoint"] if t["name"] == name]
    check(len(found) == 1, name + ": once in SharePoint")
    if found:
        _d, argv, err = c.build_command(found[0], {"url": URL}, "SharePoint")
        check(not err and argv == want + ["--webUrl", URL, "--output", "text"], "%s: %r" % (name, argv))
        check(not found[0]["destructive"], name + ": read-only")
        _d, _a, err = c.build_command(found[0], {"url": ""}, "SharePoint")
        check(bool(err), name + ": the site URL is required")
all_names = [t["name"] for ts in c.TASKS.values() for t in ts]
check(len(all_names) == len(set(all_names)) and len(all_names) >= 249, "249 tasks or more, unique (%d)" % len(all_names))
check(all(ord(ch) < 128 for ch in create["desc"] + create["template"]), "ASCII only")

# ---- the desktop window (hidden), with a stand-in m365 -----------------------------------
import M365GUI as m
tmp = tempfile.mkdtemp(prefix="m365gui_create_")
m.INI_PATH, m.TASKLISTS_PATH = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "t.json")
m.LOG_DIR = os.path.join(tmp, "Logs")
m.find_m365 = lambda saved: "m365"
m.M365Gui._startup_checks = lambda self: None
m.M365Gui._refresh_account = lambda self: None
m.messagebox.askyesno = lambda *a, **k: True
RANDOM = "Rnd!Create-123abc"
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
        if app.tree.item(child, "text") == "Create user":
            app.tree.selection_set(child)
app.update()
fields = dict(app.field_vars)
check(fields["force"].get() == "No", "the window opens the task with No")
fields["display"].set("Pat Smith")
fields["email"].set("p@contoso.com")
fields["password"].set("")
app._preview()
app._run()
wait_done()
check(ran and ran[-1] == BASE[:-1] + [RANDOM], "blank password: the random one is used (%r)" % (ran[-1:],))
check(len(shown) == 1 and shown[0][1] == RANDOM and "p@contoso.com" in shown[0][0], "shown once")
check(fields["password"].get() == "", "the box is emptied again")
log = open(app.log_path, encoding="utf-8").read()
check(RANDOM not in log, "the session log masks it")
app.destroy()

# ---- the browser version ------------------------------------------------------------------
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
WEB_RANDOM = "Zq9!webCreate-77"
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
    return json.loads(conn.getresponse().read())

tasks = req("GET", "/api/tasks")
idx = None
for sct in tasks if isinstance(tasks, list) else tasks.get("sections", []):
    if sct["name"] == SEC:
        idx = [t["idx"] for t in sct["tasks"] if t["name"] == "Create user"][0]
b = req("POST", "/api/run", {"cat": SEC, "idx": idx, "values": {"display": "Pat Smith", "email": "p@contoso.com",
                                                               "password": "", "force": "Yes"}})
seen, since, done = [], 0, False
end = time.time() + 30
while time.time() < end and not done:
    st = req("GET", "/api/job?job=%s&since=%d" % (b.get("job"), since))
    since = st["next"]
    if st.get("secret"):
        seen.append(st["secret"]["value"])
    done = st["done"]
    time.sleep(0.1)
calls = [json.loads(l) for l in open(CALLS)] if os.path.exists(CALLS) else []
check(calls and calls[-1] == BASE[:-1] + [WEB_RANDOM, "--forceChangePasswordNextSignIn"],
      "browser, blank + Yes: random password and the switch (%r)" % (calls[-1:],))
check(seen == [WEB_RANDOM], "browser: handed to the page once")
server.shutdown()

print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
