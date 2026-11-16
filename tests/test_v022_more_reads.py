# test_v022_more_reads.py - v0.22 (11-13-2026): 9 more READ-ONLY tasks, each run live
# before it was added (CLI 12.0.0). Checks: each task is in its section, is not
# marked destructive, builds the exact command (list / get only, --output text),
# optional boxes drop their option when blank, and a required box left empty is
# refused.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

ROLES, SP = "Roles and admin units", "SharePoint"
URL = "https://contoso.sharepoint.com/sites/Team"
TEXT = ["--output", "text"]
EXPECT = {
    "Admin role permissions (which are privileged)": (ROLES, {},
        ["entra", "rolepermission", "list", "--resourceNamespace", "microsoft.directory"] + TEXT),
    "Columns in a list": (SP, {"url": URL, "list": "Documents"},
        ["spo", "field", "list", "--webUrl", URL, "--listTitle", "Documents"] + TEXT),
    "Folders in a library": (SP, {"url": URL, "folder": "Shared Documents"},
        ["spo", "folder", "list", "--webUrl", URL, "--parentFolderUrl", "Shared Documents"] + TEXT),
    "Webhooks on a list": (SP, {"url": URL, "list": "Documents"},
        ["spo", "list", "webhook", "list", "--webUrl", URL, "--listTitle", "Documents"] + TEXT),
    "Event receivers on a site or list": (SP, {"url": URL},
        ["spo", "eventreceiver", "list", "--webUrl", URL] + TEXT),
    "A site's property bag": (SP, {"url": URL},
        ["spo", "propertybag", "list", "--webUrl", URL] + TEXT),
    "Custom actions on a site": (SP, {"url": URL, "scope": "All"},
        ["spo", "customaction", "list", "--webUrl", URL, "--scope", "All"] + TEXT),
    "Apps installed on a site": (SP, {"url": URL},
        ["spo", "app", "instance", "list", "--siteUrl", URL] + TEXT),
    "Site designs applied to a site": (SP, {"url": URL},
        ["spo", "sitedesign", "run", "list", "--webUrl", URL] + TEXT),
}
tasks = {}
for name, (section, values, want) in EXPECT.items():
    found = [t for t in c.TASKS.get(section, []) if t["name"] == name]
    check(len(found) == 1, "%s: once in %s" % (name, section))
    if not found:
        continue
    t = tasks[name] = found[0]
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
    check(all(ord(ch) < 128 for ch in name + t["desc"] + t["template"]
              + "".join(f["label"] for f in t["fields"])), "%s: ASCII only" % name)

# optional boxes add their option only when filled in (values checked live)
def argv_of(name, values, section):
    return c.build_command(tasks[name], values, section)[1] if name in tasks else None

a = argv_of("Admin role permissions (which are privileged)", {"priv": "true"}, ROLES)
check(a == EXPECT["Admin role permissions (which are privileged)"][2][:-2] + ["--privileged", "true"] + TEXT,
      "privileged only: %r" % (a,))
a = argv_of("Folders in a library", {"url": URL, "folder": "Shared Documents", "rec": "true"}, SP)
check(a == EXPECT["Folders in a library"][2][:-2] + ["--recursive", "true"] + TEXT, "recursive: %r" % (a,))
a = argv_of("Event receivers on a site or list", {"url": URL, "list": "Documents"}, SP)
check(a == ["spo", "eventreceiver", "list", "--webUrl", URL, "--listTitle", "Documents"] + TEXT,
      "event receivers of one list: %r" % (a,))

def field(name, key):
    t = tasks.get(name)
    f = [x for x in (t["fields"] if t else []) if x["key"] == key]
    return f[0] if f else {}

check(field("Admin role permissions (which are privileged)", "priv").get("choices") == ["", "true"],
      "privileged choices blank / true")
check(field("Folders in a library", "rec").get("choices") == ["", "true"], "recursive choices blank / true")
check(field("Folders in a library", "folder").get("default") == "Shared Documents",
      "folder defaults to Shared Documents")
sc = field("Custom actions on a site", "scope")
check(sc.get("choices") == ["All", "Site", "Web"] and sc.get("default") == "All",
      "custom action scope All / Site / Web, All by default (the CLI's values)")
check(not field("Event receivers on a site or list", "list").get("required", True),
      "event receivers: list name optional")

names = [t["name"] for ts in c.TASKS.values() for t in ts]
check(len(names) == len(set(names)), "task names unique (%d)" % len(names))
check(len(names) >= 235, "235 tasks or more (%d)" % len(names))
print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
