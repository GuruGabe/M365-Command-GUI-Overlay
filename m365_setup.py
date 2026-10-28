# =============================================================================
# m365_setup.py - the facts behind M365GUI's "Set up the CLI" window (v0.12;
# Gabe 10-27-2026: "install the M365 CLI and be able to initiate M365 login
# ... just a pop-up window if needed"). The same idea as GAMGUI's Set up GAM.
#
#   step     what is needed                    how M365GUI does it
#   -------  --------------------------------  -----------------------------------
#   1 node   Node.js (the CLI runs on it)      Windows: 'winget install --id
#                                              OpenJS.NodeJS.LTS' in its own
#                                              window (winget shows the license
#                                              and asks for admin approval);
#                                              macOS / Linux: nodejs.org
#   2 cli    the CLI for Microsoft 365         npm install -g @pnp/cli-microsoft365
#                                              (output shown in the window)
#   3 app    the CLI's own Entra app           'm365 setup' in its own window (a
#            (CLI v11: "appId is required.     wizard: create an app registration
#            TIP: use the "m365 setup"         - a Global admin consents - or use
#            command")                         an existing one)
#   4 login  a signed-in account               'm365 login --authType browser |
#                                              deviceCode' in its own window
#
# Pure functions - M365GUI.py does the asking and launching.
# =============================================================================

import os
import re
import shlex
import shutil

NPM_PACKAGE = "@pnp/cli-microsoft365"
NODE_DOWNLOAD_URL = "https://nodejs.org/en/download"
WINGET_NODE_ID = "OpenJS.NodeJS.LTS"           # winget search, checked 10-27-2026
# The CLI keeps its app ID in its 'clientId' setting (cli.js getClientId) or
# reads this environment variable.
APP_ID_ENV = "CLIMICROSOFT365_ENTRAAPPID"
CLIENT_ID_COMMAND = ["cli", "config", "get", "--key", "clientId", "--output", "json"]
SETUP_COMMAND = ["setup"]
_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# A failed command that the window can fix (the CLI's own texts, v11.11:
# Command.js "Log in to Microsoft 365 first", login.js "appId is required",
# and Entra's sign-in errors: expired / revoked token, MFA or consent needed).
_SETUP_ERRORS = re.compile(
    r"Log in to Microsoft 365 first|appId is required|"
    r"AADSTS(50173|700082|70043|70008|50076|50079|65001|500011)\b|"
    r"interaction_required|invalid_grant", re.I)


def find_npm(node_path, which=None):
    # npm, which comes with Node.js: next to node, else on the PATH.
    which = which or shutil.which
    folder = os.path.dirname(node_path or "")
    for name in (("npm.cmd",) if os.name == "nt" else ("npm",)):
        if folder and os.path.isfile(os.path.join(folder, name)):
            return os.path.join(folder, name)
    return which("npm") or ""


def npm_install_command(npm):
    return [npm, "install", "-g", NPM_PACKAGE]


def node_install_plan(system, which=None):
    # ("winget", argv) on Windows with winget; ("download", url) otherwise.
    which = which or shutil.which
    if system == "Windows":
        winget = which("winget")
        if winget:
            # No --accept-...-agreements: winget shows Node.js's license in its
            # window and the person accepts it there.
            return "winget", [winget, "install", "--id", WINGET_NODE_ID, "--exact",
                              "--source", "winget"]
    return "download", NODE_DOWNLOAD_URL


def app_id_set(returncode, output, environ=None):
    # True when the CLI has an app ID: its clientId setting (a GUID) or the
    # environment variable.
    environ = os.environ if environ is None else environ
    if _GUID.search(environ.get(APP_ID_ENV) or ""):
        return True
    return returncode == 0 and bool(_GUID.search(output or ""))


def signed_in(account_line):
    # From M365GUI.account_text: "Signed in as: <who>" when signed in; every
    # other answer is "(...)" or "nobody - run 'm365 login'".
    who = (account_line or "").split("Signed in as:", 1)[-1].strip()
    return bool(who) and not who.startswith(("(", "nobody"))


def needs_window(account_line):
    # Open the window by itself at startup? Only for a clear problem: no
    # m365, no Node.js, or nobody signed in. "(could not check ...)" /
    # "(unknown ...)" can be a network hiccup - not a reason.
    line = account_line or ""
    return ("m365 not found" in line or "Node.js is not installed" in line
            or "nobody" in line)


def needed_steps(node_found, cli_found, app_ok, account_line):
    steps = []
    if not node_found:
        steps.append("node")
    if not cli_found:
        steps.append("cli")
    if not app_ok:
        steps.append("app")
    if not signed_in(account_line):
        steps.append("login")
    return steps


def setup_can_fix(output):
    return bool(_SETUP_ERRORS.search(output or ""))


def login_command(auth_type):
    if auth_type not in ("browser", "deviceCode"):
        raise ValueError("unknown sign-in type: " + str(auth_type))
    return ["login", "--authType", auth_type]


def _applescript_text(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def console_command(argv, title, system, which=None):
    # A NEW terminal window running argv and staying open afterwards, or None
    # when this system has no terminal M365GUI knows (same as GAMGUI 2.97).
    if system == "Windows":
        return ["cmd", "/c", "start", title, "cmd", "/k"] + list(argv)
    shell = " ".join(shlex.quote(a) for a in argv)
    shell += "; echo; read -r -p 'Press Enter to close this window...' _"
    if system == "Darwin":
        return ["osascript",
                "-e", 'tell application "Terminal" to do script %s' % _applescript_text(
                    "bash -c " + shlex.quote(shell)),
                "-e", 'tell application "Terminal" to activate']
    if system == "Linux":
        which = which or shutil.which
        for name, form in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]),
                           ("konsole", ["-e"]), ("xfce4-terminal", ["-x"]), ("xterm", ["-e"])):
            if which(name):
                return [name] + form + ["bash", "-c", shell]
    return None


def npm_failure_hint(output):
    # One line after a failed 'npm install -g'.
    text = output or ""
    if re.search(r"EACCES|permission denied|EPERM", text, re.I):
        return ("npm may not write to its global folder for this account. On macOS / "
                "Linux run this in Terminal:  sudo npm install -g " + NPM_PACKAGE
                + "  - or set up npm for your own account (npm docs: 'Resolving "
                "EACCES permissions errors').")
    if re.search(r"ENOTFOUND|ETIMEDOUT|ECONNRESET|network", text, re.I):
        return "npm could not reach the internet (registry.npmjs.org) - check the network or proxy."
    return ""
