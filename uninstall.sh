#!/bin/sh
# Remove o awlight do usuário atual. A configuração em ~/.config/awlight é mantida.
set -eu
systemctl --user disable --now awlight.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/awlight.service" "$HOME/.local/bin/awlight" \
      "$HOME/.local/share/applications/awlight.desktop" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/awlight.svg"
rm -rf "$HOME/.local/share/awlight"
systemctl --user daemon-reload
if [ -f /etc/udev/rules.d/70-awlight.rules ]; then
    echo "Para remover a regra udev: sudo rm /etc/udev/rules.d/70-awlight.rules"
fi
echo "awlight removido (configuração mantida em ~/.config/awlight)."
