# test_v015_live_changes.py - v0.15 (11-02-2026): the FIRST live run of the
# tasks that CHANGE things, on throwaway objects only (a test user, a test
# Team, throwaway security groups). Worked as built: Rename user, Set job
# title / department / office, Set / Remove a user's manager, Check a
# password against the policy, Reset password, Create group (security),
# Rename a group, Add member to group, Make a member an owner, Delete group,
# Add member to a Team, Change someone's role in a Team, Remove someone from
# a Team. Found and fixed: 'Remove member from group' - without --role the
# CLI removes the person as owner AND member and failed ("Resource ... does
# not exist") for an owner who is not also a member; --suppressNotFound
# (CLI 11.11 and 12.0) fixed it - live: an owner-only and a member-only user
# were both removed. Microsoft refuses to remove a group's LAST owner.
# This file pins those commands - nothing runs.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def build(cat, name, values):
    t = [t for t in c.TASKS[cat] if t["name"] == name][0]
    _d, argv, err = c.build_command(t, values, cat)
    return t, (err or argv)

t, argv = build("Groups (Entra)", "Remove member from group (DESTRUCTIVE)",
                {"name": "Staff Group", "email": "jdoe@example.com"})
check(argv == ["entra", "group", "member", "remove", "--groupName", "Staff Group", "--userNames",
               "jdoe@example.com", "--suppressNotFound", "--force"],
      "remove from a group: --suppressNotFound, so an owner-only or member-only person is removed")
check(t["destructive"] and "LAST owner" in t["desc"] and t["desc"].isascii(),
      "it is DESTRUCTIVE and explains the last-owner rule")

LIVE_OK = [("Users (Entra ID)", "Rename user (display / first / last name)",
            {"email": "a@example.com", "display": "A B"}),
           ("Users (Entra ID)", "Set job title / department / office", {"email": "a@example.com", "title": "T"}),
           ("Users (Entra ID)", "Set a user's manager", {"email": "a@example.com", "manager": "b@example.com"}),
           ("Users (Entra ID)", "Remove a user's manager", {"email": "a@example.com"}),
           ("Groups (Entra)", "Create group", {"name": "G", "type": "security", "nick": "g"}),
           ("Groups (Entra)", "Rename a group / change its description", {"name": "G", "newname": "H"}),
           ("Groups (Entra)", "Add member to group", {"name": "G", "email": "a@example.com", "role": "Member"}),
           ("Groups (Entra)", "Make a member an owner (or back to member)",
            {"name": "G", "email": "a@example.com", "role": "Owner"}),
           ("Groups (Entra)", "Delete group (DESTRUCTIVE)", {"name": "G"}),
           ("Teams / M365 Groups", "Add member to a Team", {"team": "T", "email": "a@example.com", "role": "Member"}),
           ("Teams / M365 Groups", "Change someone's role in a Team",
            {"team": "T", "email": "a@example.com", "role": "Owner"}),
           ("Teams / M365 Groups", "Remove someone from a Team (DESTRUCTIVE)", {"team": "T", "email": "a@example.com"}),
           # also live 11-02-2026: a free license added and removed (the other kept)
           ("Users (Entra ID)", "Set usage location", {"email": "a@example.com", "loc": "US"}),
           ("Licenses", "Assign license(s)", {"email": "a@example.com", "ids": "sku-1"}),
           ("Licenses", "Remove license(s) (DESTRUCTIVE)", {"email": "a@example.com", "ids": "sku-1"})]
for cat, name, values in LIVE_OK:
    _t, argv = build(cat, name, values)
    check(isinstance(argv, list), "%s: still builds (live-tested 11-02-2026)" % name)
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
