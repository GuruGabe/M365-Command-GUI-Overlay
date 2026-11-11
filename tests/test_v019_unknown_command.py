# test_v019_unknown_command.py - v0.19 (11-10-2026): a command the installed
# CLI does not have. Seen live with CLI 12.0.0: "Command '<name>' was not
# found. Below you can find the commands ..." then the whole help screen, and
# EXIT CODE 0 - M365GUI showed it as a success, and Save results would have
# written the help screen into the file. Now a plain note; nothing is saved.
# Also the two read-only tasks new in CLI 12.0.0 (agent blueprints). The
# browser runner is run for real with a stand-in m365 (no tenant).
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import m365_setup as s
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

HELP = ("Command 'entra agent blueprint list' was not found. Below you can find the commands "
        "and command groups you can use. For detailed information on a command group, use "
        "'m365 [command group] --help'.\n\nCLI for Microsoft 365 v11.11.0\nManage Microsoft "
        "365 and SharePoint Framework projects on any platform \n\nCommands:\n\n  docs "
        "[options]     Returns the CLI for Microsoft 365 docs webpage URL\n")

# ---- 1. the facts ---------------------------------------------------------------------------
check(s.unknown_command(HELP) == "entra agent blueprint list", "the command name is read")
note = s.unknown_command_note(HELP)
check("m365 entra agent blueprint list" in note and "Update the CLI" in note
      and "Nothing was changed" in note, "the note: which command, update the CLI, nothing changed")
for ok in ("", "id  displayName\n--  -----------\n", "Error: Resource 'x' does not exist",
           "Command completed. 'Command' was not found in the name\n"):
    check(s.unknown_command_note(ok) == "", "no note for %r" % ok[:40])

# ---- 2. the browser runner, for real ------------------------------------------------------------
import m365_web as w
tmp = tempfile.mkdtemp(prefix="m365_v019_")
fake = os.path.join(tmp, "fake_m365.py")
with open(fake, "w", encoding="utf-8") as fh:
    fh.write("import sys\nsys.stdout.write(%r)\nsys.exit(0)\n" % HELP)
w.invocation = lambda argv: [sys.executable, fake] + list(argv)
import M365GUI as app
app.LOG_DIR = os.path.join(tmp, "Logs")
job = w.Job()
w.run_command(job, ["entra", "agent", "blueprint", "list", "--output", "text"])
out = "".join(job.lines)
check("Update the CLI" in out and "Commands:" not in out and "docs [options]" not in out,
      "browser: the note instead of the help screen")
job = w.Job()
w.run_command(job, ["entra", "agent", "blueprint", "list"], save_fmt="csv", save_name="x")
out = "".join(job.lines)
downloads = os.path.join(app.LOG_DIR, "Downloads")
check("Update the CLI" in out and getattr(job, "file", None) in (None, "", ())
      and not (os.path.isdir(downloads) and os.listdir(downloads)),
      "browser: Save results writes NO file")

# ---- 3. the desktop runner (source - its Tk window is tested elsewhere) ------------------------------
gui = open(os.path.join(ROOT, "M365GUI.py"), encoding="utf-8").read()
check("unknown = m365_setup.unknown_command_note(text[:2000])" in gui
      and "if proc.returncode == 0 and not unknown:" in gui
      and "unknown = m365_setup.unknown_command_note(line)" in gui,
      "desktop: the note, and Save results only when the command was known")

# ---- 4. the two tasks new in CLI 12.0.0 ----------------------------------------------------------
tasks = {t["name"]: t for ts in c.TASKS.values() for t in ts}
for name, cmd in (("AI agent blueprints (Entra Agent ID)", "entra agent blueprint list"),
                  ("AI agent blueprint principals (Entra Agent ID)",
                   "entra agent blueprintprincipal list")):
    t = tasks.get(name)
    check(t is not None and t["template"] == cmd + " --output text" and not t["fields"]
          and "12.0" in t["desc"] and not t["destructive"], "task: " + name)

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
