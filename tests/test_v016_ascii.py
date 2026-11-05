# test_v016_ascii.py - 11-02-2026 (v0.16): every text file M365GUI ships or builds
# from is plain ASCII (the project's rule). Look-alike characters that tests
# need (curly quotes, zero-width spaces) are written as \uXXXX escapes - an
# invisible zero-width space in source is easy to break by accident.
# build_res\ holds the bundled Tcl/Tk library files (not ours) and is skipped.
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKIP_DIRS = {"build_res", "Logs", "Records", "__pycache__", "build", "dist", ".git"}
TEXT = (".py", ".md", ".txt", ".bat", ".sh", ".ps1", ".spec", ".toml", ".html", ".css", ".js",
        ".json", ".cfg", ".iss", ".nsi", ".plist", ".desktop", ".yml", ".yaml")

fails = []
checked = 0
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for name in files:
        if not name.lower().endswith(TEXT):
            continue
        path = os.path.join(root, name)
        checked += 1
        data = open(path, "rb").read()
        if not data.isascii():
            lines = [i + 1 for i, line in enumerate(data.split(b"\n")) if not line.isascii()]
            fails.append("%s lines %s" % (os.path.relpath(path, ROOT), lines[:10]))
for f in fails:
    print("FAIL non-ASCII:", f)
print("PASS" if not fails else "FAIL", "%d text files checked" % checked)
if checked < 40:
    fails.append("too few files found (%d) - wrong folder?" % checked)
    print("FAIL too few files")
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
