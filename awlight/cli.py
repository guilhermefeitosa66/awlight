"""Linha de comando do awlight."""

import argparse
import json
import sys
import time

from pathlib import Path

from . import __version__, config, control, elc, keyboard, layout

UDEV_RULE = Path(__file__).parent / "resources" / "70-awlight.rules"

ZONE_CHOICES = [*layout.ZONES, "all"]
KB_MODES = ["per-key", *keyboard.EFFECTS]


def _zones(name):
    return list(layout.ZONES) if name == "all" else [name]


def cmd_status(args, cfg):
    print(json.dumps(control.status(), indent=2, ensure_ascii=False))


def cmd_apply(args, cfg):
    return control.apply_all(cfg)


def cmd_zone(args, cfg):
    for name in _zones(args.zone):
        z = cfg["chassis"]["zones"][name]
        z["mode"] = args.mode
        if args.color:
            z["color"] = config.format_color(config.parse_color(args.color))
        if args.color2:
            z["color2"] = config.format_color(config.parse_color(args.color2))
        if args.speed:
            z["speed"] = args.speed
    config.save(cfg)
    control.apply_chassis_lights(cfg)


def cmd_power(args, cfg):
    p = cfg["chassis"]["power"]
    if args.ac:
        p["ac"] = config.format_color(config.parse_color(args.ac))
    if args.battery:
        p["battery"] = config.format_color(config.parse_color(args.battery))
    config.save(cfg)
    control.apply_power(cfg, force=True)


def cmd_kb_color(args, cfg):
    kb = cfg["keyboard"]
    kb.update(mode="per-key", color=config.format_color(config.parse_color(args.color)))
    if not args.keep_keys:
        kb["keys"] = {}
    config.save(cfg)
    control.apply_keyboard(cfg)


def cmd_kb_key(args, cfg):
    kb = cfg["keyboard"]
    kb["mode"] = "per-key"
    for item in args.assignments:
        if "=" not in item:
            raise ValueError(f"use TECLA=COR, recebido: {item}")
        name, color = item.split("=", 1)
        layout.resolve_key(name)
        kb["keys"][name.lower()] = config.format_color(config.parse_color(color))
    config.save(cfg)
    control.apply_keyboard(cfg)


def cmd_kb_effect(args, cfg):
    kb = cfg["keyboard"]
    kb["mode"] = args.effect
    if args.color:
        kb["color"] = config.format_color(config.parse_color(args.color))
    if args.color2:
        kb["color2"] = config.format_color(config.parse_color(args.color2))
    if args.speed:
        kb["speed"] = args.speed
    config.save(cfg)
    control.apply_keyboard(cfg)


def cmd_kb_keys(args, cfg):
    for k in layout.KEYS:
        print(f"{k.name:14} {k.label:8} ids={','.join(map(str, k.ids))}")


def cmd_kb_identify(args, cfg):
    """Acende um ID por vez para descobrir a posição de LEDs."""
    ids = range(args.start, min(args.end, layout.MAX_KEY_ID) + 1)
    with keyboard.Keyboard() as dev:
        for i in ids:
            dev.set_keys({j: ((255, 0, 0) if j == i else (0, 0, 0)) for j in range(layout.MAX_KEY_ID + 1)})
            input(f"ID {i} aceso em vermelho. Enter para o próximo (Ctrl+C sai) ")
    control.apply_keyboard(cfg)


def cmd_brightness(args, cfg):
    if args.keyboard is None and args.chassis is None:
        print(f"teclado: {cfg['keyboard']['brightness']}%  chassi: {cfg['chassis']['brightness']}%")
        return
    if args.keyboard is not None:
        cfg["keyboard"]["brightness"] = args.keyboard
    if args.chassis is not None:
        cfg["chassis"]["brightness"] = args.chassis
    config.save(cfg)
    if args.keyboard is not None:
        control.apply_keyboard(cfg)
    if args.chassis is not None:
        control.set_chassis_brightness(args.chassis)


def cmd_off(args, cfg):
    return control.turn_off(cfg)


def cmd_save(args, cfg):
    control.save_chassis_to_firmware(cfg)
    control.apply_power(cfg, force=True)
    print("efeito do chassi e botão power gravados no firmware")


def cmd_daemon(args, cfg):
    _require_gi()
    from gi.repository import Gio, GLib

    def reapply(reason):
        for attempt in range(10):
            errors = control.apply_all(config.load())
            if not errors:
                print(f"cores aplicadas ({reason})", flush=True)
                return
            time.sleep(1.5)
        print(f"falha ao aplicar ({reason}): {'; '.join(errors)}", file=sys.stderr, flush=True)

    def on_signal(conn, sender, path, iface, signal, params):
        if not params.unpack()[0]:  # False = acabou de acordar
            GLib.timeout_add_seconds(2, lambda: reapply("retorno da suspensão") or GLib.SOURCE_REMOVE)

    reapply("início da sessão")
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    bus.signal_subscribe("org.freedesktop.login1", "org.freedesktop.login1.Manager",
                         "PrepareForSleep", "/org/freedesktop/login1", None,
                         Gio.DBusSignalFlags.NONE, on_signal)
    GLib.MainLoop().run()


def _require_gi():
    try:
        import gi  # noqa: F401
    except ImportError:
        raise RuntimeError("PyGObject não encontrado; instale com: sudo apt install python3-gi gir1.2-gtk-3.0") from None


def cmd_gui(args, cfg):
    _require_gi()
    from . import gui
    gui.main()


def cmd_udev_rule(args, cfg):
    print(UDEV_RULE.read_text(), end="")


def cmd_version(args, cfg):
    print(__version__)


def build_parser():
    p = argparse.ArgumentParser(prog="awlight", description="Iluminação RGB do Alienware m16 R2")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="mostra os controladores encontrados").set_defaults(fn=cmd_status)
    sub.add_parser("apply", help="aplica a configuração salva").set_defaults(fn=cmd_apply)
    sub.add_parser("off", help="apaga todas as luzes (sem mudar a configuração)").set_defaults(fn=cmd_off)
    sub.add_parser("save", help="grava o chassi e o botão power no firmware").set_defaults(fn=cmd_save)
    sub.add_parser("daemon", help="reaplica no login e ao voltar da suspensão").set_defaults(fn=cmd_daemon)
    sub.add_parser("gui", help="abre a interface gráfica").set_defaults(fn=cmd_gui)
    sub.add_parser("udev-rule", help="imprime a regra udev para acesso sem root").set_defaults(fn=cmd_udev_rule)
    sub.add_parser("version", help="mostra a versão").set_defaults(fn=cmd_version)

    z = sub.add_parser("zone", help="trackpad/logo: modo e cores")
    z.add_argument("zone", choices=ZONE_CHOICES)
    z.add_argument("mode", choices=elc.MODES)
    z.add_argument("color", nargs="?")
    z.add_argument("color2", nargs="?")
    z.add_argument("--speed", type=int, choices=range(1, 11), metavar="1-10")
    z.set_defaults(fn=cmd_zone)

    pw = sub.add_parser("power", help="cores do botão power (grava no firmware)")
    pw.add_argument("--ac", help="cor na tomada")
    pw.add_argument("--battery", help="cor na bateria")
    pw.set_defaults(fn=cmd_power)

    b = sub.add_parser("brightness", help="brilho de 0 a 100")
    b.add_argument("--keyboard", "-k", type=int, choices=range(0, 101), metavar="0-100")
    b.add_argument("--chassis", "-c", type=int, choices=range(0, 101), metavar="0-100")
    b.set_defaults(fn=cmd_brightness)

    kb = sub.add_parser("kb", help="teclado").add_subparsers(dest="kb_command", required=True)
    c = kb.add_parser("color", help="uma cor para o teclado inteiro")
    c.add_argument("color")
    c.add_argument("--keep-keys", action="store_true", help="mantém as cores individuais")
    c.set_defaults(fn=cmd_kb_color)
    k = kb.add_parser("key", help="cor por tecla: kb key esc=ff0000 w=00ff00 a=00ff00")
    k.add_argument("assignments", nargs="+", metavar="TECLA=COR")
    k.set_defaults(fn=cmd_kb_key)
    e = kb.add_parser("effect", help="efeito de hardware")
    e.add_argument("effect", choices=list(keyboard.EFFECTS))
    e.add_argument("color", nargs="?")
    e.add_argument("color2", nargs="?")
    e.add_argument("--speed", type=int, choices=range(1, 11), metavar="1-10")
    e.set_defaults(fn=cmd_kb_effect)
    kb.add_parser("keys", help="lista os nomes das teclas").set_defaults(fn=cmd_kb_keys)
    i = kb.add_parser("identify", help="acende um ID de LED por vez")
    i.add_argument("--start", type=int, default=0)
    i.add_argument("--end", type=int, default=layout.MAX_KEY_ID)
    i.set_defaults(fn=cmd_kb_identify)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = config.load()
    try:
        errors = args.fn(args, cfg)
    except Exception as exc:  # noqa: BLE001 - mensagem curta para o usuário
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    for err in errors or []:
        print(f"erro: {err}", file=sys.stderr)
    return 1 if errors else 0
