#!/usr/bin/env bash
# =============================================================================
# build-linux-packages.sh - build a .deb and a .rpm for M365GUI with fpm.
#
# Run AFTER build-app.sh has produced dist/M365GUI/ (the one-folder app). Usage:
#   installer/build-linux-packages.sh <version>
# Produces, in the current directory:
#   m365gui_<version>_amd64.deb
#   m365gui-<version>-1.x86_64.rpm
#
# Installing either one registers M365GUI with the system package manager (dpkg
# / rpm) - so the OS knows it is installed and at what version (dpkg -l m365gui,
# rpm -q m365gui), and it can be removed with apt/dnf/rpm. The app lands in
# /opt/M365GUI, with a launcher at /usr/bin/m365gui and a desktop-menu entry.
#
# Requires fpm (gem install fpm) and, for the .rpm, the 'rpm' tools; the CI
# workflow installs both.
# =============================================================================
set -euo pipefail

VER="${1:?usage: build-linux-packages.sh <version>}"
APPDIR="dist/M365GUI"
MAINT="Gabriel Clifton (FSISD IT)"
URL="https://github.com/GuruGabe/M365-Command-GUI-Overlay"
DESC="M365GUI - a point-and-click window for the CLI for Microsoft 365."

if [ ! -d "$APPDIR" ]; then
    echo "ERROR: $APPDIR not found. Run build-app.sh first." >&2
    exit 1
fi

# Build a staging tree that mirrors where the files install on the target.
STAGE="$(mktemp -d)"
mkdir -p "$STAGE/opt/M365GUI" "$STAGE/usr/bin" "$STAGE/usr/share/applications"
cp -R "$APPDIR/." "$STAGE/opt/M365GUI/"

# A small launcher on PATH so users can just run "m365gui".
cat > "$STAGE/usr/bin/m365gui" <<'EOF'
#!/bin/sh
exec /opt/M365GUI/M365GUI "$@"
EOF
chmod 755 "$STAGE/usr/bin/m365gui"

# A desktop-menu entry so it shows up in the application launcher.
cat > "$STAGE/usr/share/applications/m365gui.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=M365GUI
Comment=$DESC
Exec=/opt/M365GUI/M365GUI
Terminal=false
Categories=Utility;System;
EOF

COMMON=(-s dir -n m365gui -v "$VER" --description "$DESC" --url "$URL"
        --maintainer "$MAINT" --license "Apache-2.0" -a amd64
        --category admin -C "$STAGE" .)

# .deb (Debian/Ubuntu)
rm -f m365gui_*.deb
fpm -t deb -p "m365gui_${VER}_amd64.deb" "${COMMON[@]}"

# .rpm (Fedora/RHEL). fpm uses its own arch label for rpm.
rm -f m365gui-*.rpm
fpm -t rpm -a x86_64 -p "m365gui-${VER}-1.x86_64.rpm" -s dir -n m365gui -v "$VER" \
    --description "$DESC" --url "$URL" --maintainer "$MAINT" \
    --license "Apache-2.0" --category admin -C "$STAGE" .

rm -rf "$STAGE"
echo "Built m365gui_${VER}_amd64.deb and m365gui-${VER}-1.x86_64.rpm"
