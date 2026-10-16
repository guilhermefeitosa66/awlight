#!/bin/sh
# Gera dist/AWLight-<versão>-x86_64.AppImage
# Usa o python3 e o PyGObject do sistema (python3-gi, gir1.2-gtk-3.0).
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/awlight/__init__.py")"
BUILD="$ROOT/build/appimage"
APPDIR="$BUILD/AWLight.AppDir"
TOOLS="$ROOT/build/tools"
TOOL="$TOOLS/appimagetool-x86_64.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
OUT="$ROOT/dist/AWLight-${VERSION}-x86_64.AppImage"

if [ ! -x "$TOOL" ]; then
    mkdir -p "$TOOLS"
    curl -fsSL -o "$TOOL" "$TOOL_URL"
    chmod +x "$TOOL"
fi

rm -rf "$BUILD"
mkdir -p "$APPDIR/usr/lib/awlight" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps" "$ROOT/dist"
cp -r "$ROOT/awlight" "$APPDIR/usr/lib/awlight/awlight"
find "$APPDIR/usr/lib/awlight" -name '__pycache__' -prune -exec rm -rf {} +

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
PYTHON=/usr/bin/python3
if [ ! -x "$PYTHON" ]; then
    echo "awlight precisa do python3 do sistema (/usr/bin/python3)" >&2
    exit 1
fi
[ "$#" -eq 0 ] && set -- gui
PYTHONPATH="$HERE/usr/lib/awlight" exec "$PYTHON" -m awlight "$@"
EOF
chmod 0755 "$APPDIR/AppRun"

sed "s|@BIN@|awlight|" "$ROOT/data/awlight.desktop" > "$APPDIR/awlight.desktop"
cp "$APPDIR/awlight.desktop" "$APPDIR/usr/share/applications/awlight.desktop"
cp "$ROOT/data/awlight.svg" "$APPDIR/awlight.svg"
cp "$ROOT/data/awlight.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/awlight.svg"

ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT" >/dev/null 2>"$BUILD/appimagetool.log" \
    || { cat "$BUILD/appimagetool.log" >&2; exit 1; }
echo "$OUT"
