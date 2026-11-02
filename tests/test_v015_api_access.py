# test_v015_api_access.py - v0.15 (10-30-2026): two read-only SharePoint
# tasks for SharePoint admin center > Advanced > API access, run live
# (read-only): the approved API permissions (spo serviceprincipal grant list,
# with a --query that keeps the permissions first - its own columns are ids)
# and the requests waiting for approval (spo serviceprincipal permissionrequest
# list). Builds each command - nothing runs.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

tasks = {t["name"]: t for t in c.TASKS["SharePoint"]}
WANT = {"API permissions approved for SharePoint":
            ["spo", "serviceprincipal", "grant", "list",
             "--query", "[].{Scope:scope,ResourceId:resourceId,Id:id}", "--output", "text"],
        "API permission requests waiting for approval":
            ["spo", "serviceprincipal", "permissionrequest", "list", "--output", "text"]}
for name, want in WANT.items():
    task = tasks.get(name)
    check(task is not None, "%s is in SharePoint" % name)
    if not task:
        continue
    check(not task["destructive"] and task["fields"] == [] and not task["workflow"],
          "%s: read-only, no boxes" % name)
    _d, argv, err = c.build_command(task, {}, "SharePoint")
    check(not err and argv == want, "%s: %s" % (name, argv))
    check(task["desc"].isascii() and c.saves_output(task), "%s: ASCII, can be saved" % name)
check(not any("serviceprincipal grant revoke" in t["template"] or "permissionrequest approve" in t["template"]
              or "permissionrequest deny" in t["template"] for ts in c.TASKS.values() for t in ts),
      "no approve / deny / revoke task (read-only for now)")
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
