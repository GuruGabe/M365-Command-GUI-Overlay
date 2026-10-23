# test_catalog_docs.py - v0.7 (10-23-2026): every task's m365 command is
# checked against the CLI's OWN documentation, which npm installs with it
# (node_modules/@pnp/cli-microsoft365/docs/docs/cmd/...mdx). The M365GUI
# counterpart of GAMGUI's parse check against gam.exe:
#   - the command has a doc page (it exists in this CLI version),
#   - every --option the template uses is documented for that command,
#   - every REQUIRED option (shown as --name <value> in the docs) is given,
#   - a dropdown's values are values the docs allow (when they list them).
# Skipped (not failed) on a PC without the CLI installed.
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as c
import M365GUI as m

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

GLOBAL = {"--output", "--query", "--verbose", "--debug", "--help"}

def docs_root():
    exe = m.find_m365("")
    candidates = []
    if exe:
        real = os.path.realpath(exe)
        candidates += [os.path.join(os.path.dirname(exe), "node_modules", "@pnp", "cli-microsoft365"),
                       os.path.dirname(os.path.dirname(real))]
    candidates.append(os.path.join(os.environ.get("APPDATA") or "", "npm", "node_modules", "@pnp",
                                   "cli-microsoft365"))
    for base in candidates:
        path = os.path.join(base, "docs", "docs", "cmd")
        if os.path.isdir(path):
            return path
    return None

def command_words(template):
    words = []
    for tok in template.split():
        if tok.startswith("-") or tok.startswith("[") or "{" in tok:
            break
        words.append(tok)
    return words

def doc_page(root, words):
    if len(words) == 1:
        return os.path.join(root, words[0] + ".mdx")
    # e.g. entra user list -> entra/user/user-list.mdx; onedrive list ->
    # onedrive/onedrive-list.mdx (a group's own commands carry its name).
    for path in (os.path.join(root, words[0], words[1], "-".join(words[1:]) + ".mdx"),
                 os.path.join(root, words[0], "-".join(words[1:]) + ".mdx"),
                 os.path.join(root, words[0], "-".join(words) + ".mdx")):
        if os.path.exists(path):
            return path
    return None

def doc_options(text):
    # {--option: (required, text of its description)} from the Options list:
    #   `-u, --webUrl <webUrl>`     required     `--force`   optional switch
    #   `--type [type]`             optional
    section = text.split("## Options", 1)[-1].split("\n## ", 1)[0]
    out = {}
    for m_ in re.finditer(r"`(?:-\w, )?(--[A-Za-z0-9]+)( <[^>]+>| \[[^\]]+\])?`\s*\n:([^\n]*)", section):
        out[m_.group(1)] = ((m_.group(2) or "").strip().startswith("<"), m_.group(3))
    return out

root = docs_root()
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
        words = command_words(template)
        page = doc_page(root, words)
        name = "%s > %s" % (category, task["name"])
        if not page:
            check(False, name + ": 'm365 " + " ".join(words) + "' has no doc page in this CLI")
            continue
        options = doc_options(open(page, encoding="utf-8").read())
        used = set(re.findall(r"(--[A-Za-z0-9]+)", template))
        unknown = sorted(used - set(options) - GLOBAL)
        required = sorted(o for o, (req, _d) in options.items() if req)
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
