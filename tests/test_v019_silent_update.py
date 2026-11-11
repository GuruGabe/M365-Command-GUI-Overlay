# test_v019_silent_update.py - M365GUI 0.19 (11-11-2026): 'Install updates
# automatically' (Gabe: "add the ability to silently update" - at startup), the
# same design as GAMGUI 3.04. No window opens: M365Gui's own methods run on a
# stand-in object. The updater is run for real in a temporary folder against a
# repo name that does not exist (it must fail AND reopen the app, which here is
# whoami.exe).
import os, shutil, subprocess, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import m365_update as mu
import M365GUI as m

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

# ---- 1. m365_update.silent_update_blocker ---------------------------------------------------------
B = mu.silent_update_blocker
ok = dict(system="Windows", frozen=True, busy=False, exe_install=False, updater_present=True,
          posix_kind="", failed_tag="", tag="0.20")
check(B(**ok) == "", "portable Windows copy: silent")
for change, word in ((dict(exe_install=True), "administrator"), (dict(busy=True), "running"),
                     (dict(frozen=False), "source"), (dict(updater_present=False), "updatem365gui.ps1"),
                     (dict(failed_tag="0.20"), "did not finish")):
    got = B(**dict(ok, **change))
    check(word in got, "asks when %s: %r" % (list(change)[0], got))
check(B(**dict(ok, failed_tag="0.19")) == "", "an OLDER failed version does not block a newer one")
for kind, silent in (("mac-app", True), ("linux-portable", True), ("linux-package", False),
                     ("source", False), ("unknown", False)):
    got = B(**dict(ok, system="Darwin" if kind == "mac-app" else "Linux", posix_kind=kind))
    check((got == "") == silent, "%s: %s (%r)" % (kind, "silent" if silent else "asks", got))

# ---- 2. M365Gui's own methods on a stand-in -------------------------------------------------------
class Fake:
    pass
for name in ("_on_update_check_result", "_check_silent_update_result", "_silent_self_update",
             "_toggle_auto_install"):
    setattr(Fake, name, getattr(m.M365Gui, name))


def make(auto_install=True, blocker=""):
    f = Fake()
    f.calls, f.settings = [], {}
    f.auto_install_updates = auto_install
    f._version_tuple = m.M365Gui._version_tuple.__get__(f)
    f._log = lambda text: f.calls.append(("log", text))
    f._prompt_update = lambda tag: f.calls.append(("prompt", tag))
    f._silent_update_blocker = lambda tag: blocker
    f.real_silent = f._silent_self_update
    f._silent_self_update = lambda tag: f.calls.append(("silent", tag))
    f._setting = lambda key, default="": f.settings.get(key, default)
    f._save_setting = lambda key, value: f.settings.__setitem__(key, value)
    return f

newer = "9.99"
f = make()
f._on_update_check_result(newer, "", True)
check(("silent", newer) in f.calls and not any(c[0] == "prompt" for c in f.calls),
      "startup + setting on + nothing blocks: silent, no question")
f = make(blocker="a command is running")
f._on_update_check_result(newer, "", True)
check(("prompt", newer) in f.calls and any("needs a question: a command is running" in str(c[1])
                                           for c in f.calls), "blocked: asks and logs why")
f = make()
f._on_update_check_result(newer, "", False)
check(("prompt", newer) in f.calls, "Check for updates now always asks")
f = make(auto_install=False)
f._on_update_check_result(newer, "", True)
check(("prompt", newer) in f.calls and not any(c[0] == "silent" for c in f.calls), "setting off: asks")

shown = []
real_warning = m.messagebox.showwarning
m.messagebox.showwarning = lambda title, text: shown.append(text)
f = make()
f.settings["silent_update_pending"] = newer
f._check_silent_update_result()
check(f.settings.get("silent_update_pending") == "" and f.settings.get("silent_update_failed") == newer,
      "older than the pending version: marked failed")
check(shown and "did not finish" in shown[0] and "ask before trying " + newer in shown[0],
      "it says so once, and that it will ask")
shown.clear()
f = make()
f.settings["silent_update_pending"] = m.APP_VERSION
f._check_silent_update_result()
check(f.settings.get("silent_update_pending") == "" and "silent_update_failed" not in f.settings
      and not shown, "reached the version: cleared, nothing shown")
m.messagebox.showwarning = real_warning

if sys.platform == "win32":
    started = []
    real_popen = m.subprocess.Popen
    m.subprocess.Popen = lambda args, **kw: started.append((args, kw))
    f = make()
    f.destroyed = False
    f.destroy = lambda: setattr(f, "destroyed", True)
    f._update_in_progress = False
    f.real_silent("0.99")
    m.subprocess.Popen = real_popen
    args, kw = started[0]
    check("-Quiet -Launch" in args[-1] and "updatem365gui.ps1" in args[-1]
          and "-InstallType zip" in args[-1], "the updater runs with -Quiet -Launch")
    check("Hidden" in args and kw.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW, "no window")
    check(f.destroyed and f._update_in_progress and f.settings.get("silent_update_pending") == "0.99",
          "pending recorded, M365GUI closes")
    def boom(*a, **k):
        raise OSError("blocked")
    m.subprocess.Popen = boom
    f = make()
    f.destroyed = False
    f.destroy = lambda: setattr(f, "destroyed", True)
    f._update_in_progress = False
    f.real_silent("0.99")
    m.subprocess.Popen = real_popen
    check(("prompt", "0.99") in f.calls and not f.destroyed and f.settings.get("silent_update_pending") == "",
          "updater could not start: asks instead, stays open")

f = make(auto_install=False)
f.check_updates = False
f.auto_install_var = types.SimpleNamespace(get=lambda: True)
f.check_updates_var = types.SimpleNamespace(set=lambda v: None)
f._toggle_auto_install()
check(f.auto_install_updates and f.check_updates
      and f.settings == {"auto_install_updates": "true", "check_updates": "true"},
      "turning it on turns the startup check on")

# ---- 3. updatem365gui.ps1 1.1: a failed -Quiet -Launch update reopens the app ---------------------
if sys.platform == "win32":
    box = tempfile.mkdtemp(prefix="m365gui_v019_upd_")
    shutil.copy2(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "whoami.exe"),
                 os.path.join(box, "M365GUI.exe"))
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                        os.path.join(ROOT, "updatem365gui.ps1"), "-InstallType", "zip",
                        "-InstallRoot", box, "-Repo", "GuruGabe/no-such-repo-m365gui-v019-test",
                        "-Quiet", "-Launch"], capture_output=True, text=True, timeout=300)
    p = os.path.join(box, "Logs", "M365GUI-Update.log")
    log = open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else ""
    check(r.returncode == 1, "the updater failed (exit %s)" % r.returncode)
    check("ERROR:" in log and "Reopening M365GUI after the failed update." in log,
          "it logged the error and reopened M365GUI")
    check(not (r.stdout or "").strip(), "-Quiet: nothing printed")
    shutil.rmtree(box, ignore_errors=True)

for name in ("M365GUI.py", "m365_update.py", "updatem365gui.ps1", "CHANGELOG.txt", "README.txt"):
    data = open(os.path.join(ROOT, name), "rb").read()
    check(all(b < 128 for b in data), name + ": ASCII only")

print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
