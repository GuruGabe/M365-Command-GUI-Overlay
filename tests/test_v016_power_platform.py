# test_v016_power_platform.py - v0.16 (11-02-2026): the new 'Power Platform'
# section - 'Power Platform environments' and the read-only 'Power Automate
# flows and Power Apps review' (m365_workflows.power_platform) - against a
# fake m365 that answers in the shape the real tenant did (live run
# 11-02-2026: 'flow environment list', 'flow list --asAdmin', 'flow get
# --asAdmin', 'pa app list --asAdmin', Graph directoryObjects). Checks: only
# reads, who made each flow (person, guest, app, system account, deleted
# account - each looked up once), the notes, plain-words triggers, the faster
# list, apps, an environment that cannot be read, Stop, and the CSV.
import csv, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_workflows as wf
import m365_catalog as cat

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

# ---- the catalog ------------------------------------------------------------------
tasks = cat.TASKS.get("Power Platform") or []
names = [t["name"] for t in tasks]
# (later in 0.16 four read-only tasks follow - test_v016_power_more.py)
check(names[:2] == ["Power Platform environments", "Power Automate flows and Power Apps review"],
      "a Power Platform section that starts with both tasks (%s)" % names)
check(list(cat.TASKS)[-1] == "Diagnostics", "Diagnostics is still the last section")
env_task, review = tasks[0], tasks[1]
_d, argv, err = cat.build_command(env_task, {}, "Power Platform")
check(not err and argv[:3] == ["flow", "environment", "list"] and argv[-2:] == ["--output", "text"]
      and "Name:name" in argv[4] and "Default:properties.isDefault" in argv[4],
      "environments: one read with a --query that keeps the Name column (%s)" % argv)
check(review["workflow"] == "power_platform" and not review["destructive"]
      and not env_task["destructive"], "both are read-only")
check(review["fields"][0]["choices"] == [cat.POWER_DETAILS_FULL, cat.POWER_DETAILS_FAST],
      "the review offers the full read first, then the faster list")
check("read-only" in cat.WORKFLOW_PLANS["power_platform"]
      and "Nothing is changed" in cat.WORKFLOW_PLANS["power_platform"], "its plan says read-only")
check(all(t["desc"].isascii() and "Global" in t["desc"] for t in tasks),
      "descriptions are ASCII and say who can run them")

# ---- a fake tenant ----------------------------------------------------------------
ENV1, ENV2 = "Default-11111111-2222-3333-4444-555555555555", "env-broken"
P_USER, P_GUEST, P_GONE, P_APP = ("aaaaaaaa-0000-0000-0000-000000000001",
                                  "aaaaaaaa-0000-0000-0000-000000000002",
                                  "aaaaaaaa-0000-0000-0000-000000000003",
                                  "aaaaaaaa-0000-0000-0000-000000000004")
DIRECTORY = {
    P_USER: {"@odata.type": "#microsoft.graph.user", "displayName": "Jane Doe",
             "userPrincipalName": "jdoe@example.com"},
    P_GUEST: {"@odata.type": "#microsoft.graph.user", "displayName": "Pat Guest",
              "userPrincipalName": "pat_partner.org#EXT#@example.onmicrosoft.com"},
    P_APP: {"@odata.type": "#microsoft.graph.servicePrincipal", "displayName": "Project Service"},
}

def flow(name, title, creator, user_type="ActiveDirectory", state="Started", suspended="None"):
    return {"name": name, "id": "/providers/x/" + name, "type": "Microsoft.ProcessSimple/flows",
            "properties": {"displayName": title, "state": state, "createdTime": "2026-01-02T03:04:05Z",
                           "lastModifiedTime": "2026-09-17T20:26:28Z",
                           "flowSuspensionReason": suspended,
                           "creator": {"objectId": creator, "userType": user_type,
                                       "tenantId": "t", "userId": creator}}}

FLOWS = [flow("f-mail", "Copy mail to Gmail", P_USER),
         flow("f-guest", "Guest timesheet", P_GUEST, state="Stopped"),
         flow("f-gone", "Old export", P_GONE),
         flow("f-sys", "SLA monitor", "e8d4c823-0000-0000-0000-000000000000",
              user_type="DataverseSystemUser", state="Stopped"),
         flow("f-app", "Abandon operation sets", P_APP, suspended="CompanyDlpViolation"),
         flow("f-hook", "Form intake", P_USER)]
DETAILS = {
    "f-mail": ("Recurrence", "OpenApiConnection-GetEmails, OpenApiConnection-SendEmail",
               {"shared_office365": {"apiName": "office365", "displayName": "Office 365 Outlook"},
                "shared_gmail": {"apiName": "gmail", "displayName": "Gmail"}}),
    "f-guest": ("Request-Button", "Compose", {}),
    "f-gone": ("Recurrence", "Http, Compose",
               {"x": {"id": "/providers/Microsoft.PowerApps/apis/shared_dropbox",
                      "displayName": "Dropbox"}}),
    "f-sys": ("OpenApiConnectionWebhook", "If",
              {"x": {"apiName": "commondataserviceforapps", "displayName": "Microsoft Dataverse"}}),
    "f-app": ("Recurrence", "OpenApiConnection-PerformUnboundAction",
              {"x": {"apiName": "commondataserviceforapps", "displayName": "Microsoft Dataverse"}}),
    "f-hook": ("Request-Http", "Compose, Response", {}),
}
APPS = [{"name": "app-1", "properties": {
            "displayName": "Field trip forms", "appType": "ClassicCanvasApp",
            "lastModifiedTime": "2026-10-01T00:00:00Z", "createdTime": "2026-01-01T00:00:00Z",
            "owner": {"id": P_USER, "displayName": "Jane Doe", "email": "jdoe@example.com"},
            "sharedUsersCount": 4, "sharedGroupsCount": 1,
            "connectionReferences": {"c1": {"id": "/providers/microsoft.powerapps/apis/shared_googledrive",
                                            "displayName": "Google Drive"}}}},
        {"name": "app-2", "properties": {"displayName": "Bus list", "appType": "ClassicCanvasApp",
                                         "owner": {"id": P_GUEST}}}]

def make_run(calls, flag=None, stop_after_gets=None):
    def run(argv):
        calls.append(argv)
        assert argv[-2:] == ["--output", "json"], argv
        if argv[:3] == ["flow", "environment", "list"]:
            return 0, json.dumps([{"name": ENV1, "properties": {"displayName": "Contoso (default)",
                                                                "isDefault": True}},
                                  {"name": ENV2, "properties": {"displayName": "Sandbox"}}])
        if argv[:2] == ["flow", "list"]:
            assert argv[2:6] == ["--environmentName", argv[3], "--asAdmin", "--output"], argv
            if argv[3] == ENV2:
                return 1, "Error: Access to the environment 'env-broken' is denied."
            return 0, json.dumps(FLOWS)
        if argv[:2] == ["flow", "get"]:
            assert argv[2] == "--name" and argv[4:7] == ["--environmentName", ENV1, "--asAdmin"], argv
            if stop_after_gets is not None and len([c for c in calls if c[:2] == ["flow", "get"]]) >= stop_after_gets:
                flag["stop"] = True
            trig, acts, refs = DETAILS[argv[3]]
            return 0, json.dumps({"name": argv[3], "triggers": trig, "actions": acts,
                                  "properties": {"connectionReferences": refs}})
        if argv[:3] == ["pa", "app", "list"]:
            assert argv[3] == "--environmentName" and argv[5] == "--asAdmin", argv
            if argv[4] == ENV2:
                return 1, "Error: Access to the environment 'env-broken' is denied."
            return 0, json.dumps(APPS)
        assert argv[:2] == ["request", "--url"] and "--method" not in argv, argv
        oid = argv[2].rsplit("/", 1)[-1]
        assert argv[2] == wf.GRAPH + "directoryObjects/" + oid, argv
        if oid in DIRECTORY:
            return 0, json.dumps(DIRECTORY[oid])
        return 1, '{"error":"Request failed with status code 404"}'
    return run

def go(values, **kw):
    calls, lines = [], []
    tmp = tempfile.mkdtemp(prefix="m365power_")
    flag = {"stop": False}
    r = wf.power_platform(make_run(calls, flag=flag, **kw), lines.append,
                          lambda: flag["stop"], values, tmp)
    return r, calls, "".join(lines), tmp

# ---- the full read ----------------------------------------------------------------
r, calls, text, tmp = go({"details": cat.POWER_DETAILS_FULL})
check(r["flows"] == 6 and r["apps"] == 2, "every flow and app is read (%s)" % r)
check(not r["ok"] and "Sandbox" in text and "COULD NOT LIST THE FLOWS" in text
      and "is denied" in text, "an environment that cannot be read is reported, not hidden")
kinds = sorted(set(" ".join(c[:2]) for c in calls))
check(kinds == ["flow environment", "flow get", "flow list", "pa app", "request --url"],
      "only reads were run (%s)" % kinds)
lookups = [c[2].rsplit("/", 1)[-1] for c in calls if c[0] == "request"]
check(sorted(lookups) == sorted([P_USER, P_GUEST, P_GONE, P_APP]),
      "each creator / owner is looked up once; the Dataverse system account is not (%s)" % lookups)
check(len([c for c in calls if c[:2] == ["flow", "get"]]) == 6, "one 'flow get --asAdmin' per flow")
check(text.index("Abandon operation sets") < text.index("Copy mail to Gmail")
      < text.index("Guest timesheet") < text.index("SLA monitor"), "flows are sorted by name")
check("FLOW  Copy mail to Gmail  [ON]" in text and "FLOW  Guest timesheet  [stopped]" in text,
      "on / off is shown")
check("Jane Doe <jdoe@example.com>" in text and "app: Project Service" in text
      and "system account (Dataverse)" in text and "(deleted or unknown account %s)" % P_GONE in text,
      "who made it: a person, an app, a system account, a deleted account")
check("on a schedule (Recurrence)" in text and "by hand (a button) (Request-Button)" in text
      and "when someone calls its web address (Request-Http)" in text, "triggers in plain words")
check("Connectors:     Office 365 Outlook, Gmail" in text, "a flow's connectors are listed")
for want in ["Contoso (default) / flow 'Copy mail to Gmail': can send data outside Microsoft 365: Gmail",
             "flow 'Guest timesheet': made by a guest",
             "flow 'Old export': the account that made it is deleted or unknown - and it is still ON",
             "flow 'Old export': can send data outside Microsoft 365: Dropbox",
             "flow 'Old export': calls web addresses directly (HTTP)",
             "flow 'Abandon operation sets': suspended by Microsoft (CompanyDlpViolation)",
             "flow 'Form intake': starts when someone calls its web address",
             "app 'Field trip forms': can send data outside Microsoft 365: Google Drive",
             "app 'Bus list': made by a guest"]:
    check(want in text, "note: " + want)
check("SLA monitor':" not in text and "Office 365 Outlook" not in text.split("Worth a second look:")[1],
      "no note for a system flow or for Office 365 Outlook")
check("Shared with:    4 people, 1 group(s)" in text, "an app's sharing counts are shown")
rows = list(csv.DictReader(open(os.path.join(r["folder"], "power-platform.csv"), encoding="utf-8")))
check(len(rows) == 10 and rows[0]["kind"] == "flow"
      and [x["state"] for x in rows[-2:]] == ["COULD NOT READ"] * 2
      and [x["name"] for x in rows[-2:]] == ["flows", "apps"],
      "power-platform.csv: 6 flows, 2 apps and the unreadable environment's flows and apps "
      "(%d rows)" % len(rows))
gmail = [x for x in rows if x["name"] == "Copy mail to Gmail"][0]
check(gmail["id"] == "f-mail" and gmail["made_by_kind"] == "user"
      and gmail["connectors"] == "Office 365 Outlook; Gmail" and "Gmail" in gmail["notes"],
      "a CSV row has the flow id, who made it, connectors and notes")
check(open(os.path.join(r["folder"], "power-platform.csv"), encoding="utf-8").read().isascii(),
      "the CSV is ASCII for this data")

# ---- the faster list --------------------------------------------------------------
r, calls, text, tmp = go({"details": cat.POWER_DETAILS_FAST})
check(not any(c[:2] == ["flow", "get"] for c in calls) and r["flows"] == 6,
      "faster list: no 'flow get', every flow still listed")
check("were skipped" in text and "Starts:" not in text, "faster list: it says what was skipped")
check("made by a guest" in text and "deleted or unknown" in text,
      "faster list: who made it is still checked")

# ---- environments cannot be listed ----------------------------------------------
def no_envs(argv):
    return 1, "Error: You do not have permission"
lines = []
r = wf.power_platform(no_envs, lines.append, lambda: False, {}, tempfile.mkdtemp())
check(not r["ok"] and "Power Platform or Global administrator" in r["error"]
      and "do not have permission" in r["error"], "no environments: a clear error (%s)" % r["error"])

# ---- Stop -------------------------------------------------------------------------
r, calls, text, tmp = go({"details": cat.POWER_DETAILS_FULL}, stop_after_gets=2)
check(len([c for c in calls if c[:2] == ["flow", "get"]]) == 2 and not r["ok"]
      and "[Stopped.]" in text and not any(c[:2] == ["pa", "app"] for c in calls),
      "Stop: nothing more is read after it")
check(os.path.exists(os.path.join(r["folder"], "power-platform.csv")), "Stop: the CSV is still saved")

# ---- helpers ----------------------------------------------------------------------
check(wf._power_connectors([{"id": "/apis/shared_FTP"}, {"id": "/apis/shared_FTP"}]) == [("ftp", "ftp")],
      "connector names: last part of the id, 'shared_' dropped, no repeats")
check(wf._power_trigger_text("Mystery, Recurrence") == "Mystery; on a schedule (Recurrence)",
      "an unknown trigger is shown as it is")
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
