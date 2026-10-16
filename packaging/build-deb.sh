#!/bin/sh
# Gera dist/awlight_<versão>_all.deb
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/awlight/__init__.py")"
BUILD="$ROOT/build/deb"
PKG="$BUILD/awlight_${VERSION}_all"
OUT="$ROOT/dist/awlight_${VERSION}_all.deb"

rm -rf "$BUILD"
mkdir -p "$PKG/DEBIAN" "$PKG/usr/lib/awlight" "$PKG/usr/bin" \
         "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" \
         "$PKG/usr/lib/udev/rules.d" "$PKG/usr/lib/systemd/user" \
         "$PKG/usr/share/doc/awlight" "$ROOT/dist"

cp -r "$ROOT/awlight" "$PKG/usr/lib/awlight/awlight"
find "$PKG/usr/lib/awlight" -name '__pycache__' -prune -exec rm -rf {} +

cat > "$PKG/usr/bin/awlight" <<'EOF'
#!/bin/sh
PYTHONPATH=/usr/lib/awlight exec /usr/bin/python3 -m awlight "$@"
EOF
chmod 0755 "$PKG/usr/bin/awlight"

sed "s|@BIN@|/usr/bin/awlight|" "$ROOT/data/awlight.desktop" > "$PKG/usr/share/applications/awlight.desktop"
sed "s|@BIN@|/usr/bin/awlight|" "$ROOT/data/awlight.service" > "$PKG/usr/lib/systemd/user/awlight.service"
cp "$ROOT/data/awlight.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/awlight.svg"
cp "$ROOT/awlight/resources/70-awlight.rules" "$PKG/usr/lib/udev/rules.d/70-awlight.rules"
cp "$ROOT/LICENSE" "$PKG/usr/share/doc/awlight/copyright"
cp "$ROOT/NOTICE" "$ROOT/README.md" "$PKG/usr/share/doc/awlight/"

SIZE="$(du -sk "$PKG" --exclude=DEBIAN | cut -f1)"
cat > "$PKG/DEBIAN/control" <<EOF
Package: awlight
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0
Installed-Size: $SIZE
Maintainer: Guilherme Feitoza <guilhermefeitosa66@gmail.com>
Homepage: https://github.com/guilhermefeitosa66/awlight
Description: RGB lighting control for the Alienware m16 R2
 Controls the per-key RGB keyboard, touchpad ring, lid logo and power
 button LEDs of the Alienware m16 R2 through hidraw, with a GTK interface,
 a command line tool and a user service that reapplies the colors at login
 and after resume.
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --subsystem-match=hidraw 2>/dev/null || true
    systemctl --global enable awlight.service 2>/dev/null || true
fi
EOF
cat > "$PKG/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
    systemctl --global disable awlight.service 2>/dev/null || true
fi
EOF
chmod 0755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/prerm"

fakeroot dpkg-deb --build --root-owner-group "$PKG" "$OUT" >/dev/null
echo "$OUT"
