"""Traduz a configuração em comandos para os dois controladores."""

import json

from . import config, elc, keyboard, layout


def speed_to_duration(speed) -> int:
    """Velocidade 1 (lento) .. 10 (rápido) -> duração de cada fase em ms."""
    speed = max(1, min(10, int(speed)))
    return 4000 - (speed - 1) * 390


def zone_effect(zone_cfg: dict) -> elc.ZoneEffect:
    return elc.ZoneEffect(
        mode=zone_cfg["mode"],
        color=config.parse_color(zone_cfg["color"]),
        color2=config.parse_color(zone_cfg.get("color2", "#000000")),
        duration_ms=speed_to_duration(zone_cfg.get("speed", 5)),
    )


def chassis_effects(cfg: dict) -> dict:
    zones = cfg["chassis"]["zones"]
    return {layout.ZONES[name][0]: zone_effect(z) for name, z in zones.items() if name in layout.ZONES}


def key_colors(cfg: dict) -> dict:
    kb = cfg["keyboard"]
    base = config.parse_color(kb["color"])
    colors = {i: base for i in layout.ALL_KEY_IDS}
    for name, value in kb.get("keys", {}).items():
        for i in layout.resolve_key(name):
            colors[i] = config.parse_color(value)
    return colors


def apply_keyboard(cfg: dict):
    kb = cfg["keyboard"]
    with keyboard.Keyboard() as dev:
        dev.set_brightness(kb["brightness"])
        if kb["mode"] == "per-key":
            dev.set_keys(key_colors(cfg))
        else:
            dev.set_effect(kb["mode"], config.parse_color(kb["color"]),
                           config.parse_color(kb["color2"]), kb["speed"])


CHASSIS_LIGHT_IDS = [z for z, _ in layout.ZONES.values()] + [layout.POWER_ZONE]


def apply_chassis_lights(cfg: dict):
    """Trackpad e logo (volátil) e o brilho do chassi; não toca no botão power."""
    with elc.Elc() as dev:
        dev.apply(chassis_effects(cfg))
        dev.set_brightness(CHASSIS_LIGHT_IDS, cfg["chassis"]["brightness"])


def set_chassis_brightness(percent: int):
    with elc.Elc() as dev:
        dev.set_brightness(CHASSIS_LIGHT_IDS, percent)


def apply_chassis(cfg: dict):
    apply_chassis_lights(cfg)
    apply_power(cfg)


def apply_power(cfg: dict, force: bool = False) -> bool:
    """Programa o botão power só quando as cores mudaram: isso grava na flash do ELC."""
    power = cfg["chassis"]["power"]
    wanted = json.dumps(power, sort_keys=True)
    state = config.load_state()
    if not force and state.get("power") == wanted:
        return False
    with elc.Elc() as dev:
        dev.set_power_button(layout.POWER_ZONE, config.parse_color(power["ac"]),
                             config.parse_color(power["battery"]))
    state["power"] = wanted
    config.save_state(state)
    return True


def save_chassis_to_firmware(cfg: dict):
    """Grava o efeito do chassi como padrão do firmware (vale desde o boot)."""
    with elc.Elc() as dev:
        dev.save_default(chassis_effects(cfg))


def apply_all(cfg: dict) -> list:
    """Aplica tudo; devolve a lista de erros (um dispositivo falhar não impede o outro)."""
    errors = []
    for fn in (apply_chassis, apply_keyboard):
        try:
            fn(cfg)
        except Exception as exc:  # noqa: BLE001 - relatado ao usuário
            errors.append(str(exc))
    return errors


def turn_off(cfg: dict) -> list:
    off = json.loads(json.dumps(cfg))
    off["keyboard"].update(mode="per-key", color="#000000", keys={})
    for z in off["chassis"]["zones"].values():
        z["mode"] = "off"
    errors = []
    for fn in (lambda: apply_keyboard(off), lambda: _chassis_off(off)):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    return errors


def _chassis_off(cfg: dict):
    with elc.Elc() as dev:
        dev.apply(chassis_effects(cfg))
        dev.set_brightness([layout.POWER_ZONE], 0)


def status() -> dict:
    out = {}
    try:
        with elc.Elc() as dev:
            out["chassis"] = {"node": dev.dev.info.node, "firmware": dev.firmware_version(), **dev.config()}
    except Exception as exc:  # noqa: BLE001
        out["chassis"] = {"error": str(exc)}
    try:
        with keyboard.Keyboard() as dev:
            out["keyboard"] = {"node": dev.dev.info.node, "status": f"0x{dev.status():02x}"}
    except Exception as exc:  # noqa: BLE001
        out["keyboard"] = {"error": str(exc)}
    return out
