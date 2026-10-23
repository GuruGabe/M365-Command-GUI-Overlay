# test_v08_workflows.py - v0.8 (10-23-2026): the guided Staff hand-off and
# Compromised account response (like GAMGUI's), against a FAKE m365 that
# records every command. Also: every command they run is checked against
# the CLI's own docs (m365docs). Nothing touches a tenant.
import os, sys, csv, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import M365GUI as m
import m365_workflows as w
import m365docs as d

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

LEAVER, BOSS = "jdoe@contoso.com", "boss@contoso.com"
HOST = "https://contoso-my.sharepoint.com"
GROUPS = [{"@odata.type": "#microsoft.graph.group", "id": "g1", "displayName": "Staff"},
          {"@odata.type": "#microsoft.graph.group", "id": "g2", "displayName": "Science"},
          {"@odata.type": "#microsoft.graph.directoryRole", "id": "r1", "displayName": "Helpdesk"}]
LICENSES = [{"skuId": "sku-a", "skuPartNumber": "A1"}, {"skuId": "sku-b", "skuPartNumber": "B1"}]

class Fake:
    def __init__(self, fail=()):
        self.calls, self.fail = [], fail
    def __call__(self, argv):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        for word in self.fail:
            if word in joined:
                return 1, '{"error":"Access denied"}'
        if argv[:1] == ["status"]:
            return 0, '{"connectedAs": "admin@contoso.com"}'
        if argv[:3] == ["entra", "user", "get"]:
            upn = argv[argv.index("--userName") + 1]
            return 0, json.dumps({"userPrincipalName": upn, "displayName": upn.split("@")[0],
                                  "mySite": HOST + "/personal/%s/" % upn.replace("@", "_").replace(".", "_")})
        if argv[:4] == ["entra", "user", "groupmembership", "list"]:
            return 0, json.dumps(GROUPS)
        if argv[:4] == ["entra", "user", "license", "list"]:
            return 0, json.dumps(LICENSES)
        if argv[:4] == ["spo", "site", "admin", "list"]:
            return 0, "[]"
        if argv[:3] in (["spo", "file", "list"], ["spo", "folder", "list"]):
            folder = argv[argv.index("--folderUrl" if "--folderUrl" in argv else "--parentFolderUrl") + 1]
            if argv[1] == "folder":
                return 0, "[]"
            return 0, json.dumps([{"Name": "a.docx", "ServerRelativeUrl": folder + "/a.docx", "Length": 5}])
        if argv[:3] == ["spo", "folder", "add"]:
            return 0, json.dumps({"ServerRelativeUrl": argv[argv.index("--parentFolderUrl") + 1] + "/x"})
        if argv[:4] == ["entra", "user", "signin", "list"]:
            return 0, json.dumps([{"ipAddress": "203.0.113.9", "location": {"countryOrRegion": "XX"}}])
        return 0, "{}"

def handoff(values, answer=True, fail=(), cancel_at=None):
    fake = Fake(fail)
    out, asked = [], []
    base = tempfile.mkdtemp(prefix="m365gui_rec_")
    vals = {"leaver": LEAVER, "manager": BOSS, "block": "Yes", "signout": "Yes", "copy": "Yes",
            "autoreply": "No", "reply": "", "groups": "No", "licenses": "No"}
    vals.update(values)
    def cancelled():
        return cancel_at is not None and any(cancel_at in " ".join(c) for c in fake.calls)
    res = w.staff_handoff(fake, out.append, lambda q: asked.append(q) or answer, cancelled, vals, base)
    return res, fake, "".join(out), asked

def idx(calls, *words):
    for i, c in enumerate(calls):
        if all(x in c for x in words):
            return i
    return -1

# ---- 1. the hand-off -----------------------------------------------------------------
res, fake, out, asked = handoff({"groups": "Yes", "licenses": "Yes", "autoreply": "Yes",
                                 "reply": "Jo has left; contact boss@contoso.com"})
calls = fake.calls
check(res["ok"], "a full hand-off succeeds (%s)" % res.get("error"))
check(len(asked) == 2 and "REMOVE THEIR LICENSES" in asked[0] and "remove them from every group" in asked[0],
      "it asks ONCE for the hand-off (naming every chosen step), and the copy asks its own file count")
first_change = min(i for i in (idx(calls, "--accountEnabled"), idx(calls, "session", "revoke")) if i >= 0)
check(idx(calls, "groupmembership") < first_change and idx(calls, "license", "list") < first_change,
      "groups and licenses are RECORDED before anything changes")
check(idx(calls, "--accountEnabled", "false") < idx(calls, "spo", "copy") < idx(calls, "license", "remove"),
      "order: block -> copy files -> remove licenses (files copied while the license exists)")
removed = [c[c.index("--groupId") + 1] for c in calls if c[:4] == ["entra", "group", "member", "remove"]]
check(removed == ["g1", "g2"], "removed from both groups - a directory role is not a group (%s)" % removed)
lic = next(c for c in calls if c[:4] == ["entra", "user", "license", "remove"])
check(lic[lic.index("--ids") + 1] == "sku-a,sku-b" and "--force" in lic, "both licenses removed in one call")
ar = next(c for c in calls if c[:4] == ["outlook", "mailbox", "settings", "set"])
check(ar[ar.index("--autoReplyStatus") + 1] == "alwaysEnabled" and "boss@contoso.com" in " ".join(ar),
      "the automatic reply is set with the message")
folder = res["folder"]
files = sorted(os.listdir(folder))
check(files == ["groups-before.json", "licenses-before.json", "onedrive-copy.csv", "steps.csv", "user.json"],
      "the record folder holds the before-state, the copy record and the steps (%s)" % files)
rows = list(csv.reader(open(os.path.join(folder, "steps.csv"), encoding="utf-8")))
check(rows[0] == ["step", "result", "detail"] and all(r[1] == "OK" for r in rows[1:]) and len(rows) == 8,
      "steps.csv lists every step with its result (%d)" % (len(rows) - 1))

res, fake, out, asked = handoff({"copy": "No", "block": "Yes", "signout": "No"})
check([c[:3] for c in fake.calls if c[:3] in (["entra", "user", "set"], ["entra", "user", "session"])]
      == [["entra", "user", "set"]] and not any(c[:2] == ["spo", "file"] for c in fake.calls),
      "only the steps set to Yes run")
res, fake, out, asked = handoff({}, answer=False)
check(not res["ok"] and not any(c[:3] in (["entra", "user", "set"], ["entra", "user", "session"])
                                 for c in fake.calls), "No at the question: nothing is changed")
res, fake, out, asked = handoff({"leaver": BOSS})
check(not fake.calls and "same person" in out, "leaver = manager is refused before anything runs")
res, fake, out, asked = handoff({"autoreply": "Yes", "reply": ""})
check(not fake.calls and "automatic reply" in out, "an automatic reply without a message is refused")
res, fake, out, asked = handoff({"block": "No", "signout": "No", "copy": "No"})
check(not fake.calls and "Nothing to do" in out, "all steps No is refused")
res, fake, out, asked = handoff({"autoreply": "Yes", "reply": "Gone"}, fail=("mailbox settings",))
check(not res["ok"] and "FAILED  Set an automatic reply" in out and idx(fake.calls, "session", "revoke") >= 0,
      "a failed step (no rights to the mailbox) is reported and the others still run")
res, fake, out, asked = handoff({"groups": "Yes", "copy": "No"}, cancel_at="--accountEnabled")
check(not any(c[:4] == ["entra", "group", "member", "remove"] for c in fake.calls) and "Stopped" in out,
      "Stop ends it after the current step")

# ---- 2. compromised account ------------------------------------------------------------------
shown = []
fake = Fake()
out = []
base = tempfile.mkdtemp(prefix="m365gui_inc_")
PASSWORD = "Xy7!secret-Pass9"
res = w.compromised_response(fake, out.append, lambda q: True, lambda: False,
                             {"email": LEAVER, "block": "Yes", "signout": "Yes", "password": "Yes"},
                             base, lambda title, secret: shown.append(secret), lambda: PASSWORD)
text = "".join(out)
check(res["ok"], "the response succeeds (%s)" % res.get("error"))
check(idx(fake.calls, "--accountEnabled") < idx(fake.calls, "session") < idx(fake.calls, "--resetPassword")
      < idx(fake.calls, "signin", "list"), "contain first (block, sign out, password), then evidence")
pw = next(c for c in fake.calls if "--resetPassword" in c)
check(pw[pw.index("--newPassword") + 1] == PASSWORD and "--forceChangePasswordNextSignIn" in pw,
      "the new password is set and must be changed at next sign-in")
check(shown == [PASSWORD], "the password is handed to show_secret once")
everything = text + "".join(open(os.path.join(res["folder"], f), encoding="utf-8").read()
                            for f in os.listdir(res["folder"]))
check(PASSWORD not in everything, "the password is NOT in the output window or any saved file")
check(sorted(os.listdir(res["folder"])) == ["NEXT-STEPS.txt", "groups.json", "licenses.json", "mfa-methods.json",
                                            "signins.json", "steps.csv", "user.json"],
      "evidence + next steps are saved")
check("203.0.113.9" in open(os.path.join(res["folder"], "signins.json")).read(), "the sign-ins are saved as returned")
check("inbox rules" in text, "the next steps are shown in the window too")
shown.clear()
fake = Fake(fail=("--resetPassword",))
w.compromised_response(fake, lambda t: None, lambda q: True, lambda: False,
                       {"email": LEAVER, "block": "Yes", "signout": "Yes", "password": "Yes"},
                       base, lambda title, secret: shown.append(secret), lambda: PASSWORD)
check(shown == [], "a password that could not be set is never shown")
check(len(set(m.random_password() for _ in range(20))) == 20 and all(
          any(ch.isupper() for ch in p) and any(ch.islower() for ch in p) and any(ch.isdigit() for ch in p)
          and not set(p) & set("%^\"'") for p in (m.random_password() for _ in range(50))),
      "random passwords: all different, every kind of character, no % ^ or quotes")

# ---- 3. every command the workflows run is in the CLI's docs -----------------------------------
root = d.docs_root()
if root:
    seen = {}
    for argv in [c for c in calls] + fake.calls + Fake().calls:
        if argv[:1] != ["status"]:
            seen[" ".join(d.command_words(argv))] = argv
    problems = {k: d.argv_problems(root, v) for k, v in seen.items()}
    bad = {k: v for k, v in problems.items() if v}
    check(not bad, "every command the workflows run is documented, with its options (%d commands) %s"
          % (len(seen), bad or ""))
else:
    print("SKIP the docs check (CLI not installed)")

# ---- 4. through the window (hidden): Run -> workflow -> the password window --------------------
import time
tmp = tempfile.mkdtemp(prefix="m365gui_win_")
m.INI_PATH, m.TASKLISTS_PATH = os.path.join(tmp, "m365gui.ini"), os.path.join(tmp, "t.json")
m.LOG_DIR, m.RECORDS_DIR = os.path.join(tmp, "Logs"), os.path.join(tmp, "Records")
m.find_m365 = lambda saved: "m365"
m.M365Gui._startup_checks = lambda self: None
m.M365Gui._refresh_account = lambda self: None
m.messagebox.askyesno = lambda *a, **k: True
m.random_password = lambda: PASSWORD
app = m.M365Gui()
app.withdraw()
app.update()
app._capture = Fake()
for parent in app.tree.get_children(""):
    for child in app.tree.get_children(parent):
        if app.tree.item(child, "text") == "Compromised account response":
            app.tree.selection_set(child)
app.update()
dict(app.field_vars)["email"].set(LEAVER)
app._run()
end = time.time() + 20
while time.time() < end and getattr(app, "_secret_window", None) is None:
    app.update(); time.sleep(0.05)
win = getattr(app, "_secret_window", None)
if win is not None:
    win.withdraw()
while time.time() < end and str(app.run_button.cget("state")) != "normal":
    app.update(); time.sleep(0.05)
app.update()
shown_box = [w_ for w_ in win.winfo_children() if w_.winfo_class() == "TEntry"] if win else []
check(win is not None and shown_box and shown_box[0].get() == PASSWORD,
      "the new password appears in its own window")
log_text = open(app.log_path, encoding="utf-8").read() if os.path.exists(app.log_path) else ""
check(PASSWORD not in app.output_box.get("1.0", "end") and PASSWORD not in log_text
      and "its own window" in app.output_box.get("1.0", "end"),
      "...and NOT in the output window or the session log")
check(os.listdir(m.RECORDS_DIR) and os.listdir(m.RECORDS_DIR)[0].startswith("Compromised_jdoe_"),
      "the evidence folder is in the Records folder")
app.destroy()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
