# M365GUI - Development Notes

## Status

- Single-file tkinter application (`M365GUI.py`), Python standard library only.
- 35 tasks across 8 categories, plus a Custom-command mode and two guided
  workflows: "remove all guest users" and (0.4) "copy a user's OneDrive files
  to another user".
- Drives the [CLI for Microsoft 365](https://pnp.github.io/cli-microsoft365/)
  (`m365`). All commands verified against CLI v11 with `m365 <command> --help`.
- Windows one-folder build via `Build-EXE.bat` (bundles Tcl/Tk 9 data for
  Python 3.14; see `extract_tcl.py`).
- Shares its engine and design with
  [GAMGUI](https://github.com/GuruGabe/GAM-GUI-Overlay).

## Roadmap / ideas

- Exchange Online tasks (mailbox settings, forwarding) - the `exo`/`outlook`
  command names need confirming on the target CLI build first.
- Intune device tasks; guest invitations; Conditional Access.
- More Teams and SharePoint coverage.
- CSV bulk-run builder; favorites; dark mode.
- macOS/Linux builds (the source is cross-platform; needs building/testing).

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
