"""Configuração persistente em ~/.config/awlight/config.json."""

import copy
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "awlight"
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "awlight"
STATE_FILE = STATE_DIR / "state.json"

DEFAULT = {
    "chassis": {
        "brightness": 100,
        "zones": {
            "trackpad": {"mode": "color", "color": "#0050ff", "color2": "#000000", "speed": 5},
            "logo": {"mode": "color", "color": "#0050ff", "color2": "#000000", "speed": 5},
        },
        "power": {"ac": "#0050ff", "battery": "#ff8000"},
    },
    "keyboard": {
        "brightness": 100,
        "mode": "per-key",
        "color": "#0050ff",
        "color2": "#000000",
        "speed": 5,
        "keys": {},
    },
}


def parse_color(value) -> tuple:
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return tuple(max(0, min(255, int(c))) for c in value)
    s = str(value).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"cor inválida: {value} (use #rrggbb)")
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError(f"cor inválida: {value} (use #rrggbb)") from None


def format_color(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "keys":
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def load() -> dict:
    try:
        return _merge(DEFAULT, json.loads(CONFIG_FILE.read_text()))
    except FileNotFoundError:
        return copy.deepcopy(DEFAULT)


def save(cfg: dict):
    _write_json(CONFIG_FILE, cfg)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict):
    _write_json(STATE_FILE, state)
