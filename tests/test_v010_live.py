# test_v010_live.py - v0.10 (10-26-2026): what the first live run against
# the tenant found (44 read-only tasks, 33 OK) that the docs check could not:
#   - every usage report failed: "output: Invalid option: expected one of
#     json|csv" - report commands take ONLY --output csv or json (the docs
#     list --output as a global option, without that limit);
#   - 'entra m365group list/get --withSiteUrl' answers "Access denied" for a
#     PRIVATE group the signed-in admin is not a member of (it reads the
#     group's files), so the whole list failed; without it the list works;
#   - sensitivity labels: "The resource could not be found" when the tenant
#     has none / is not licensed for them - the description says so.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

reports = [(cat, t) for cat, ts in c.TASKS.items() for t in ts if " report " in " " + t["template"] + " "]
# 9 in v0.10; 11 since 10-28-2026 (v0.12: mailbox quota counts, OneDrive
# storage for the whole organization).
check(len(reports) == 11, "the 11 usage reports are found (%d)" % len(reports))
for cat, t in reports:
    check("--output csv" in t["template"] and "--output text" not in t["template"],
          "%s: runs with --output csv (report commands refuse text)" % t["name"])
    check(c.saves_output(t), "%s: can still be saved to a CSV / JSON file" % t["name"])
check(not any("--output text" in t["template"] and (" report " in " " + t["template"] + " ")
              for ts in c.TASKS.values() for t in ts), "no report command anywhere uses --output text")
check(not any("activeusercounts" in t["template"] for ts in c.TASKS.values() for t in ts)
      and any("servicesusercounts" in t["template"] for _cat, t in reports),
      "the active-users counts use servicesusercounts (activeusercounts: connection reset every time)")
check(not any("--withSiteUrl" in t["template"] for ts in c.TASKS.values() for t in ts),
      "no task asks for --withSiteUrl (Access denied on private groups the admin is not in)")
names = [t["name"] for t in c.TASKS["Teams / M365 Groups"]]
check("List Microsoft 365 groups" in names, "the group list task is there (without site addresses)")
labels = next(t for t in c.TASKS["Service health and security"] if t["name"] == "Sensitivity labels")
check("could not be found" in labels["desc"], "Sensitivity labels explains 'could not be found'")
check(c.saves_output({"template": "x --output csv", "workflow": ""}) and
      not c.saves_output({"template": "x --output json", "workflow": ""}),
      "saves_output: text or csv commands can be saved")

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
