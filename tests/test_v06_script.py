# test_v06_script.py - v0.6 (10-23-2026): "Save as script" (as GAMGUI). The
# saved PowerShell / bash script must hand m365 EXACTLY the values in the
# form, whatever they contain - checked by running the scripts in the real
# shells with a stand-in 'm365' function that echoes its arguments.
import os, sys, json, shutil, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

ARGV = ["entra", "group", "add", "--displayName", "Sales & Marketing 'East' \"HQ\"",
        "--description", "50% off; $HOME `whoami` | x > y", "--mailNickname", "sales"]
ps1 = c.script_text(ARGV, "ps1", "Create group", "0.6", "10-23-2026")
sh = c.script_text(ARGV, "sh", "Create group", "0.6", "10-23-2026")
check(ps1.count("\r\n") == ps1.count("\n") and "& m365 @arguments" in ps1, "the .ps1 has CRLF lines and runs m365")
# Everything but double quotes (Windows PowerShell 5.1 cannot pass those).
ARGV2 = [a.replace('"', "") for a in ARGV]
check(sh.startswith("#!/usr/bin/env bash\n") and "\r" not in sh and "set -euo pipefail" in sh,
      "the .sh starts with its shell line, LF only, stops on errors")
check(ps1.isascii() and sh.isascii(), "both are ASCII for ASCII values")
check("10-23-2026" in ps1 and "Create group" in sh, "they name the task and the date")

tmp = tempfile.mkdtemp(prefix="m365gui_script_")

# The same with a real PROGRAM in m365's place (m365 is node, a separate
# program): Windows PowerShell 5.1 is known to mangle double quotes inside
# an argument it hands to a program. A python script that prints its
# arguments stands in for m365.
echo = os.path.join(tmp, "argecho.py")
open(echo, "w").write("import sys, json\nprint(json.dumps(sys.argv[1:]))\n")
def run_ps(exe, argv):
    text = c.script_text(argv, "ps1", "Create group", "0.6", "10-23-2026")
    text = text.replace("& m365 ", "& %s %s " % (c.ps_quote(sys.executable), c.ps_quote(echo)))
    path = os.path.join(tmp, "native.ps1")
    open(path, "w", newline="", encoding="ascii").write(text)
    r = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
                       capture_output=True, text=True, timeout=120)
    try:
        return r.returncode, json.loads(r.stdout.strip().splitlines()[0]), r.stderr
    except Exception:
        return r.returncode, None, r.stdout + r.stderr

for exe in ("powershell", "pwsh"):
    if not shutil.which(exe):
        print("SKIP " + exe)
        continue
    rc, got, err = run_ps(exe, ARGV2)
    check(rc == 0 and got == ARGV2, "%s hands m365 every value unchanged: & ' ; $ ` | > %% (%s)"
          % (exe, str(got)[:120]))
    rc, got, err = run_ps(exe, ARGV)
    if exe == "powershell":
        check(rc != 0 and got is None and "PowerShell 7" in err,
              "Windows PowerShell 5.1 REFUSES a value with a double quote (it would change it)")
    else:
        check(rc == 0 and got == ARGV, "PowerShell 7 passes a double quote unchanged too (%s)" % str(got)[:120])

bash = shutil.which("bash")
if bash:
    path = os.path.join(tmp, "s.sh")
    open(path, "w", newline="", encoding="ascii").write(sh)
    r = subprocess.run([bash, "-c", 'm365() { for a in "$@"; do printf "%s\\n" "$a"; done; }; '
                        'source "$1"', "x", path.replace("\\", "/")],
                       capture_output=True, text=True, timeout=120)
    check(r.stdout.splitlines() == ARGV, "bash passes every value through unchanged (%s)" % r.stdout[:120])
else:
    print("SKIP bash")

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
