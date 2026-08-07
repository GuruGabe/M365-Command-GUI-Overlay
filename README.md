# M365GUI

**A friendly, point-and-click window for the [CLI for Microsoft 365](https://pnp.github.io/cli-microsoft365/) -
the free tool that lets you manage Microsoft 365 and Microsoft Entra ID (users,
groups, licenses, Teams, SharePoint) faster than clicking through the admin
portals.**

M365GUI turns common admin tasks into simple fill-in-the-blank forms, shows you
the exact command it will run **before** it runs, and prints the results in the
window. You get the CLI's power without memorizing any commands. It is the
Microsoft-world counterpart to [GAMGUI](https://github.com/GuruGabe/GAM-GUI-Overlay)
(which does the same for Google Workspace / GAM).

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20source%3A%20macOS%2FLinux-informational)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Dependencies](https://img.shields.io/badge/dependencies-none%20(standard%20library)-brightgreen)

![M365GUI main window](screenshot.png)

---

## New here? Start with this

**What is Microsoft 365 / Entra administration?** If your organization uses
Microsoft 365 (Outlook, Teams, SharePoint, OneDrive) and Microsoft Entra ID
(formerly Azure AD) for accounts, an administrator manages all of it - users,
groups, licenses, devices - from the Microsoft admin portals in a web browser.
That works, but doing the same thing for hundreds of people, one click at a
time, is slow.

**What is the CLI for Microsoft 365?** The
[CLI for Microsoft 365](https://pnp.github.io/cli-microsoft365/) (the `m365`
command) is a free, open-source, cross-platform tool that talks to Microsoft
365 and Entra ID and does those admin jobs in seconds. It is the Microsoft
equivalent of GAM for Google Workspace.

**The catch:** it's a *command-line* tool - you type commands like
`m365 entra user add --displayName "John Doe" --userName jdoe@contoso.com`.
That scares off a lot of people who would otherwise love what it can do.

**That's what M365GUI fixes.** It puts a normal windowed program on top of the
CLI. You pick a task, fill in a couple of boxes, and click **Run**. M365GUI
writes the correct command for you, shows it, runs it, and displays the result.

> [!IMPORTANT]
> **M365GUI does not replace the CLI - it drives it.** You still need the CLI
> for Microsoft 365 installed and signed in on the computer (a one-time setup,
> below). M365GUI stores no credentials of its own; it simply runs *your* `m365`.

---

## What can you actually do with it?

Real jobs M365GUI makes easy. Each links to the matching CLI documentation.

### Manage people (Entra ID users)
- **Onboard:** create an account with a display name, sign-in name, and
  password; set the usage location so it can be licensed.
- **Everyday help-desk:** reset a password, block/unblock sign-in, rename,
  look up a user, list all users or just guests.
- **Offboard:** delete an account, or restore one deleted by mistake (30-day
  recycle bin).
- **Clean up:** remove **all** guest accounts in one guided, confirm-first
  workflow.
- Docs: [entra user](https://pnp.github.io/cli-microsoft365/cmd/entra/user/user-list/)

### Groups
- **List** groups (all, or just Microsoft 365 / security groups), **view** a
  group's details, **create** and **delete** groups, and **add/remove members**.
- Docs: [entra group](https://pnp.github.io/cli-microsoft365/cmd/entra/group/group-list/)

### Licenses
- **See every license** your tenant owns (with used/total and each SKU id).
- **List all users** who have a specific license.
- **Assign** and **remove** licenses.
- Docs: [entra license list](https://pnp.github.io/cli-microsoft365/cmd/entra/license/license-list/)
  · [entra user license](https://pnp.github.io/cli-microsoft365/cmd/entra/user/user-license-add/)

### Teams & SharePoint
- **Add members to a Team**, **list SharePoint sites**, add a user to a
  SharePoint group.
- Docs: [Teams / M365 groups](https://pnp.github.io/cli-microsoft365/cmd/entra/m365group/m365group-user-add/)
  · [SharePoint](https://pnp.github.io/cli-microsoft365/cmd/spo/site/site-list/)

### Security
- **Sign a user out everywhere** (revoke sessions) - first move on a
  compromised account - and view **sign-in activity**.
- Docs: [session revoke](https://pnp.github.io/cli-microsoft365/cmd/entra/user/user-session-revoke/)

There's also a **Custom command** box for anything not yet built into a form -
so you're never limited to the built-in tasks.

---

## Get it running (the whole path, from zero)

### Step 1 - Install the CLI for Microsoft 365 (one time, required)
M365GUI needs the `m365` CLI installed and signed in. It runs on
[Node.js](https://nodejs.org):

```bash
npm install -g @pnp/cli-microsoft365
m365 login
```

Full guide: [Installing the CLI](https://pnp.github.io/cli-microsoft365/user-guide/installing-cli/)
and [signing in](https://pnp.github.io/cli-microsoft365/user-guide/connecting-microsoft-365/).
Some tasks (like sign-in activity) need extra Graph permissions and/or an Entra
ID P1/P2 tenant - the app notes these where they apply.

> Not sure it's working? Run `m365 status` and `m365 version`. If those succeed,
> you're ready for M365GUI.

### Step 2 - Get M365GUI (prebuilt - no building required)
1. Go to the **[Releases](../../releases)** page and download
   **`M365GUI-vX.Y-Windows.zip`** from the latest release.
2. **Unzip it**, keeping the whole `M365GUI` folder together (the `M365GUI.exe`
   needs the `_internal` folder next to it).
3. Double-click **`M365GUI.exe`**. (Windows may warn about an unrecognized app
   because it isn't code-signed; choose **More info -> Run anyway**.)

Prefer to build it yourself? See [Build from source](#build-from-source).

### Step 3 - First launch
- If the top of the window says `m365: (not found)`, click **Locate m365...**
  and point it at your `m365` program (M365GUI finds it automatically when it's
  on the PATH).
- **Try a safe one first:** open **Diagnostics -> Login status** and click
  **Run**. It only reads information - a perfect way to confirm everything works.

New, non-technical users: open **HOW-TO-GUIDE.txt** for a plain-English
walkthrough. **README.txt** is the full reference.

---

## The task list at a glance

| Category | What it's for | Docs |
|----------|---------------|------|
| Users (Entra ID) | List, get, create, reset password, rename, usage location, block/unblock, delete, recycle bin, restore, remove all guests | [entra user](https://pnp.github.io/cli-microsoft365/cmd/entra/user/user-list/) |
| Groups (Entra) | List, list by type, get info, create, list/add/remove members, delete | [entra group](https://pnp.github.io/cli-microsoft365/cmd/entra/group/group-list/) |
| Licenses | View all SKUs, list users with a license, assign, remove | [entra license](https://pnp.github.io/cli-microsoft365/cmd/entra/license/license-list/) |
| Teams / M365 Groups | Add member to a Team | [m365group](https://pnp.github.io/cli-microsoft365/cmd/entra/m365group/m365group-user-add/) |
| SharePoint | List sites, add user to a site group | [spo](https://pnp.github.io/cli-microsoft365/cmd/spo/site/site-list/) |
| Security | Sign out everywhere, sign-in activity | [session revoke](https://pnp.github.io/cli-microsoft365/cmd/entra/user/user-session-revoke/) |
| Diagnostics | Login status, CLI version, tenant id | [status](https://pnp.github.io/cli-microsoft365/cmd/status/) |

Plus a **Custom command** mode that accepts any `m365` command
([full command reference](https://pnp.github.io/cli-microsoft365/cmd/docs/)).

---

## Safety and security

M365GUI runs real commands against your live Microsoft 365 tenant. It's built to
be careful, but treat it with respect:

- **It can do whatever your `m365` can do.** M365GUI has no permissions of its
  own - give it to people you trust with that level of access, and think about
  who should have the destructive tasks (delete user/group, remove all guests,
  remove license).
- **You always see the command first,** and destructive tasks pop a
  confirmation. The "Remove all guests" workflow lists everything and makes you
  type **DELETE** before it removes anything.
- **Test in a non-production tenant first** when you're learning.
- **Logs can contain user and tenant details** - store and share accordingly.

---

## Build from source

M365GUI is a single Python file (`M365GUI.py`) using only the standard library.

```bat
py -m pip install pyinstaller
Build-EXE.bat
```

`Build-EXE.bat` runs `extract_tcl.py` and then PyInstaller in one-folder mode.
The extract step is **required on Python 3.14+**: Tcl/Tk 9 stores its script
library inside the DLL as a virtual zip filesystem, which PyInstaller doesn't
bundle on its own - without it the app crashes at startup with
`Tcl data directory _tcl_data not found`. The result is `dist\M365GUI\` -
distribute the whole folder.

**macOS/Linux:** build on that OS with
`pyinstaller --onedir --windowed --name M365GUI M365GUI.py` (Linux needs the
`python3-tk` package). To just run it without building: `python M365GUI.py`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Top bar shows `m365: (not found)` | Click **Locate m365...**, or install the CLI so `m365` is on the PATH. |
| `Error: [object Object]` | The CLI is hiding a real error. Re-run the command in **Custom command** with `--debug` added to see the actual message (often a missing Graph permission or a premium-license requirement). |
| "Windows protected your PC" on launch | The app isn't code-signed. Click **More info -> Run anyway**. |
| A command says you're not signed in | Run `m365 login` in a terminal, or **Diagnostics -> Login status** to check. |
| App won't start after unzipping | Keep `M365GUI.exe` and its `_internal` folder together in one folder. |
| `Tcl data directory _tcl_data not found` (building yourself) | Run `extract_tcl.py` before PyInstaller, or just use `Build-EXE.bat`. |

---

## Project files

| File | Purpose |
|------|---------|
| `M365GUI.py` | The entire application (single file, standard library only) |
| `extract_tcl.py` | Build helper: bundles Tcl/Tk data for Python 3.14+ |
| `Build-EXE.bat` | One-command Windows build |
| `HOW-TO-GUIDE.txt` | Plain-English guide for non-technical users |
| `README.txt` | Full reference and troubleshooting |
| `CHANGELOG.txt` | Version history |
| `NOTES.md` | Development notes, roadmap, known limitations |

## Contributing

Issues and pull requests are welcome. `M365GUI.py` uses a data-driven task
catalog (the `TASKS` dictionary), so adding a task is a few lines and needs no
new code. Please keep the app dependency-free (standard library only) so it
stays easy to build and audit. Commands were verified against CLI for Microsoft
365 v11; if you add tasks, confirm the syntax with `m365 <command> --help`.

## License and disclaimer

Created by Gabriel Clifton. Licensed under the [Apache License 2.0](LICENSE).

M365GUI runs real administrative commands against a live Microsoft 365 tenant
through the CLI for Microsoft 365. Review the command preview before running,
and test in a non-production tenant first. Provided **as-is, without warranty**.
This is an independent project and is **not affiliated with or endorsed by** the
CLI for Microsoft 365 project, Microsoft, or PnP.
