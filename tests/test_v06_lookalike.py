# test_v06_lookalike.py - v0.6 (10-23-2026): pasted look-alike characters,
# as in GAMGUI 2.93 (GAM issue #1623). An address pasted from Word, Outlook,
# a web page or a chat often carries curly quotes or an invisible zero-width
# space; Microsoft 365 then answers "does not exist". Address / ID boxes are
# cleaned before the command is built; passwords and names are not. The
# characters are made with chr() so this file stays ASCII.
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import M365GUI as m
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

LQ, RQ, ZW, NB = chr(0x201c), chr(0x201d), chr(0x200b), chr(0xa0)

def task(cat, name):
    return next(t for t in c.TASKS[cat] if t["name"] == name)

check(c.clean_identifier(LQ + "j" + ZW + "smith@contoso.com" + RQ) == "jsmith@contoso.com",
      "curly quotes around it and a zero-width space inside are removed")
check(c.clean_identifier("a@x.com, " + NB + "'b@x.com'") == "a@x.com, b@x.com",
      "each comma-separated item is cleaned; a pasted non-breaking space too")
check(c.clean_identifier("o'brien@x.com") == "o'brien@x.com", "an apostrophe INSIDE an address stays")

reset = task("Users (Entra ID)", "Reset password")
_d, argv, err = c.build_command(reset, {"email": LQ + "jsmith@contoso.com" + RQ,
                                        "password": LQ + "Pa ss" + RQ}, "Users (Entra ID)")
check(not err and argv[argv.index("--userName") + 1] == "jsmith@contoso.com",
      "Reset password: the UPN box is cleaned")
check(argv[argv.index("--newPassword") + 1] == LQ + "Pa ss" + RQ, "...but the password keeps every character")

create = task("Users (Entra ID)", "Create user")
_d, argv, err = c.build_command(create, {"display": LQ + "Jo" + RQ, "email": "jo@x.com" + ZW,
                                         "password": "p", "loc": "US"}, "Users (Entra ID)")
check(argv[argv.index("--displayName") + 1] == LQ + "Jo" + RQ and argv[argv.index("--userName") + 1] == "jo@x.com",
      "Create user: the display name keeps its quotes, the address is cleaned")

add = task("Groups (Entra)", "Add member to group")
_d, argv, err = c.build_command(add, {"name": LQ + "Sales" + RQ, "email": "a@x.com", "role": "Member"},
                                "Groups (Entra)")
check(argv[argv.index("--groupName") + 1] == "Sales", "a group picked by name (Pick... box) is cleaned")
newgroup = task("Groups (Entra)", "Create group")
_d, argv, err = c.build_command(newgroup, {"name": LQ + "Sales" + RQ, "type": "security", "nick": "",
                                           "desc": ""}, "Groups (Entra)")
check(argv[argv.index("--displayName") + 1] == LQ + "Sales" + RQ, "a NEW group's name is left as typed")

# The OneDrive copy cleans its From / To boxes too.
seen = []
def fake(argv):
    seen.append(list(argv))
    return 1, '{"error":"stop here"}'
m.transfer_onedrive(fake, lambda t: None, lambda q: False, lambda: False,
                    {"from": LQ + "a@x.com" + RQ, "to": "b@x.com" + ZW, "folder": "",
                     "access": m.TRANSFER_ACCESS_REMOVE}, os.devnull)
check(seen and seen[0][:1] == ["status"], "OneDrive copy: pasted quotes do not make it refuse the From box")

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
