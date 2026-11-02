# test_v015_office_activations.py - v0.15 (10-30-2026): three read-only
# Reports (usage) tasks for Microsoft 365 Apps (Office) activations. These
# reports take NO --period (CLI v11.11 --help) and were run live (read-only):
# per person (one row per person and product), assigned vs activated, and by
# device type. Builds each command - nothing runs.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

WANT = {"Office activations - per person": "office365activationsuserdetail",
        "Office activations - assigned vs activated (counts)": "office365activationsusercounts",
        "Office activations by device type (counts)": "office365activationcounts"}
tasks = {t["name"]: t for t in c.TASKS["Reports (usage)"]}
for name, report in WANT.items():
    task = tasks.get(name)
    check(task is not None, "%s is in Reports (usage)" % name)
    if not task:
        continue
    check(not task["destructive"] and task["fields"] == [], "%s: read-only, no boxes" % name)
    _d, argv, err = c.build_command(task, {}, "Reports (usage)")
    check(not err and argv == ["tenant", "report", report, "--output", "csv"],
          "%s: %s (no --period - these reports do not take one)" % (name, " ".join(argv)))
    check("--period" not in task["template"] and task["desc"].isascii(), "%s: no period, ASCII" % name)
    check(c.saves_output(task), "%s: can be saved to CSV like the other reports" % name)
print("FAILURES:", len(fails))
