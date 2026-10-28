# test_v011_connections.py - v0.11 (10-26-2026): switch between the accounts /
# tenants the CLI is signed in to, like GAMGUI's Section dropdown. 'm365 login'
# adds a CONNECTION each time; 'm365 connection use --name' picks the one every
# command uses (CLI v11.11 docs: connection list / use / set / remove; JSON:
# name, connectedAs, authType, active - checked live 10-26-2026). The window is
# HIDDEN and m365 is a fake - nothing touches a tenant.
import os, sys, json, time, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import M365GUI as m
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

# ---- 1. reading 'connection list' --------------------------------------------------
GUID1 = "028de82d-7fd9-476e-a9fd-be9714280ff3"
GUID2 = "acd6df42-10a9-4315-8928-53334f1c9d01"
sample = [{"name": GUID1, "connectedAs": "alexw@contoso.com", "authType": "DeviceCode", "active": True},
          {"name": "myworkaccount", "connectedAs": "Contoso Application", "authType": "Secret",
           "active": False}]
got = c.connection_choices(sample)
check(got == [("alexw@contoso.com  [028de82d]", GUID1, True),
              ("Contoso Application  [myworkaccount]", "myworkaccount", False)],
      "connection list -> (label, name, active); a GUID name is shortened in the label only")
check(c.connection_choices(None) == [] and c.connection_choices("x") == []
      and c.connection_choices([{}, None, {"connectedAs": "a@b.c"}]) == [],
      "bad or nameless entries are skipped, never raised")
check(c.connection_choices([{"name": GUID2}])[0][0] == "(unknown account)  [acd6df42]",
      "an entry without connectedAs still shows")
check(c.CONNECTION_LIST_COMMAND == ["connection", "list", "--output", "json"],
      "the list is read as JSON")
check(c.connection_use_command("myworkaccount") == ["connection", "use", "--name", "myworkaccount"],
      "switching runs 'connection use --name'")
for argv, want in ((["login", "--authType", "deviceCode"], True), (["logout"], True),
                   (["connection", "use", "--name", "x"], True),
                   (["connection", "set", "--name", "x", "--newName", "y"], True),
                   (["connection", "remove", "--name", "x", "--force"], True),
                   (["connection", "list"], False), (["entra", "user", "list"], False),
                   ([], False)):
    check(c.changes_connection(argv) == want, "changes_connection(%s) is %s" % (argv, want))

# ---- 2. the tasks --------------------------------------------------------------------
diag = {t["name"]: t for t in c.TASKS["Diagnostics"]}
for name in ("List saved connections (accounts / tenants)", "Switch to another connection",
             "Rename a connection", "Remove a saved connection",
             "Sign in another account (adds a connection)", "Sign out"):
    check(name in diag, "Diagnostics has '%s'" % name)
check(diag["Remove a saved connection"]["destructive"] and diag["Sign out"]["destructive"],
      "removing a connection and signing out ask first")
check(not diag["Switch to another connection"]["destructive"], "switching does not ask")
_d, argv, problem = c.build_command(diag["Switch to another connection"], {"connection": "work"}, "Diagnostics")
check(argv == ["connection", "use", "--name", "work"] and not problem, "Switch builds 'connection use --name work'")
_d, argv, problem = c.build_command(diag["Rename a connection"],
                                    {"connection": GUID1, "newname": "school"}, "Diagnostics")
check(argv == ["connection", "set", "--name", GUID1, "--newName", "school"], "Rename builds 'connection set'")
_d, argv, problem = c.build_command(diag["Remove a saved connection"], {"connection": "old"}, "Diagnostics")
check(argv == ["connection", "remove", "--name", "old", "--force"],
      "Remove adds --force (M365GUI asks instead; the CLI cannot ask - no input)")
login = diag["Sign in another account (adds a connection)"]
_d, argv, problem = c.build_command(login, {"authtype": "deviceCode", "connname": ""}, "Diagnostics")
check(argv == ["login", "--authType", "deviceCode"], "Sign in: no name -> no --connectionName")
_d, argv, problem = c.build_command(login, {"authtype": "browser", "connname": "school"}, "Diagnostics")
check(argv == ["login", "--authType", "browser", "--connectionName", "school"],
      "Sign in with a name for the new connection")
check(login["fields"][0]["choices"] == ["deviceCode", "browser"],
      "Sign in offers only the two ways a person signs in (code or web browser)")
for name in ("Switch to another connection", "Rename a connection", "Remove a saved connection"):
    t = diag[name]
    kinds = {f["key"]: c.picker_kind("Diagnostics", t, f) for f in t["fields"]}
    check(kinds.get("connection") == "connection", "%s: the connection box gets a Pick... list" % name)
check(c.picker_kind("Diagnostics", login, login["fields"][1]) is None,
      "the NEW connection's name gets no list")

# ---- 3. the window (hidden), with a fake m365 ---------------------------------------------
tmp = tempfile.mkdtemp(prefix="m365gui_conn_")
m.INI_PATH, m.LOG_DIR = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "Logs")
m.TASKLISTS_PATH = os.path.join(tmp, "m365gui_tasklists.json")
m.find_m365 = lambda saved: "m365"
m.M365Gui._startup_checks = lambda self: None
state = {"active": GUID1}
calls = []
def fake_run(self, argv, timeout=60):
    calls.append(list(argv))
    if argv[:1] == ["status"]:
        who = "alexw@contoso.com" if state["active"] == GUID1 else "admin@fabrikam.com"
        return 0, json.dumps({"connectedAs": who})
    if argv[:2] == ["connection", "list"]:
        return 0, json.dumps([{"name": GUID1, "connectedAs": "alexw@contoso.com", "authType": "browser",
                               "active": state["active"] == GUID1},
                              {"name": "fabrikam", "connectedAs": "admin@fabrikam.com",
                               "authType": "deviceCode", "active": state["active"] == "fabrikam"}])
    if argv[:2] == ["connection", "use"]:
        state["active"] = argv[3]
        return 0, ""
    return 1, "unexpected"
m.M365Gui._quiet_run = fake_run
app = m.M365Gui()
app.withdraw()
app.update()

def settle(seconds=3):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.05)

def widgets(win, cls):
    out, todo = [], [win]
    while todo:
        w = todo.pop()
        todo.extend(w.winfo_children())
        if w.winfo_class() == cls:
            out.append(w)
    return out

settle()
values = tuple(app.connection_box.cget("values"))
check(values == ("alexw@contoso.com  [028de82d]", "admin@fabrikam.com  [fabrikam]"),
      "the Connection list shows both connections (%s)" % (values,))
check(app.connection_var.get() == "alexw@contoso.com  [028de82d]", "the active one is selected")
check(app.account_label.cget("text") == "Signed in as: alexw@contoso.com", "Signed in as the active one")

app._group_cache = [{"displayName": "Contoso staff"}]
app.connection_var.set("admin@fabrikam.com  [fabrikam]")
app._switch_connection()
settle()
check(["connection", "use", "--name", "fabrikam"] in calls, "choosing it runs 'connection use --name fabrikam'")
check(app.account_label.cget("text") == "Signed in as: admin@fabrikam.com", "Signed in as is checked again")
check(app._group_cache is None, "the Pick... group list of the OTHER tenant is forgotten")
check(app.connection_var.get() == "admin@fabrikam.com  [fabrikam]", "the new active one stays selected")

# Busy: a running task or workflow uses the connection - no switch, back to the active one.
before = len([a for a in calls if a[:2] == ["connection", "use"]])
m.messagebox.showinfo = lambda *a, **k: None
app.run_button.config(state="disabled")
app.connection_var.set("alexw@contoso.com  [028de82d]")
app._switch_connection()
settle(1)
check(len([a for a in calls if a[:2] == ["connection", "use"]]) == before,
      "while a task runs, the connection is NOT switched")
check(app.connection_var.get() == "admin@fabrikam.com  [fabrikam]", "the list goes back to the active one")
app.run_button.config(state="normal")

# Choosing the one already active does nothing.
app.connection_var.set("admin@fabrikam.com  [fabrikam]")
app._switch_connection()
settle(1)
check(len([a for a in calls if a[:2] == ["connection", "use"]]) == before, "choosing the active one runs nothing")

# A task that signs in / out or changes a connection checks the account again afterwards.
status_before = len([a for a in calls if a[:1] == ["status"]])
app._after_task(["connection", "set", "--name", "fabrikam", "--newName", "fab"])
settle()
check(len([a for a in calls if a[:1] == ["status"]]) > status_before,
      "after a connection task, Signed in as and the list are checked again")
status_before = len([a for a in calls if a[:1] == ["status"]])
app._after_task(["entra", "user", "list"])
settle(1)
check(len([a for a in calls if a[:1] == ["status"]]) == status_before, "any other task does not")

# The Pick... list for a connection box.
import tkinter as tk
cvar = tk.StringVar(value="")
app._pick("connection", cvar)
win = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
win.withdraw()
settle(2)
box = widgets(win, "Listbox")[0]
check(len(box.get(0, "end")) == 2, "Pick... lists the saved connections")
box.selection_set(0)
next(b for b in widgets(win, "TButton") if b.cget("text") == "OK").invoke()
check(cvar.get() == GUID1, "OK puts the connection's NAME (what --name takes) in the box")
app.destroy()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
