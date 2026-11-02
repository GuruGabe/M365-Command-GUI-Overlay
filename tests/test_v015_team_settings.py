# test_v015_team_settings.py - v0.15 (10-30-2026): the read-only 'Team
# settings review' workflow (m365_workflows.team_settings) against a fake
# m365 that answers 'teams team list' / 'teams team get --id' in the shape
# the real tenant did (live run 10-30-2026). Checks: only reads, one Team by
# name or id, every Team when blank, the plain-words lines, the notes (no
# owner, public, guests, guest channel rights - NOT the default 'members can
# delete channels'), a Team that cannot be read, Stop, and the CSV.
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

ID_A = "042115b3-bd46-44e4-aa52-cb5b7d94336b"
ID_B = "f38e4b84-50da-403e-9085-c7f547d9f83a"
ID_C = "570c6ca2-94ad-4a75-9102-5979a2d0ca00"

def team(ident, name, owners=1, guests=0, visibility="private", guest_channels=False,
         archived=False):
    return {"id": ident, "displayName": name, "visibility": visibility, "isArchived": archived,
            "summary": {"ownersCount": owners, "membersCount": 2, "guestsCount": guests},
            "guestSettings": {"allowCreateUpdateChannels": guest_channels, "allowDeleteChannels": False},
            "memberSettings": {"allowAddRemoveApps": True, "allowCreatePrivateChannels": True,
                               "allowCreateUpdateChannels": True,
                               "allowCreateUpdateRemoveConnectors": True,
                               "allowCreateUpdateRemoveTabs": True, "allowDeleteChannels": True},
            "messagingSettings": {"allowChannelMentions": True, "allowOwnerDeleteMessages": True,
                                  "allowTeamMentions": True, "allowUserDeleteMessages": True,
                                  "allowUserEditMessages": True},
            "funSettings": {"allowCustomMemes": True, "allowGiphy": True,
                            "allowStickersAndMemes": True, "giphyContentRating": "moderate"},
            "discoverySettings": {"showInTeamsSearchAndSuggestions": False},
            "tagSettings": None}

TEAMS = {ID_A: team(ID_A, "Testing", owners=0),
         ID_B: team(ID_B, "Science Dept"),
         ID_C: team(ID_C, "Band Boosters", guests=2, visibility="public", guest_channels=True)}

def make_run(calls, broken=(), stop_after=None, flag=None):
    def run(argv):
        calls.append(argv)
        assert argv[0] == "teams" and argv[-2:] == ["--output", "json"], argv
        if argv[1:3] == ["team", "list"]:
            return 0, json.dumps([{"id": t["id"], "displayName": t["displayName"]}
                                  for t in TEAMS.values()])
        assert argv[1:4] == ["team", "get", "--id"], argv
        if stop_after is not None and len([c for c in calls if c[2] == "get"]) >= stop_after:
            flag["stop"] = True
        if argv[4] in broken:
            return 1, "Error: Forbidden"
        return 0, json.dumps(TEAMS[argv[4]])
    return run

def go(values, **kw):
    calls, lines = [], []
    tmp = tempfile.mkdtemp(prefix="m365teams_")
    flag = kw.pop("flag", {"stop": False})
    r = wf.team_settings(make_run(calls, flag=flag, **kw), lines.append,
                         lambda: flag["stop"], values, tmp)
    return r, calls, "".join(lines), tmp

# ---- every Team (blank box) ----------------------------------------------------
r, calls, text, tmp = go({"team": ""})
check(r["ok"] and r["teams"] == 3, "blank box: every Team is read (%s)" % r)
check(all(c[2] in ("list", "get") for c in calls), "only 'list' and 'get' were run")
check(len([c for c in calls if c[2] == "get"]) == 3, "one 'teams team get --id' per Team")
check(text.index("Band Boosters") < text.index("Science Dept") < text.index("Testing  (id"),
      "Teams are shown sorted by name")
check("Who can find and join it (visibility)" in text and "Giphy content rating" in text
      and "moderate" in text and "Members can delete channels" in text,
      "settings are shown in plain words")
check("Testing: no owner" in text, "note: a Team with no owner")
check("Band Boosters: public" in text and "Band Boosters: 2 guest(s)" in text
      and "Band Boosters: guests can create and edit channels" in text,
      "notes: public, guests, guest channel rights")
check("members can delete channels" not in text,
      "the default 'members can delete channels' is shown but not pointed out")
check("Science Dept:" not in text.split("Worth a second look:")[1],
      "a Team with nothing unusual gets no note")
found = [os.path.join(d, f) for d, _s, fs in os.walk(tmp) for f in fs if f == "team-settings.csv"]
check(len(found) == 1 and "TeamSettings_all-teams_" in found[0], "team-settings.csv saved (all-teams)")
rows = list(csv.DictReader(open(found[0], encoding="utf-8")))
check(rows and set(rows[0]) == {"team", "id", "area", "setting", "value"}
      and any(r["setting"] == "Owners" and r["value"] == "0" for r in rows),
      "the CSV has team / id / area / setting / value rows (%d)" % len(rows))
shutil.rmtree(tmp, ignore_errors=True)

# ---- one Team by name (any case) and by id -------------------------------------
r, calls, text, tmp = go({"team": "  science DEPT "})
check(r["ok"] and r["teams"] == 1 and [c[4] for c in calls if c[2] == "get"] == [ID_B],
      "a name finds that one Team (any case, spaces trimmed)")
check("Nothing to point out" in text, "a Team with nothing unusual: 'Nothing to point out'")
shutil.rmtree(tmp, ignore_errors=True)
r, calls, text, tmp = go({"team": ID_C.upper()})
check(r["ok"] and [c[4] for c in calls if c[2] == "get"] == [ID_C], "an id finds that one Team")
shutil.rmtree(tmp, ignore_errors=True)
r, calls, text, tmp = go({"team": "“Testing”"})
check(r["ok"] and [c[4] for c in calls if c[2] == "get"] == [ID_A],
      "pasted curly quotes around the name are removed")
shutil.rmtree(tmp, ignore_errors=True)

# ---- no such Team / list fails / one Team cannot be read / Stop ------------------
r, calls, text, tmp = go({"team": "Nope"})
check(not r["ok"] and "No Team is called 'Nope'" in r["error"]
      and not [c for c in calls if c[2] == "get"], "an unknown name stops before reading anything")
shutil.rmtree(tmp, ignore_errors=True)

def failing_list(argv):
    return 1, "Error: Access denied"
lines = []
r = wf.team_settings(failing_list, lines.append, lambda: False, {"team": ""}, tempfile.mkdtemp())
check(not r["ok"] and "Could not list the Teams: Error: Access denied" in r["error"],
      "a failed Team list is reported")

r, calls, text, tmp = go({"team": ""}, broken=(ID_B,))
check(not r["ok"] and r["teams"] == 2 and "COULD NOT READ - Error: Forbidden" in text,
      "a Team that cannot be read is reported and the others still are")
found = [os.path.join(d, f) for d, _s, fs in os.walk(tmp) for f in fs if f == "team-settings.csv"]
check(found and "COULD NOT READ" in open(found[0], encoding="utf-8").read(),
      "the CSV records the Team that could not be read")
shutil.rmtree(tmp, ignore_errors=True)

flag = {"stop": False}
r, calls, text, tmp = go({"team": ""}, stop_after=1, flag=flag)
check(not r["ok"] and len([c for c in calls if c[2] == "get"]) == 1 and "[Stopped after 1 of 3" in text,
      "Stop ends the run after the current Team")
shutil.rmtree(tmp, ignore_errors=True)

# ---- catalog and wiring -------------------------------------------------------------
task = next((t for t in cat.TASKS["Teams / M365 Groups"] if t["name"] == "Team settings review"), None)
check(task is not None and task["workflow"] == "team_settings" and not task["destructive"],
      "catalog: a read-only workflow in Teams / M365 Groups")
check(task and len(task["fields"]) == 1 and task["fields"][0]["key"] == "team"
      and not task["fields"][0]["required"], "catalog: one optional Team box (blank = every Team)")
check(task and cat.picker_kind("Teams / M365 Groups", task, task["fields"][0]) == "group",
      "the Team box has the Pick... list")
check("read-only" in cat.WORKFLOW_PLANS.get("team_settings", ""), "the workflow has its plan text")
for front in ("M365GUI.py", "m365_web.py"):
    with open(os.path.join(os.path.dirname(HERE), front), encoding="utf-8") as fh:
        check("team_settings(" in fh.read(), front + " runs the workflow")
check(task and task["desc"].isascii(), "ASCII description")
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
