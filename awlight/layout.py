"""Mapa físico do Alienware m16 R2 (teclado ABNT2) e das zonas do chassi.

IDs de tecla do firmware conferidos no aparelho; base: banco do alienfx-tools
(m16R2 US e m16R1 Brasil). IDs válidos vão de 0 a 135; acima disso o firmware
reaproveita LEDs da primeira fileira.
"""

from dataclasses import dataclass

MAX_KEY_ID = 135


@dataclass(frozen=True)
class Key:
    name: str
    label: str
    ids: tuple
    x: float
    y: float
    w: float = 1.0
    h: float = 1.0


def _row(y, items, h=1.0, x=0.0):
    keys = []
    for item in items:
        if item is None:
            x += 0.25
            continue
        name, label, ids, w = item
        keys.append(Key(name, label, tuple(ids), x, y, w, h))
        x += w
    return keys


# Proporções tiradas de uma foto do teclado ABNT2 do m16 R2 (16 unidades de largura)
KEYS = [
    *_row(0, [
        ("esc", "Esc", [0], 1), ("f1", "F1", [1], 1), ("f2", "F2", [2], 1),
        ("f3", "F3", [3], 1), ("f4", "F4", [4], 1), ("f5", "F5", [5], 1),
        ("f6", "F6", [6], 1), ("f7", "F7", [7], 1), ("f8", "F8", [8], 1),
        ("f9", "F9", [9], 1), ("f10", "F10", [10], 1), ("f11", "F11", [11], 1),
        ("f12", "F12", [12], 1), ("home", "Home", [13], 1), ("end", "End", [14], 1),
        ("delete", "Del", [15], 1),
    ], h=0.7),
    *_row(0.8, [
        ("apostrophe", "' \"", [20], 1), ("1", "1", [21], 1), ("2", "2", [22], 1),
        ("3", "3", [23], 1), ("4", "4", [24], 1), ("5", "5", [25], 1), ("6", "6", [26], 1),
        ("7", "7", [27], 1), ("8", "8", [28], 1), ("9", "9", [29], 1), ("0", "0", [30], 1),
        ("minus", "-", [31], 1), ("equal", "=", [32], 1), ("backspace", "⌫", [34, 35], 2),
        ("micmute", "Mic", [19], 1),
    ]),
    *_row(1.8, [
        ("tab", "Tab", [40], 1.5), ("q", "Q", [42], 1), ("w", "W", [43], 1), ("e", "E", [44], 1),
        ("r", "R", [45], 1), ("t", "T", [46], 1), ("y", "Y", [47], 1), ("u", "U", [48], 1),
        ("i", "I", [49], 1), ("o", "O", [50], 1), ("p", "P", [51], 1), ("acute", "´ `", [52], 1),
        ("bracketleft", "[ {", [53], 1),
    ]),
    *_row(2.8, [
        ("capslock", "Fixa", [60, 61], 1.75), ("a", "A", [62], 1), ("s", "S", [63], 1),
        ("d", "D", [64], 1), ("f", "F", [65], 1), ("g", "G", [66], 1), ("h", "H", [67], 1),
        ("j", "J", [68], 1), ("k", "K", [69], 1), ("l", "L", [70], 1), ("ccedilla", "Ç", [71], 1),
        ("tilde", "~ ^", [72], 1), ("bracketright", "] }", [73], 1),
    ]),
    *_row(3.8, [
        ("shift", "Shift", [80, 81], 1.25), ("backslash", "\\ |", [82], 1), ("z", "Z", [83], 1),
        ("x", "X", [84], 1), ("c", "C", [85], 1), ("v", "V", [86], 1), ("b", "B", [87], 1),
        ("n", "N", [88], 1), ("m", "M", [89], 1), ("comma", ", <", [90], 1),
        ("period", ". >", [91], 1), ("semicolon", "; :", [92], 1), ("rshift", "Shift", [94], 1.75),
        ("up", "↑ PgUp", [114], 1),
    ]),
    *_row(4.8, [
        ("ctrl", "Ctrl", [100], 1.25), ("fn", "Fn", [101], 1), ("super", "Win", [102, 103], 1),
        ("alt", "Alt", [104], 1), ("space", "", [106, 107], 5.1), ("altgr", "AltGr", [111], 1),
        ("winlock", "Win 🔒", [109], 1), ("slash", "/ ?", [112], 1.65), ("left", "←", [133], 1),
        ("down", "↓ PgDn", [134], 1), ("right", "→", [135], 1),
    ]),
    Key("enter", "Enter", (74,), 13.75, 1.8, 1.25, 2.0),
    # coluna de mídia à direita
    Key("mute", "Mudo", (16,), 15, 1.8),
    Key("volup", "Vol+", (18,), 15, 2.8),
    Key("voldown", "Vol-", (17,), 15, 3.8),
]

KEYS_BY_NAME = {k.name: k for k in KEYS}
ALL_KEY_IDS = sorted({i for k in KEYS for i in k.ids})

# Zonas do controlador ELC (conferidas no aparelho)
ZONES = {
    "trackpad": (0, "Bordas do trackpad"),
    "logo": (2, "Logo da tampa"),
}
POWER_ZONE = 4


def resolve_key(token: str) -> tuple:
    """Aceita o nome da tecla (ex.: 'a', 'esc', 'enter') ou um ID numérico."""
    t = token.strip().lower()
    if t in KEYS_BY_NAME:
        return KEYS_BY_NAME[t].ids
    if t.isdigit() and 0 <= int(t) <= MAX_KEY_ID:
        return (int(t),)
    raise ValueError(f"tecla desconhecida: {token}")
