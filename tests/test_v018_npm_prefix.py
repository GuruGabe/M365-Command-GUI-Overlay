# test_v018_npm_prefix.py - v0.18 (11-10-2026): Install / Update the CLI with
# nvm. Seen on a Windows PC after Node.js + nvm were reinstalled: npm's global
# folder became nvm's own folder while the CLI in use stayed in %APPDATA%\npm,
# so a plain 'npm install -g' would add a SECOND m365; and that nvm has
# npm.exe next to node.exe, no npm.cmd. The update now goes into the folder
# the CLI in use came from (--prefix); npm.exe is found. Folders are made in a
# temp folder; nothing is installed.
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_setup as s

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

tmp = tempfile.mkdtemp(prefix="m365_v018_")
PKG = os.path.join("node_modules", "@pnp", "cli-microsoft365")


def touch(*parts):
    path = os.path.join(tmp, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()
    return path


# ---- Windows layout: <prefix>\m365.cmd + <prefix>\node_modules\@pnp\... -----------------
win_prefix = os.path.join(tmp, "Roaming", "npm")
m365_cmd = touch("Roaming", "npm", "m365.cmd")
touch("Roaming", "npm", PKG, "package.json")
check(s.cli_prefix(m365_cmd) == win_prefix, "Windows layout: the folder of m365.cmd")
check(s.npm_install_command("npm.exe", m365_cmd) ==
      ["npm.exe", "install", "-g", "--prefix", win_prefix, "@pnp/cli-microsoft365"],
      "update: npm install -g --prefix <that folder> @pnp/cli-microsoft365")

# ---- macOS / Linux layout: <prefix>/bin/m365 + <prefix>/lib/node_modules/@pnp/... -------
unix_prefix = os.path.join(tmp, "usr", "local")
m365_bin = touch("usr", "local", "bin", "m365")
touch("usr", "local", "lib", PKG, "package.json")
check(s.cli_prefix(m365_bin) == unix_prefix, "macOS / Linux layout: the folder above bin")

# ---- not known -> npm's own default, as before 0.18 --------------------------------------
lonely = touch("elsewhere", "m365.cmd")
check(s.cli_prefix(lonely) == "" and s.cli_prefix("") == "", "no CLI package next to it -> no prefix")
check(s.npm_install_command("npm") == ["npm", "install", "-g", "@pnp/cli-microsoft365"],
      "first install (no m365 yet): unchanged")

# ---- npm.exe next to nvm's node.exe -------------------------------------------------------
node = touch("nvm", ".nodejs", "node.exe")
npm_exe = touch("nvm", ".nodejs", "npm.exe")
if os.name == "nt":
    check(s.find_npm(node, which=lambda n: None) == npm_exe, "npm.exe next to node.exe is found")
    npm_cmd = touch("nvm", ".nodejs", "npm.cmd")
    check(s.find_npm(node, which=lambda n: None) == npm_cmd, "npm.cmd still comes first")
else:
    check(True, "npm.exe check is Windows-only")

# ---- the callers pass the CLI in use -------------------------------------------------------
root = os.path.dirname(HERE)
gui = open(os.path.join(root, "M365GUI.py"), encoding="utf-8").read()
web = open(os.path.join(root, "m365_web.py"), encoding="utf-8").read()
check("npm_install_command(npm, self.m365_path)" in gui, "desktop: Install the CLI passes the CLI in use")
check(web.count("npm_install_command(") == 2 and web.count("M365_PATH)") >= 2
      and "npm_install_command(npm, M365_PATH)" in web, "browser: both uses pass the CLI in use")

print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
