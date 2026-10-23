; =============================================================================
; m365gui.iss - Inno Setup script that builds the M365GUI Windows installer.
;
; What it produces:
;   M365GUI-<version>-Setup.exe - a standard Windows installer that:
;     - installs the one-folder app into Program Files\M365GUI (per-machine),
;     - adds a Start Menu shortcut (and an optional desktop shortcut),
;     - bundles the auto-updater (updatem365gui.ps1),
;     - creates an uninstaller, and
;     - registers an Add/Remove Programs entry AUTOMATICALLY under
;         HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{AppId}_is1
;       carrying DisplayName, DisplayVersion, Publisher, UninstallString,
;       InstallLocation, etc. (Inno Setup writes this for us because the install
;       is per-machine / PrivilegesRequired=admin.)
;   It ALSO writes an explicit HKLM\SOFTWARE\M365GUI key with the version and
;   install path, so any other tooling can read the installed version directly.
;
; The version is injected by the build with:  iscc /DMyAppVersion=2.9 m365gui.iss
; A default is provided so the script still compiles if run by hand.
;
; The [Files] source is dist\M365GUI (the PyInstaller one-folder output), so run
; Build-EXE.bat (or the CI build) first. Compile from the repo root:
;   iscc /DMyAppVersion=2.9 installer\m365gui.iss
; =============================================================================

#ifndef MyAppVersion
  #define MyAppVersion "0.0"
#endif
#define MyAppName "M365GUI"
#define MyAppPublisher "Gabriel Clifton (FSISD IT)"
#define MyAppURL "https://github.com/GuruGabe/M365-Command-GUI-Overlay"
#define MyAppExeName "M365GUI.exe"

[Setup]
; A STABLE AppId so version upgrades replace the previous install in place and
; update the same Add/Remove Programs entry (never change this GUID).
AppId={{0A8E479E-C0EC-4A8D-907C-4027C3C422CD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; The script lives in installer\ but the built app is at the repo root in
; dist\M365GUI, so resolve [Files] sources and the output from the repo root
; (one level up from this script). The Setup.exe therefore lands in the repo
; root, where the CI workflow uploads it from.
SourceDir=..
OutputDir=.
OutputBaseFilename=M365GUI-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Per-machine install: needs admin, registers the Uninstall entry under HKLM.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
; Stamps the installer's own file-version resource too.
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; The whole one-folder app (M365GUI.exe + _internal + the bundled updater).
Source: "dist\M365GUI\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; Start Menu entry and its uninstaller, plus a desktop shortcut that is ALWAYS
; created (no opt-out, so it also appears in silent/deployment installs).
; {autodesktop} is the ALL-USERS desktop here because this is a per-machine
; install, so every user of the PC gets the shortcut.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Registry]
; An explicit, easy-to-find record of the installed version and location, in
; ADDITION to the automatic Uninstall entry. Removed cleanly on uninstall.
Root: HKLM; Subkey: "SOFTWARE\M365GUI"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\M365GUI"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
