# test_v023_more_reads.py - v0.23 (11-16-2026): 12 more READ-ONLY tasks, each run live
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

PP, SP = "Power Platform", "SharePoint"
SVC, OD = "Service health and security", "OneDrive"
URL = "https://contoso.sharepoint.com/sites/Team"
ENV = "Default-00000000-0000-0000-0000-000000000000"
TEXT = ["--output", "text"]
EXPECT = {
    "Solution publishers in an environment": (PP, {"env": ENV},
        ["pp", "solution", "publisher", "list", "--environmentName", ENV] + TEXT),
    "AI Builder models in an environment": (PP, {"env": ENV},
        ["pp", "aibuildermodel", "list", "--environmentName", ENV] + TEXT),
    "Site design tasks waiting to run": (SP, {"url": URL},
        ["spo", "sitedesign", "task", "list", "--webUrl", URL] + TEXT),
    "SharePoint Embedded container types": (SP, {},
        ["spe", "containertype", "list"] + TEXT),
    "Knowledge hub site": (SP, {},
        ["spo", "knowledgehub", "get"] + TEXT),
    "Columns of a content type in a list": (SP, {"url": URL, "list": "Documents", "ctype": "Document"},
        ["spo", "contenttype", "field", "list", "--webUrl", URL, "--listTitle", "Documents",
         "--contentTypeName", "Document"] + TEXT),
    "Default column values in a library": (SP, {"url": URL, "list": "Documents"},
        ["spo", "list", "defaultvalue", "list", "--webUrl", URL, "--listTitle", "Documents"] + TEXT),
    "Retention label of a list": (SP, {"url": URL, "list": "Documents"},
        ["spo", "list", "retentionlabel", "get", "--webUrl", URL, "--listTitle", "Documents"] + TEXT),
    # round 2 (11-16-2026)
    "Microsoft Search connectors": (SVC, {},
        ["external", "connection", "list"] + TEXT),
    "Custom attributes apps add to accounts (directory extensions)": (SVC, {},
        ["graph", "directoryextension", "list"] + TEXT),
    "A user's OneNote notebooks": (OD, {"email": "a@contoso.com"},
        ["onenote", "notebook", "list", "--userName", "a@contoso.com"] + TEXT),
    "SharePoint Premium content centers": (SP, {},
        ["spp", "contentcenter", "list"] + TEXT),
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
    check(all(ord(ch) < 128 for ch in name + t["desc"] + t["template"]
              + "".join(f["label"] for f in t["fields"])), "%s: ASCII only" % name)

ct = [t for t in c.TASKS.get(SP, []) if t["name"] == "Columns of a content type in a list"]
if ct:
    f = [x for x in ct[0]["fields"] if x["key"] == "ctype"]
    check(bool(f) and f[0]["default"] == "Document", "content type defaults to Document")

dx = [t for t in c.TASKS.get(SVC, []) if t["name"].startswith("Custom attributes apps add")]
if dx:
    _s, a, err = c.build_command(dx[0], {"app": "Contoso Sync"}, SVC)
    check(not err and a == ["graph", "directoryextension", "list", "--appName", "Contoso Sync"] + TEXT,
          "directory extensions of one app: %r" % (a,))

names = [t["name"] for ts in c.TASKS.values() for t in ts]
check(len(names) == len(set(names)), "task names unique (%d)" % len(names))
check(len(names) >= 247, "247 tasks or more (%d)" % len(names))
print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
