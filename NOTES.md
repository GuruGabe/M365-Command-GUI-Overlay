# M365GUI - Development Notes

## Status

- tkinter desktop app (`M365GUI.py`) plus a browser version (`m365_web.py`),
  Python standard library only. The task catalog (`m365_catalog.py`), the
  guided workflows (`m365_workflows.py`) and the setup facts
  (`m365_setup.py`) are shared by both.
- 194 tasks in 14 sections (counted 11-02-2026, v0.16), plus a Custom-command
  mode and ten guided workflows: staff hand-off, remove all guest users,
  compromised account response, copy a user's OneDrive files to another
  user, move a user's OneDrive files to a Team or SharePoint site, who holds
  admin roles, files shared by link, Conditional Access review, Team
  settings review and the Power Automate flows and Power Apps review (the
  last five read-only).
- Search, Favorites and Recent, Pick... lists, Save results to CSV / JSON,
  Run for each CSV row, a Connection list (v0.11), Settings > Set up the
  CLI and Settings > Dark mode (v0.12).
- Drives the [CLI for Microsoft 365](https://pnp.github.io/cli-microsoft365/)
  (`m365`). Commands checked against CLI v11.11 with `m365 <command> --help`,
  and against CLI 12.0.0's command list (v0.17: 231 uses, 0 problems).
- Builds for Windows (`Build-EXE.bat`), macOS (.dmg) and Linux (.deb / .rpm)
  - see the README's download table.
- Shares its engine and design with
  [GAMGUI](https://github.com/GuruGabe/GAM-GUI-Overlay).

## Roadmap / ideas

- More Exchange Online tasks. Done in v0.12 (checked with `--help full` on
  CLI v11.11): automatic replies, a user's calendars / events / mail folder.
  The CLI's `outlook` commands have no mail-forwarding setting.
- Admin roles: done in v0.13 (Who holds admin roles); v0.14 adds the MFA
  registration check. Still open: roles that are only ELIGIBLE (PIM) need
  Entra ID P2 to read.
- The CLI (v11.11) has no Intune commands. Guest invitations exist (Users >
  Invite a guest).
- More Teams and SharePoint coverage. v0.14 added SharePoint groups and
  members, lists and libraries, files, sharing links / sharing details and
  hub sites; v0.15 a site's owners / members / visitors, people added to a
  site, permission levels, version history settings, earlier versions of a
  file, folder sharing links, pages, navigation links, list items, the
  SharePoint API permissions and a Team settings review; v0.16 content
  types. Still open: page sections / web parts (spo page section / control
  list answered [] on a new team site's Home.aspx and a classic page is
  refused - add when there is a real modern page to check the columns).
- Power Platform: v0.16 environments + a read-only flows and apps review.
  v0.16 also: a flow's owners, run history, deleted flows, Power App
  permissions. Still open: turn a flow off / on as an admin (flow disable /
  enable --asAdmin) - needs a throwaway flow to live-test. CLI 11.11 + 12
  beta: flow owner / run / export / remove / recyclebinitem restore check
  --flowName with zod z.uuid() (RFC version digit 1-8) and refuse real
  flow ids like xxxxxxxx-xxxx-b028-... ('Invalid UUID'); flow get does not.
  Already reported upstream: pnp/cli-microsoft365#7678 (opened 10-31-2026,
  open - replace z.uuid() with z.guid()); drop the task notes when fixed.
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
- CLI 12 (v0.17): everyone signs in again after updating (its sign-in moved
  to the computer's credential store); a team given by name needs
  Team.ReadBasic.All; some real flow ids still fail with 'Invalid UUID'
  (pnp/cli-microsoft365#7678).

## Contributing

`M365GUI.py` uses a data-driven task catalog (the `TASKS` dictionary), so adding
a task is a few lines and needs no new code. Please keep it dependency-free
(standard library only), and verify any new command with `m365 <command> --help`
before adding it.

## Session log
- 11-06-2026 (v0.17): CLI for Microsoft 365 12.0.0 became npm's 'latest' on
  11-04-2026. Its package (integrity checked, read only - not run) was
  compared with every command M365GUI uses (231, 0 problems) and its v12
  upgrade guidance read: AUTH-1 (sign in again; until then 'm365 status'
  waits for an interactive sign-in - Auth.js ensureAccessToken falls back
  to browser / device code when no cached account), TEAMS-1, GEN-1 (no
  M365GUI task uses --recycle / --skipRecycleBin; 'spo site remove' keeps
  its recycle-bin default), GEN-2..4 (not used / text output only). 12.0
  still validates flow ids with z.uuid() (#7678) and dropped the
  TotalUserCount check in 'spo externaluser list'. Not live-tested with CLI
  12 yet. Also: on a Windows PC whose Node.js folder had disappeared, 'node'
  was nvm's stand-in, answering 'No active Node.js version is configured'
  (exit 1, stderr only) - M365GUI now recognizes it (status, Set up the CLI,
  browser version). 2 new test files.
- 11-05-2026: v0.16 published by the 5 PM daily release (Release-M365GUI.ps1).
- 11-02-2026 (v0.16): second live run of CHANGE tasks (throwaway new user
  made and PERMANENTLY deleted; throwaway Teams 'M365GUI Live Teams Test
  1102' and 'M365GUI Live Teamify Test 1102' made and deleted - they sit in
  the M365 group recycle bin for 30 days; one more from a stopped first
  run is there too). OK: user create / block / unblock /
  session revoke / remove / restore / recyclebinitem remove; team add
  (provisioning took ~7 min), channel add / remove, archive / unarchive,
  team remove, m365group teamify. FIXED: entra group add --type
  microsoft365 needs --visibility (CLI refine; docs wrong) -> 'vis' box;
  m365group recyclebinitem restore by name refused for two deleted groups
  -> optional --id. FOUND: outlook mailbox settings get/set for another
  user need APP-ONLY auth (CLI check), outlook calendar/event list for
  another user -> 'Access is denied', message list needs Full Access ->
  texts + staff hand-off hint. teams team archive
  --shouldSetSpoSiteReadOnlyForMembers -> BadRequest 'team's site url is
  not available' (new Team, SharePoint site not ready) -> text. SECURITY:
  'm365 ... --debug' prints 'authorization: Bearer <token>' and more JWTs
  (6 in one request) - redact_secrets now masks Bearer tokens and bare JWTs
  (checked against real --debug output: 6 -> 0). GAM's own debug output
  already masks its tokens ('Bearer *****') - nothing needed in GAMGUI.
  Not run: send email, invite guest, empty the user recycle bin (every
  deleted user), give an admin role, connection tasks (the release uses
  the sign-in). Tests: test_v016_live_changes.py, test_v016_redact_tokens.py.
  SharePoint (throwaway /sites/m365gui-live-* sites, left in Deleted sites
  for 93 days): comm + team site add, site admin add / remove, group
  member add, lockState ReadOnly / Unlock, sharingCapability Disabled /
  ExistingExternalUserSharingOnly (read back 0 / 3), recyclebinitem restore
  --allPrimary, site remove, tenant recyclebinitem restore - all OK. FIXED:
  lockState NoAdditions refused by SharePoint Online (CLI docs list it) ->
  removed. A new team site's 'spo site remove' said 'Site not found' for
  ~30 s, then worked. Note for tests: CLI 11 'spo file remove' without
  --recycle deletes PERMANENTLY (12.0 flips it to --permanent).
  + 'Remove a user from an administrative unit' (entra administrativeunit
  member remove --administrativeUnitName --userName --force). Live on a
  throwaway unit made and deleted with 'entra administrativeunit add /
  remove': add / member list / remove OK; the member list lags ~15 s both
  ways (first check after add: not listed; after remove: still listed).
  Task count 175.
  + 5 read-only tasks run live: Owners of a flow (flow owner list
  --asAdmin -> roleName/id/type), Run history of a flow (flow run list
  [--status]; no runs in this tenant -> blank), Deleted flows (flow
  recyclebinitem list -> blank), Who can use a Power App (pa app permission
  list; no apps here - docs only), Content types on a site (spo contenttype
  list [--category], OK on 2 sites). 2 of 6 real flow ids -> 'flowName:
  Invalid UUID' (zod strict). Task count 180.
  + 7 organization-wide read-only tasks run live: spo app list, spo tenant
  applicationcustomizer list, spo site apppermission list (all empty
  here), pp tenant settings list with a --query of plain names (the
  output is sorted A-Z), pp
  copilot list --asAdmin (1 agent), pp gateway list, entra agent list
  (empty). Task count 187.
  + 7 more read-only tasks run live: planner tenant settings list (OK),
  spo tenant commandset list, spo site appcatalog list, spo homesite list,
  spo orgnewssite list, pa connector list (NON-admin API - only the
  caller's connectors), pp managementapp list (all empty here). Skipped:
  purview sensitivitylabel policysettings list (delegated = the signed-in
  person's own policy only). Task count 194.
- 11-02-2026 (v0.16): new section Power Platform. 'Power Platform
  environments' (flow environment list --query ... --output text) and the
  guided, read-only 'Power Automate flows and Power Apps review'
  (m365_workflows.power_platform): flow environment list -> per
  environment flow list --asAdmin, flow get --asAdmin (trigger / actions /
  connectionReferences; skipped with 'List the flows only'), pa app list
  --asAdmin -> each creator / owner looked up ONCE as Graph
  directoryObjects/<id> (a person, an app = servicePrincipal; 404 =
  deleted; userType DataverseSystemUser = system account, not looked up).
  Notes: guest, deleted creator (still ON), outside connectors, HTTP
  actions, Request / Request-Http trigger, flowSuspensionReason. Live,
  read-only: 1 environment, 6 flows (Dynamics / Dataverse system flows),
  0 apps, nothing pointed out, about 60 s. The app fields (owner,
  sharedUsersCount, connectionReferences) follow Microsoft's admin API -
  the live tenant had no apps to check them against. Tests:
  test_v016_power_platform.py, test_v016_web_power_platform.py.
- 11-02-2026 (v0.15): usage location + Assign / Remove license(s) live OK
  (free Power BI SKU added and removed, A1 kept). The test user's OneDrive
  was NEVER created (3 Request-SPOPersonalSite runs, 10-30 to 11-02; a 90
  minute watch ended 09:46 11-02) -> the OneDrive move is NOT live-tested.
  Gabe: ship 0.15 with it anyway (may work for others); the task, release
  notes and CHANGELOG say it has not run against a real tenant. Still not
  live-run: the move, block / unblock, delete / restore user.
- 11-02-2026 (v0.15): FIRST live run of the CHANGE tasks (throwaway user
  m365gui.movetest@<tenant>.onmicrosoft.com, the Team 'M365GUI Move Test',
  throwaway security groups made and deleted): rename user, job fields,
  set / remove manager, password check, reset password, create / rename /
  delete group, add member, make owner, Team add / role / remove - all OK as
  built. 'Remove member from group' FAILED for an owner who was not a member
  ('entra group member remove' without --role removes both roles and
  errors on the missing one) -> + --suppressNotFound (CLI 11.11 and 12.0);
  live: owner-only and member-only both removed. Entra refuses to remove a
  group's LAST owner - the description says so. Then usage location (set
  to US), Assign / Remove license(s) (the free Power BI SKU; the A1 license
  kept) - OK. Not run yet: block / unblock, delete / restore user (they wait
  for the OneDrive move test). Tests: test_v015_live_changes.py.
- 11-02-2026 (v0.15): CLI 12.0 is in beta (npm tag next, 12.0.0-beta.235caf5).
  Its release notes list 10 breaking changes; _scratch\m365_cli_compat.py
  compared every command and option M365GUI uses (catalog templates and the
  lists in m365_workflows.py - 206 uses in 0.15, 179 in 0.14) with the
  beta's allCommandsFull.json (package downloaded, NOT installed): nothing
  missing (the checker does catch a removed command / option). M365GUI uses
  none of --recycle / --skipRecycleBin / 'spo file add' / 'spo listitem get
  --properties'; 'spo navigation node list' (new output shape) is a text
  task. #7674 (spo externaluser list) closed 10-31, fixed in 12.0 - the
  task's description says so. Tests: test_v015_sharepoint_more.py.
- 10-30-2026 (v0.15): + Team settings review (m365_workflows.team_settings,
  read-only, Teams / M365 Groups): one Team by name or id, or every Team
  when blank. 'teams team get --id' answers guestSettings, memberSettings,
  messagingSettings, funSettings, discoverySettings, visibility,
  isArchived and summary (owners / members / guests counts) in ONE call,
  so the four 'teams <x>settings list' commands (--teamId only) are not
  needed. Notes: no owner (unless archived), public, guests, guests who
  can create / edit / delete channels. 'Members can delete channels' is
  ON by default (every Team on the live run), so it is shown but not
  pointed out. Run live (read-only) on every Team, one by name and an
  unknown name. + API permissions approved for SharePoint (spo
  serviceprincipal grant list - its own columns are ids, so --query puts
  Scope first) and API permission requests waiting for approval (spo
  serviceprincipal permissionrequest list), both run live. Skipped (empty
  on the test tenant, so their columns could not be checked): home sites,
  organization news sites, org assets libraries, site designs / scripts,
  tenant app catalog apps, a site's app permissions. Tests:
  tests\test_v015_team_settings.py, test_v015_web_team_settings.py,
  test_v015_api_access.py.
- 10-30-2026 (v0.15): six read-only SharePoint tasks, each run live
  (read-only): spo site membership list (works on any site), spo user
  list / roledefinition list / site versionpolicy get (answer
  'Attempted to perform an unauthorized operation' on a site the
  signed-in admin cannot open), spo file version list (an empty list =
  only the current version), spo folder sharinglink list. Found a CLI
  v11.11 bug: 'spo externaluser list' prints people only when
  SharePoint's TotalUserCount > 0, and SharePoint sent people with a
  count of 0 - so nothing at all was shown. The existing task now says
  so and points to 'List guest users'. The Teams guest / member /
  messaging / fun settings commands were skipped: 'Get a Team's
  settings' (teams team get) already shows them (see Team settings
  review, below). Tests:
  tests\test_v015_sharepoint_more.py.
- 10-30-2026 (v0.15): + Pages on a site (spo page list - its text output
  shows only Title, so a JMESPath --query picks Title, FileName, Url,
  Modified), Navigation links on a site (QuickLaunch / TopNavigationBar)
  and Items in a list (optional --fields). All run live, read-only, on
  the root site exactly as build_command makes them. The CLI bug was
  reported as pnp/cli-microsoft365#7674 (with the maintainer's OK); drop
  the warning from the external-users task once it is fixed.
- 10-30-2026 (v0.15): + three Office activation reports (tenant report
  office365activationsuserdetail / office365activationsusercounts /
  office365activationcounts - NO --period, run live: per person, assigned
  vs activated, by device type). test_v010_live.py now expects 14 usage
  reports. Tests: tests\test_v015_office_activations.py.
- 10-29-2026 (v0.15): Move a user's OneDrive files to a Team or SharePoint
  site (m365_workflows.move_to_site), asked for by the maintainer (move,
  Team picker OR any site + library). Read-only checks first: Team -> site
  = 'spo site list' GroupId '/Guid(<id>)/' equals the Team id (Graph
  groups/{id}/sites/root answered 403 and 'm365group get --withSiteUrl'
  'Access denied'); library root via 'spo list list --properties
  Title,RootFolder/ServerRelativeUrl'; 'spo listitem list --fields
  Id,FileRef,FSObjType,HasUniqueRoleAssignments,File/Length' (6,455 items
  in 36 s; File_x0020_Size does NOT exist there; FSObjType '0'/'1');
  'spo listitem get --withPermissions' gives RoleAssignments (Member
  Title / LoginName, RoleDefinitionBindings Name) for files AND folders,
  where folder sharing-link lists were empty. 'spo folder move' allows
  only fail|rename; a OneDrive is on the -my host, so the target is an
  ABSOLUTE URL. The move itself still needs its live test on throwaway
  accounts. Tests: tests\test_v015_move_to_site.py.
- 11-02-2026: v0.15 published by the 5 PM daily release (Release-M365GUI.ps1).
- 10-30-2026: v0.14 published by the 5 PM daily release (Release-M365GUI.ps1).
- 10-29-2026: v0.13 published by the 5 PM daily release (Release-M365GUI.ps1).
- 10-28-2026: v0.12 published by the 5 PM daily release (Release-M365GUI.ps1).

- 10-29-2026 (v0.14): nine read-only tasks (SharePoint groups / members,
  lists and libraries, files in a folder with and without subfolders,
  sharing links, sharing details, hub sites; a person's Teams apps). Options
  from '--help' / '--help full' (v11.11); each command run live, read-only.
  Found live: 'spo group list --associatedGroupsOnly' answers ONE object
  (AssociatedOwnerGroup / MemberGroup / VisitorGroup), not a list; a
  recursive 'spo file list' includes the library's Forms/*.aspx pages, and
  'spo file sharinglink list' / 'sharinginfo get' on such a page fail
  ("Resource not found for the segment ..." / "Cannot read properties of
  undefined (reading 'Id')") - on a real document both work, by
  server-relative --fileUrl or by --fileId; 'sharinginfo get' with
  --output text or csv prints NOTHING (JSON only); a recursive list of a big
  OneDrive took over 5 minutes. Tests: tests\test_v014_sharepoint_more.py.
  Also (v0.14): Files shared by link in a folder (guided, read-only;
  m365_workflows.shared_links): 'spo file list' (--recursive) then one
  'spo file sharinglink list --fileId <UniqueId>' per file (--scope
  anonymous for anyone links), Forms pages skipped, link webUrl never
  shown or saved, 2,000-file guard. Live read-only run OK (a team site and
  a OneDrive folder) but they had NO sharing links, so the link parsing is
  checked only against the CLI's documented JSON (--help response). Tests:
  tests\test_v014_shared_links.py, tests\test_v014_web_shared_links.py.
  Also (v0.14): six read-only Service health and security tasks ('entra
  approleassignment list --appDisplayName', 'entra app list --properties',
  'entra app permission list --appName --type', 'entra groupsetting list',
  'tenant report settings get', 'tenant people pronouns get'), run live.
  'entra app permission list' answers nothing for an app that requests no
  permissions (most app registrations); --output text works for all six.
  Tests: tests\test_v014_apps_settings.py.
  Also (v0.14): Who holds admin roles reads MFA registration with 'entra
  user registrationdetails list --userIds <20 ids> --properties
  id,isMfaRegistered,methodsRegistered' (AuditLog.Read.All; P1+). Live:
  one call for the tenant's role holders. An unreadable MFA status is
  blank, never 'NO'. Tests: tests\test_v014_admin_roles_mfa.py (and the
  two v0.13 admin-role tests now allow that read). It also reads each role
  holder's last sign-in (Graph users/{id}?$select=signInActivity, one GET
  each; the newest of lastSuccessful / lastSignIn / lastNonInteractive).
  Live: one account answered an EMPTY body while eight read fine, so only
  a failed FIRST read stops (permission); later ones are skipped and
  counted. Tests: tests\test_v014_admin_roles_signin.py.
  Also (v0.14): Conditional Access review (m365_workflows.conditional_access):
  Graph identity/conditionalAccess/policies + directoryRoleTemplates
  (includeRoles are role TEMPLATE ids) + users/{id} and groups/{id} for
  names, all through 'm365 request'. Found live: a policy can list all four
  clientAppTypes one by one (= all); grantControls always has
  authenticationStrength (null when unused). The MFA gap notes count only
  policies that are ON and cover ALL apps. Tests:
  tests\test_v014_conditional_access.py, tests\test_v014_web_conditional_access.py.

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
