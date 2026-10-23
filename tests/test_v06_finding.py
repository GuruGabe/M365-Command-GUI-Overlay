# test_v06_finding.py - v0.6 (10-23-2026): finding tasks like in GAMGUI -
# the Search box, Favorites and Recent (m365gui_tasklists.json), and the
# "Signed in as" line. The window is built HIDDEN (withdrawn before Tk ever
# draws it) and every file it writes goes to a temporary folder.
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import M365GUI as m
import m365_catalog as c

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

# ---- 1. the plain rules ------------------------------------------------------------
copy = next(t for t in c.TASKS["OneDrive"] if t["name"].startswith("Copy"))
check(c.task_matches("OneDrive", copy, "copy onedrive") and c.task_matches("OneDrive", copy, "LEAVING"),
      "search: every word must appear (any case, description counts)")
check(not c.task_matches("OneDrive", copy, "onedrive guest"), "search: a word that is not there hides the task")
check(c.task_matches("OneDrive", copy, "   "), "search: blank shows everything")
key = c.task_key("OneDrive", copy["name"])
check(c.find_task(key) == ("OneDrive", c.TASKS["OneDrive"].index(copy)), "a Favorites key finds its task again")
check(c.find_task("OneDrive|A task that was renamed") is None and c.find_task("") is None,
      "a key for a task that no longer exists is dropped, not an error")

# ---- 2. "Signed in as" ---------------------------------------------------------------
check(m.account_text("", None) == "Signed in as: (m365 not found)", "no m365")
check(m.account_text("m365", lambda a: (0, '{"connectedAs": "admin@contoso.com"}')) ==
      "Signed in as: admin@contoso.com", "signed in")
check("m365 login" in m.account_text("m365", lambda a: (0, "Logged out")), "logged out -> says to run m365 login")
check("Node.js" in m.account_text("m365", lambda a: (1, "'node' is not recognized as an internal or "
                                                     "external command")),
      "Node.js missing -> says so (seen 10-23-2026)")
def boom(_argv):
    raise OSError("no such file")
check("could not check" in m.account_text("m365", boom), "a crash in the check is reported, not raised")

# ---- 3. the window, hidden, with its files in a temporary folder -----------------------
tmp = tempfile.mkdtemp(prefix="m365gui_find_")
m.INI_PATH = os.path.join(tmp, "m365gui.ini")
m.LOG_DIR = os.path.join(tmp, "Logs")
m.TASKLISTS_PATH = os.path.join(tmp, "m365gui_tasklists.json")
json.dump({"favorites": [key, "Gone|Old task"], "recent": []}, open(m.TASKLISTS_PATH, "w"))
m.find_m365 = lambda saved: ""            # no m365: nothing real is ever run
m.M365Gui._startup_checks = lambda self: None   # no update check from a test
app = m.M365Gui()
app.withdraw()
app.update()

def top_titles():
    return [app.tree.item(i, "text") for i in app.tree.get_children("")]

def children(title):
    node = next(i for i in app.tree.get_children("") if app.tree.item(i, "text") == title)
    return [app.tree.item(i, "text") for i in app.tree.get_children(node)]

check(top_titles()[0] == "Favorites" and children("Favorites") == [copy["name"]],
      "Favorites sit at the top; a favorite that no longer exists is skipped")
check("Recent" not in top_titles(), "no Recent group before anything has run")
app.search_var.set("guest")
app.update()
shown = [t for title in top_titles() if title not in ("Custom command",) for t in children(title)]
check(shown and all("guest" in (t.lower() + " ".join(x["desc"] for cat in c.TASKS.values()
                                                   for x in cat if x["name"] == t).lower())
                    for t in shown), "typing 'guest' shows only matching tasks (%d)" % len(shown))
check("Favorites" not in top_titles(), "a favorite that does not match the search is hidden too")
app.search_var.set("")
app.update()
app.current_task = copy
app._remember_recent()
check(children("Recent") == [copy["name"]], "a task that ran appears under Recent")
saved = json.load(open(m.TASKLISTS_PATH))
check(saved["recent"] == [key] and key in saved["favorites"], "Favorites and Recent are saved to the JSON file")
app._toggle_favorite(key)
check("Favorites" not in top_titles() and key not in json.load(open(m.TASKLISTS_PATH))["favorites"],
      "removing the last favorite removes the Favorites group")
for _ in range(15):
    app.current_task = c.TASKS["Users (Entra ID)"][_ % 10]
    app._remember_recent()
check(len(app.recent) == m.RECENT_MAX, "Recent keeps the last %d" % m.RECENT_MAX)
app.update()
check(app.account_label.cget("text") in ("Signed in as: (checking...)", "Signed in as: (m365 not found)"),
      "the account line is there (%s)" % app.account_label.cget("text"))
app.destroy()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
