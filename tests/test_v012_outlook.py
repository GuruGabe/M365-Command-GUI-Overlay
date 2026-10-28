# test_v012_outlook.py - v0.12 (10-27-2026): six new Outlook tasks (a user's
# calendars, calendar events, messages in a folder; automatic replies on /
# scheduled / off), checked against 'm365 outlook ... --help full' on CLI
# v11.11. Builds each command - nothing runs.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

tasks = {t["name"]: t for t in c.TASKS["Outlook"]}
def build(name, **values):
    return c.build_command(tasks[name], values, "Outlook")

_d, argv, err = build("A user's calendars", email="ann@contoso.com")
check(not err and argv == ["outlook", "calendar", "list", "--userName", "ann@contoso.com",
                           "--output", "text"], "calendars: %s" % argv)

_d, argv, err = build("A user's calendar events", email="ann@contoso.com", start="", end="")
check(not err and argv[:5] == ["outlook", "event", "list", "--userName", "ann@contoso.com"]
      and "--startDateTime" not in argv and "subject,start,end,organizer,isCancelled" in argv,
      "events, no dates: default calendar, readable columns (%s)" % argv)
_d, argv, err = build("A user's calendar events", email="ann@contoso.com",
                      start="2026-11-01", end="2026-11-30")
check(not err and argv[5:9] == ["--startDateTime", "2026-11-01", "--endDateTime", "2026-11-30"],
      "events with a date range")

_d, argv, err = build("Messages in a user's mail folder", email="ann@contoso.com", folder="sentitems")
check(not err and argv == ["outlook", "message", "list", "--userName", "ann@contoso.com",
                           "--folderName", "sentitems", "--output", "text"], "messages in a folder")

name = "Turn on automatic replies (until turned off)"
_d, argv, err = build(name, email="ann@contoso.com", internal="I am out until Monday.",
                      audience="all", external="")
check(not err and argv == ["outlook", "mailbox", "settings", "set", "--userName", "ann@contoso.com",
                           "--autoReplyStatus", "alwaysEnabled", "--autoReplyInternalMessage",
                           "I am out until Monday.", "--autoReplyExternalAudience", "all"],
      "auto-reply on: a message with spaces stays ONE argument, no external message")
_d, argv, err = build(name, email="ann@contoso.com", internal="Out", audience="contactsOnly",
                      external="Away - back Monday")
check(argv[-2:] == ["--autoReplyExternalMessage", "Away - back Monday"], "auto-reply on: external message")
_d, argv, err = build(name, email="ann@contoso.com", internal="", audience="none", external="")
check(bool(err), "auto-reply on: the internal message is required (%s)" % err)
check(tasks[name]["destructive"], "auto-reply on asks first")

name = "Turn on automatic replies for dates (scheduled)"
_d, argv, err = build(name, email="ann@contoso.com", start="2026-11-02T08:00:00",
                      end="2026-11-06T17:00:00", tz="Central Standard Time", internal="Out",
                      audience="none", external="")
check(not err and argv[argv.index("--autoReplyStatus") + 1] == "scheduled"
      and argv[argv.index("--autoReplyStartTimeZone") + 1] == "Central Standard Time"
      and argv[argv.index("--autoReplyEndTimeZone") + 1] == "Central Standard Time"
      and argv[argv.index("--autoReplyEndDateTime") + 1] == "2026-11-06T17:00:00",
      "scheduled: start, end and the same time zone for both")

_d, argv, err = build("Turn off automatic replies", email="ann@contoso.com")
check(not err and argv[-2:] == ["--autoReplyStatus", "disabled"]
      and tasks["Turn off automatic replies"]["destructive"], "auto-reply off (asks first)")

for t in ("A user's calendars", "A user's calendar events", "Messages in a user's mail folder",
          "Turn off automatic replies"):
    field = next(f for f in tasks[t]["fields"] if f["key"] == "email")
    check(c.picker_kind("Outlook", tasks[t], field) == "user", "Pick... a user: " + t)
check(c.saves_output(tasks["A user's calendar events"]), "events can be saved to CSV / JSON")
print("FAILURES:", len(fails))
