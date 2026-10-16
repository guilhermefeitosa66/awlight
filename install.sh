#!/bin/sh
# Instala o awlight para o usuário atual. Só a regra udev precisa de sudo (opcional).
set -eu

SRC="$(cd "$(dirname "$0")" && pwd)"
SHARE="$HOME/.local/share/awlight"
BIN="$HOME/.local/bin/awlight"
DESKTOP="$HOME/.local/share/applications/awlight.desktop"
UNIT="$HOME/.config/systemd/user/awlight.service"
RULE="/etc/udev/rules.d/70-awlight.rules"
RULE_SRC="$SRC/awlight/resources/70-awlight.rules"
ICON="$HOME/.local/share/icons/hicolor/scalable/apps/awlight.svg"

if ! /usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "3.0")' 2>/dev/null; then
    echo "Falta o PyGObject do sistema (pacote python3-gi). Instale com: sudo apt install python3-gi gir1.2-gtk-3.0" >&2
    exit 1
fi

echo "O awlight vai:"
echo "  - copiar o programa para $SHARE"
echo "  - criar o comando $BIN"
echo "  - criar o atalho no menu em $DESKTOP (ícone em $ICON)"
echo "  - criar e ativar o serviço de usuário $UNIT (reaplica as cores no login e ao acordar)"
if [ ! -f "$RULE" ] || ! cmp -s "$RULE_SRC" "$RULE"; then
    echo "  - (com sudo) instalar a regra udev $RULE para acessar os LEDs sem root"
    NEED_RULE=1
else
    NEED_RULE=0
fi
printf "Continuar? [s/N] "
read -r answer
case "$answer" in s|S|sim|y|Y) ;; *) echo "Cancelado."; exit 0 ;; esac

for f in "$BIN" "$DESKTOP" "$UNIT"; do
    if [ -f "$f" ]; then cp -p "$f" "$f.bak"; fi
done

mkdir -p "$SHARE" "$(dirname "$BIN")" "$(dirname "$DESKTOP")" "$(dirname "$UNIT")" "$(dirname "$ICON")"
rm -rf "$SHARE/awlight"
cp -r "$SRC/awlight" "$SHARE/awlight"
find "$SHARE/awlight" -name '__pycache__' -prune -exec rm -rf {} +

cat > "$BIN" <<WRAP
#!/bin/sh
PYTHONPATH="$SHARE" exec /usr/bin/python3 -m awlight "\$@"
WRAP
chmod +x "$BIN"

sed "s|@BIN@|$BIN|" "$SRC/data/awlight.desktop" > "$DESKTOP"
sed "s|@BIN@|$BIN|" "$SRC/data/awlight.service" > "$UNIT"
cp "$SRC/data/awlight.svg" "$ICON"

if [ "$NEED_RULE" = 1 ]; then
    sudo install -m 0644 "$RULE_SRC" "$RULE"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=hidraw
fi

systemctl --user daemon-reload
systemctl --user enable --now awlight.service
systemctl --user restart awlight.service

echo "Pronto. Abra 'AW Light' no menu ou use: awlight --help"
