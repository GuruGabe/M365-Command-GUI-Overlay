================================================================================
  M365GUI - A GRAPHICAL FRONT-END FOR THE CLI FOR MICROSOFT 365
  Author: Gabriel Clifton
================================================================================

1. WHAT THIS PROGRAM DOES
   M365GUI is a point-and-click front end for the CLI for Microsoft 365 (the
   "m365" command), the command-line tool for Microsoft 365 and Microsoft Entra
   ID administration (https://pnp.github.io/cli-microsoft365/). It presents 35
   common admin tasks as fill-in forms across 8 categories: OneDrive, Users (Entra ID),
   Groups, Licenses, Teams / M365 Groups, SharePoint, Security, and Diagnostics
   - plus a Custom-command mode for any m365 command.

   For every task M365GUI:
     - Builds the exact m365 command from your form entries
     - Shows it in an editable preview BEFORE anything runs
     - Runs it through YOUR m365 CLI and streams the output live
     - Requires confirmation for destructive actions
     - Logs everything to a session log file
   And (v0.6, as GAMGUI): a Search box, Favorites and Recent, "Signed in as",
   Pick... lists for users and groups, Save results to a CSV / JSON file, Run
   for each CSV row (record in Logs\Bulk_*.csv), Save as script (.ps1 / .sh),
   and removal of pasted curly quotes / invisible characters in address and
   ID boxes. Favorites and Recent are kept in m365gui_tasklists.json in the
   settings folder.

   M365GUI is the Microsoft-world counterpart to GAMGUI (for Google Workspace).
   It holds no credentials of its own; all authority comes from your existing
   m365 sign-in.

2. REQUIREMENTS
   - Windows 10/11, macOS or Linux (installers for all three since v0.5).
     From source: any OS with Python 3.10+ and tkinter.
   - The CLI for Microsoft 365 installed and signed in:
       npm install -g @pnp/cli-microsoft365
       m365 login
   - Node.js (the CLI runs on Node).
   - Some tasks need extra Microsoft Graph permissions and/or an Entra ID P1/P2
     tenant (noted in the task description).

3. HOW TO RUN IT
   FOR NON-TECHNICAL USERS: see HOW-TO-GUIDE.txt for a plain-English
   walkthrough.

   INSTALLERS (v0.5) - from the Releases page on GitHub:
     Windows  M365GUI-<version>-Setup.exe   installs to Program Files (admin),
              Start Menu + desktop shortcuts, Add/Remove Programs entry,
              registry HKLM\SOFTWARE\M365GUI (Version, InstallLocation).
     macOS    M365GUI-<version>.dmg         drag M365GUI to Applications.
     Linux    m365gui_<version>_amd64.deb   sudo apt install ./m365gui_*.deb
              m365gui-<version>-1.x86_64.rpm  sudo dnf install ./m365gui-*.rpm
              (installs to /opt/M365GUI, command 'm365gui', menu entry)
     The SHA-256 of every file is in the release notes.
   PORTABLE - M365GUI-<version>-Windows.zip / -macOS.zip / -Linux.tar.gz:
     a. M365GUI ships as a FOLDER (M365GUI\ containing M365GUI.exe and an
        _internal\ folder). Keep the folder together.
     b. Launch M365GUI\M365GUI.exe.
   Either way: m365 is found automatically if it is on the PATH (or in npm's
   usual folders). If not, click "Locate m365..." (top right); the choice is
   saved in m365gui.ini.
   UPDATES: M365GUI checks GitHub for a newer version when it starts (Help >
   Check for updates at startup) and asks first. It installs a download only
   if its SHA-256 matches the release notes. Windows: an installed copy
   re-runs the new Setup.exe (administrator approval needed); a portable copy
   is replaced by updatem365gui.ps1, keeping m365gui.ini and Logs. Help >
   What's new lists the changes.
   From source:
     a. Install Python 3.10+.
     b. python M365GUI.py
   Building the app yourself (Windows):
     a. py -m pip install pyinstaller
     b. Run Build-EXE.bat (runs extract_tcl.py, then builds one-folder).
     c. Result is dist\M365GUI\ - copy the whole folder.

4. WHAT IT CHANGES / SIDE EFFECTS
   M365GUI itself only writes m365gui.ini and log files (next to the app for
   a portable copy; for an installed copy in %LOCALAPPDATA%\M365GUI,
   ~/Library/Application Support/M365GUI or ~/.local/share/M365GUI). The
   update check reads GitHub's public release list (no account, no token). The m365 commands you
   run change whatever they say they change - the preview shows the exact
   command first. Tasks marked DESTRUCTIVE (delete user/group, remove member,
   remove license, sign out, remove all guests) pop a confirmation showing the
   full command. The "Remove ALL guest users" task lists everything and makes
   you type DELETE before removing anything.

   COPY A USER'S ONEDRIVE FILES TO ANOTHER USER (OneDrive section, v0.4):
     - Copies EVERYTHING in the From user's OneDrive into a new folder in the
       To user's OneDrive (default name 'Files from <name> MM-DD-YYYY').
       Nothing is removed from the From user. A file with the same name is
       renamed (Report1.docx), never overwritten.
     - To read and write both OneDrives, the signed-in admin is made a site
       collection admin of each (SharePoint admin center). Afterwards M365GUI
       removes ONLY the access it added, unless 'Keep my access to both
       OneDrives' was chosen.
     - It shows the number of files and their size and asks once (Yes/No)
       before copying anything. Stop ends it after the current item; the
       temporary access is still removed.

5. LOG FILES
   Logs\M365GUI_MM-DD-YYYY_HH-MM-SS.log in the settings folder - one per session,
   with every command and its output. Logs can include user/tenant details;
   keep or purge per your retention practice.
   Logs\OneDrive-Copy_<name>_MM-DD-YYYY_HH-MM-SS.csv - one per OneDrive copy:
   every item copied (type, source path, copied / FAILED, detail). File and
   folder names of the leaver's OneDrive are in it - keep it with the
   hand-over records and delete it when no longer needed.

6. TROUBLESHOOTING
   "m365 (not found)"        - Click Locate m365, or install the CLI on PATH.
   "Error: [object Object]"  - m365 is hiding a real error. Re-run the command
                               in Custom command with --debug to see the actual
                               message (often a missing Graph permission or a
                               premium-license requirement).
   "not signed in"           - Run "m365 login" in a terminal.
   SharePoint / OneDrive tasks fail with {"error":{"error":"invalid_request"}}
                             - the CLI is signed in through the Azure CLI's
                               app, which SharePoint refuses. Run "m365 setup"
                               once in a terminal: create a new app
                               registration (a Global administrator approves
                               it), full permission set, scripting use; then
                               "m365 login" again.
   OneDrive copy: "Could not read who can manage ..."
                             - you need the SharePoint administrator or Global
                               administrator role (and the fix above).
   Window won't start        - Keep M365GUI.exe with its _internal folder.
   Build error _tcl_data     - Run extract_tcl.py before PyInstaller, or use
                               Build-EXE.bat.

7. KNOWN LIMITATIONS
   - The 35 built-in forms cover everyday Entra/M365 tasks, not every m365
     command - that is what Custom command mode is for.
   - No Exchange Online (email) tasks yet; the command names need confirming on
     the target CLI build.
   - Commands are executed as an editable preview; treat it like a terminal.
   - English only.
================================================================================
