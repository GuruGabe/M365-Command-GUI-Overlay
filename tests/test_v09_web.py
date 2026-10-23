# test_v09_web.py - v0.9 (10-23-2026): the browser version (m365_web.py),
# like GAMGUI's gam_web. A real server on a free local port; a stand-in
# 'm365' (a small Python script) answers the commands and records them.
# Checks the security rules, every API route, downloads, the workflows'
# questions and the one-time password hand-over. Nothing touches a tenant.
import os, sys, json, time, base64, tempfile, threading, http.client
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import m365_web as w
import M365GUI as app

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

tmp = tempfile.mkdtemp(prefix="m365web_")
CALLS = os.path.join(tmp, "calls.jsonl")
FAKE = os.path.join(tmp, "fake_m365.py")
open(FAKE, "w").write(r'''
import sys, json, os
argv = sys.argv[1:]
open(os.environ["M365_CALLS"], "a").write(json.dumps(argv) + "\n")
j = " ".join(argv)
if "--fail" in argv or "nosuchuser" in j:
    print('{"error":"Resource does not exist"}'); sys.exit(1)
if argv[:1] == ["status"]:
    print(json.dumps({"connectedAs": "admin@contoso.com"}))
elif argv[:3] == ["entra", "user", "list"] and "--type" in argv and "Guest" in argv:
    print(json.dumps([{"id": "g1", "displayName": "Guest One", "userPrincipalName": "g1#EXT#@contoso.com"}]))
elif argv[:3] == ["entra", "user", "list"]:
    if "csv" in argv:
        print("displayName,userPrincipalName"); print("Pat,p@contoso.com")
    else:
        print(json.dumps([{"displayName": "Pat Smith", "userPrincipalName": "psmith@contoso.com"}]))
elif argv[:3] == ["entra", "group", "list"]:
    print(json.dumps([{"displayName": "Sales", "mail": "sales@contoso.com"}, {"displayName": "IT", "mail": None}]))
elif argv[:3] == ["entra", "user", "get"]:
    print(json.dumps({"userPrincipalName": argv[argv.index("--userName") + 1]}))
elif argv[:4] in (["entra", "user", "groupmembership", "list"], ["entra", "user", "license", "list"],
                  ["entra", "user", "signin", "list"], ["entra", "user", "registrationdetails", "list"]):
    print("[]")
else:
    print("done")
''')
os.environ["M365_CALLS"] = CALLS
w.invocation = lambda argv: [sys.executable, FAKE] + list(argv)
w.M365_PATH = "m365"
app.DATA_DIR, app.LOG_DIR = tmp, os.path.join(tmp, "Logs")
w.UPLOAD_DIR = os.path.join(tmp, "Uploads")
app.random_password = lambda: "Zq9!webSecret-77"

server = w.make_server(0)
PORT = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()

def req(method, path, body=None, token=True, host="127.0.0.1:%d" % PORT, ctype="application/json"):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    headers = {"Host": host}
    if token:
        headers["X-M365Web-Token"] = w.SESSION_TOKEN
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = ctype
    c.request(method, path, body=data, headers=headers)
    r = c.getresponse()
    raw = r.read()
    try:
        return r.status, json.loads(raw), dict(r.getheaders())
    except ValueError:
        return r.status, raw, dict(r.getheaders())

def calls():
    return [json.loads(l) for l in open(CALLS)] if os.path.exists(CALLS) else []

def follow(job, answers=()):
    answers = list(answers)
    lines, seen_secret, since = [], [], 0
    end = time.time() + 30
    while time.time() < end:
        _s, st, _h = req("GET", "/api/job?job=%s&since=%d" % (job, since))
        lines += st["lines"]
        since = st["next"]
        if st.get("secret"):
            seen_secret.append(st["secret"]["value"])
        if st.get("question") and answers:
            ok, typed = answers.pop(0)
            req("POST", "/api/job/answer", {"job": job, "ok": ok, "typed": typed})
        if st["done"]:
            return "".join(lines), st, seen_secret
        time.sleep(0.1)
    return "".join(lines), {"done": False}, seen_secret

# ---- 1. security -------------------------------------------------------------------------
s, body, h = req("GET", "/", token=False)
check(s == 200 and w.SESSION_TOKEN.encode() in body and "Content-Security-Policy" in h,
      "the page is served (with its token and a CSP) to localhost")
check(req("GET", "/", token=False, host="evil.example.com")[0] == 403, "another Host name is refused (DNS rebinding)")
check(req("GET", "/api/tasks", token=False)[0] == 403, "the API refuses a request without the token")
check(req("POST", "/api/run", {"custom": "status"}, ctype="text/plain")[0] == 415, "a non-JSON POST is refused")
s, tasks, _h = req("GET", "/api/tasks")
check(s == 200 and len(tasks) == len(app.TASKS) and any(t["workflow"] == "compromised" for sct in tasks for t in sct["tasks"]),
      "/api/tasks lists every section and task")

def find(section, name):
    for sct in tasks:
        if sct["name"] == section:
            for t in sct["tasks"]:
                if t["name"] == name:
                    return t
reset = find("Users (Entra ID)", "Reset password")
check([f["picker"] for f in reset["fields"]] == ["user", None], "a task's boxes carry their Pick... list")

# ---- 2. build / run / save ----------------------------------------------------------------
s, b, _h = req("POST", "/api/build", {"cat": "Users (Entra ID)", "idx": reset["idx"],
                                      "values": {"email": "a@contoso.com", "password": "x y"}})
check(b["display"].startswith("entra user set --userName a@contoso.com") and not b["error"], "/api/build builds the command")
delete = find("Users (Entra ID)", "Delete user (DESTRUCTIVE)")
s, b, _h = req("POST", "/api/run", {"cat": "Users (Entra ID)", "idx": delete["idx"], "values": {"email": "a@contoso.com"}})
check("confirm" in b.get("error", ""), "a destructive task is refused unless the page confirmed it")
s, b, _h = req("POST", "/api/run", {"cat": "Users (Entra ID)", "idx": delete["idx"], "values": {"email": "a@contoso.com"},
                                    "confirmed": True})
text, st, _sec = follow(b["job"])
check(st["rc"] == 0 and calls()[-1] == ["entra", "user", "remove", "--userName", "a@contoso.com", "--force"],
      "confirmed: it runs exactly the built command")
lst = find("Users (Entra ID)", "List users")
s, b, _h = req("POST", "/api/run", {"cat": "Users (Entra ID)", "idx": lst["idx"], "values": {}, "save": "CSV file"})
text, st, _sec = follow(b["job"])
check(st["file"] and "--output" in calls()[-1] and calls()[-1][calls()[-1].index("--output") + 1] == "csv",
      "Save results to CSV: runs with --output csv and offers a download")
s, data, h = req("GET", "/api/job/file?job=" + b["job"])
check(s == 200 and data == b"displayName,userPrincipalName\nPat,p@contoso.com\n"
      and "attachment" in h.get("Content-Disposition", ""), "the download is the CSV, as an attachment")
check(req("GET", "/api/job/file?job=" + b["job"], token=False)[0] == 403, "the download needs the token too")
s, b, _h = req("POST", "/api/run", {"custom": "entra user list --fail"})
text, st, _sec = follow(b["job"])
check(st["rc"] == 1 and "does not exist" in text, "Custom command runs and shows its error")

# ---- 3. pickers ----------------------------------------------------------------------------
s, b, _h = req("POST", "/api/pick", {"kind": "user", "text": "pat"})
check(b.get("choices") == [["Pat Smith  <psmith@contoso.com>", "psmith@contoso.com"]], "the user picker searches")
s, b, _h = req("POST", "/api/pick", {"kind": "group", "text": "sal"})
check(b.get("choices") == [["Sales  <sales@contoso.com>", "Sales"]], "the group picker filters the groups")

# ---- 4. workflows: questions and the password --------------------------------------------------
comp = find("Security", "Compromised account response")
s, b, _h = req("POST", "/api/workflow/start", {"cat": "Security", "idx": comp["idx"],
                                               "values": {"email": "jdoe@contoso.com", "block": "Yes",
                                                          "signout": "Yes", "password": "Yes"}})
text, st, secrets_seen = follow(b["job"], answers=[(True, "")])
check(st["done"] and any("--resetPassword" in c for c in calls()), "the compromised-account workflow ran after Yes")
check(secrets_seen == ["Zq9!webSecret-77"], "the new password is handed to the page ONCE")
check("Zq9!webSecret-77" not in text and "own window" in text, "...and never appears in the output")
logs = "".join(open(os.path.join(dp, f), encoding="utf-8", errors="replace").read()
               for dp, _d, fs in os.walk(tmp) for f in fs if f.endswith((".csv", ".json", ".txt", ".log")))
check("Zq9!webSecret-77" not in logs, "...or in any saved record")
guests = find("Users (Entra ID)", "Remove ALL guest users (DESTRUCTIVE)")
before = len(calls())
s, b, _h = req("POST", "/api/workflow/start", {"cat": "Users (Entra ID)", "idx": guests["idx"], "values": {}})
text, st, _sec = follow(b["job"], answers=[(True, "delete")])
check(not any(c[:3] == ["entra", "user", "remove"] for c in calls()[before:]) and "nothing deleted" in text,
      "remove ALL guests: Yes without TYPING DELETE (server-checked) deletes nothing")
s, b, _h = req("POST", "/api/workflow/start", {"cat": "Users (Entra ID)", "idx": guests["idx"], "values": {}})
text, st, _sec = follow(b["job"], answers=[(True, "DELETE")])
check(any(c[:4] == ["entra", "user", "remove", "--id"] for c in calls()), "...typing DELETE removes them")

# ---- 5. Run for each CSV row --------------------------------------------------------------------
block = find("Users (Entra ID)", "Block sign-in")
csvdata = "displayName,userPrincipalName\nA,a@contoso.com\nB,b@contoso.com\nC,c@contoso.com\n"
s, up, _h = req("POST", "/api/bulk/upload", {"name": "people.csv", "data": base64.b64encode(csvdata.encode()).decode()})
check(up.get("path", "").startswith(os.path.realpath(w.UPLOAD_DIR)), "a CSV upload is stored in the Uploads folder")
s, cols, _h = req("POST", "/api/bulk/columns", {"cat": "Users (Entra ID)", "idx": block["idx"], "path": up["path"]})
check(cols.get("rows") == 3 and cols["guess"] == {"email": "userPrincipalName"}, "its columns are read and the UPN column guessed")
s, b, _h = req("POST", "/api/bulk/columns", {"cat": "Users (Entra ID)", "idx": block["idx"],
                                             "path": os.path.join(tmp, "..", "secret.csv")})
check("Upload the CSV" in b.get("error", ""), "a path outside the Uploads folder is refused")
body = {"cat": "Users (Entra ID)", "idx": block["idx"], "path": up["path"], "values": {},
        "mapping": {"email": "userPrincipalName"}, "limit": "2"}
s, b, _h = req("POST", "/api/bulk/start", dict(body, preview=True))
check(b.get("count") == 2 and b["first"].endswith("--userName a@contoso.com --accountEnabled false"),
      "test run: the first row's command and the row count")
before = len(calls())
s, b, _h = req("POST", "/api/bulk/start", body)
text, st, _sec = follow(b["job"])
users = [c[c.index("--userName") + 1] for c in calls()[before:] if "--userName" in c]
check(users == ["a@contoso.com", "b@contoso.com"] and "DONE: 2 OK, 0 failed" in text, "only the 2 test rows ran")
s, b, _h = req("POST", "/api/bulk/start", {"cat": "Users (Entra ID)", "idx": delete["idx"], "path": up["path"],
                                           "values": {}, "mapping": {"email": "userPrincipalName"}})
check("confirm" in b.get("error", "") and b.get("count") == 3, "a destructive task per row must be confirmed")

# ---- 6. status ----------------------------------------------------------------------------------
s, b, _h = req("GET", "/api/status")
check(b.get("account") == "Signed in as: admin@contoso.com" and b.get("version") == app.APP_VERSION,
      "/api/status: version and the signed-in account")
server.shutdown()

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
