# test_v06_bulk.py - v0.6 (10-23-2026): "Run for each CSV row" (as
# GAMGUI). The m365 CLI has no CSV loop, so M365GUI runs the task once per
# row. Hidden window; m365 is a fake that records every command.
import os, sys, csv, time, tempfile
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

# ---- 1. the plain rules ----------------------------------------------------------------
block = task("Users (Entra ID)", "Block sign-in")
check(c.bulk_guess_column(block["fields"][0], ["displayName", "UserPrincipalName"]) == "UserPrincipalName",
      "a UPN box guesses the userPrincipalName column (any case)")
check(c.bulk_guess_column({"key": "password"}, ["upn"]) == c.FORM_VALUE, "no likely column -> the form's value")
add = task("Groups (Entra)", "Add member to group")
check(c.bulk_guess_column(add["fields"][0], ["displayName", "upn"]) == "displayName", "a group name box -> displayName")
plan = c.bulk_plan(add, "Groups (Entra)", {"name": "Staff", "email": "", "role": "Member"},
                   {"name": c.FORM_VALUE, "email": "upn", "role": c.FORM_VALUE},
                   [{"upn": "a@x.com"}, {"upn": " "}, {"upn": chr(0x201c) + "b@x.com" + chr(0x201d)}])
check(plan[0] == (2, ["entra", "group", "member", "add", "--groupName", "Staff", "--userNames", "a@x.com",
                      "--role", "Member"], ""), "row 2: the form's group + the row's user")
check(plan[1][0] == 3 and plan[1][2] == "Missing required value: email", "a blank cell is reported with its row number")
check(plan[2][1][7] == "b@x.com", "pasted curly quotes in a cell are cleaned too")
check(c.bulk_available(block) and not c.bulk_available(task("OneDrive", "Copy a user's OneDrive files to another user"))
      and not c.bulk_available(task("Users (Entra ID)", "List users")),
      "available for change tasks with boxes; not for workflows or box-less lists")

# ---- 2. the dialog and the run (hidden window, fake m365) ------------------------------------
tmp = tempfile.mkdtemp(prefix="m365gui_bulk_")
m.INI_PATH, m.TASKLISTS_PATH = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "t.json")
m.LOG_DIR = os.path.join(tmp, "Logs")
m.find_m365 = lambda saved: "m365"
m.M365Gui._startup_checks = lambda self: None
m.M365Gui._refresh_account = lambda self: None
asked = []
m.messagebox.askyesno = lambda *a, **k: asked.append(a) or True
m.messagebox.showerror = lambda *a, **k: asked.append(("ERROR",) + a)
m.messagebox.showinfo = lambda *a, **k: asked.append(("INFO",) + a)
app = m.M365Gui()
app.withdraw()
app.update()
ran = []
def fake_capture(argv):
    ran.append(list(argv))
    if "bad@x.com" in argv:
        return 1, '{"error":"Resource bad@x.com does not exist"}'
    return 0, ""
app._capture = fake_capture

def open_task(cat, name):
    for parent in app.tree.get_children(""):
        if app.tree.item(parent, "text") == cat:
            for child in app.tree.get_children(parent):
                if app.tree.item(child, "text") == name:
                    app.tree.selection_set(child)
                    app.update()
                    return

def widgets(win, cls):
    out, todo = [], [win]
    while todo:
        w = todo.pop()
        todo.extend(w.winfo_children())
        if w.winfo_class() == cls:
            out.append(w)
    return out

def button(win, text):
    return next(b for b in widgets(win, "TButton") if b.cget("text") == text)

def wait_done():
    end = time.time() + 20
    while time.time() < end:
        app.update()
        if str(app.run_button.cget("state")) == "normal":
            break
        time.sleep(0.05)
    app.update()

data = os.path.join(tmp, "leavers.csv")
with open(data, "w", newline="", encoding="utf-8") as h:
    w = csv.writer(h)
    w.writerow(["displayName", "userPrincipalName"])
    for upn in ("a@x.com", "bad@x.com", "c@x.com", "d@x.com"):
        w.writerow([upn.split("@")[0], upn])

open_task("Users (Entra ID)", "Delete user (DESTRUCTIVE)")
app._bulk_dialog()
win = app._bulk_window
win.withdraw()
m.filedialog.askopenfilename = lambda **k: data
button(win, "Browse...").invoke()
app.update()
combos = widgets(win, "TCombobox")
check(len(combos) == 1 and combos[0].get() == "userPrincipalName", "the dialog guessed the UPN column")
entries = widgets(win, "TEntry")
limit = next(e for e in entries if int(e.cget("width")) == 5)
limit.insert(0, "2")
button(win, "Run").invoke()
wait_done()
check([a[a.index("--userName") + 1] for a in ran] == ["a@x.com", "bad@x.com"],
      "test run: only the first 2 rows ran, in order")
check(any("2 row(s)" in str(q) for q in asked), "a DESTRUCTIVE task asks once, naming the row count")
out = app.output_box.get("1.0", "end")
check("row 2 OK" in out and "row 3 FAILED" in out and "does not exist" in out,
      "each row's result is shown, with the error of a failed row")
records = [f for f in os.listdir(m.LOG_DIR) if f.startswith("Bulk_")]
rows = list(csv.reader(open(os.path.join(m.LOG_DIR, records[0]), encoding="utf-8"))) if records else []
check(len(records) == 1 and [r[1] for r in rows[1:]] == ["OK", "FAILED"], "a CSV record of every row is saved")
check("DONE: 1 OK, 1 failed" in out, "the summary counts OK and failed rows")

# Stop: a fake m365 that takes a moment, Stop after the first row.
ran.clear()
def slow_capture(argv):
    ran.append(list(argv))
    time.sleep(0.4)
    return 0, ""
app._capture = slow_capture
app._bulk_dialog()
win = app._bulk_window
win.withdraw()
button(win, "Browse...").invoke()
button(win, "Run").invoke()
end = time.time() + 5
while not ran and time.time() < end:
    app.update(); time.sleep(0.02)
app._stop()
wait_done()
check(1 <= len(ran) < 4 and "Stopped" in app.output_box.get("1.0", "end"),
      "Stop ends the run after the current row (%d of 4 ran)" % len(ran))

# A row that cannot be built stops everything BEFORE anything runs.
ran.clear()
with open(data, "a", newline="", encoding="utf-8") as h:
    csv.writer(h).writerow(["nobody", ""])
app._capture = fake_capture
app._bulk_dialog()
win = app._bulk_window
win.withdraw()
button(win, "Browse...").invoke()
button(win, "Run").invoke()
app.update()
check(not ran and any(q[0] == "ERROR" and "row 6" in str(q) for q in asked),
      "a blank cell (row 6) is reported and NOTHING runs")
win.destroy()
app.destroy()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
