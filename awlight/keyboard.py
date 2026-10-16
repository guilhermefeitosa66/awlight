"""Teclado RGB por tecla do m16 (Darfon 0d62:d2b1), protocolo "API v5".

Feature reports de 64 bytes com report ID 0xCC. Referência: alienfx-tools (SDK v5).
"""

import time

from . import hidraw

VENDOR = 0x0D62
PRODUCT = 0xD2B1
REPORT_ID = 0xCC
REPORT_SIZE = 64

CMD_EFFECT = 0x80
CMD_BRIGHTNESS = 0x83
CMD_UPDATE = 0x8B
CMD_COLOR = 0x8C
CMD_STATUS = 0x93
CMD_RESET = 0x94

STATUS_WAIT_UPDATE = 0x80

KEYS_PER_PACKET = 15

# Efeitos de hardware (código do firmware, quantidade de cores usadas)
EFFECTS = {
    "static": (0x01, 1),
    "breathing": (0x02, 1),
    "wave": (0x03, 1),
    "dual-wave": (0x04, 2),
    "pulse": (0x08, 1),
    "morph": (0x09, 2),
    "bounce": (0x0A, 2),
    "laser": (0x0B, 1),
    "rainbow": (0x0E, 1),
}


class Keyboard:
    def __init__(self, info: hidraw.HidInfo | None = None):
        self.dev = hidraw.HidDevice(info or hidraw.find(VENDOR, PRODUCT))

    def close(self):
        self.dev.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _send(self, *payload: int, at: dict[int, bytes] | None = None):
        buf = bytearray(REPORT_SIZE)
        buf[0] = REPORT_ID
        buf[1:1 + len(payload)] = bytes(payload)
        for offset, data in (at or {}).items():
            buf[offset:offset + len(data)] = data
        self.dev.send_feature(bytes(buf))
        time.sleep(0.002)

    def status(self) -> int:
        self._send(CMD_STATUS)
        return self.dev.get_feature(REPORT_SIZE, REPORT_ID)[2]

    def _wait_ready(self, timeout: float = 0.5):
        deadline = time.monotonic() + timeout
        while self.status() == STATUS_WAIT_UPDATE and time.monotonic() < deadline:
            time.sleep(0.01)

    def _reset(self):
        self._send(CMD_RESET)
        self.status()

    def _update(self):
        self._send(CMD_UPDATE, 0x01, 0xFF)
        self._wait_ready()

    def set_keys(self, colors: dict[int, tuple]):
        """Define a cor de cada tecla (ID do firmware -> (r, g, b)) em modo por tecla."""
        self._reset()
        # modo por tecla: efeito estático "sem efeito"
        self._send(CMD_EFFECT, 0x01, 0xFE, 0x00, 0x00, 0x01, 0x01, 0x01)
        self._update()
        self._reset()
        items = sorted(colors.items())
        for i in range(0, len(items), KEYS_PER_PACKET):
            blocks = {}
            for k, (key, (r, g, b)) in enumerate(items[i:i + KEYS_PER_PACKET]):
                blocks[4 + 4 * k] = bytes([key + 1, r, g, b])
            self._send(CMD_COLOR, 0x02, at=blocks)
        self._send(CMD_COLOR, 0x13)
        self._update()

    def set_effect(self, name: str, color: tuple = (255, 255, 255),
                   color2: tuple = (0, 0, 0), speed: int = 5):
        """Efeito de hardware no teclado inteiro. speed de 1 (lento) a 10 (rápido)."""
        code, ncolors = EFFECTS[name]
        speed = max(1, min(10, int(speed)))
        tempo = 0xFF - (speed - 1) * 25
        self._reset()
        self._send(CMD_EFFECT, code, tempo, 0x00, 0x00, 0x01, 0x01, 0x01,
                   ncolors - 1, *color, *color2)
        self._update()

    def set_brightness(self, percent: int):
        value = round(max(0, min(100, int(percent))) * 255 / 100)
        self._reset()
        self._send(CMD_BRIGHTNESS, 0x38, 0x9C, value)
        self._wait_ready()
