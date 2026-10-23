# test_invocation.py - v0.4 (10-22-2026): how M365GUI starts m365. npm's
# m365.cmd wrapper went through cmd.exe, which treats & | < > ^ as commands
# even inside a value: an argument 'a&echo.x' RAN 'echo.x' (checked live
# 10-22-2026 with m365 v11.11.0). A folder or file name, display name or
# group name can contain '&', so M365GUI now starts node with the CLI's own
# script directly - no shell - whenever it can find them.
import os, sys, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import M365GUI as m

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

# A fake npm folder: m365.cmd + m365.ps1 + node_modules\...\index.js, and a
# 'node.exe' next to them (npm puts one there on some installs).
npm = tempfile.mkdtemp(prefix="m365gui_npm_")
script = os.path.join(npm, "node_modules", "@pnp", "cli-microsoft365", "dist", "index.js")
os.makedirs(os.path.dirname(script))
open(script, "w").write("")
for name in ("m365.cmd", "m365.ps1", "m365"):
    open(os.path.join(npm, name), "w").write("")
node_here = os.path.join(npm, "node.exe")
open(node_here, "w").write("")

argv = ["spo", "folder", "copy", "--sourceUrl", "/personal/x/Documents/Q&A (2026)"]
for wrapper in ("m365.cmd", "m365.ps1", "m365"):
    inv = m.build_invocation(os.path.join(npm, wrapper), argv)
    check(inv == [node_here, script] + argv, "%s -> node + the CLI script, no shell (%s)" % (wrapper, inv[:2]))
os.remove(node_here)
# A stand-in node on the PATH (the test must not depend on this PC having
# Node.js installed - it was uninstalled from the dev PC on 10-23-2026).
fake_bin = tempfile.mkdtemp(prefix="m365gui_node_")
open(os.path.join(fake_bin, "node.exe" if os.name == "nt" else "node"), "w").write("")
if os.name != "nt":
    os.chmod(os.path.join(fake_bin, "node"), 0o755)
saved_path = os.environ["PATH"]
os.environ["PATH"] = fake_bin + os.pathsep + saved_path
inv = m.build_invocation(os.path.join(npm, "m365.cmd"), argv)
os.environ["PATH"] = saved_path
check(inv[1:] == [script] + argv and os.path.dirname(inv[0]) == fake_bin,
      "no node.exe next to the wrapper -> node from PATH (%s)" % inv[0])

# v0.5: macOS / Linux npm makes 'm365' a LINK to dist/index.js - followed,
# and node started directly (a Mac app from Finder has no Terminal PATH,
# so '#!/usr/bin/env node' would fail). realpath() of the link is index.js;
# passing index.js itself exercises the same branch on any OS.
os.environ["PATH"] = fake_bin + os.pathsep + saved_path
inv = m.build_invocation(script, ["status"])
os.environ["PATH"] = saved_path
check(inv[1:] == [script, "status"], "a link to the CLI's index.js -> node + index.js (%s)" % inv[:2])

# No CLI script found (an unusual install): the old cmd.exe way is used, but
# a value cmd.exe would treat as a command is REFUSED rather than run.
bare = tempfile.mkdtemp(prefix="m365gui_bare_")
cmdfile = os.path.join(bare, "m365.cmd")
open(cmdfile, "w").write("@echo off\r\n")
try:
    m.build_invocation(cmdfile, argv)
    check(False, "cmd.exe fallback refuses a value with '&'")
except ValueError as e:
    check("&" in str(e), "cmd.exe fallback refuses a value with '&' (%s)" % e)
inv = m.build_invocation(cmdfile, ["status"])
check(inv[-2:] == [cmdfile, "status"], "cmd.exe fallback still works for plain values")

# The real proof: through the REAL m365 install (if present), '&' is now
# just text. 'version --query <x>' prints the version and runs nothing else.
real = m.find_m365("")
if real and os.name == "nt" and not m.find_node(os.path.dirname(real)):
    print("SKIP real m365 check (m365 is installed but Node.js is not)")
elif real and os.name == "nt":
    r = subprocess.run(m.build_invocation(real, ["version", "--output", "json", "--query", "a&echo.zzinjected"]),
                       capture_output=True, text=True, timeout=120)
    check("zzinjected" not in r.stdout + r.stderr, "real m365: '&' in a value no longer runs a command")
else:
    print("SKIP real m365 check (not installed)")

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
