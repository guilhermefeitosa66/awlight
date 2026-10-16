"""Acesso mínimo a dispositivos /dev/hidraw* via ioctl, sem dependências externas."""

import errno
import fcntl
import os
from dataclasses import dataclass
from pathlib import Path

_IOC_READ_WRITE = 3


def _ioc(nr: int, size: int) -> int:
    return (_IOC_READ_WRITE << 30) | (size << 16) | (ord("H") << 8) | nr


def _hidiocsfeature(size: int) -> int:
    return _ioc(0x06, size)


def _hidiocgfeature(size: int) -> int:
    return _ioc(0x07, size)


def _hidiocginput(size: int) -> int:
    return _ioc(0x0A, size)


def _hidiocsoutput(size: int) -> int:
    return _ioc(0x0B, size)


class DeviceNotFound(Exception):
    pass


class DeviceAccessError(Exception):
    pass


@dataclass(frozen=True)
class HidInfo:
    node: str
    vendor: int
    product: int
    name: str


def enumerate_devices():
    """Lista os hidraw do sistema com VID/PID lidos do sysfs."""
    for entry in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        try:
            uevent = (entry / "device" / "uevent").read_text()
        except OSError:
            continue
        fields = dict(line.split("=", 1) for line in uevent.splitlines() if "=" in line)
        hid_id = fields.get("HID_ID", "")
        parts = hid_id.split(":")
        if len(parts) != 3:
            continue
        yield HidInfo(
            node=f"/dev/{entry.name}",
            vendor=int(parts[1], 16),
            product=int(parts[2], 16),
            name=fields.get("HID_NAME", ""),
        )


def find(vendor: int, product: int) -> HidInfo:
    for info in enumerate_devices():
        if info.vendor == vendor and info.product == product:
            return info
    raise DeviceNotFound(f"dispositivo {vendor:04x}:{product:04x} não encontrado")


class HidDevice:
    def __init__(self, info: HidInfo):
        self.info = info
        try:
            self._fd = os.open(info.node, os.O_RDWR)
        except PermissionError as exc:
            raise DeviceAccessError(
                f"sem permissão para abrir {info.node}; instale a regra udev "
                "(veja o README) e reconecte a sessão"
            ) from exc

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _ioctl(self, request: int, buf: bytearray):
        try:
            fcntl.ioctl(self._fd, request, buf)
        except OSError as exc:
            if exc.errno in (errno.ENODEV, errno.ENOENT):
                raise DeviceNotFound(f"{self.info.node} desconectado") from exc
            raise DeviceAccessError(f"falha de ioctl em {self.info.node}: {exc}") from exc

    def send_output(self, data: bytes):
        """SET_REPORT (output) pelo canal de controle. data[0] é o report ID."""
        self._ioctl(_hidiocsoutput(len(data)), bytearray(data))

    def get_input(self, size: int, report_id: int = 0) -> bytes:
        buf = bytearray(size)
        buf[0] = report_id
        self._ioctl(_hidiocginput(size), buf)
        return bytes(buf)

    def send_feature(self, data: bytes):
        self._ioctl(_hidiocsfeature(len(data)), bytearray(data))

    def get_feature(self, size: int, report_id: int) -> bytes:
        buf = bytearray(size)
        buf[0] = report_id
        self._ioctl(_hidiocgfeature(size), buf)
        return bytes(buf)
