# test_v021_more_reads.py - v0.21 (11-13-2026): 8 more READ-ONLY tasks, each run live
# before it was added (CLI 12.0.0). Checks: each task is in its section, is not
# marked destructive, builds the exact command (list / get only, --output text),
# and a required box left empty is refused.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

SVC, SP, OL = "Service health and security", "SharePoint", "Outlook"
URL = "https://contoso.sharepoint.com/sites/Team"
LISTPROPS = "Title,ItemCount,Created,LastItemModifiedDate,EnableVersioning,MajorVersionLimit,Hidden,BaseTemplate"
EXPECT = {
    "Retention events": (SVC, {},
        ["purview", "retentionevent", "list", "--output", "text"]),
    "A user's calendar groups": (OL, {"email": "a@contoso.com"},
        ["outlook", "calendargroup", "list", "--userName", "a@contoso.com", "--output", "text"]),
    "Subsites of a site": (SP, {"url": URL},
        ["spo", "web", "list", "--url", URL, "--output", "text"]),
    "Features turned on for a site": (SP, {"url": URL, "scope": "Web"},
        ["spo", "feature", "list", "--webUrl", URL, "--scope", "Web", "--output", "text"]),
    "A list's details (items, versions)": (SP, {"url": URL, "list": "Documents"},
        ["spo", "list", "get", "--webUrl", URL, "--title", "Documents", "--properties", LISTPROPS,
         "--output", "text"]),
    "Views of a list": (SP, {"url": URL, "list": "Documents"},
        ["spo", "list", "view", "list", "--webUrl", URL, "--listTitle", "Documents", "--output", "text"]),
    "Content types in a list": (SP, {"url": URL, "list": "Documents"},
        ["spo", "list", "contenttype", "list", "--webUrl", URL, "--listTitle", "Documents",
         "--output", "text"]),
    "Languages a site can use": (SP, {"url": URL},
        ["spo", "web", "installedlanguage", "list", "--webUrl", URL, "--output", "text"]),
}
for name, (section, values, want) in EXPECT.items():
    found = [t for t in c.TASKS.get(section, []) if t["name"] == name]
    check(len(found) == 1, "%s: once in %s" % (name, section))
    if not found:
        continue
    t = found[0]
    check(not t.get("destructive"), "%s: not destructive" % name)
    _shown, argv, err = c.build_command(t, values, section)
    check(not err and argv == want, "%s: %r" % (name, argv))
    words = []
    for a in argv:
        if a.startswith("-"):
            break
        words.append(a)
    check(bool(words) and words[-1] in ("list", "get"), "%s: list / get only" % name)
    for f in t["fields"]:
        if f["required"] and not f.get("default"):
            _s, _a, err = c.build_command(t, dict(values, **{f["key"]: ""}), section)
            check(bool(err), "%s: '%s' required" % (name, f["key"]))
    check(all(ord(ch) < 128 for ch in name + t["desc"] + t["template"]), "%s: ASCII only" % name)

# the scope box offers only the two values the CLI takes
feat = [t for t in c.TASKS.get(SP, []) if t["name"] == "Features turned on for a site"]
if feat:
    sc = [f for f in feat[0]["fields"] if f["key"] == "scope"]
    check(bool(sc) and sc[0].get("choices") == ["Site", "Web"], "feature scope choices Site / Web")

names = [t["name"] for ts in c.TASKS.values() for t in ts]
check(len(names) == len(set(names)), "task names unique (%d)" % len(names))
check(len(names) >= 226, "226 tasks or more (%d)" % len(names))
print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
