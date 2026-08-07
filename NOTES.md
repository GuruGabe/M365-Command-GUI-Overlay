# M365GUI - Development Notes

## Status

- Single-file tkinter application (`M365GUI.py`), Python standard library only.
- 33 tasks across 7 categories, plus a Custom-command mode and a guided
  "remove all guest users" workflow.
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
