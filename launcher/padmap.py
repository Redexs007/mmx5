"""Leitura de controles via /dev/input/jsN (joydev) e geracao de mapeamento SDL.

O runtime so' aceita controles que o SDL reconhece como 'gamepad'. Controles genericos
('USB gamepad') nao tem mapeamento; aqui o jogador aperta cada botao e geramos a string
SDL_GAMECONTROLLERCONFIG correspondente.
"""
from __future__ import annotations

import array
import fcntl
import glob
import os
import struct
from pathlib import Path

JSIOCGAXES = 0x80016A11
JSIOCGBUTTONS = 0x80016A12
JSIOCGAXMAP = 0x80406A32      # u8[ABS_CNT=64]
JSIOCGBTNMAP = 0x84006A34     # u16[512]  (KEY_MAX - BTN_MISC + 1)

BTN_MISC, BTN_JOYSTICK = 0x100, 0x120
ABS_HAT0X, ABS_HAT3Y = 0x10, 0x17
HAT_MASK = {"up": 1, "right": 2, "down": 4, "left": 8}


def _sysfs(js: str, rel: str) -> str:
    try:
        return Path(f"/sys/class/input/{js}/device/{rel}").read_text().strip()
    except OSError:
        return ""


def list_devices() -> list[dict]:
    out = []
    for path in sorted(glob.glob("/dev/input/js*")):
        js = os.path.basename(path)
        try:
            out.append(dict(
                path=path, js=js, name=_sysfs(js, "name") or js,
                bus=int(_sysfs(js, "id/bustype") or "3", 16),
                vendor=int(_sysfs(js, "id/vendor") or "0", 16),
                product=int(_sysfs(js, "id/product") or "0", 16),
                version=int(_sysfs(js, "id/version") or "0", 16),
                readable=os.access(path, os.R_OK)))
        except ValueError:
            continue
    return out


def make_guid(bus: int, vendor: int, product: int, version: int) -> str:
    le = lambda v: struct.pack("<H", v & 0xFFFF).hex()
    return le(bus) + "0000" + le(vendor) + "0000" + le(product) + "0000" + le(version) + "0000"


class JoyDev:
    def __init__(self, path: str):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        buf = array.array("B", [0])
        fcntl.ioctl(self.fd, JSIOCGAXES, buf, True)
        self.naxes = buf[0]
        fcntl.ioctl(self.fd, JSIOCGBUTTONS, buf, True)
        self.nbuttons = buf[0]
        self.axmap = array.array("B", [0] * 64)
        fcntl.ioctl(self.fd, JSIOCGAXMAP, self.axmap, True)
        self.btnmap = array.array("H", [0] * 512)
        fcntl.ioctl(self.fd, JSIOCGBTNMAP, self.btnmap, True)
        self.rest: dict[int, int] = {}
        # ordem de botoes do SDL: codigos >= BTN_JOYSTICK primeiro, depois BTN_MISC..BTN_JOYSTICK-1
        codes = [self.btnmap[i] for i in range(self.nbuttons)]
        self.sdl_buttons = sorted(c for c in codes if c >= BTN_JOYSTICK) + \
            sorted(c for c in codes if BTN_MISC <= c < BTN_JOYSTICK)
        axes = [self.axmap[i] for i in range(self.naxes)]
        self.sdl_axes = sorted(c for c in axes if not (ABS_HAT0X <= c <= ABS_HAT3Y))

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass

    def events(self):
        while True:
            try:
                data = os.read(self.fd, 8)
            except BlockingIOError:
                return
            except OSError:
                return
            if len(data) < 8:
                return
            _t, value, typ, number = struct.unpack("IhBB", data)
            init = bool(typ & 0x80)
            typ &= 0x7F
            if typ == 2 and init:
                self.rest[number] = value
                continue
            if typ == 1 and init:
                continue
            yield typ, number, value

    # --- traducao joydev -> SDL
    def describe(self, typ: int, number: int, value: int) -> dict | None:
        """Devolve {'kind': 'b'|'a'|'h', ...} no vocabulario do SDL."""
        if typ == 1:
            if number >= self.nbuttons:
                return None
            code = self.btnmap[number]
            if code not in self.sdl_buttons:
                return None
            return dict(kind="b", idx=self.sdl_buttons.index(code), js=number)
        if typ == 2:
            if number >= self.naxes:
                return None
            code = self.axmap[number]
            rest = self.rest.get(number, 0)
            if ABS_HAT0X <= code <= ABS_HAT3Y:
                hat, is_y = (code - ABS_HAT0X) // 2, (code - ABS_HAT0X) % 2
                if value == 0:
                    return None
                name = ("up" if value < 0 else "down") if is_y else ("left" if value < 0 else "right")
                return dict(kind="h", idx=hat, mask=HAT_MASK[name], js=number, sign=1 if value > 0 else -1)
            if code not in self.sdl_axes:
                return None
            return dict(kind="a", idx=self.sdl_axes.index(code), js=number,
                        sign=1 if value - rest > 0 else -1, rest=rest)
        return None


def src_string(d: dict, role: str) -> str:
    """role: 'button' | 'trigger' | 'stick' -> pedaco do mapeamento SDL."""
    k = d["kind"]
    if k == "b":
        return f"b{d['idx']}"
    if k == "h":
        return f"h{d['idx']}.{d['mask']}"
    sign = d["sign"]
    if role == "stick":
        return f"a{d['idx']}" + ("" if sign > 0 else "~")
    if role == "trigger" and d.get("rest", 0) < -20000:
        return f"a{d['idx']}"
    return ("+" if sign > 0 else "-") + f"a{d['idx']}"


def build_mapping(guid: str, name: str, assigns: dict[str, str]) -> str:
    parts = [guid, name.replace(",", " "), "platform:Linux"]
    parts += [f"{k}:{v}" for k, v in assigns.items()]
    return ",".join(parts)
