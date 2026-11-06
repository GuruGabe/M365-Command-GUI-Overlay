# test_v017_cli12.py - v0.17 (11-06-2026): the CLI for Microsoft 365 12.0.0
# (npm 'latest' since 11-04-2026). Checked against its package: every
# command and option M365GUI uses still exists (231 uses, 0 problems), and
# the texts M365GUI reads are unchanged in 12.0's dist ("Logged out" in
# status.js, "Log in to Microsoft 365 first" in Command.js, "appId is
# required" in login.js). What changed for M365GUI users (v12 upgrade
# guidance AUTH-1, TEAMS-1; flow ids still z.uuid() - #7678):
#  - everyone signs in again after updating; until then 'm365 status' waits
#    for a sign-in and M365GUI's check runs out of time -> say so plainly;
#  - a team given by name needs Team.ReadBasic.All -> README;
#  - the flow notes name both CLI versions.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import m365_setup as s
import M365GUI as m

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

# ---- "Signed in as" when 'm365 status' gave no answer in time ---------------------------
timeout = ("Command '['C:\\\\Program Files\\\\nodejs\\\\node.exe', 'C:\\\\npm\\\\index.js', 'status', "
           "'--output', 'json']' timed out after 60 seconds")
line = m.account_text("m365.cmd", lambda argv: (1, timeout))
check(line.startswith("Signed in as: (no answer") and "sign in" in line and "Set up the CLI" in line,
      "no answer in time -> may be waiting for a new sign-in (got %r)" % line)
check("Program Files" not in line, "the command line itself is not shown")
check(not s.signed_in(line), "it is not a signed-in account")
check(not s.needs_window(line), "the window does NOT open by itself (could be the network)")
check(m.account_text("m365.cmd", lambda a: (0, '{"connectedAs": "admin@contoso.com"}'))
      == "Signed in as: admin@contoso.com", "signed in: unchanged")
check(m.account_text("m365.cmd", lambda a: (0, "Logged out")) == "Signed in as: nobody - run 'm365 login'",
      "logged out (CLI 12's own text, status.js): unchanged")

# ---- the task texts ------------------------------------------------------------------------
import m365_catalog as c
# TASKS: {section: [task dicts from T(name, desc, template, fields, ...)]}
# (or a flat list of them) - read both shapes.
groups = c.TASKS.values() if isinstance(c.TASKS, dict) else [c.TASKS]
descs = {t["name"]: t["desc"] for group in groups for t in group}
for name in ("Owners of a flow", "Run history of a flow"):
    check("v11.11 and v12.0" in descs.get(name, "") and "Invalid UUID" in descs.get(name, ""),
          "%s: the Invalid UUID note names CLI 11.11 and 12.0" % name)
guest = descs.get("External (guest) users files were shared with", "")
check("fixed in CLI 12.0" in guest and "update the CLI" in guest, "guest list: fixed in 12.0 - update the CLI")

# ---- the READMEs ------------------------------------------------------------------------
for doc in ("README.md", "README.txt"):
    text = open(os.path.join(ROOT, doc), encoding="ascii").read()
    check("Team.ReadBasic.All" in text and "nvm install <version>" in text
          and "12.0" in text and "credential store" in text,
          "%s: troubleshooting for nvm, CLI 12 sign-in and teams by name" % doc)

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
