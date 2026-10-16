"""Interface gráfica GTK3 do awlight."""

import copy
import math
import queue
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import config, control, layout  # noqa: E402

KB_MODES = [
    ("per-key", "Por tecla"), ("static", "Estático"), ("breathing", "Respiração"),
    ("wave", "Onda"), ("dual-wave", "Onda dupla"), ("pulse", "Pulso"), ("morph", "Morph"),
    ("bounce", "Bounce"), ("laser", "Laser"), ("rainbow", "Arco-íris"),
]
ZONE_MODES = [
    ("color", "Cor fixa"), ("pulse", "Pulso"), ("morph", "Morph (2 cores)"),
    ("breathing", "Respiração"), ("spectrum", "Espectro"), ("off", "Desligado"),
]
UNIT = 46  # pixels por unidade de tecla


def _rgba(hex_color: str) -> Gdk.RGBA:
    c = Gdk.RGBA()
    c.parse(hex_color)
    return c


def _hex(rgba: Gdk.RGBA) -> str:
    return config.format_color(tuple(round(v * 255) for v in (rgba.red, rgba.green, rgba.blue)))


class Worker:
    """Fila de aplicação: cada alvo guarda só o pedido mais recente."""

    def __init__(self, on_result):
        self._pending = {}
        self._lock = threading.Lock()
        self._wake = queue.Queue()
        self._on_result = on_result
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, target, fn, cfg):
        with self._lock:
            self._pending[target] = (fn, copy.deepcopy(cfg))
        self._wake.put(None)

    def _run(self):
        while True:
            self._wake.get()
            while True:
                with self._lock:
                    if not self._pending:
                        break
                    target, (fn, cfg) = self._pending.popitem()
                try:
                    msg = fn(cfg)
                    GLib.idle_add(self._on_result, target, None, msg)
                except Exception as exc:  # noqa: BLE001
                    GLib.idle_add(self._on_result, target, str(exc), None)


class KeyboardView(Gtk.DrawingArea):
    def __init__(self, window):
        super().__init__()
        self.win = window
        width = max(k.x + k.w for k in layout.KEYS)
        height = max(k.y + k.h for k in layout.KEYS)
        self.set_size_request(int(width * UNIT) + 24, int(height * UNIT) + 24)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON1_MOTION_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("motion-notify-event", self._motion)
        self._last_painted = None

    def _key_at(self, x, y):
        ox, oy = self._origin()
        ux, uy = (x - ox) / UNIT, (y - oy) / UNIT
        for k in layout.KEYS:
            if k.x <= ux < k.x + k.w and k.y <= uy < k.y + k.h:
                return k
        return None

    def _origin(self):
        alloc = self.get_allocation()
        width = max(k.x + k.w for k in layout.KEYS) * UNIT
        return max(12, (alloc.width - width) / 2), 12

    def _press(self, _w, event):
        key = self._key_at(event.x, event.y)
        if key:
            self._last_painted = key.name
            self.win.paint_key(key, erase=event.button == 3)

    def _motion(self, _w, event):
        key = self._key_at(event.x, event.y)
        if key and key.name != self._last_painted:
            self._last_painted = key.name
            self.win.paint_key(key, erase=False)

    def _draw(self, _w, cr):
        kb = self.win.cfg["keyboard"]
        per_key = kb["mode"] == "per-key"
        base = kb["color"]
        overrides = kb.get("keys", {})
        ox, oy = self._origin()
        for k in layout.KEYS:
            color = overrides.get(k.name, base) if per_key else base
            r, g, b = (v / 255 for v in config.parse_color(color))
            x, y = ox + k.x * UNIT + 2, oy + k.y * UNIT + 2
            w, h = k.w * UNIT - 4, k.h * UNIT - 4
            self._rounded(cr, x, y, w, h, 6)
            cr.set_source_rgb(0.13, 0.13, 0.15)
            cr.fill_preserve()
            cr.set_source_rgba(r, g, b, 0.9 if per_key else 0.45)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.15)
            cr.set_line_width(1)
            cr.stroke()
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            cr.set_source_rgb(*((0.05,) * 3 if lum > 0.55 else (0.92,) * 3))
            text = PangoCairo.create_layout(cr)
            text.set_font_description(Pango.FontDescription.from_string("Sans 9" if k.h >= 1 else "Sans 8"))
            text.set_text(k.label, -1)
            tw, th = text.get_pixel_size()
            cr.move_to(x + (w - tw) / 2, y + (h - th) / 2)
            PangoCairo.show_layout(cr, text)

    @staticmethod
    def _rounded(cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="AW Light")
        self.set_default_size(820, 560)
        self.cfg = config.load()
        self.worker = Worker(self._on_result)
        self._timers = {}
        self._loading = True

        header = Gtk.HeaderBar(show_close_button=True, title="AW Light", subtitle="Alienware m16 R2")
        self.set_titlebar(header)
        off_btn = Gtk.Button(label="Desligar tudo")
        off_btn.connect("clicked", lambda _b: self._submit("all", self._turn_off))
        header.pack_start(off_btn)
        apply_btn = Gtk.Button(label="Reaplicar")
        apply_btn.connect("clicked", lambda _b: self._submit("all", self._apply_all))
        header.pack_start(apply_btn)

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        stack.add_titled(self._keyboard_page(), "keyboard", "Teclado")
        stack.add_titled(self._chassis_page(), "chassis", "Chassi")
        header.set_custom_title(Gtk.StackSwitcher(stack=stack))

        self.status = Gtk.Label(xalign=0, margin=8)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(stack, True, True, 0)
        box.pack_start(Gtk.Separator(), False, False, 0)
        box.pack_start(self.status, False, False, 0)
        self.add(box)
        self._loading = False
        self._sync_kb_sensitivity()

    # -- auxiliares de widgets ------------------------------------------
    @staticmethod
    def _combo(options, active):
        combo = Gtk.ComboBoxText()
        for key, label in options:
            combo.append(key, label)
        combo.set_active_id(active)
        return combo

    @staticmethod
    def _scale(lo, hi, value):
        s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        s.set_value(value)
        s.set_hexpand(True)
        s.set_digits(0)
        return s

    @staticmethod
    def _grid():
        return Gtk.Grid(column_spacing=12, row_spacing=8, margin=12)

    @staticmethod
    def _label(text):
        return Gtk.Label(label=text, xalign=1)

    # -- teclado ---------------------------------------------------------
    def _keyboard_page(self):
        kb = self.cfg["keyboard"]
        grid = self._grid()

        self.kb_mode = self._combo(KB_MODES, kb["mode"])
        self.kb_mode.connect("changed", self._on_kb_mode)
        self.kb_color = Gtk.ColorButton(rgba=_rgba(kb["color"]), title="Cor base")
        self.kb_color.connect("color-set", self._on_kb_color)
        self.kb_color2 = Gtk.ColorButton(rgba=_rgba(kb["color2"]), title="Cor 2")
        self.kb_color2.connect("color-set", self._on_kb_color2)
        self.kb_speed = self._scale(1, 10, kb["speed"])
        self.kb_speed.connect("value-changed", self._on_kb_speed)
        self.kb_bright = self._scale(0, 100, kb["brightness"])
        self.kb_bright.connect("value-changed", self._on_kb_bright)

        grid.attach(self._label("Modo"), 0, 0, 1, 1)
        grid.attach(self.kb_mode, 1, 0, 1, 1)
        grid.attach(self._label("Cor base"), 2, 0, 1, 1)
        grid.attach(self.kb_color, 3, 0, 1, 1)
        grid.attach(self._label("Cor 2"), 4, 0, 1, 1)
        grid.attach(self.kb_color2, 5, 0, 1, 1)
        grid.attach(self._label("Velocidade"), 0, 1, 1, 1)
        grid.attach(self.kb_speed, 1, 1, 2, 1)
        grid.attach(self._label("Brilho"), 3, 1, 1, 1)
        grid.attach(self.kb_bright, 4, 1, 2, 1)

        self.brush = Gtk.ColorButton(rgba=_rgba("#ff0000"), title="Pincel")
        clear = Gtk.Button(label="Limpar cores individuais")
        clear.connect("clicked", self._on_clear_keys)
        self.paint_bar = Gtk.Box(spacing=8)
        self.paint_bar.pack_start(Gtk.Label(label="Pincel"), False, False, 0)
        self.paint_bar.pack_start(self.brush, False, False, 0)
        self.paint_bar.pack_start(
            Gtk.Label(label="clique ou arraste para pintar · botão direito volta à cor base"),
            False, False, 0)
        self.paint_bar.pack_end(clear, False, False, 0)
        grid.attach(self.paint_bar, 0, 2, 6, 1)

        self.kb_view = KeyboardView(self)
        self.kb_view.set_hexpand(True)
        self.kb_view.set_vexpand(True)
        grid.attach(self.kb_view, 0, 3, 6, 1)
        return grid

    def _sync_kb_sensitivity(self):
        per_key = self.cfg["keyboard"]["mode"] == "per-key"
        self.paint_bar.set_sensitive(per_key)
        self.kb_speed.set_sensitive(not per_key)
        self.kb_color2.set_sensitive(self.cfg["keyboard"]["mode"] in ("dual-wave", "morph", "bounce"))
        self.kb_view.queue_draw()

    def _kb_changed(self, delay=120):
        if self._loading:
            return
        config.save(self.cfg)
        self._sync_kb_sensitivity()
        self._debounce("keyboard", lambda: self._submit("keyboard", control.apply_keyboard), delay)

    def _on_kb_mode(self, combo):
        self.cfg["keyboard"]["mode"] = combo.get_active_id()
        self._kb_changed(0)

    def _on_kb_color(self, btn):
        self.cfg["keyboard"]["color"] = _hex(btn.get_rgba())
        self._kb_changed()

    def _on_kb_color2(self, btn):
        self.cfg["keyboard"]["color2"] = _hex(btn.get_rgba())
        self._kb_changed()

    def _on_kb_speed(self, scale):
        self.cfg["keyboard"]["speed"] = int(scale.get_value())
        self._kb_changed(300)

    def _on_kb_bright(self, scale):
        self.cfg["keyboard"]["brightness"] = int(scale.get_value())
        self._kb_changed(200)

    def _on_clear_keys(self, _btn):
        self.cfg["keyboard"]["keys"] = {}
        self._kb_changed(0)

    def paint_key(self, key, erase):
        if self.cfg["keyboard"]["mode"] != "per-key":
            return
        keys = self.cfg["keyboard"].setdefault("keys", {})
        if erase:
            keys.pop(key.name, None)
        else:
            keys[key.name] = _hex(self.brush.get_rgba())
        self._kb_changed(60)

    # -- chassi ----------------------------------------------------------
    def _chassis_page(self):
        ch = self.cfg["chassis"]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)

        for name, (_zid, title) in layout.ZONES.items():
            z = ch["zones"][name]
            frame = Gtk.Frame(label=title, margin=6)
            grid = self._grid()
            mode = self._combo(ZONE_MODES, z["mode"])
            c1 = Gtk.ColorButton(rgba=_rgba(z["color"]), title="Cor")
            c2 = Gtk.ColorButton(rgba=_rgba(z["color2"]), title="Cor 2")
            speed = self._scale(1, 10, z["speed"])
            mode.connect("changed", lambda w, n=name: self._zone_set(n, "mode", w.get_active_id(), 0))
            c1.connect("color-set", lambda w, n=name: self._zone_set(n, "color", _hex(w.get_rgba())))
            c2.connect("color-set", lambda w, n=name: self._zone_set(n, "color2", _hex(w.get_rgba())))
            speed.connect("value-changed", lambda w, n=name: self._zone_set(n, "speed", int(w.get_value()), 400))
            for col, widget in enumerate([self._label("Modo"), mode, self._label("Cor"), c1,
                                          self._label("Cor 2"), c2]):
                grid.attach(widget, col, 0, 1, 1)
            grid.attach(self._label("Velocidade"), 0, 1, 1, 1)
            grid.attach(speed, 1, 1, 5, 1)
            frame.add(grid)
            box.pack_start(frame, False, False, 0)

        frame = Gtk.Frame(label="Botão power", margin=6)
        grid = self._grid()
        self.pw_ac = Gtk.ColorButton(rgba=_rgba(ch["power"]["ac"]), title="Na tomada")
        self.pw_bat = Gtk.ColorButton(rgba=_rgba(ch["power"]["battery"]), title="Na bateria")
        pw_apply = Gtk.Button(label="Aplicar no botão power")
        pw_apply.connect("clicked", self._on_power_apply)
        grid.attach(self._label("Na tomada"), 0, 0, 1, 1)
        grid.attach(self.pw_ac, 1, 0, 1, 1)
        grid.attach(self._label("Na bateria"), 2, 0, 1, 1)
        grid.attach(self.pw_bat, 3, 0, 1, 1)
        grid.attach(pw_apply, 4, 0, 1, 1)
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_markup("<small>O firmware troca a cor sozinho conforme tomada, bateria e suspensão. "
                        "Essas cores ficam gravadas no controlador.</small>")
        grid.attach(hint, 0, 1, 5, 1)
        frame.add(grid)
        box.pack_start(frame, False, False, 0)

        bottom = self._grid()
        self.ch_bright = self._scale(0, 100, ch["brightness"])
        self.ch_bright.connect("value-changed", self._on_ch_bright)
        save = Gtk.Button(label="Gravar como padrão do firmware")
        save.set_tooltip_text("Faz o trackpad e a logo acenderem com estas cores desde o boot")
        save.connect("clicked", self._on_save_firmware)
        bottom.attach(self._label("Brilho"), 0, 0, 1, 1)
        bottom.attach(self.ch_bright, 1, 0, 1, 1)
        bottom.attach(save, 2, 0, 1, 1)
        box.pack_start(bottom, False, False, 0)
        return box

    def _zone_set(self, name, field, value, delay=120):
        if self._loading:
            return
        self.cfg["chassis"]["zones"][name][field] = value
        config.save(self.cfg)
        self._debounce("chassis", lambda: self._submit("chassis", control.apply_chassis_lights), delay)

    def _on_ch_bright(self, scale):
        self.cfg["chassis"]["brightness"] = int(scale.get_value())
        config.save(self.cfg)
        self._debounce("chassis", lambda: self._submit("chassis", control.apply_chassis_lights), 200)

    def _on_power_apply(self, _btn):
        self.cfg["chassis"]["power"] = {"ac": _hex(self.pw_ac.get_rgba()),
                                        "battery": _hex(self.pw_bat.get_rgba())}
        config.save(self.cfg)
        self._submit("power", lambda c: control.apply_power(c, force=True) and "botão power gravado")

    def _on_save_firmware(self, _btn):
        def run(c):
            control.save_chassis_to_firmware(c)
            return "efeito do chassi gravado como padrão do firmware"
        self._submit("firmware", run)

    @staticmethod
    def _turn_off(c):
        errors = control.turn_off(c)
        if errors:
            raise RuntimeError("; ".join(errors))
        return "luzes apagadas (use Reaplicar para voltar)"

    @staticmethod
    def _apply_all(c):
        errors = control.apply_all(c)
        if errors:
            raise RuntimeError("; ".join(errors))
        return "configuração reaplicada"

    # -- infraestrutura --------------------------------------------------
    def _debounce(self, key, fn, delay):
        if key in self._timers:
            GLib.source_remove(self._timers.pop(key))
        if delay <= 0:
            fn()
            return

        def fire():
            self._timers.pop(key, None)
            fn()
            return GLib.SOURCE_REMOVE
        self._timers[key] = GLib.timeout_add(delay, fire)

    def _submit(self, target, fn):
        self.status.set_text("aplicando…")
        self.worker.submit(target, fn, self.cfg)

    def _on_result(self, target, error, message):
        if error:
            self.status.set_markup(f"<span foreground='#e05050'>Erro: {GLib.markup_escape_text(error)}</span>")
        else:
            self.status.set_text(message if isinstance(message, str) else "aplicado")
        return GLib.SOURCE_REMOVE


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.guilhermefeitosa66.awlight")

    def do_activate(self):
        win = self.get_active_window() or Window(self)
        win.show_all()
        win.present()


def main():
    App().run(None)
