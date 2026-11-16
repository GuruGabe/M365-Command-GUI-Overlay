# test_updater_clm.py - 11-16-2026: the updater script (updategamgui.ps1 2.3 /
# updatem365gui.ps1 1.2) works in PowerShell's Constrained Language Mode - the mode
# a portable copy's updater runs in on PCs with AppLocker / WDAC script rules.
# Before, it stopped on its first line there ("Cannot set property ...") without
# writing a log, so 'Install updates automatically' and Help > Check for updates
# could never update a portable copy on such a PC.
#  1. The four .NET spots CLM blocks are only used when $FullLanguage is true.
#  2. Convert-ToVersion gives the same answers in Full and Constrained Language.
#     (When PowerShell is already constrained, setting the mode throws - ignored.)
#  3. The whole updater, forced into CLM, reaches GitHub, logs the language mode
#     and fails cleanly on a repository that does not exist.
import os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = [n for n in ("updategamgui.ps1", "updatem365gui.ps1") if os.path.exists(os.path.join(ROOT, n))]
fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

check(len(NAMES) == 1, "one updater script in the repo (%r)" % NAMES)
if not NAMES:
    print("FAILURES: %d" % len(fails))
    sys.exit(1)
SCRIPT = os.path.join(ROOT, NAMES[0])
APP = "GAMGUI" if "gamgui" in NAMES[0] else "M365GUI"
text = open(SCRIPT, encoding="utf-8-sig").read()
check(all(ord(ch) < 128 for ch in text), "ASCII only")

# ---- 1. blocked .NET calls only on the FullLanguage path ---------------------------------
check('$FullLanguage = ($ExecutionContext.SessionState.LanguageMode -eq "FullLanguage")' in text,
      "the script works out its language mode")


def guarded(snippet):
    # Every use of the snippet sits inside an 'if ($FullLanguage) {' block.
    lines = text.splitlines()
    hits = [i for i, l in enumerate(lines) if snippet in l and not l.strip().startswith("#")]
    ok = bool(hits)
    for i in hits:
        depth, inside = 0, False
        for j in range(i - 1, -1, -1):
            l = lines[j]
            depth += l.count("}") - l.count("{")
            if depth < 0:
                inside = "if ($FullLanguage) {" in l
                break
        ok = ok and inside
    return ok


for snippet in ("[Net.ServicePointManager]::SecurityProtocol =",
                "[Security.Principal.WindowsIdentity]::GetCurrent()",
                "New-Object System.Net.WebClient"):
    check(guarded(snippet), "only with Full Language: %s" % snippet)
check(not any("[version]::TryParse" in l for l in text.splitlines() if not l.strip().startswith("#")),
      "no [version]::TryParse (CLM blocks [ref])")
check("Invoke-WebRequest -Uri $Url -OutFile $Destination -UserAgent $UserAgent -UseBasicParsing" in text,
      "Constrained Language downloads with Invoke-WebRequest")
check('S-1-16-12288|S-1-16-16384' in text, "Constrained Language admin check reads the integrity level")
check("language mode: " in text, "the log names the language mode")

# ---- 2. Convert-ToVersion, both modes ------------------------------------------------------
m = re.search(r"(function Convert-ToVersion \{.*?\n\})", text, re.S)
check(bool(m), "Convert-ToVersion found")
if m and sys.platform == "win32":
    calls = "; ".join('(Convert-ToVersion "%s").ToString()' % t for t in ("3.05", "v2.10", " V1.2 ", "beta", ""))
    for force in ("", "try { $ExecutionContext.SessionState.LanguageMode = 'ConstrainedLanguage' } catch { }; "):
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                            force + m.group(1) + "\n" + calls], capture_output=True, text=True, timeout=120)
        got = r.stdout.split()
        check(got == ["3.5", "2.10", "1.2", "0.0", "0.0"],
              "Convert-ToVersion %s: %r %s" % ("forced CLM" if force else "as is", got, r.stderr.strip()[:150]))

# ---- 3. the whole updater in Constrained Language Mode -------------------------------------
if sys.platform == "win32":
    box = tempfile.mkdtemp(prefix="updater_clm_test_")
    try:
        cmd = ("try { $ExecutionContext.SessionState.LanguageMode = 'ConstrainedLanguage' } catch { }; "
               "& '%s' -InstallType zip -InstallRoot '%s' -Repo 'GuruGabe/no-such-repo-updater-clm-test' -Quiet; "
               "exit $LASTEXITCODE" % (SCRIPT.replace("'", "''"), box.replace("'", "''")))
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, timeout=300)
        p = os.path.join(box, "Logs", APP + "-Update.log")
        log = open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else ""
        out = (r.stdout or "") + (r.stderr or "")
        check("Cannot set property" not in out + log and "Only core types" not in out + log,
              "no Constrained Language error (%s)" % out.strip()[-160:])
        check("language mode: " in log, "the log names the language mode")
        if "language mode: FullLanguage" in log:
            print("NOTE: this PowerShell would not switch to Constrained Language; part 3 ran in Full Language")
        check("ERROR:" in log and r.returncode == 1, "a repository that does not exist fails cleanly (exit %s)"
              % r.returncode)
    finally:
        shutil.rmtree(box, ignore_errors=True)

print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
