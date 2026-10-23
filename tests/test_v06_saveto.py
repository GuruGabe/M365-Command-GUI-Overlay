# test_v06_saveto.py - v0.6 (10-23-2026): "Save results to" Screen / CSV
# file / JSON file for the tasks that print lists (as GAMGUI's output
# choice). The CLI writes the format itself (--output csv / json); M365GUI
# saves it - and never saves an ERROR into the file. Also: a dropdown starts
# on its default (GAMGUI 2.91's fix). Hidden window, stand-in m365.
import os, sys, time, tempfile
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

# ---- 1. the plain rules -------------------------------------------------------------
check(c.saves_output(task("Users (Entra ID)", "List users")), "a list task can save to a file")
check(not c.saves_output(task("Users (Entra ID)", "Reset password")), "a change task cannot")
check(not c.saves_output(task("OneDrive", "Copy a user's OneDrive files to another user")), "a workflow cannot")
check(c.with_output_format(["entra", "user", "list", "--output", "text"], "csv") ==
      ["entra", "user", "list", "--output", "csv"], "--output text becomes csv")
check(c.with_output_format(["status"], "json") == ["status", "--output", "json"], "added when missing")
check(c.dropdown_start({"choices": ["a", "b"], "default": "b"}) == "b", "a dropdown starts on its default")
check(c.dropdown_start({"choices": ["a", "b"], "default": ""}) == "a", "...else on the first choice")
tmp = tempfile.mkdtemp(prefix="m365gui_save_")
out = os.path.join(tmp, "x.csv")
check(m.save_results(out, "a,b\n1,2\n") == "Saved to %s (2 lines).\n" % out
      and open(out).read() == "a,b\n1,2\n", "save_results writes the file and says how many lines")
check("Could not save" in m.save_results(os.path.join(tmp, "no", "such", "dir", "x.csv"), "x"),
      "a file that cannot be written is reported, not raised")

# ---- 2. the window (hidden) with a stand-in m365 ----------------------------------------
m.INI_PATH, m.LOG_DIR = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "Logs")
m.TASKLISTS_PATH = os.path.join(tmp, "m365gui_tasklists.json")
m.find_m365 = lambda saved: "m365"
m.M365Gui._startup_checks = lambda self: None
m.M365Gui._refresh_account = lambda self: None
app = m.M365Gui()
app.withdraw()
app.update()
ran = []
SCRIPT = {"ok": "import sys; print('displayName,userPrincipalName'); print('Pat,p@x.com')",
          "fail": "import sys; print('{\"error\":\"Insufficient privileges\"}'); sys.exit(1)"}
mode = ["ok"]
def fake_invocation(argv):
    ran.append(list(argv))
    return [sys.executable, "-c", SCRIPT[mode[0]]]
app._build_invocation = fake_invocation

def output():
    return app.output_box.get("1.0", "end")

def run_and_wait():
    app._run()
    end = time.time() + 20
    while time.time() < end:
        app.update()
        if app.running_proc is None and str(app.run_button.cget("state")) == "normal":
            break
        time.sleep(0.05)
    app.update()

def open_task(cat, name):
    # Clicks the task in the list, as a person would.
    for parent in app.tree.get_children(""):
        if app.tree.item(parent, "text") != cat:
            continue
        for child in app.tree.get_children(parent):
            if app.tree.item(child, "text") == name:
                app.tree.selection_set(child)
                app.update()
                return
    raise SystemExit("not in the list: " + name)

open_task("Users (Entra ID)", "List users")
labels = [w.cget("text") for w in app.form_frame.winfo_children() if w.winfo_class() == "TLabel"]
check("Save results to" in labels, "List users shows 'Save results to'")
app.save_var.set("CSV file")
app.save_path_var.set("")
before = len(ran)
import tkinter.messagebox as mb
shown = []
mb.showerror = lambda *a, **k: shown.append(a)
m.messagebox.showerror = mb.showerror
app._run()
check(len(ran) == before and shown, "CSV chosen but no file -> asks for one, runs nothing")

target = os.path.join(tmp, "users.csv")
app.save_path_var.set(target)
run_and_wait()
check(ran[-1][-2:] == ["--output", "csv"], "the command runs with --output csv (%s)" % ran[-1][-2:])
check(open(target).read().splitlines() == ["displayName,userPrincipalName", "Pat,p@x.com"],
      "the CLI's CSV is saved to the chosen file")
check("Saved to " + target in output() and "Pat,p@x.com" not in output(),
      "the window says where it was saved (the rows go to the file, not the screen)")

mode[0] = "fail"
bad = os.path.join(tmp, "bad.csv")
app.save_path_var.set(bad)
run_and_wait()
check(not os.path.exists(bad), "a failed command saves NO file")
check("Insufficient privileges" in output(), "...its error is shown in the window instead")

mode[0] = "ok"
app.save_var.set("Screen")
run_and_wait()
check(ran[-1][-2:] == ["--output", "text"] and "Pat,p@x.com" in output(),
      "Screen: the command is unchanged and its output shows in the window")

# v0.6 bug found by this test: after a run, Recent is redrawn and the same
# task re-selected - which used to redraw the form and WIPE what was typed.
open_task("Users (Entra ID)", "Get user info")
box_var = dict(app.field_vars)["email"]
box_var.set("typed@x.com")
app._preview()
run_and_wait()
app.update()
check(dict(app.field_vars).get("email") is box_var and box_var.get() == "typed@x.com",
      "what was typed is still in the boxes after a run")

open_task("Groups (Entra)", "Get group info")
labels = [w.cget("text") for w in app.form_frame.winfo_children() if w.winfo_class() == "TLabel"]
check("Save results to" in labels, "Get group info (details) can be saved too")
open_task("Users (Entra ID)", "Block sign-in")
labels = [w.cget("text") for w in app.form_frame.winfo_children() if w.winfo_class() == "TLabel"]
check("Save results to" not in labels, "Block sign-in (a change) has no save choice")
app.destroy()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
