# test_v012_dark.py - v0.12 (10-27-2026): Settings > Dark mode (as GAMGUI).
# A hidden window with a stand-in m365 (nothing runs, nothing touches a
# tenant): light by default with the native theme left alone, dark paints
# the ttk styles, both boxes and later pop-ups, the choice is saved in
# m365gui.ini and comes back on the next start, and light restores the
# native theme.
import os, sys, time, tempfile, configparser
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import M365GUI as m

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

tmp = tempfile.mkdtemp(prefix="m365gui_dark_")
m.INI_PATH, m.LOG_DIR = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "Logs")
m.TASKLISTS_PATH = os.path.join(tmp, "m365gui_tasklists.json")
m.M365Gui._startup_checks = lambda self: None
m.M365Gui._refresh_account = lambda self: None
m.find_m365 = lambda saved: "m365"

def settle(app, seconds=0.5):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.05)

app = m.M365Gui()
app.withdraw()
try:
    settle(app)
    native = app._default_theme
    light_bg = app.output_box.cget("bg")
    check(not app.dark_mode and app.style.theme_use() == native, "light by default, native theme")
    check(app.dark_var.get() is False, "the Settings menu checkbox is off")

    app.dark_var.set(True)
    app._toggle_dark()
    settle(app)
    p = m.DARK_PALETTE
    check(app.style.theme_use() == "clam", "dark: the clam theme (honors colors on Windows)")
    check(app.output_box.cget("bg") == p["entry_bg"] and app.preview_box.cget("fg") == p["fg"],
          "dark: the output and preview boxes")
    check(app.style.lookup("TLabel", "background") == p["bg"]
          and app.style.lookup("Treeview", "fieldbackground") == p["entry_bg"],
          "dark: labels and the task list")
    cfg = configparser.ConfigParser(); cfg.read(m.INI_PATH)
    check(cfg.get("m365gui", "dark_mode", fallback="") == "true", "dark is saved in m365gui.ini")
    import tkinter as tk
    pop = tk.Toplevel(app); lst = tk.Listbox(pop); txt = tk.Text(pop)
    check(lst.cget("background") == p["entry_bg"] and txt.cget("background") == p["entry_bg"]
          and pop.cget("background") == p["bg"], "dark: a pop-up made later (Pick... list, text) is dark too")
    pop.destroy()

    app.dark_var.set(False)
    app._toggle_dark()
    settle(app)
    check(app.style.theme_use() == native, "light again: the native theme")
    check(app.output_box.cget("bg") == m.LIGHT_PALETTE["entry_bg"], "light again: the boxes are light")
    pop = tk.Toplevel(app); lst = tk.Listbox(pop)
    check(lst.cget("background") == m.LIGHT_PALETTE["entry_bg"], "light again: later pop-ups are light")
    pop.destroy()
finally:
    app.destroy()

# The next start remembers dark.
cfg = configparser.ConfigParser(); cfg.read(m.INI_PATH)
cfg.set("m365gui", "dark_mode", "true")
with open(m.INI_PATH, "w") as h:
    cfg.write(h)
app = m.M365Gui()
app.withdraw()
try:
    settle(app)
    check(app.dark_mode and app.style.theme_use() == "clam"
          and app.output_box.cget("bg") == m.DARK_PALETTE["entry_bg"], "dark comes back on the next start")
finally:
    app.destroy()
check(light_bg != "", "light start left the output box's native color (%s)" % light_bg)
import shutil; shutil.rmtree(tmp, ignore_errors=True)
print("FAILURES:", len(fails))
