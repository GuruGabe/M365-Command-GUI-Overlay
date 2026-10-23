# test_v09_redact.py - v0.9 (10-23-2026): a password typed into a form never
# reaches a file (as GAMGUI's redact_secrets). Before 0.9 the session log and
# the Run-for-each-CSV-row record held each command as it ran - with the new
# password of Reset password / Create user. The window still shows it.
import os, sys, csv, json, time, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import M365GUI as m
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

R = c.redact_secrets
check(R('m365 entra user set --userName a@x --resetPassword --newPassword "Temp Pass1!" --x')
      == 'm365 entra user set --userName a@x --resetPassword --newPassword ******** --x',
      "--newPassword with a quoted value")
check(R("entra user add --password p@ss --displayName X") == "entra user add --password ******** --displayName X",
      "--password")
check(R("--currentPassword=old --newPassword=new") == "--currentPassword=******** --newPassword=********",
      "--currentPassword / the = form")
check(R("--resetPassword --forceChangePasswordNextSignIn --passwordProfile x") ==
      "--resetPassword --forceChangePasswordNextSignIn --passwordProfile x", "look-alike option names are left alone")

# ---- the desktop window (hidden), with a stand-in m365 -----------------------------------
tmp = tempfile.mkdtemp(prefix="m365gui_redact_")
m.INI_PATH, m.TASKLISTS_PATH = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "t.json")
m.LOG_DIR = os.path.join(tmp, "Logs")
m.find_m365 = lambda saved: "m365"
m.M365Gui._startup_checks = lambda self: None
m.M365Gui._refresh_account = lambda self: None
m.messagebox.askyesno = lambda *a, **k: True
app = m.M365Gui()
app.withdraw()
app.update()
app._build_invocation = lambda argv: [sys.executable, "-c", "print('ok')"]
app._capture = lambda argv: (0, "")

def wait_done():
    end = time.time() + 20
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
fields["email"].set("a@contoso.com")
fields["password"].set("Secret Pass9!")
app._preview()
app._run()
wait_done()
log = open(app.log_path, encoding="utf-8").read()
check("Secret Pass9!" in app.output_box.get("1.0", "end"), "the window shows the command as typed")
check("Secret Pass9!" not in log and "--newPassword ********" in log, "the session log has ******** instead")

# Run for each CSV row: the record file is masked too.
data = os.path.join(tmp, "people.csv")
with open(data, "w", newline="") as h:
    w = csv.writer(h)
    w.writerow(["upn", "pw"])
    w.writerow(["a@contoso.com", "RowSecret1!"])
app._bulk_dialog()
win = app._bulk_window
win.withdraw()
steps = c.bulk_plan(app.current_task, app.current_category, app._collect(),
                    {"email": "upn", "password": "pw"}, [{"upn": "a@contoso.com", "pw": "RowSecret1!"}])
win.destroy()
app._run_bulk(app.current_task, steps, data)
wait_done()
record = [f for f in os.listdir(m.LOG_DIR) if f.startswith("Bulk_")]
text = open(os.path.join(m.LOG_DIR, record[0]), encoding="utf-8").read() if record else ""
check(record and "RowSecret1!" not in text and "********" in text, "the CSV-row record has ******** instead")
check("RowSecret1!" not in open(app.log_path, encoding="utf-8").read(), "...and so does the log")
app.destroy()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
