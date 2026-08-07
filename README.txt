================================================================================
  M365GUI - A GRAPHICAL FRONT-END FOR THE CLI FOR MICROSOFT 365
  Author: Gabriel Clifton
================================================================================

1. WHAT THIS PROGRAM DOES
   M365GUI is a point-and-click front end for the CLI for Microsoft 365 (the
   "m365" command), the command-line tool for Microsoft 365 and Microsoft Entra
   ID administration (https://pnp.github.io/cli-microsoft365/). It presents 33
   common admin tasks as fill-in forms across 7 categories: Users (Entra ID),
   Groups, Licenses, Teams / M365 Groups, SharePoint, Security, and Diagnostics
   - plus a Custom-command mode for any m365 command.

   For every task M365GUI:
     - Builds the exact m365 command from your form entries
     - Shows it in an editable preview BEFORE anything runs
     - Runs it through YOUR m365 CLI and streams the output live
     - Requires confirmation for destructive actions
     - Logs everything to a session log file

   M365GUI is the Microsoft-world counterpart to GAMGUI (for Google Workspace).
   It holds no credentials of its own; all authority comes from your existing
   m365 sign-in.

2. REQUIREMENTS
   - Windows 10/11 (EXE build). From source: any OS with Python 3.10+ and
     tkinter.
   - The CLI for Microsoft 365 installed and signed in:
       npm install -g @pnp/cli-microsoft365
       m365 login
   - Node.js (the CLI runs on Node).
   - Some tasks need extra Microsoft Graph permissions and/or an Entra ID P1/P2
     tenant (noted in the task description).

3. HOW TO RUN IT
   FOR NON-TECHNICAL USERS: see HOW-TO-GUIDE.txt for a plain-English
   walkthrough.

   EXE (recommended) - ONE-FOLDER app:
     a. M365GUI ships as a FOLDER (M365GUI\ containing M365GUI.exe and an
        _internal\ folder). Keep the folder together.
     b. Launch M365GUI\M365GUI.exe.
     c. m365 is found automatically if it is on the PATH. If not, click
        "Locate m365..." (top right); the choice is saved in m365gui.ini.
   From source:
     a. Install Python 3.10+.
     b. python M365GUI.py
   Building the app yourself (Windows):
     a. py -m pip install pyinstaller
     b. Run Build-EXE.bat (runs extract_tcl.py, then builds one-folder).
     c. Result is dist\M365GUI\ - copy the whole folder.

4. WHAT IT CHANGES / SIDE EFFECTS
   M365GUI itself only writes m365gui.ini and log files. The m365 commands you
   run change whatever they say they change - the preview shows the exact
   command first. Tasks marked DESTRUCTIVE (delete user/group, remove member,
   remove license, sign out, remove all guests) pop a confirmation showing the
   full command. The "Remove ALL guest users" task lists everything and makes
   you type DELETE before removing anything.

5. LOG FILES
   Logs\M365GUI_MM-DD-YYYY_HH-MM-SS.log next to the program - one per session,
   with every command and its output. Logs can include user/tenant details;
   keep or purge per your retention practice.

6. TROUBLESHOOTING
   "m365 (not found)"        - Click Locate m365, or install the CLI on PATH.
   "Error: [object Object]"  - m365 is hiding a real error. Re-run the command
                               in Custom command with --debug to see the actual
                               message (often a missing Graph permission or a
                               premium-license requirement).
   "not signed in"           - Run "m365 login" in a terminal.
   Window won't start        - Keep M365GUI.exe with its _internal folder.
   Build error _tcl_data     - Run extract_tcl.py before PyInstaller, or use
                               Build-EXE.bat.

7. KNOWN LIMITATIONS
   - The 33 built-in forms cover everyday Entra/M365 tasks, not every m365
     command - that is what Custom command mode is for.
   - No Exchange Online (email) tasks yet; the command names need confirming on
     the target CLI build.
   - Commands are executed as an editable preview; treat it like a terminal.
   - English only.
================================================================================
