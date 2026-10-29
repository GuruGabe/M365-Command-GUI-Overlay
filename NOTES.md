# M365GUI - Development Notes

## Status

- tkinter desktop app (`M365GUI.py`) plus a browser version (`m365_web.py`),
  Python standard library only. The task catalog (`m365_catalog.py`), the
  guided workflows (`m365_workflows.py`) and the setup facts
  (`m365_setup.py`) are shared by both.
- 139 tasks in 13 sections (counted 10-28-2026, v0.13), plus a Custom-command
  mode and five guided workflows: staff hand-off, remove all guest users,
  compromised account response, copy a user's OneDrive files to another
  user, and who holds admin roles (read-only).
- Search, Favorites and Recent, Pick... lists, Save results to CSV / JSON,
  Run for each CSV row, a Connection list (v0.11), Settings > Set up the
  CLI and Settings > Dark mode (v0.12).
- Drives the [CLI for Microsoft 365](https://pnp.github.io/cli-microsoft365/)
  (`m365`). Commands checked against CLI v11.11 with `m365 <command> --help`.
- Builds for Windows (`Build-EXE.bat`), macOS (.dmg) and Linux (.deb / .rpm)
  - see the README's download table.
- Shares its engine and design with
  [GAMGUI](https://github.com/GuruGabe/GAM-GUI-Overlay).

## Roadmap / ideas

- More Exchange Online tasks. Done in v0.12 (checked with `--help full` on
  CLI v11.11): automatic replies, a user's calendars / events / mail folder.
  The CLI's `outlook` commands have no mail-forwarding setting.
- Admin roles: done in v0.13 (Who holds admin roles). Still open: roles
  that are only ELIGIBLE (PIM) need Entra ID P2 to read.
- The CLI (v11.11) has no Intune commands. Guest invitations exist (Users >
  Invite a guest).
- More Teams and SharePoint coverage.
- Live tests of the tasks that change things and of the guided workflows,
  on throwaway accounts.

## Known limitations

- M365GUI runs the operator's own signed-in `m365` and has no permission model
  of its own: whoever can open it can run whatever their `m365` is allowed to do.
- Some tasks need extra Microsoft Graph permissions and/or an Entra ID P1/P2
  tenant (e.g. sign-in activity needs AuditLog.Read.All + premium). The task
  descriptions note this where it applies.
- The CLI sometimes reports errors as `Error: [object Object]`; re-run with
  `--debug` to see the real message.
- The command preview is editable by design - treat it like a terminal.

## Contributing

`M365GUI.py` uses a data-driven task catalog (the `TASKS` dictionary), so adding
a task is a few lines and needs no new code. Please keep it dependency-free
(standard library only), and verify any new command with `m365 <command> --help`
before adding it.

## Session log
- 10-28-2026: v0.12 published by the 5 PM daily release (Release-M365GUI.ps1).

- 10-28-2026 (v0.13): Who holds admin roles (guided, read-only;
  m365_workflows.admin_roles). 'entra pim role assignment list' /
  'eligibility list' need Entra ID P2 ("The tenant needs to have Microsoft
  Entra ID P2 or Microsoft Entra ID Governance license"), so it reads Graph
  through 'm365 request': roleAssignments?$expand=principal (a second
  $expand -> 400; 'directoryRoles?$expand=members' -> 500), paged by
  @odata.nextLink (request does not page), then roleDefinitions; a few
  hidden built-in roles are missing from that list and are read by id.
  Notes: Global Administrators counted as PEOPLE (apps apart) - >4 or <2;
  10+ roles on one account; blocked account with a role. CSV in
  Records\AdminRoles_tenant_<stamp>. Built in a copy while the 0.12 release
  was pending, live run read-only OK (101 assignments, 5 calls, every role
  named). Tests: tests\test_v013_admin_roles.py (fake Graph: 2 pages, a
  hidden role, apps on/off, 403, Stop).

- 10-27-2026 (v0.12): Settings > Set up the CLI (as GAMGUI 2.97 Set up GAM),
  m365_setup.py: 1 Node.js (winget install --id OpenJS.NodeJS.LTS --exact
  --source winget in its own console, NO --accept-*-agreements - the person
  accepts the license there; download page off Windows), 2 npm install -g
  @pnp/cli-microsoft365 streamed (EACCES / network hints), 3 'm365 setup'
  (wizard, own console; app ID = 'cli config get --key clientId' GUID or
  CLIMICROSOFT365_ENTRAAPPID), 4 'm365 login --authType browser|deviceCode'
  (own console; never password). Auto-open once/session when account_text
  says m365 not found / Node.js missing / nobody; after a failed task whose
  output matches "Log in to Microsoft 365 first" / "appId is required" /
  AADSTS expired-or-MFA codes (asked once/session). New Settings menu.
  Tests: tests\test_v012_setup.py (passed once Python was back).
  Browser version (same day): Set up the CLI... header button + <dialog>;
  GET /api/setup, POST /api/setup/cli (npm job, find_m365 again), POST
  /api/setup/login (deviceCode login job - code + URL in the output box);
  Node.js / 'm365 setup' / browser login shown as commands to paste into a
  terminal on the server. /api/status 'setup' = needs_window; /api/job
  'setup' = failed job matching setup_can_fix. Tests:
  tests\test_v012_web_setup.py.
  Also: Settings > Dark mode (GAMGUI's palettes and clam theme; option
  database for later Listbox / Text / Toplevel; light start leaves the
  native colors alone - only repainted light after a dark switch, so macOS
  dark appearance is not overridden). Saved as dark_mode in m365gui.ini.
  Tests: tests\test_v012_dark.py. NOTES Status/Roadmap refreshed (126
  tasks, 13 sections, 4 workflows; builds for all three OSes).
  Six Outlook tasks (calendar list, event list with --properties, message
  list by folderName, mailbox settings set autoReply alwaysEnabled /
  scheduled / disabled) -> 132 tasks. Options read from 'm365 outlook ...
  --help full' (v11.11); not live-tested yet (the auto-reply ones change a
  mailbox - throwaway user needed). Tests: tests\test_v012_outlook.py.
  0.12 did not go out on 10-27 (the release run could not start its
  tests); the release script now finds Python itself. Planned for the
  10-28 release.
  10-28: six read-only tasks added to 0.12 (Entra policies by type, apps in
  a Team, Teams app catalog, mailbox quota counts, OneDrive storage total,
  organization details) -> 138 tasks. Found from a list of CLI commands no
  task uses yet (170 in teams/entra/outlook/todo/onedrive). All run LIVE
  read-only and OK; 'entra policy list' with no --type fails without Entra
  ID P2 (it also reads roleManagement), so the type is required.
  Tests: tests\test_v012_readonly_more.py.

- 10-26-2026 (v0.11): Connection list (GAMGUI's Section dropdown) in the
  desktop top bar and the browser header, from 'connection list --output
  json' (name, connectedAs, authType, active - live shape checked 10-26; one
  connection on the test PC). Switch = 'connection use --name' (refused while
  a task/workflow runs; the web version only accepts a name the CLI listed);
  afterwards status + list are read again and the group Pick... cache is
  dropped (changes_connection: login, logout, connection use/set/remove).
  Diagnostics +6 tasks (list/switch/rename/remove, sign in deviceCode|browser
  with optional --connectionName, sign out). Docs check covers them. NOT
  live-tested: switching between two real connections, sign in, sign out
  (only one connection exists, and signing in is the admin's own step).
- 10-26-2026: v0.10 published by the 5 PM daily release (Release-M365GUI.ps1).

- 10-26-2026 (v0.10): first LIVE run of every read-only, no-typed-input task
  against the tenant (44): 33 OK. Fixed: report commands accept only
  --output csv|json (the docs list --output as global, without the limit);
  --withSiteUrl -> "Access denied" on private groups the admin is not a
  member of (dropped). Sensitivity labels: "resource could not be found" =
  none/not licensed (described). Tasks that need typed input, change data or
  run workflows are still not live-tested (need throwaway test accounts).

- 10-23-2026 (v0.9): m365_web.py browser version (127.0.0.1, session token
  header, JSON-only POSTs, Host allow-list + M365WEB_ALLOWED_HOSTS; the server
  rebuilds commands from form values and refuses unconfirmed destructive
  tasks; jobs polled via /api/job; workflow questions via /api/job/answer;
  the secret is handed over once then forgotten; uploads only under
  DATA_DIR/Uploads, deleted after 7 days). Clicked through in the built-in
  browser with a stand-in m365. remove_all_guests moved to m365_workflows.
  SECURITY: passwords were written to the session log and the bulk record -
  now masked (m365_catalog.redact_secrets). Tests: test_v09_web.py (28),
  test_v09_redact.py.

- 10-23-2026 (v0.8): guided Staff hand-off (record -> ask -> block -> sign out
  -> OneDrive copy (reuses transfer_onedrive) -> auto-reply -> groups ->
  licenses) and Compromised account response (block, sign out, random
  password via secrets, evidence + NEXT-STEPS.txt) in m365_workflows.py;
  records in DATA_DIR/Records (gitignored). Auto-reply for ANOTHER user needs
  rights to that mailbox (delegated Graph) - an optional step that reports
  its result. Found by the window test: the password window used a local
  StringVar, garbage-collected on return -> an EMPTY box; the text is now
  inserted directly. tests\m365docs.py is the shared docs reader.

- 10-23-2026 (v0.7): catalog 35 -> 118 tasks in 13 sections (Users, Groups,
  Teams/M365 groups + channels, SharePoint admin, OneDrive list, Roles and admin
  units, Service health and security, Outlook, Planner, usage Reports). Every
  command task is checked by tests\test_catalog_docs.py against the docs npm
  installs with the CLI (docs/docs/cmd/**.mdx): page exists, options
  documented, required options present, dropdown values allowed. A copy of
  the test with 3 planted mistakes fails all 3 (checked). Docs naming:
  <group>/<sub>/<sub>-<rest>.mdx, <group>/<rest>.mdx or <group>/<group>-<rest>.mdx;
  some pages list values as one code span (`a,b`, `asc|desc`).

- 10-23-2026 (v0.6): split into M365GUI.py (window), m365_catalog.py (tasks,
  command builder, search/pickers/bulk/script helpers) and m365_workflows.py
  (OneDrive copy), like GAMGUI. Added search, Favorites/Recent
  (m365gui_tasklists.json), "Signed in as", Pick... lists (users searched with
  the CLI's startsWith filters; groups loaded once), Save results to CSV/JSON,
  Run for each CSV row (M365GUI loops; the CLI has no CSV loop), Save as
  script (.ps1/.sh; Windows PowerShell 5.1 drops embedded double quotes when
  starting a program - the .ps1 refuses such values there), look-alike
  character cleaning. Fixed: the form was redrawn (typed values lost) when
  Recent re-selected the task after a run; dropdowns ignored their default.
  Tests: tests\test_v06_*.py (hidden windows, fake m365).

- 10-23-2026 (v0.5): installers and in-app updates ported from GAMGUI -
  .github/workflows/build-installers.yml (7 files per release),
  installer/m365gui.iss (its own AppId), build-macos-dmg.sh,
  build-linux-packages.sh, updatem365gui.ps1 (refuses a file without a
  published SHA-256), m365_update.py; Help menu (update check, What's new,
  About); settings/logs in a per-user folder for installed copies; m365 and
  node found in the usual npm/Node folders on macOS/Linux. Releases are made
  by a release script kept outside the repo (tests, scan, build, SHA-256
  lines, smoke test). Test: tests\test_v05_installers.py.

- 10-22-2026 (v0.4): OneDrive section - 'Copy a user's OneDrive files to
  another user' (spo folder/file copy into a new folder, temporary site
  collection admin via spo site admin add/remove --asAdmin, file counts
  before/after, CSV record) and 'Find a user's OneDrive address' (Graph
  mySite). Commands now start node + the CLI script directly (cmd.exe ran
  anything after an '&' in a value). Tests: tests\test_onedrive_transfer.py,
  tests\test_invocation.py. Not yet run against a real tenant: with the CLI
  signed in through the Azure CLI app, every SharePoint call returns 401
  invalid_request ('m365 setup' with the CLI's own Entra app is the fix).
