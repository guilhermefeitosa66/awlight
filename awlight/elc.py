"""Controlador de iluminação Alienware AW-ELC (187c:0551), protocolo "API v4".

Pacotes de 34 bytes: [0] report ID (0), [1] 0x03, [2] comando, [3..] parâmetros.
Enviados como output report pelo canal de controle; a resposta é lida como
input report. Referências: OpenRGB (AlienwareController) e alienfx-tools (SDK v4).
"""

import time
from dataclasses import dataclass

from . import hidraw

VENDOR = 0x187C
PRODUCT = 0x0551
REPORT_SIZE = 34

CMD_REPORT = 0x20
CMD_ANIMATION = 0x21
CMD_POWER_ANIMATION = 0x22
CMD_SELECT_ZONES = 0x23
CMD_ADD_ACTION = 0x24
CMD_DIM = 0x26
CMD_SET_COLOR = 0x27

REPORT_FIRMWARE = 0x00
REPORT_CONFIG = 0x02

ANIM_NEW = 1
ANIM_FINISH_SAVE = 2
ANIM_FINISH_PLAY = 3
ANIM_REMOVE = 4
ANIM_SET_DEFAULT = 6

SLOT_VOLATILE = 0xFFFF
SLOT_DEFAULT = 0x0061

ACTION_COLOR = 0
ACTION_PULSE = 1
ACTION_MORPH = 2

TEMPO_STEADY = 0xFA
MAX_IDS_PER_PACKET = 25
MAX_ACTIONS_PER_PACKET = 3

SPECTRUM = [
    (0xFF, 0x00, 0x00), (0xFF, 0xA5, 0x00), (0xFF, 0xFF, 0x00), (0x00, 0x80, 0x00),
    (0x00, 0xBF, 0xFF), (0x00, 0x00, 0xFF), (0x80, 0x00, 0x80),
]

MODES = ("color", "pulse", "morph", "breathing", "spectrum", "off")


@dataclass
class ZoneEffect:
    mode: str = "color"
    color: tuple = (0, 0, 0)
    color2: tuple = (0, 0, 0)
    duration_ms: int = 2000


@dataclass
class Action:
    kind: int
    duration_ms: int
    tempo: int
    rgb: tuple


def effect_actions(effect: ZoneEffect):
    d = max(1, min(0xFFFF, int(effect.duration_ms)))
    black = (0, 0, 0)
    if effect.mode == "off":
        return [Action(ACTION_COLOR, 2000, TEMPO_STEADY, black)]
    if effect.mode == "color":
        return [Action(ACTION_COLOR, 2000, TEMPO_STEADY, effect.color)]
    if effect.mode == "pulse":
        return [Action(ACTION_PULSE, d, 0x64, effect.color)]
    if effect.mode == "morph":
        return [Action(ACTION_MORPH, d, 0x64, effect.color),
                Action(ACTION_MORPH, d, 0x64, effect.color2)]
    if effect.mode == "breathing":
        return [Action(ACTION_MORPH, d, 0x64, effect.color),
                Action(ACTION_MORPH, d, 0x64, black)]
    if effect.mode == "spectrum":
        return [Action(ACTION_MORPH, d, 0x64, c) for c in SPECTRUM]
    raise ValueError(f"modo desconhecido: {effect.mode}")


class ElcError(Exception):
    pass


class Elc:
    def __init__(self, info: hidraw.HidInfo | None = None):
        self.dev = hidraw.HidDevice(info or hidraw.find(VENDOR, PRODUCT))

    def close(self):
        self.dev.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _command(self, cmd: int, payload: bytes = b"") -> bytes:
        buf = bytearray(REPORT_SIZE)
        buf[1] = 0x03
        buf[2] = cmd
        buf[3:3 + len(payload)] = payload
        self.dev.send_output(bytes(buf))
        time.sleep(0.005)
        reply = self.dev.get_input(REPORT_SIZE)
        if reply[2] != cmd:
            raise ElcError(f"resposta inesperada ao comando 0x{cmd:02x}: {reply[:8].hex(' ')}")
        return reply

    # -- consultas -------------------------------------------------------
    def firmware_version(self) -> str:
        r = self._command(CMD_REPORT, bytes([REPORT_FIRMWARE]))
        return f"{r[4]}.{r[5]}.{r[6]}"

    def config(self) -> dict:
        r = self._command(CMD_REPORT, bytes([REPORT_CONFIG]))
        return {"platform": (r[4] << 8) | r[5], "zones": r[6]}

    def zone_ids(self) -> list[int]:
        return list(range(self.config()["zones"]))

    # -- animação --------------------------------------------------------
    def _animation(self, op: int, slot: int):
        self._command(CMD_ANIMATION, bytes([op >> 8, op & 0xFF, slot >> 8, slot & 0xFF, 0, 0]))

    def _select(self, zones):
        zones = list(zones)
        for i in range(0, len(zones), MAX_IDS_PER_PACKET):
            chunk = zones[i:i + MAX_IDS_PER_PACKET]
            self._command(CMD_SELECT_ZONES, bytes([1, len(chunk) >> 8, len(chunk) & 0xFF, *chunk]))

    def _add_actions(self, actions):
        for i in range(0, len(actions), MAX_ACTIONS_PER_PACKET):
            payload = bytearray()
            for a in actions[i:i + MAX_ACTIONS_PER_PACKET]:
                payload += bytes([a.kind, a.duration_ms >> 8, a.duration_ms & 0xFF,
                                  a.tempo >> 8, a.tempo & 0xFF, *a.rgb])
            self._command(CMD_ADD_ACTION, bytes(payload))

    def _program(self, effects: dict[int, ZoneEffect]):
        # zonas com o mesmo efeito vão num único select
        groups: dict[tuple, list[int]] = {}
        for zone, eff in effects.items():
            key = (eff.mode, tuple(eff.color), tuple(eff.color2), eff.duration_ms)
            groups.setdefault(key, []).append(zone)
        for zones in groups.values():
            self._select(zones)
            self._add_actions(effect_actions(effects[zones[0]]))

    def apply(self, effects: dict[int, ZoneEffect]):
        """Aplica os efeitos imediatamente (não sobrevive a reinício do controlador)."""
        self._animation(ANIM_REMOVE, SLOT_VOLATILE)
        self._animation(ANIM_NEW, SLOT_VOLATILE)
        self._program(effects)
        self._animation(ANIM_FINISH_PLAY, SLOT_VOLATILE)

    def save_default(self, effects: dict[int, ZoneEffect]):
        """Grava os efeitos no firmware como animação padrão (vale no boot, inclusive no GRUB)."""
        self._animation(ANIM_REMOVE, SLOT_DEFAULT)
        self._animation(ANIM_NEW, SLOT_DEFAULT)
        self._program(effects)
        self._animation(ANIM_FINISH_SAVE, SLOT_DEFAULT)
        self._animation(ANIM_SET_DEFAULT, SLOT_DEFAULT)

    def set_power_button(self, zone: int, ac: tuple, battery: tuple):
        """Programa as animações de estado de energia do botão power (grava no firmware).

        O firmware escolhe sozinho qual slot tocar conforme tomada/bateria/suspensão.
        """
        black = (0, 0, 0)
        slots = {
            0x5B: [Action(ACTION_MORPH, 1000, 0x64, ac), Action(ACTION_MORPH, 1000, 0x64, black)],
            0x5C: [Action(ACTION_COLOR, 2000, TEMPO_STEADY, ac)],
            0x5D: [Action(ACTION_MORPH, 1000, 0x64, ac), Action(ACTION_MORPH, 1000, 0x64, battery)],
            0x5E: [Action(ACTION_MORPH, 1000, 0x64, battery), Action(ACTION_MORPH, 1000, 0x64, black)],
            0x5F: [Action(ACTION_COLOR, 2000, TEMPO_STEADY, battery)],
            0x60: [Action(ACTION_PULSE, 1000, 0x64, battery)],
        }
        for slot, actions in slots.items():
            self._power_slot(ANIM_REMOVE, slot)
            self._power_slot(ANIM_NEW, slot)
            self._select([zone])
            self._add_actions(actions)
            self._power_slot(ANIM_FINISH_SAVE, slot)

    def _power_slot(self, op: int, slot: int):
        self._command(CMD_POWER_ANIMATION, bytes([op >> 8, op & 0xFF, slot >> 8, slot & 0xFF, 0, 0]))

    def set_brightness(self, zones, percent: int):
        """Brilho de 0 a 100 (o firmware recebe o percentual de escurecimento)."""
        zones = list(zones)
        dim = 100 - max(0, min(100, int(percent)))
        for i in range(0, len(zones), MAX_IDS_PER_PACKET):
            chunk = zones[i:i + MAX_IDS_PER_PACKET]
            self._command(CMD_DIM, bytes([dim, len(chunk) >> 8, len(chunk) & 0xFF, *chunk]))
