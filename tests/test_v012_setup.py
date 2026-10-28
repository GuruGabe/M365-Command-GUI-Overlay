# test_v012_setup.py - v0.12 (10-27-2026): the "Set up the CLI" window -
# Node.js (winget on Windows), the CLI (npm install -g), its app ('m365 setup')
# and signing in ('m365 login'), as GAMGUI 2.97's Set up GAM. Opens by itself
# only when needed. m365, node, npm and winget are fakes; nothing is
# installed, no terminal window opens and nothing touches a tenant. The CLI's
# texts are its own (v11.11 dist: Command.js, login.js; checked 10-27-2026).
import os, sys, json, time, types, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_setup as s

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

GUID = "b3e36a7c-0000-4000-8000-000000000001"
# ---- 1. the facts -----------------------------------------------------------------------
check(s.app_id_set(0, '"%s"\n' % GUID, {}) and not s.app_id_set(0, "", {})
      and not s.app_id_set(1, '"%s"' % GUID, {}), "app ID: a GUID in 'cli config get clientId'")
check(s.app_id_set(1, "", {s.APP_ID_ENV: GUID}), "app ID: or the CLIMICROSOFT365_ENTRAAPPID variable")
check(s.signed_in("Signed in as: admin@contoso.com") and s.signed_in("Signed in as: Contoso App"),
      "signed in: any account name")
for line in ("Signed in as: nobody - run 'm365 login'", "Signed in as: (m365 not found)",
             "Signed in as: (checking...)", "Signed in as: (unknown - x)", ""):
    check(not s.signed_in(line), "not signed in: %r" % line)
check(s.needs_window("Signed in as: (m365 not found)") and
      s.needs_window("Signed in as: (Node.js is not installed - m365 cannot run)") and
      s.needs_window("Signed in as: nobody - run 'm365 login'"), "opens by itself: no m365 / no Node.js / nobody")
check(not s.needs_window("Signed in as: (could not check: timeout)") and
      not s.needs_window("Signed in as: (unknown - ECONNRESET)") and
      not s.needs_window("Signed in as: admin@contoso.com"), "NOT for a hiccup or when signed in")
check(s.needed_steps(False, False, False, "Signed in as: (m365 not found)") == ["node", "cli", "app", "login"],
      "nothing installed -> every step")
check(s.needed_steps(True, True, True, "Signed in as: admin@contoso.com") == [], "all done -> nothing")
check(s.needed_steps(True, True, True, "Signed in as: nobody - run 'm365 login'") == ["login"],
      "only the sign-in missing")
for text in ("Error: Log in to Microsoft 365 first",
             'Error: appId is required. TIP: use the "m365 setup" command to configure the default appId.',
             "AADSTS700082: The refresh token has expired due to inactivity.",
             "AADSTS50076: Due to a configuration change made by your administrator ... multi-factor",
             "invalid_grant"):
    check(s.setup_can_fix(text), "offered for: " + text[:50])
for text in ("Error: Resource 'x' does not exist", "Access denied", "AADSTS90002: Tenant not found"):
    check(not s.setup_can_fix(text), "NOT offered for: " + text[:50])
check(s.login_command("browser") == ["login", "--authType", "browser"] and
      s.login_command("deviceCode") == ["login", "--authType", "deviceCode"], "sign in: browser / code")
try:
    s.login_command("password")
    check(False, "a password sign-in is never built (M365GUI never handles passwords here)")
except ValueError:
    check(True, "a password sign-in is never built (M365GUI never handles passwords here)")
kind, what = s.node_install_plan("Windows", which=lambda n: r"C:\winget.exe" if n == "winget" else None)
check(kind == "winget" and what == [r"C:\winget.exe", "install", "--id", "OpenJS.NodeJS.LTS", "--exact",
                                    "--source", "winget"]
      and not any("accept" in a for a in what),
      "Windows: winget installs Node.js LTS - the license is accepted by the person, never by M365GUI")
check(s.node_install_plan("Windows", which=lambda n: None) == ("download", s.NODE_DOWNLOAD_URL),
      "Windows without winget: the download page")
check(s.node_install_plan("Darwin")[0] == "download", "macOS / Linux: the download page")
check(s.npm_install_command("npm") == ["npm", "install", "-g", "@pnp/cli-microsoft365"], "npm install -g the CLI")
tmp = tempfile.mkdtemp(prefix="m365gui_setup_")
npm_name = "npm.cmd" if os.name == "nt" else "npm"
open(os.path.join(tmp, npm_name), "w").write("")
check(s.find_npm(os.path.join(tmp, "node.exe"), which=lambda n: None) == os.path.join(tmp, npm_name),
      "npm is found next to node")
check(s.find_npm("", which=lambda n: "/usr/bin/npm") == "/usr/bin/npm", "or on the PATH")
check("sudo npm install -g" in s.npm_failure_hint("npm ERR! code EACCES"), "EACCES -> the sudo / npm docs hint")
win = s.console_command(["node", "cli.js", "login", "--authType", "browser"], "m365 login", "Windows")
check(win == ["cmd", "/c", "start", "m365 login", "cmd", "/k", "node", "cli.js", "login", "--authType", "browser"],
      "Windows: its own console that stays open")
mac = s.console_command(["/usr/local/bin/node", "/x/index.js", "setup"], "m365 setup", "Darwin")
check(mac[0] == "osascript" and "Terminal" in mac[2] and "index.js setup" in mac[2], "macOS: a Terminal window")
check(s.console_command(["m365"], "t", "Linux", which=lambda n: None) is None, "Linux without a terminal -> None")

# ---- 2. the window (hidden), with fakes ---------------------------------------------------
import M365GUI as m
m.INI_PATH, m.LOG_DIR = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "Logs")
m.TASKLISTS_PATH = os.path.join(tmp, "m365gui_tasklists.json")
m.M365Gui._startup_checks = lambda self: None
m.find_m365 = lambda saved: "m365"
m.find_node = lambda near="": os.path.join(tmp, "node.exe")
os.environ.pop(s.APP_ID_ENV, None)
state = {"status": "Logged out", "client": ""}
calls, launched = [], []
def fake_quiet(self, argv, timeout=60):
    calls.append(list(argv))
    if argv[:1] == ["status"]:
        return 0, state["status"]
    if argv[:1] == ["version"]:
        return 0, '"11.11.0"'
    if argv[:3] == ["cli", "config", "get"]:
        return 0, state["client"]
    if argv[:2] == ["connection", "list"]:
        return 0, "[]"
    return 1, "unexpected"
m.M365Gui._quiet_run = fake_quiet
real_run, real_popen = m.subprocess.run, m.subprocess.Popen
m.subprocess.run = lambda argv, **kw: types.SimpleNamespace(stdout="v24.22.1\n", returncode=0)
class FakeProc:
    def __init__(self, lines, rc):
        self.stdout, self.returncode, self.pid = iter(lines), rc, 1
    def wait(self):
        return self.returncode
npm_answer = {"lines": ["added 1 package in 9s\n"], "rc": 0}
def fake_popen(argv, **kw):
    launched.append(list(argv))
    if "install" in argv and "-g" in argv:
        return FakeProc(npm_answer["lines"], npm_answer["rc"])
    return types.SimpleNamespace(pid=1)
m.subprocess.Popen = fake_popen
asked = []
m.messagebox.askyesno = lambda *a, **k: asked.append(a[1]) or True
m.messagebox.showinfo = lambda *a, **k: asked.append(a[1])
m.messagebox.showerror = lambda *a, **k: asked.append(a[1])
try:
    app = m.M365Gui()
    app.withdraw()

    def settle(seconds=3):
        end = time.time() + seconds
        while time.time() < end:
            app.update()
            time.sleep(0.05)
    settle()
    w = getattr(app, "_setup_win", None)
    check(w is not None and w.winfo_exists(), "nobody signed in -> Set up the CLI opens by itself")
    w.withdraw()
    st = {k: v.cget("text") for k, v in app._setup_status.items()}
    check("Node.js v24.22.1" in st["node"], "step 1 shows Node.js (%s)" % st["node"][:40])
    check("CLI for Microsoft 365 11.11.0" in st["cli"], "step 2 shows the CLI version")
    check(st["app"].startswith("Not set up yet") and "m365 setup" in st["app"], "step 3: no app ID -> m365 setup")
    check("app first" in st["login"], "step 4 says the app comes first")
    app._setup_win.destroy()
    app._refresh_account(); settle(2)
    check(not app._setup_win.winfo_exists(), "it opens by itself only ONCE per session")

    app._open_setup(); settle(2); app._setup_win.withdraw()
    app._setup_launch(s.SETUP_COMMAND, "m365 setup")
    check(launched[-1] == ["cmd", "/c", "start", "m365 setup", "cmd", "/k", "m365", "setup"]
          if os.name == "nt" else launched[-1][-1].endswith("setup") or "setup" in " ".join(launched[-1]),
          "Run m365 setup -> its own window (%s)" % launched[-1][-3:])
    app._setup_launch(s.login_command("deviceCode"), "m365 login")
    check("deviceCode" in " ".join(launched[-1]) and "login" in " ".join(launched[-1]),
          "Sign in with a code -> 'm365 login --authType deviceCode' in its own window")

    # After signing in there: Check again shows it and re-reads the account.
    state.update(status=json.dumps({"connectedAs": "admin@contoso.com"}), client='"%s"' % GUID)
    before = len([a for a in calls if a[:1] == ["status"]])
    app._setup_check(); settle(3)
    st = {k: v.cget("text") for k, v in app._setup_status.items()}
    check(st["app"].startswith("Set up:") and "admin@contoso.com" in st["login"], "signed in: steps 3 and 4 done")
    check(app.account_label.cget("text") == "Signed in as: admin@contoso.com", "the top bar follows")
    check(len([a for a in calls if a[:1] == ["status"]]) > before + 1,
          "a changed account re-reads Signed in as and the Connection list")

    # Install the CLI: asks, then npm install -g, its output in the pane.
    asked.clear()
    app._setup_install_cli(); settle(2)
    npm_calls = [a for a in launched if "install" in a and "-g" in a]
    check(asked and "npm" in asked[0] and npm_calls and npm_calls[-1][1:] ==
          ["install", "-g", "@pnp/cli-microsoft365"], "Install the CLI asks, then runs npm install -g")
    out = app.output_box.get("1.0", "end")
    check("added 1 package" in out and "The CLI is installed." in out, "npm's output is shown")
    check(str(app.run_button.cget("state")) == "normal", "Run works again afterwards")
    npm_answer.update(lines=["npm ERR! code EACCES\n"], rc=243)
    app._setup_install_cli(); settle(2)
    check("exit code 243" in app.output_box.get("1.0", "end") and "sudo npm" in app.output_box.get("1.0", "end"),
          "a failed npm says why")

    # A sign-in error after a task offers the window once.
    asked.clear()
    m.messagebox.askyesno = lambda *a, **k: asked.append(a[1]) or False
    app._offer_setup(); app._offer_setup()
    check(len(asked) == 1 and "sign-in problem" in asked[0], "a sign-in error offers Set up the CLI once")
    menubar = app.nametowidget(app["menu"])
    settings = app.nametowidget(menubar.entrycget(0, "menu"))
    check(menubar.entrycget(0, "label") == "Settings"
          and settings.entrycget(0, "label") == "Set up the CLI (install / sign in)...",
          "Settings > Set up the CLI (install / sign in)... is the first menu item")
    app.destroy()

    # No CLI at all -> opens at startup and says so.
    m.find_m365 = lambda saved: ""
    app = m.M365Gui(); app.withdraw(); settle_end = time.time() + 3
    while time.time() < settle_end:
        app.update(); time.sleep(0.05)
    labels = [w.cget("text") for w in app._setup_win.winfo_children()[0].winfo_children()
              if w.winfo_class() == "TLabel"]
    check(any("could not find the CLI" in t for t in labels), "no CLI -> it opens at startup with the reason")
    check("The CLI was not found" in app._setup_status["cli"].cget("text"), "step 2 offers Install the CLI")
    app.destroy()
finally:
    m.subprocess.run, m.subprocess.Popen = real_run, real_popen

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
