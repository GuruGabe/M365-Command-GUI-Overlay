# test_v06_pickers.py - v0.6 (10-23-2026): Pick... lists for user and group
# boxes, as in GAMGUI. 'entra user list' turns an extra --<property> <text>
# into a Graph startsWith filter (CLI v11.11 user-list.js + its docs), so
# users are searched on the server; groups are loaded once. The window is
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

def task(cat, name):
    return next(t for t in c.TASKS[cat] if t["name"] == name)

def kinds(cat, name):
    t = task(cat, name)
    return {f["key"]: c.picker_kind(cat, t, f) for f in t["fields"]}

# ---- 1. which boxes get a list ----------------------------------------------------
check(kinds("Users (Entra ID)", "Reset password")["email"] == "user", "a user's UPN box gets the user list")
check(kinds("Users (Entra ID)", "Create user")["email"] is None, "Create user (a NEW address) gets none")
check(kinds("Groups (Entra)", "Add member to group") == {"name": "group", "email": "user", "role": None},
      "Add member to group: group list + user list, none on the Role dropdown")
check(kinds("Groups (Entra)", "Create group")["name"] is None, "Create group (a NEW name) gets none")
check(kinds("Teams / M365 Groups", "Add member to a Team")["team"] == "group", "a Team's name gets the group list")
od = kinds("OneDrive", "Copy a user's OneDrive files to another user")
check(od["from"] == "user" and od["to"] == "user" and od["folder"] is None, "OneDrive copy: From and To get the user list")

# ---- 2. searching -------------------------------------------------------------------
cmds = c.user_search_commands("  Patt ")
check(cmds == [["entra", "user", "list", "--displayName", "Patt", "--properties",
                "displayName,userPrincipalName", "--output", "json"],
               ["entra", "user", "list", "--userPrincipalName", "Patt", "--properties",
                "displayName,userPrincipalName", "--output", "json"]],
      "a user search asks for names AND addresses that start with the text")
check(c.user_search_commands("   ") == [], "nothing typed -> no search")
merged = c.people_choices([[{"displayName": "Pat Smith", "userPrincipalName": "psmith@contoso.com"}],
                           [{"displayName": "Pat Smith", "userPrincipalName": "PSmith@contoso.com"},
                            {"displayName": "Adam Pat", "userPrincipalName": "pat.adam@contoso.com"}]])
check(merged == [("Adam Pat  <pat.adam@contoso.com>", "pat.adam@contoso.com"),
                 ("Pat Smith  <psmith@contoso.com>", "psmith@contoso.com")],
      "the two searches are merged, de-duplicated (any case) and sorted")
groups = [{"displayName": "Sales Team", "mail": "sales@contoso.com"},
          {"displayName": "Staff - Sales", "mail": None}, {"displayName": "IT", "mail": "it@contoso.com"}]
check([v for _l, v in c.group_choices(groups, "sales")] == ["Sales Team", "Staff - Sales"],
      "groups: every word typed, anywhere in the name or address")
check(len(c.group_choices(groups, "")) == 3, "groups: blank shows them all")

# ---- 3. the window (hidden), with a fake m365 ------------------------------------------
tmp = tempfile.mkdtemp(prefix="m365gui_pick_")
m.INI_PATH, m.LOG_DIR = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "Logs")
m.TASKLISTS_PATH = os.path.join(tmp, "m365gui_tasklists.json")
m.find_m365 = lambda saved: "m365"
m.M365Gui._startup_checks = lambda self: None
calls = []
def fake_run(self, argv, timeout=60):
    calls.append(list(argv))
    if argv[:1] == ["status"]:
        return 0, '{"connectedAs": "admin@contoso.com"}'
    if argv[:3] == ["entra", "user", "list"]:
        return 0, json.dumps([{"displayName": "Pat Smith", "userPrincipalName": "psmith@contoso.com"}])
    if argv[:3] == ["entra", "group", "list"]:
        return 0, json.dumps(groups)
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

def form_buttons():
    return [w.cget("text") for w in app.form_frame.winfo_children() if w.winfo_class() == "TButton"]

app.current_category = "Groups (Entra)"
app._show_form(task("Groups (Entra)", "Add member to group"))
check(form_buttons().count("Pick...") == 2, "the form shows 2 Pick... buttons (group + user)")
app.current_category = "Users (Entra ID)"
app._show_form(task("Users (Entra ID)", "Create user"))
check("Pick..." not in form_buttons(), "Create user shows none")

import tkinter as tk
var = tk.StringVar(value="pat")
app._pick("user", var)
win = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
win.withdraw()
next(b for b in widgets(win, "TButton") if b.cget("text") == "Search").invoke()
settle()
box = widgets(win, "Listbox")[0]
check(box.get(0, "end") == ("Pat Smith  <psmith@contoso.com>",), "the user list shows the search result")
check(["entra", "user", "list", "--displayName", "pat"] == calls[-2][:5], "searched with what was typed")
box.selection_set(0)
next(b for b in widgets(win, "TButton") if b.cget("text") == "OK").invoke()
check(var.get() == "psmith@contoso.com", "OK puts the sign-in name (UPN) in the box")

gvar = tk.StringVar(value="")
app._pick("group", gvar)
win = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
win.withdraw()
settle()
box = widgets(win, "Listbox")[0]
check(len(box.get(0, "end")) == 3, "the group list loads every group once")
widgets(win, "TEntry")[0].insert(0, "it")
settle(1)
check(box.get(0, "end") == ("IT  <it@contoso.com>",), "typing narrows the group list straight away")
box.selection_set(0)
next(b for b in widgets(win, "TButton") if b.cget("text") == "OK").invoke()
check(gvar.get() == "IT", "OK puts the group's display name in the box")
before = len([a for a in calls if a[:3] == ["entra", "group", "list"]])
app._pick("group", gvar)
settle(1)
check(len([a for a in calls if a[:3] == ["entra", "group", "list"]]) == before == 1,
      "the groups are NOT loaded again in the same session")
app.destroy()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
