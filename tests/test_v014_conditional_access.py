# test_v014_conditional_access.py - v0.14 (10-29-2026): the read-only
# 'Conditional Access review' workflow (m365_workflows.conditional_access)
# against a fake m365 that answers 'request --url' like Microsoft Graph did
# on a real tenant (policy shape, directoryRoleTemplates, users / groups by
# id). Checks: only GETs, names resolved, plain-words lines, the gap notes,
# exclusions, the CSV, a 403 and Stop. Nothing runs.
import csv, json, os, shutil, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_workflows as wf
import m365_catalog as cat

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

G = wf.GRAPH
GA = wf.GA_ROLE_TEMPLATE
HELPDESK = "729827e3-9c14-49f7-bb1b-9608f156bbb8"

def policy(name, state="enabled", controls=(), strength=None, users=None, clients=("all",),
           locations=False, apps=("All",)):
    return {"id": name.lower().replace(" ", "-"), "displayName": name, "state": state,
            "grantControls": {"operator": "OR", "builtInControls": list(controls),
                              "authenticationStrength": {"displayName": strength} if strength else None,
                              "termsOfUse": [], "customAuthenticationFactors": []},
            "sessionControls": None,
            "conditions": {"users": users or {}, "clientAppTypes": list(clients),
                           "locations": {"includeLocations": ["All"]} if locations else None,
                           "platforms": None, "devices": None, "signInRiskLevels": [], "userRiskLevels": [],
                           "applications": {"includeApplications": list(apps), "excludeApplications": []}}}

GOOD = [
    policy("MFA for admins", strength="Phishing-resistant MFA",
           users={"includeRoles": [GA, HELPDESK], "excludeUsers": ["u-break"]}),
    policy("MFA for everyone", controls=["mfa", "compliantDevice"], locations=True,
           users={"includeUsers": ["All"], "excludeUsers": ["u-break"], "excludeGroups": ["g-svc"]}),
    policy("Block legacy auth", controls=["block"], clients=("exchangeActiveSync", "other"),
           users={"includeUsers": ["All"], "excludeUsers": ["u-break"]}),
    policy("Trial policy", state="enabledForReportingButNotEnforced", controls=["mfa"],
           users={"includeUsers": ["GuestsOrExternalUsers"]}),
]
WEAK = [policy("Helpdesk only", controls=["mfa"], users={"includeRoles": [HELPDESK]}),
        policy("Old off policy", state="disabled", controls=["mfa"], users={"includeUsers": ["All"]})]


def make_run(policies, calls, fail=False):
    def run(argv):
        calls.append(argv)
        assert argv[:2] == ["request", "--url"] and argv[-2:] == ["--output", "json"], argv
        url = argv[2]
        if url == G + "identity/conditionalAccess/policies":
            if fail:
                return 1, '{"error":"Request failed with status code 403"}'
            return 0, json.dumps({"value": policies})
        if url.startswith(G + "directoryRoleTemplates"):
            return 0, json.dumps({"value": [{"id": GA, "displayName": "Global Administrator"},
                                            {"id": HELPDESK, "displayName": "Helpdesk Administrator"}]})
        if url == G + "users/u-break?$select=displayName,userPrincipalName":
            return 0, json.dumps({"displayName": "Break Glass", "userPrincipalName": "bg@contoso.com"})
        if url == G + "groups/g-svc?$select=displayName":
            return 0, json.dumps({"displayName": "Service accounts"})
        return 1, '{"error":"unexpected %s"}' % url
    return run


base = tempfile.mkdtemp(prefix="m365ca_")
try:
    calls, lines = [], []
    res = wf.conditional_access(make_run(GOOD, calls), lines.append, lambda: False, {}, base)
    text = "".join(lines)
    check(res["ok"] and res["policies"] == 4, "runs OK, 4 policies (%s)" % res)
    check(all(c[:2] == ["request", "--url"] for c in calls), "only Graph GETs through 'm365 request'")
    check(sum(1 for c in calls if "/users/" in c[2] or "/groups/" in c[2]) == 2,
          "each excluded user / group is looked up once (cached)")
    check("MFA for admins  [ON]\n  requires: authentication strength 'Phishing-resistant MFA'\n"
          "  applies to: 2 admin roles (incl. Global Administrator)\n  excludes: Break Glass <bg@contoso.com>" in text,
          "a policy in plain words, with role and user names")
    check("requires: any of: MFA, a compliant device" in text and "only when: only some locations" in text,
          "several controls and a location condition")
    check("only Exchange ActiveSync / other old clients" in text, "legacy client types in words")
    check("Trial policy  [report-only (not enforced)]" in text and "applies to: guests" in text,
          "report-only state and guests")
    check(text.index("Block legacy auth  [ON]") < text.index("Trial policy"), "policies that are ON come first")
    check("4 policy(ies): 3 ON, 1 report-only, 0 off." in text, "the count line")
    check("no policy that is ON requires MFA" not in text and "blocks legacy" not in text,
          "a good set of policies has no gap notes")
    check("NOTE: Break Glass <bg@contoso.com> is excluded from 3 MFA / block policy(ies) that are ON" in text,
          "an account excluded from policies that are ON is named, with the count")
    check("NOTE: group Service accounts is excluded from 1 MFA / block policy(ies)" in text,
          "an excluded group is named as a group")
    with open(os.path.join(res["folder"], "conditional-access.csv"), encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    check(len(rows) == 4 and rows[0]["policy"] == "Block legacy auth" and rows[0]["state"] == "ON",
          "conditional-access.csv: one row per policy, ON first")
    check(os.path.basename(res["folder"]).startswith("ConditionalAccess_tenant_"), "record folder name")

    calls, lines = [], []
    res = wf.conditional_access(make_run(WEAK, calls), lines.append, lambda: False, {}, base)
    text = "".join(lines)
    check("NOTE: no policy that is ON requires MFA for everyone on all apps." in text, "gap: MFA for everyone")
    check("NOTE: no policy that is ON requires MFA for Global Administrators on all apps" in text,
          "gap: MFA for Global Administrators (a policy that is off does not count)")
    check("NOTE: no policy that is ON blocks legacy authentication" in text, "gap: legacy authentication")

    # A policy for ONE app does not count as 'MFA for everyone / Global Administrators'.
    one_app = [policy("MFA everyone, portal only", controls=["mfa"], apps=("app-portal",),
                      users={"includeUsers": ["All"]}),
               policy("Block legacy auth", controls=["block"], clients=("exchangeActiveSync", "other"),
                      users={"includeUsers": ["All"]})]
    calls, lines = [], []
    wf.conditional_access(make_run(one_app, calls), lines.append, lambda: False, {}, base)
    text = "".join(lines)
    check("requires MFA for everyone on all apps" in text and "apps: 1 app(s)" in text,
          "a one-app MFA policy does not count")
    # All four client types listed one by one reads as no condition (seen live).
    four = [policy("MFA everyone", controls=["mfa"], users={"includeUsers": ["All"]},
                   clients=("exchangeActiveSync", "browser", "mobileAppsAndDesktopClients", "other"))]
    calls, lines = [], []
    wf.conditional_access(make_run(four, calls), lines.append, lambda: False, {}, base)
    text = "".join(lines)
    check("only when" not in text and "requires MFA for everyone" not in text,
          "four client types = all clients (no 'only when', counts as MFA for everyone)")

    calls, lines = [], []
    res = wf.conditional_access(make_run([], calls, fail=True), lines.append, lambda: False, {}, base)
    text = "".join(lines)
    check(not res["ok"] and "403" in res["error"] and "Policy.Read.All" in text,
          "a Graph error stops with the permission hint")

    calls, lines = [], []
    res = wf.conditional_access(make_run(GOOD, calls), lines.append, lambda: True, {}, base)
    check(not res["ok"], "Stop -> not OK")
finally:
    shutil.rmtree(base, ignore_errors=True)

task = next((t for t in cat.TASKS["Security"] if t["name"] == "Conditional Access review"), None)
check(task is not None and task["workflow"] == "conditional_access" and not task["destructive"]
      and task["fields"] == [], "catalog: a read-only workflow in Security with no boxes")
check("read-only" in cat.WORKFLOW_PLANS.get("conditional_access", ""), "catalog: its plan says read-only")
for front in ("M365GUI.py", "m365_web.py"):
    with open(os.path.join(os.path.dirname(HERE), front), encoding="utf-8") as fh:
        check("conditional_access(" in fh.read(), front + " runs the workflow")
print("FAILURES:", len(fails))
