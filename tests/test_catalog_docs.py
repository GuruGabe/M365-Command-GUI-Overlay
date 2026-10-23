# test_catalog_docs.py - v0.7 (10-23-2026): every task's m365 command is
# checked against the CLI's OWN documentation, which npm installs with it
# (see m365docs.py). The M365GUI counterpart of GAMGUI's parse check
# against gam.exe:
#   - the command has a doc page (it exists in this CLI version),
#   - every --option the template uses is documented for that command,
#   - every REQUIRED option (shown as --name <value> in the docs) is given,
#   - a dropdown's values are values the docs allow (when they list them).
# Skipped (not failed) on a PC without the CLI installed.
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import m365_catalog as c
import m365docs as d

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

root = d.docs_root()
if not root:
    print("SKIP the CLI for Microsoft 365 (and its docs) is not installed here")
    print("FAILURES: 0")
    sys.exit(0)
print("docs:", root)

checked = 0
for category, tasks in c.TASKS.items():
    for task in tasks:
        template = task["template"]
        if not template:
            continue                        # guided workflows: their own tests
        words = d.command_words(template)
        page = d.doc_page(root, words)
        name = "%s > %s" % (category, task["name"])
        if not page:
            check(False, name + ": 'm365 " + " ".join(words) + "' has no doc page in this CLI")
            continue
        options = d.doc_options(open(page, encoding="utf-8").read())
        used = set(re.findall(r"(--[A-Za-z0-9]+)", template))
        unknown = sorted(used - set(options) - d.GLOBAL)
        required = sorted(o for o, (req, _desc) in options.items() if req)
        missing = [o for o in required if o not in used]
        # Some commands take ONE of several ways to name a thing (e.g. --id
        # or --userName): the docs mark each optional and say "Specify either"
        # - those are not 'required' in the docs, so this stays exact.
        check(not unknown, name + ": every option is documented " + (str(unknown) if unknown else ""))
        check(not missing, name + ": every required option is given " + (str(missing) if missing else ""))
        for field in task["fields"]:
            if not field.get("choices"):
                continue
            flag = re.search(r"(--[A-Za-z0-9]+) \{" + re.escape(field["key"]) + r"\}", template)
            if not flag or flag.group(1) not in options:
                continue
            desc = options[flag.group(1)][1]
            # Some pages write the list as ONE code span (`TeamSite,CommunicationSite`,
            # `asc|desc`) - split those.
            listed = [v.strip() for span in re.findall(r"`([^`]+)`", desc)
                      for v in re.split(r"[,|]", span)]
            if listed:
                bad = [v for v in field["choices"] if v and v not in listed]   # "" = leave out
                check(not bad, name + ": dropdown values are allowed by the docs " + (str(bad) if bad else ""))
        checked += 1
check(checked == sum(1 for ts in c.TASKS.values() for t in ts if t["template"]),
      "every command task was checked (%d)" % checked)

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
