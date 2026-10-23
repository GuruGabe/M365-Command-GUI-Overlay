# test_v05_installers.py - v0.5 (10-23-2026): installers + in-app updates,
# ported from GAMGUI. The pieces must agree with each other: the names the
# GitHub workflow attaches, the names the updaters download, the Windows
# installer's registry key and the one the app reads. Nothing here builds
# or downloads anything.
import os, re, sys, shutil, tempfile, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import M365GUI as m
import m365_update as u

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8", newline="").read()

FILES = ["installer/m365gui.iss", "installer/build-macos-dmg.sh",
         "installer/build-linux-packages.sh", ".github/workflows/build-installers.yml",
         "updatem365gui.ps1", "m365_update.py"]
texts = {f: read(f) for f in FILES}

# ---- 1. the 7 release files: workflow == updaters ------------------------------
wf = texts[".github/workflows/build-installers.yml"].replace("${{ github.event.inputs.tag }}", "9.9")
attached = set(re.findall(r"^\s+((?:M365GUI|m365gui)[-_][^\s]+)$", wf, re.M))
want = {"M365GUI-9.9-Windows.zip", "M365GUI-9.9-Setup.exe", "M365GUI-9.9-macOS.zip",
        "M365GUI-9.9.dmg", "M365GUI-9.9-Linux.tar.gz", "m365gui_9.9_amd64.deb",
        "m365gui-9.9-1.x86_64.rpm"}
check(attached == want, "the workflow attaches exactly the 7 files (%s)" % sorted(attached))
for kind, tool in (("mac-app", None), ("linux-portable", None), ("linux-package", "apt"),
                   ("linux-package", "dnf")):
    check(u.asset_name(kind, "9.9", tool) in want, "macOS/Linux updater downloads a built file: "
          + str(u.asset_name(kind, "9.9", tool)))
ps1 = texts["updatem365gui.ps1"]
check('"M365GUI-*Windows.zip"' in ps1 and '"M365GUI-*Setup.exe"' in ps1,
      "the Windows updater looks for the Windows zip and Setup.exe")
check("OutputBaseFilename=M365GUI-{#MyAppVersion}-Setup" in texts["installer/m365gui.iss"],
      "Inno Setup writes M365GUI-<version>-Setup.exe")
check('OUT="M365GUI-${VER}.dmg"' in texts["installer/build-macos-dmg.sh"], "the DMG name")
check('"m365gui_${VER}_amd64.deb"' in texts["installer/build-linux-packages.sh"]
      and '"m365gui-${VER}-1.x86_64.rpm"' in texts["installer/build-linux-packages.sh"],
      "the deb and rpm names")

# ---- 2. each build bundles What's new + the Windows updater -------------------------
builds = re.findall(r"python -m PyInstaller .*?M365GUI\.py", wf, re.S)
check(len(builds) == 3 and all("CHANGELOG.txt" in b for b in builds),
      "all 3 workflow builds bundle CHANGELOG.txt (What's new)")
check(wf.count("updatem365gui.ps1 dist") == 3, "the updater script is copied into each build")
for name, needle in (("Build-EXE.bat", '--add-data "CHANGELOG.txt;."'),
                     ("build-app.sh", '--add-data "CHANGELOG.txt:."')):
    check(needle in read(name), name + " bundles CHANGELOG.txt too")
raw = open(os.path.join(ROOT, "Build-EXE.bat"), "rb").read()
check(raw.count(b"\n") == raw.count(b"\r\n"), "Build-EXE.bat keeps CRLF line endings")

# ---- 3. Windows install record: installer == updater == app ------------------------
iss = texts["installer/m365gui.iss"]
app_id = re.search(r"AppId=\{\{([0-9A-F-]{36})\}", iss)
check(bool(app_id), "the installer has a stable AppId GUID")
gamgui_iss = os.path.join(os.path.dirname(ROOT), "GAMGUI", "installer", "gamgui.iss")
if os.path.exists(gamgui_iss) and app_id:
    check(app_id.group(1) not in open(gamgui_iss, encoding="utf-8").read(),
          "the AppId is NOT GAMGUI's (the two installers must never replace each other)")
check('Subkey: "SOFTWARE\\M365GUI"' in iss and '"HKLM:\\SOFTWARE\\M365GUI"' in ps1
      and r"SOFTWARE\M365GUI" in open(os.path.join(ROOT, "M365GUI.py"), encoding="utf-8").read(),
      "the installer, the updater and the app use the same HKLM\\SOFTWARE\\M365GUI key")
check("DefaultDirName={autopf}\\{#MyAppName}" in iss and '#define MyAppName "M365GUI"' in iss,
      "installs to Program Files\\M365GUI")
check("/XF m365gui.ini" in ps1 and "/XD Logs" in ps1 and "m365gui-version.txt" in ps1,
      "a portable update keeps m365gui.ini, the version marker and Logs")
check("throw (\"The release notes do not list a SHA-256" in ps1,
      "the Windows updater REFUSES a file with no published SHA-256 (GAMGUI's only warns)")

# ---- 4. nothing left over from GAMGUI; ASCII ------------------------------------------
# The only GAM words allowed are the notes saying where a file came from.
CREDITS = ("from GAMGUI's gam_update.py", "from GAMGUI's updategamgui.ps1", "as in GAMGUI",
           "than the GAMGUI script it came from")
for f, t in texts.items():
    left = t
    for credit in CREDITS:
        left = left.replace(credit, "")
    found = re.findall(r"(?i)\bgam\w*\b", left)
    check(not found, f + ": no GAM / GAMGUI names left " + str(found[:3]))
    check(all(ord(c) < 128 for c in t), f + ": ASCII only")

# ---- 5. the PowerShell updater parses in Windows PowerShell 5.1 and 7 --------------
path = os.path.join(ROOT, "updatem365gui.ps1")
for exe in ("powershell", "pwsh"):
    if os.name != "nt" or not shutil.which(exe):
        print("SKIP %s parse check" % exe)
        continue
    cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
           "'%s',[ref]$null,[ref]$e); $e.Count" % path.replace("'", "''"))
    r = subprocess.run([exe, "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=120)
    check(r.stdout.strip() == "0", "%s parses updatem365gui.ps1 (errors: %s)" % (exe, r.stdout.strip()))

# ---- 6. m365_update: hashes, install kinds, scripts ------------------------------------
body = ("notes\n\nSHA-256 (M365GUI-9.9-macOS.zip):\n" + "ab" * 32 + "\n\nSHA-256 (M365GUI-9.9.dmg):\n"
        + "cd" * 32 + "\n")
check(u.published_sha256(body, "M365GUI-9.9-macOS.zip") == "AB" * 32
      and u.published_sha256(body, "M365GUI-9.9-Linux.tar.gz") is None,
      "the SHA-256 for a file is read from the release notes; none = None")
# Built with this computer's separator (m365_update splits on os.sep).
app = os.path.abspath(os.sep.join(["", "Applications", "M365GUI.app"]))
check(u.install_kind("Darwin", os.path.join(app, "Contents", "MacOS", "M365GUI"), True,
                     lambda p: True) == ("mac-app", app), "a Mac app")
check(u.install_kind("Linux", "/opt/M365GUI/M365GUI", True, lambda p: False)[0] == "linux-package",
      "/opt (not writable) = the deb/rpm install")
check(u.install_kind("Linux", "/x/M365GUI", False, lambda p: True)[0] == "source", "from source")
mac = u.mac_update_script(1, "/Applications/M365GUI.app", "/tmp/n/M365GUI.app", "/a", "/d", "/tmp/w",
                          "/l.log", "9.9")
lin = u.linux_update_script(1, "/x/M365GUI", "/tmp/n/M365GUI", "/tmp/w", "/l.log", "9.9")
check("M365GUI" in mac and "codesign --verify" in mac and "m365gui.ini" in mac, "the macOS swap script")
check('nohup "$DIR/M365GUI"' in lin and "m365gui.ini|" in lin, "the Linux swap script keeps m365gui.ini")
entries = u.changelog_since(read("CHANGELOG.txt"), "0.3", "0.9")
check(any(v == "0.4" for v, _d, _t, _b in entries), "What's new reads M365GUI's CHANGELOG (0.4 found)")
check(not any(b.startswith("Tests:") for _v, _d, _t, bs in entries for b in bs),
      "What's new leaves out the developer 'Tests:' lines")

# ---- 7. where settings and logs go ------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="m365gui_data_")
saved = (m.app_dir, m._is_writable, os.environ.get("LOCALAPPDATA"), os.environ.get("XDG_DATA_HOME"))
try:
    m.app_dir = lambda: os.path.join(tmp, "Program Files", "M365GUI")
    m._is_writable = lambda p: False
    os.environ["LOCALAPPDATA"] = os.path.join(tmp, "local")
    os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "xdg")
    got = m.data_dir()
    check(got in (os.path.join(tmp, "local", "M365GUI"), os.path.join(tmp, "xdg", "M365GUI")),
          "an installed (read-only) copy keeps settings in a per-user folder (%s)" % got)
    m._is_writable = lambda p: True
    check(m.data_dir() == m.app_dir(), "a portable (writable) copy keeps them next to the app")
finally:
    m.app_dir, m._is_writable = saved[0], saved[1]
    for key, value in (("LOCALAPPDATA", saved[2]), ("XDG_DATA_HOME", saved[3])):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
check(m.INI_PATH == os.path.join(m.DATA_DIR, "m365gui.ini") and m.LOG_DIR == os.path.join(m.DATA_DIR, "Logs"),
      "m365gui.ini and Logs live in the settings folder")
check(m.resource_path("CHANGELOG.txt").endswith("CHANGELOG.txt"), "What's new finds CHANGELOG.txt")
check(m.UPDATE_REPO == "GuruGabe/M365-Command-GUI-Overlay", "updates come from M365GUI's own repo")

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
