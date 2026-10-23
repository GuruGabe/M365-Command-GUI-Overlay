# m365docs.py - shared by the tests (not a test itself): reads the CLI for
# Microsoft 365's own documentation, which npm installs with it
# (node_modules/@pnp/cli-microsoft365/docs/docs/cmd/**.mdx), so tests can
# check a command and its options exist in the installed CLI.
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

GLOBAL = {"--output", "--query", "--verbose", "--debug", "--help"}

def docs_root():
    import M365GUI as m
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

def command_words(argv_or_template):
    # The command's words: everything before the first option or value.
    words = []
    tokens = argv_or_template.split() if isinstance(argv_or_template, str) else argv_or_template
    for tok in tokens:
        if tok.startswith("-") or tok.startswith("[") or "{" in tok:
            break
        words.append(tok)
    return words

def doc_page(root, words):
    # e.g. entra user list -> entra/user/user-list.mdx; onedrive list ->
    # onedrive/onedrive-list.mdx (a group's own commands carry its name).
    if len(words) == 1:
        return os.path.join(root, words[0] + ".mdx")
    for path in (os.path.join(root, words[0], words[1], "-".join(words[1:]) + ".mdx"),
                 os.path.join(root, words[0], "-".join(words[1:]) + ".mdx"),
                 os.path.join(root, words[0], "-".join(words) + ".mdx")):
        if os.path.exists(path):
            return path
    return None

def doc_options(text):
    # {--option: (required, description)} from a page's Options list:
    #   `-u, --webUrl <webUrl>` required    `--force` / `--type [type]` optional
    section = text.split("## Options", 1)[-1].split("\n## ", 1)[0]
    out = {}
    for m_ in re.finditer(r"`(?:-\w, )?(--[A-Za-z0-9]+)( <[^>]+>| \[[^\]]+\])?`\s*\n:([^\n]*)", section):
        out[m_.group(1)] = ((m_.group(2) or "").strip().startswith("<"), m_.group(3))
    return out

def argv_problems(root, argv):
    # What is wrong with one argv against the docs: [] when fine.
    words = command_words(argv)
    page = doc_page(root, words)
    if not page:
        return ["'m365 %s' has no doc page" % " ".join(words)]
    options = doc_options(open(page, encoding="utf-8").read())
    used = {a for a in argv if a.startswith("--")}
    problems = ["undocumented " + o for o in sorted(used - set(options) - GLOBAL)]
    problems += ["missing required " + o for o, (req, _d) in sorted(options.items())
                 if req and o not in used]
    return problems
