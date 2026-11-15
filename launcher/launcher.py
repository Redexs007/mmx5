#!/usr/bin/env python3
"""
Mega Man X5 Recompiled - Launcher para Linux
============================================
Abas: JOGAR (Zero) | CONFIGURACOES (X) | INTERFACE (Sigma)

* Grava o settings.toml / mods/state.toml / input.ini que o runtime ja le.
* Inicia o runtime com --no-launcher (o launcher interno do recomp-ui nao abre).
* Preferencias do proprio launcher ficam em ~/.config/MegaManX5Recomp/launcher.json
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import shlex
import subprocess
import sys
import tomllib
import time
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QProcess, QRectF, QSize, Qt,
                            QTimer, QVariantAnimation, QPropertyAnimation, QRect, Signal)
from PySide6.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QAbstractButton, QApplication, QButtonGroup, QCheckBox,
                               QColorDialog, QComboBox, QDialog, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget)

import gpuinfo
from ui_kit import (AMBER, THEME, Card, SlantButton, Switch, SliderRow, combo, PANEL_LINE, chamfer,
                    font as ui_font, F_UI, F_MONO, F_PIX)

APP_NAME = "Mega Man X5 Recompiled"
VERSION = "1.0.0"
GAME_SERIAL = "SLUS_013.34"

# --------------------------------------------------------------------------- paths
FROZEN = getattr(sys, "frozen", False)
RES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ASSETS = RES / "assets"
BASE = (Path(sys.executable).resolve().parent if FROZEN
        else Path(__file__).resolve().parent.parent)
GAME_DIR = Path(os.environ.get("MMX5_GAME_DIR", BASE / "game"))
ART_DIR = BASE / "launcher_art"        # arte opcional do jogador (zero.png, x.png, sigma.png, art.json)
RUNTIME = GAME_DIR / "mmx5-runtime"
BUILD_SCRIPT = BASE / "build_linux.sh"
PREFS_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / \
    "MegaManX5Recomp" / "launcher.json"


def clean_env() -> dict:
    """Ambiente sem as libs do PyInstaller (senao git/xdg-open/jogo quebram)."""
    env = dict(os.environ)
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG")
    elif FROZEN:
        env.pop("LD_LIBRARY_PATH", None)
    env.update(read_launch_env())
    return env


LAUNCH_ENV = GAME_DIR / "launch.env"


def read_launch_env() -> dict:
    out = {}
    try:
        for line in LAUNCH_ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def write_launch_env(env: dict) -> None:
    write_atomic(LAUNCH_ENV, "# Variaveis de ambiente do jogo (lido pelo launcher e pelo MegaManX5-Play)\n" +
                 "".join(f"{k}={v}\n" for k, v in env.items()))



def apply_p1_device(cfg) -> str:
    """O runtime de release comeca com o jogador 1 no TECLADO; quem escolhe o controle e' o
    launcher. Como usamos --no-launcher, gravamos [controller] p1_device aqui."""
    choice = read_launch_env().get("MMX5_P1_INPUT", "auto")
    if choice == "keyboard":
        val = "keyboard"
    elif choice == "controller":
        val = "auto"
    else:
        try:
            import padmap
            val = "auto" if padmap.list_devices() else "keyboard"
        except Exception:
            val = "auto"
    cfg.set("controller", "p1_device", val)
    return val


DEFAULT_INPUT_INI = """; PSXRecomp input mapping. PSX buttons are active when any listed source is pressed.
; Sources use SDL/Xbox names: a,b,x,y,back,start,leftshoulder,rightshoulder,
; lefttrigger,righttrigger,dpup,dpdown,dpleft,dpright,leftx-/leftx+/lefty-/lefty+.

[controller]
enabled = true
device = 0
deadzone = 12000

[mapping]
up = dpup,lefty-
down = dpdown,lefty+
left = dpleft,leftx-
right = dpright,leftx+
cross = a
circle = b
square = x
triangle = y
l1 = leftshoulder
r1 = rightshoulder
l2 = lefttrigger
r2 = righttrigger
start = start
select = back
"""

MOD_PKG_WIDE = ("mmx5.enhancement.widescreen", "1.0.0", "widescreen")
MOD_PKG_INTERP = ("mmx5.enhancement.frame-interpolation", "1.0.0", "frame-interpolation")
MOD_PKG_HD = ("psx.enhancement.hd-textures", "1.0.0", "hd-textures")

# --------------------------------------------------------------------------- toml io
_BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def _key(k: str) -> str:
    return k if _BARE.match(k) else json.dumps(k)


def _val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_val(i) for i in v) + "]"
    raise TypeError(f"tipo TOML nao suportado: {type(v)}")


def _is_aot(v) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(i, dict) for i in v)


def dump_toml(data: dict, path: tuple = ()) -> str:
    out: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict) and not _is_aot(v)}
    for k, v in scalars.items():
        out.append(f"{_key(k)} = {_val(v)}")
    for k, v in data.items():
        if isinstance(v, dict):
            p = path + (k,)
            out.append("")
            out.append("[" + ".".join(_key(x) for x in p) + "]")
            out.append(dump_toml(v, p).rstrip("\n"))
        elif _is_aot(v):
            p = path + (k,)
            for item in v:
                out.append("")
                out.append("[[" + ".".join(_key(x) for x in p) + "]]")
                out.append(dump_toml(item, p).rstrip("\n"))
    return "\n".join(l for l in out).strip("\n") + "\n"


def load_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- game config
class GameConfig:
    """settings.toml + mods/state.toml + input.ini ao lado do runtime."""

    def __init__(self, gdir: Path):
        self.dir = gdir
        self.settings_path = gdir / "settings.toml"
        self.state_path = gdir / "mods" / "state.toml"
        self.input_path = gdir / "input.ini"
        self.settings = load_toml(self.settings_path)
        self.state = load_toml(self.state_path)

    # settings.toml
    def get(self, sect: str, key: str, default=None):
        return self.settings.get(sect, {}).get(key, default)

    def set(self, sect: str, key: str, value) -> None:
        self.settings.setdefault(sect, {})[key] = value

    def remove(self, sect: str, key: str) -> None:
        self.settings.get(sect, {}).pop(key, None)

    # mods/state.toml (formato 2)
    def _feature(self, pkg: str, fid: str, create=False):
        for f in self.state.get("feature", []):
            if f.get("package_id") == pkg and f.get("id") == fid:
                return f
        if not create:
            return None
        f = {"package_id": pkg, "id": fid, "enabled": False}
        self.state.setdefault("feature", []).append(f)
        return f

    def feature_enabled(self, spec) -> bool:
        f = self._feature(spec[0], spec[2])
        return bool(f and f.get("enabled"))

    def set_feature(self, spec, enabled: bool) -> None:
        self.state.setdefault("format_version", 2)
        pkgs = self.state.setdefault("package", [])
        if not any(p.get("id") == spec[0] for p in pkgs):
            pkgs.append({"id": spec[0], "version": spec[1]})
        self._feature(spec[0], spec[2], create=True)["enabled"] = enabled

    def feature_value(self, spec, name: str, default: str) -> str:
        f = self._feature(spec[0], spec[2])
        return str((f or {}).get("values", {}).get(name, default))

    def set_feature_value(self, spec, name: str, value: str) -> None:
        self.set_feature(spec, self.feature_enabled(spec))
        self._feature(spec[0], spec[2], create=True).setdefault("values", {})[name] = value

    def set_feature_resource(self, spec, rid: str, path: str) -> None:
        self.set_feature(spec, self.feature_enabled(spec))
        self._feature(spec[0], spec[2], create=True).setdefault("resources", {})[rid] = path

    def feature_resource(self, spec, rid: str, default: str = "") -> str:
        f = self._feature(spec[0], spec[2])
        return str((f or {}).get("resources", {}).get(rid, default))

    # input.ini
    def deadzone(self) -> int:
        try:
            m = re.search(r"^\s*deadzone\s*=\s*(\d+)", self.input_path.read_text(), re.M)
            return int(m.group(1)) if m else 12000
        except OSError:
            return 12000

    def set_deadzone(self, v: int) -> None:
        try:
            txt = self.input_path.read_text()
        except OSError:
            txt = DEFAULT_INPUT_INI
        if re.search(r"^\s*deadzone\s*=", txt, re.M):
            txt = re.sub(r"^(\s*deadzone\s*=\s*)\d+", rf"\g<1>{v}", txt, flags=re.M)
        else:
            txt = txt.replace("[controller]", f"[controller]\ndeadzone = {v}", 1)
        write_atomic(self.input_path, txt)

    def save(self) -> None:
        write_atomic(self.settings_path, "# Gerado pelo launcher. Pode editar a mao.\n\n" +
                     dump_toml(self.settings))
        if self.state:
            write_atomic(self.state_path, dump_toml(self.state))


# --------------------------------------------------------------------------- prefs
PREFS_DEFAULT = dict(
    accent_mode="auto", accent_color="#ff4a4a",
    bg_style="grid", glow=70, panel_opacity=80, radius=14, font_scale=100,
    art_side="right", art_scale=100, art_float=True,
    transition="slide", duration=480, parallax=True,
    on_play="keep", prefs_ver=2, win_w=1100, win_h=680,
)

PAGE_ACCENTS = ["#f2b233", "#4cc3ff", "#4cc3ff", "#5ee08a"]   # Zero, X, Mods, Sigma


def load_prefs() -> dict:
    p = dict(PREFS_DEFAULT)
    loaded: dict = {}
    try:
        loaded = json.loads(PREFS_PATH.read_text())
    except (OSError, ValueError):
        pass
    p.update(loaded)
    if loaded and loaded.get("prefs_ver", 1) < 2:   # v0.3: manter o launcher aberto p/ mostrar o resumo da partida
        p["on_play"], p["prefs_ver"] = "keep", 2
    return p


def save_prefs(p: dict) -> None:
    try:
        write_atomic(PREFS_PATH, json.dumps(p, indent=2))
    except OSError:
        pass


# --------------------------------------------------------------------------- disc check
def verify_disc(path: str) -> tuple[bool, str]:
    if not path:
        return False, "Nenhum disco selecionado"
    p = Path(path)
    if not p.exists():
        return False, "Arquivo nao encontrado"
    target = p
    if p.suffix.lower() == ".cue":
        try:
            m = re.search(r'FILE\s+"([^"]+)"', p.read_text(errors="replace"))
        except OSError:
            return False, "Nao consegui ler o .cue"
        if not m:
            return False, ".cue sem linha FILE"
        target = p.parent / m.group(1)
        if not target.exists():
            return False, f"Falta o arquivo {m.group(1)}"
    try:
        with open(target, "rb") as f:
            head = f.read(6 * 1024 * 1024)
    except OSError:
        return False, "Nao consegui ler o disco"
    if b"SLUS_013.34" not in head:
        return False, "Nao parece ser Mega Man X5 (USA, SLUS-01334)"
    if p.suffix.lower() == ".iso":
        return True, "Verificado, mas .iso 'cooked' perde os videos/audio XA. Prefira .cue + .bin"
    return True, "Mega Man X5 (USA) - SLUS-01334 verificado"


# --------------------------------------------------------------------------- small widgets
def scroll_of(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.viewport().setAutoFillBackground(False)
    sa.setStyleSheet("QScrollArea{background:transparent;}")
    inner.setAttribute(Qt.WA_TranslucentBackground, True)
    sa.setWidget(inner)
    return sa


# --------------------------------------------------------------------------- art
class ArtLabel(QWidget):
    def __init__(self, pix: QPixmap, parent=None):
        super().__init__(parent)
        self.pix = pix
        self.accent = QColor("#ffffff")
        self.float_on = True
        self.phase = 0.0
        self.caption = ("", "")
        self.align_right = True
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def tick(self, dt):
        self.phase += dt
        if self.float_on and self.isVisible():
            self.update()

    def paintEvent(self, _):
        if self.pix.isNull() or self.pix.width() < 4:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        g = QRadialGradient(w * 0.5, h * 0.55, min(w, h) * 0.55)
        c = QColor(self.accent)
        c.setAlpha(60)
        g.setColorAt(0, c)
        c.setAlpha(0)
        g.setColorAt(1, c)
        p.fillRect(self.rect(), g)
        k = min((h - 14) / self.pix.height(), w / self.pix.width())
        dw, dh = self.pix.width() * k, self.pix.height() * k
        bob = math.sin(self.phase * 1.6) * 6 if self.float_on else 0
        p.drawPixmap(QRectF((w - dw) / 2, h - dh - 6 + bob, dw, dh), self.pix, QRectF(self.pix.rect()))
        small, big = self.caption
        if big:
            al = Qt.AlignRight if self.align_right else Qt.AlignLeft
            m = 24
            p.setPen(self.accent)
            p.setFont(ui_font(F_PIX, 12, spacing=1))
            p.drawText(QRectF(m, h - 92, w - 2 * m, 20), al | Qt.AlignVCenter, small)
            p.setPen(QColor("white"))
            p.setFont(ui_font(F_UI, 44, QFont.Bold, spacing=5))
            p.drawText(QRectF(m, h - 74, w - 2 * m, 56), al | Qt.AlignVCenter, big)


# --------------------------------------------------------------------------- pages
class Page(QWidget):
    """content (painel) + art. A arte fica ATRAS do conteudo e pode sobrepor o
    painel (Sigma e' largo); o conteudo reserva so' a parte visivel."""

    def __init__(self, art_pix: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.has_art = art_pix is not None
        self.art = ArtLabel(art_pix if art_pix is not None else QPixmap(1, 1), self)
        self.content = QWidget(self)
        self.content.setAttribute(Qt.WA_TranslucentBackground, True)
        self.art.lower()
        self.lay = QHBoxLayout(self)
        self.lay.addWidget(self.content)
        self.side, self.scale = "right", 1.0
        self.relayout()

    def apply_layout(self, side: str, scale: float):
        self.side, self.scale = side, scale
        self.relayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    def relayout(self):
        W, H = self.width(), self.height()
        show = self.has_art and self.side != "hidden" and W > 200 and H > 200
        self.art.setVisible(show)
        self.art.align_right = self.side != "left"
        left, top, right, bottom = 28, 18, 28, 20
        if show:
            aspect = self.art.pix.width() / max(1, self.art.pix.height())
            art_w = min(H * aspect * self.scale, W * 0.75)
            reserve = art_w if art_w <= 440 else 440 + (art_w - 440) * 0.3
            art_w, reserve = int(art_w), int(reserve)
            if self.side == "left":
                self.art.setGeometry(0, 0, art_w, H)
                left = reserve + 18
            else:
                self.art.setGeometry(W - art_w, 0, art_w, H)
                right = reserve + 18
            self.art.lower()
        self.lay.setContentsMargins(left, top, right, bottom)
        self.lay.activate()


# --------------------------------------------------------------------------- novo visual
class Panel(QFrame):
    """Painel com cantos cortados (sem layout proprio)."""
    cut = 16.0
    paintEvent = Card.paintEvent


class PageHeader(QWidget):
    def __init__(self, caption: str, title: str, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 6)
        v.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(10)
        ln = QFrame()
        ln.setObjectName("capLine")
        ln.setFixedSize(30, 1)
        self.cap = QLabel(caption.upper())
        self.cap.setObjectName("caption")
        row.addWidget(ln, 0, Qt.AlignVCenter)
        row.addWidget(self.cap)
        row.addStretch(1)
        self.extra = row
        v.addLayout(row)
        self.title = QLabel(title)
        self.title.setObjectName("bigTitle")
        sh = QGraphicsDropShadowEffect(self.title)
        sh.setOffset(3, 3)
        sh.setBlurRadius(0)
        sh.setColor(QColor(0, 0, 0, 170))
        self.title.setGraphicsEffect(sh)
        v.addWidget(self.title)


class Chip(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("chip")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(2)
        t = QLabel(title.upper())
        t.setObjectName("chipTitle")
        self.val = QLabel("")
        self.val.setObjectName("chipVal")
        v.addWidget(t)
        v.addWidget(self.val)

    def set(self, ok, text: str, tip: str = ""):
        col = "#f2b233" if ok else ("#ff6b6b" if ok is False else "#8a96ab")
        mark = "✓ " if ok else ("✗ " if ok is False else "")
        self.val.setText(f'<span style="color:{col}">{mark}{text}</span>')
        self.setToolTip(tip)


class MemcardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Memory cards")
        self.resize(520, 320)
        v = QVBoxLayout(self)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.RichText)
        v.addWidget(self.info, 1)
        row = QHBoxLayout()
        b1 = SlantButton("Fazer backup agora", "primary")
        b1.clicked.connect(self.backup)
        b2 = SlantButton("Abrir pasta", "ghost")
        b2.clicked.connect(lambda: subprocess.Popen(["xdg-open", str(GAME_DIR)], env=clean_env(),
                                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        v.addLayout(row)
        self.refresh()

    def cards(self):
        pats = ("*.mcd", "*.mcr", "*.mc", "*.mcc", "*.gme", "*memcard*", "*memory_card*")
        seen = {}
        for pat in pats:
            for f in GAME_DIR.glob(pat):
                if f.is_file():
                    seen[f] = f.stat().st_size
        return seen

    def refresh(self):
        c = self.cards()
        if not c:
            self.info.setText("Nenhum memory card encontrado ainda.<br>Ele é criado quando o jogo salva "
                              "pela primeira vez (fica na pasta do jogo).")
        else:
            self.info.setText("<b>Memory cards encontrados:</b><br>" + "<br>".join(
                f"• {f.name} ({s // 1024} KB)" for f, s in sorted(c.items())))

    def backup(self):
        import shutil
        import time
        c = self.cards()
        if not c:
            QMessageBox.information(self, APP_NAME, "Nada para copiar ainda.")
            return
        dst = GAME_DIR / "backups" / time.strftime("%Y%m%d-%H%M%S")
        dst.mkdir(parents=True, exist_ok=True)
        for f in c:
            shutil.copy2(f, dst / f.name)
        QMessageBox.information(self, APP_NAME, f"Backup salvo em:\n{dst}")


class PlayPage(Page):
    play_clicked = Signal()
    settings_changed = Signal()

    def __init__(self, cfg: GameConfig, art: QPixmap):
        super().__init__(art)
        self.cfg = cfg
        v = QVBoxLayout(self.content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addWidget(PageHeader("Recompilado · Linux · SLUS-01334", "MEGA MAN X5"))

        card = Card("Disco do jogo")
        self.disc_edit = QLineEdit(cfg.get("disc", "path", ""))
        self.disc_edit.setReadOnly(True)
        self.disc_edit.setPlaceholderText("Selecione o .cue do seu disco de Mega Man X5 (USA)")
        self.disc_edit.setFixedHeight(40)
        b = SlantButton("Procurar", "primary")
        b.clicked.connect(self.pick_disc)
        hb = QHBoxLayout()
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(10)
        hb.addWidget(self.disc_edit, 1)
        hb.addWidget(b)
        w = QWidget()
        w.setLayout(hb)
        card.full(w)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chip_img, self.chip_id, self.chip_rt = Chip("Imagem"), Chip("ID"), Chip("Runtime")
        for c in (self.chip_img, self.chip_id, self.chip_rt):
            chips.addWidget(c, 1)
        cw = QWidget()
        cw.setLayout(chips)
        card.grid.setRowMinimumHeight(card._r, 10)
        card._r += 1
        card.full(cw)
        v.addWidget(card)
        self.hint = QLabel("")
        self.hint.setObjectName("status")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)
        self.run_info = QLabel("")
        self.run_info.setObjectName("status")
        self.run_info.setWordWrap(True)
        self.run_info.setTextFormat(Qt.RichText)
        v.addWidget(self.run_info)

        v.addStretch(1)
        ps = QLabel("▸ PRESS START")
        ps.setObjectName("pressStart")
        v.addWidget(ps)
        self.play_btn = SlantButton("READY?", "play")
        self.play_btn.clicked.connect(self.play_clicked)
        v.addWidget(self.play_btn)

        row = QHBoxLayout()
        row.setSpacing(8)
        for text, fn in (("Criar atalho no menu", self.make_shortcut), ("Pasta de saves", self.open_saves),
                         ("Memory card", self.open_memcards)):
            bt = SlantButton(text, "ghost")
            bt.clicked.connect(fn)
            row.addWidget(bt)
        row.addStretch(1)
        v.addLayout(row)
        self.refresh()

    def refresh(self):
        txt = self.disc_edit.text()
        ok, msg = verify_disc(txt)
        self.disc_ok = ok
        if not txt:
            self.chip_img.set(None, "Nenhum disco")
            self.chip_id.set(None, "—")
        elif ok:
            self.chip_img.set(True, "Mega Man X5 (USA)", msg)
            self.chip_id.set(True, "SLUS-01334", msg)
        else:
            self.chip_img.set(False, "Inválida", msg)
            self.chip_id.set(False, "Não confere", msg)
        self.rt_ok = RUNTIME.exists()
        if self.rt_ok:
            self.chip_rt.set(True, "Compilado")
            self.play_btn.setText("READY?")
            self.hint.setText("")
        else:
            self.chip_rt.set(False, "Não compilado")
            self.play_btn.setText("COMPILAR")
            self.hint.setText("Selecione o disco e clique em COMPILAR (demora e precisa de internet).")
        if ok and "iso" in msg.lower() and "cooked" in msg.lower():
            self.hint.setText(msg)

    def refresh_run_info(self):
        ds = hd_disk_state(GAME_DIR)
        try:
            has = "HD textures" in (GAME_DIR / "last_run.log").read_text(errors="replace")
        except OSError:
            has = False
        parts = []
        if ds["present"] or has:
            pack = Path(ds["pack"]) if ds["pack"] else MODS_DIR / "hd-texturas"
            parts.append(hd_run_report(pack))
        rr = render_report()
        if rr:
            parts.append(rr)
        self.run_info.setText("<br>".join(p for p in parts if p))

    def pick_disc(self):
        f, _ = QFileDialog.getOpenFileName(self, "Disco de Mega Man X5 (USA)",
                                           str(Path(self.disc_edit.text() or Path.home()).parent),
                                           "Imagens de disco (*.cue *.bin *.iso);;Todos (*)")
        if f:
            self.disc_edit.setText(f)
            self.cfg.set("disc", "path", f)
            self.settings_changed.emit()
            self.refresh()

    def open_saves(self):
        GAME_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(GAME_DIR)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=clean_env())

    def open_memcards(self):
        MemcardDialog(self).exec()

    def make_shortcut(self):
        play = BASE / "MegaManX5-Play"
        icon = ASSETS / "icon.png"
        d = Path.home() / ".local/share/applications"
        d.mkdir(parents=True, exist_ok=True)
        entries = {
            "mmx5-launcher.desktop": (APP_NAME + " (Launcher)", str(BASE / "MegaManX5-Launcher")),
            "mmx5-play.desktop": (APP_NAME + " (Jogar direto)", str(play)),
        }
        for fn, (name, exe) in entries.items():
            (d / fn).write_text(
                "[Desktop Entry]\nType=Application\n"
                f"Name={name}\nExec={shlex.quote(exe)}\nIcon={icon}\n"
                f"Path={BASE}\nCategories=Game;\nTerminal=false\n")
        QMessageBox.information(self, APP_NAME,
                                "Atalhos criados no menu de aplicativos:\n"
                                "• Launcher\n• Jogar direto (sem launcher)")


PAD_JSON = GAME_DIR / "controller_mapping.json"
WIZ_STEPS = [
    ("dpup", "Direcional  ↑  (cima)", "button"), ("dpdown", "Direcional  ↓  (baixo)", "button"),
    ("dpleft", "Direcional  ←  (esquerda)", "button"), ("dpright", "Direcional  →  (direita)", "button"),
    ("a", "Botão  ✕  (Cross) — o principal", "button"), ("b", "Botão  ○  (Circle)", "button"),
    ("x", "Botão  □  (Square)", "button"), ("y", "Botão  △  (Triangle)", "button"),
    ("leftshoulder", "Botão  L1", "button"), ("rightshoulder", "Botão  R1", "button"),
    ("lefttrigger", "Botão  L2", "trigger"), ("righttrigger", "Botão  R2", "trigger"),
    ("back", "Botão  SELECT", "button"), ("start", "Botão  START", "button"),
    ("leftx", "Analógico esquerdo: empurre para a DIREITA", "stick"),
    ("lefty", "Analógico esquerdo: empurre para BAIXO", "stick"),
]


class ControllerWizard(QDialog):
    saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar controle")
        self.resize(560, 360)
        self.dev = None
        self.info = None
        v = QVBoxLayout(self)
        v.setSpacing(12)
        self.title = QLabel("")
        self.title.setObjectName("pageTitle")
        self.title.setWordWrap(True)
        self.sub = QLabel("")
        self.sub.setObjectName("hint")
        self.sub.setWordWrap(True)
        self.sub.setTextFormat(Qt.RichText)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMaximumHeight(90)
        self.out.hide()
        self.devbox = None
        v.addWidget(self.title)
        v.addWidget(self.sub)
        v.addWidget(self.out)
        v.addStretch(1)
        row = QHBoxLayout()
        self.b_back = SlantButton("Voltar", "ghost")
        self.b_skip = SlantButton("Pular", "ghost")
        self.b_cancel = SlantButton("Cancelar", "ghost")
        self.b_save = SlantButton("Salvar", "primary")
        self.b_back.clicked.connect(self.back)
        self.b_skip.clicked.connect(self.skip)
        self.b_cancel.clicked.connect(self.reject)
        self.b_save.clicked.connect(self.save)
        for b in (self.b_back, self.b_skip, self.b_cancel, self.b_save):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self.poll)
        self.i = 0
        self.assigns = {}
        self.raw = {}
        self.wait_release = None
        self.block_until = 0.0
        self.begin()

    def begin(self):
        import padmap
        devs = padmap.list_devices()
        self.b_save.hide()
        self.out.hide()
        if not devs:
            self.title.setText("Nenhum controle encontrado")
            self.sub.setText("O Linux não mostra nenhum /dev/input/js*. Conecte o controle e, se continuar "
                             "assim, rode <b>sudo modprobe joydev</b> no terminal.")
            self.b_skip.hide()
            self.b_back.hide()
            return
        self.info = next((d for d in devs if d["readable"]), devs[0])
        if not self.info["readable"]:
            self.title.setText("Sem permissão para ler o controle")
            self.sub.setText("Rode <b>sudo usermod -aG input $USER</b>, reinicie a sessão e tente de novo.")
            self.b_skip.hide()
            self.b_back.hide()
            return
        try:
            self.dev = padmap.JoyDev(self.info["path"])
        except OSError as e:
            self.title.setText("Não consegui abrir o controle")
            self.sub.setText(str(e))
            return
        self.i, self.assigns, self.raw = 0, {}, {}
        self.block_until = time.monotonic() + 0.8
        self.timer.start()
        self.show_step()

    def show_step(self):
        if self.i >= len(WIZ_STEPS):
            self.finish()
            return
        name, text, _role = WIZ_STEPS[self.i]
        self.title.setText(text)
        self.sub.setText(f'<span style="color:#f2b233">Passo {self.i + 1} de {len(WIZ_STEPS)}</span> · '
                         f'controle: <b>{self.info["name"]}</b><br>Aperte o botão no controle. '
                         f'Se ele não existir, clique em <b>Pular</b>.')
        self.b_back.setEnabled(self.i > 0)

    def poll(self):
        if not self.dev or self.i >= len(WIZ_STEPS):
            return
        now = time.monotonic()
        name, _text, role = WIZ_STEPS[self.i]
        for typ, num, val in self.dev.events():
            if typ == 2 and num not in self.dev.rest:
                self.dev.rest[num] = val
                continue
            rest = self.dev.rest.get(num, 0) if typ == 2 else 0
            if self.wait_release is not None:
                if self.wait_release == (typ, num) and ((typ == 1 and val == 0) or
                                                        (typ == 2 and abs(val - rest) < 8000)):
                    self.wait_release = None
                continue
            if now < self.block_until:
                continue
            active = (typ == 1 and val == 1) or (typ == 2 and abs(val - rest) > 16000)
            if not active:
                continue
            d = self.dev.describe(typ, num, val)
            if d is None or (role == "stick" and d["kind"] != "a"):
                continue
            import padmap
            self.assigns[name] = padmap.src_string(d, role)
            self.raw[name] = dict(typ=typ, num=num, sign=d.get("sign", 1))
            self.wait_release = (typ, num)
            self.i += 1
            self.block_until = now + 0.35
            self.show_step()
            break

    def skip(self):
        self.i += 1
        self.wait_release = None
        self.block_until = time.monotonic() + 0.3
        self.show_step()

    def back(self):
        if self.i > 0:
            self.i -= 1
            n = WIZ_STEPS[self.i][0]
            self.assigns.pop(n, None)
            self.raw.pop(n, None)
            self.wait_release = None
            self.block_until = time.monotonic() + 0.3
            self.show_step()

    def finish(self):
        import padmap
        self.timer.stop()
        i = self.info
        guid = padmap.make_guid(i["bus"], i["vendor"], i["product"], i["version"])
        self.mapping = padmap.build_mapping(guid, i["name"], self.assigns)
        self.title.setText("Pronto!")
        miss = [n for n in ("a", "b", "start") if n not in self.assigns]
        warn = ('<br><span style="color:#ffcc66">Faltaram botões importantes (' + ", ".join(miss) +
                ').</span>') if miss else ""
        self.sub.setText(f"Mapeamento criado com {len(self.assigns)} botões/eixos. Clique em Salvar e depois "
                         f"em <b>Testar</b> para conferir.{warn}")
        self.out.setPlainText(self.mapping)
        self.out.show()
        self.b_skip.hide()
        self.b_save.show()

    def save(self):
        env = read_launch_env()
        env["SDL_GAMECONTROLLERCONFIG"] = self.mapping
        write_launch_env(env)
        i = self.info
        write_atomic(PAD_JSON, json.dumps(dict(name=i["name"], path=i["path"], vendor=i["vendor"],
                                               product=i["product"], assigns=self.assigns, raw=self.raw,
                                               mapping=self.mapping), indent=1))
        self.saved.emit()
        self.accept()

    def done(self, r):
        self.timer.stop()
        if self.dev:
            self.dev.close()
        super().done(r)


class ControllerTestDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Testar controle")
        self.resize(560, 380)
        v = QVBoxLayout(self)
        self.lbl = QLabel("")
        self.lbl.setObjectName("hint")
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        grid = QGridLayout()
        self.cells = {}
        for k, (name, text, _r) in enumerate(WIZ_STEPS):
            lab = QLabel(text.replace("Botão  ", "").replace("Direcional  ", "").split(" — ")[0].split(":")[0])
            lab.setAlignment(Qt.AlignCenter)
            lab.setMinimumHeight(34)
            lab.setStyleSheet("background:rgba(255,255,255,18);")
            self.cells[name] = lab
            grid.addWidget(lab, k // 4, k % 4)
        v.addLayout(grid)
        self.raw_lbl = QLabel("")
        self.raw_lbl.setObjectName("hint")
        v.addWidget(self.raw_lbl)
        v.addStretch(1)
        self.dev = None
        self.map = {}
        self.state = {}
        try:
            data = json.loads(PAD_JSON.read_text())
            self.map = data["raw"]
            import padmap
            self.dev = padmap.JoyDev(data["path"])
            self.lbl.setText(f"Controle: <b>{data['name']}</b>. Aperte os botões: os quadros acendem.")
            self.lbl.setTextFormat(Qt.RichText)
        except (OSError, ValueError, KeyError):
            self.lbl.setText("Nenhum mapeamento salvo (ou o controle está desconectado). "
                             "Use 'Configurar controle' primeiro.")
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def poll(self):
        if not self.dev:
            return
        for typ, num, val in self.dev.events():
            if typ == 2 and num not in self.dev.rest:
                self.dev.rest[num] = val
                continue
            self.state[(typ, num)] = val
            self.raw_lbl.setText(f"último evento: {'botão' if typ == 1 else 'eixo'} {num} = {val}")
        for name, r in self.map.items():
            val = self.state.get((r["typ"], r["num"]), 0)
            if r["typ"] == 1:
                on = val == 1
            else:
                rest = self.dev.rest.get(r["num"], 0)
                on = abs(val - rest) > 16000 and ((val - rest) > 0) == (r["sign"] > 0)
            self.cells[name].setStyleSheet(
                "background:#f2b233;color:#10141c;font-weight:700;" if on else "background:rgba(255,255,255,18);")

    def done(self, r):
        self.timer.stop()
        if self.dev:
            self.dev.close()
        super().done(r)


class LogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log do último jogo")
        self.resize(760, 460)
        v = QVBoxLayout(self)
        self.box = QPlainTextEdit()
        self.box.setReadOnly(True)
        self.box.setStyleSheet("font-family:'Share Tech Mono',monospace;")
        v.addWidget(self.box)
        row = QHBoxLayout()
        b1 = SlantButton("Só linhas de vídeo/controle", "ghost")
        b2 = SlantButton("Tudo", "ghost")
        b3 = SlantButton("Copiar", "primary")
        b1.clicked.connect(lambda: self.load(True))
        b2.clicked.connect(lambda: self.load(False))
        b3.clicked.connect(lambda: QApplication.clipboard().setText(self.box.toPlainText()))
        for b in (b1, b2, b3):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.load(False)

    def load(self, only):
        try:
            lines = (GAME_DIR / "last_run.log").read_text(errors="replace").splitlines()
        except OSError:
            self.box.setPlainText("Ainda não há log. Abra o jogo uma vez pelo launcher (ou pelo MegaManX5-Play).")
            return
        if only:
            keys = ("scale", "resolution", "renderer", "opengl", "gl ", "filter", "xbr", "controller",
                    "gamepad", "joystick", "pad", "input", "sdl", "error", "warn", "fail")
            lines = [l for l in lines if any(k in l.lower() for k in keys)]
        self.box.setPlainText("\n".join(lines[-400:]) or "(nenhuma linha encontrada)")
        self.box.verticalScrollBar().setValue(self.box.verticalScrollBar().maximum())


def make_report() -> str:
    """Relatorio de diagnostico para abrir um bug (com o caminho da home escondido)."""
    import platform
    home = str(Path.home())

    def rd(p: Path, tail: int = 0) -> str:
        try:
            t = p.read_text(errors="replace")
        except OSError:
            return "(nao encontrado)"
        if tail:
            t = "\n".join(t.splitlines()[-tail:])
        return t.replace(home, "~")

    osr = {}
    try:
        for ln in Path("/etc/os-release").read_text().splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                osr[k] = v.strip('"')
    except OSError:
        pass
    gpus = gpuinfo.list_gpus()
    vk_ok, vk_msg = gpuinfo.vulkan_available()
    env = {k: v for k, v in read_launch_env().items() if k != "SDL_GAMECONTROLLERCONFIG"}
    out = [f"== {APP_NAME} v{VERSION}",
           f"Sistema: {osr.get('PRETTY_NAME', platform.platform())} / kernel {platform.release()}",
           f"Sessao: {os.environ.get('XDG_SESSION_TYPE', '?')} / {os.environ.get('XDG_CURRENT_DESKTOP', '?')}",
           "GPUs: " + ("; ".join(f"{g['name']} ({g['kind']}, {g['driver']})" for g in gpus) or "nenhuma detectada"),
           f"Vulkan: {vk_ok} - {vk_msg}", f"Runtime compilado: {RUNTIME.exists()}",
           "Framework: " + rd(BASE / "project" / ".framework-ref").strip(),
           f"launch.env (sem mapeamento de controle): {env}", "",
           "== settings.toml", rd(GAME_DIR / "settings.toml"), "",
           "== mods/state.toml", rd(GAME_DIR / "mods" / "state.toml"), "",
           "== input.ini", rd(GAME_DIR / "input.ini"), "",
           "== mods instalados (game/mods/bundled)",
           ", ".join(sorted(p.name for p in (GAME_DIR / "mods" / "bundled").glob("*"))) or "(vazio)", "",
           "== ultimas 200 linhas do log do jogo", rd(GAME_DIR / "last_run.log", 200)]
    return "\n".join(out)


class ReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Relatório de diagnóstico")
        self.resize(760, 480)
        v = QVBoxLayout(self)
        info = QLabel("Cole este texto ao abrir um problema no GitHub. Seu nome de usuário/pasta pessoal é "
                      "escondido (~); o caminho do disco não é incluído.")
        info.setObjectName("hint")
        info.setWordWrap(True)
        v.addWidget(info)
        self.box = QPlainTextEdit()
        self.box.setReadOnly(True)
        self.box.setStyleSheet("font-family:'Share Tech Mono',monospace;")
        self.box.setPlainText(make_report())
        v.addWidget(self.box)
        row = QHBoxLayout()
        b1 = SlantButton("Copiar", "primary")
        b1.clicked.connect(lambda: QApplication.clipboard().setText(self.box.toPlainText()))
        b2 = SlantButton("Salvar em arquivo", "ghost")
        b2.clicked.connect(self.save)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        v.addLayout(row)

    def save(self):
        f = GAME_DIR / f"relatorio-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        try:
            write_atomic(f, self.box.toPlainText())
            QMessageBox.information(self, APP_NAME, f"Salvo em:\n{f}")
        except OSError as ex:
            QMessageBox.warning(self, APP_NAME, f"Não consegui salvar: {ex}")


class GpuTestDialog(QDialog):
    def __init__(self, parent, kind: str):
        super().__init__(parent)
        self.setWindowTitle("Testar OpenGL" if kind == "gl" else "Testar Vulkan")
        self.resize(720, 420)
        v = QVBoxLayout(self)
        self.box = QPlainTextEdit()
        self.box.setReadOnly(True)
        self.box.setStyleSheet("font-family:'Share Tech Mono',monospace;")
        v.addWidget(self.box)
        cmd = gpuinfo.test_command(kind)
        if not cmd:
            self.box.setPlainText(gpuinfo.INSTALL_HINT[kind])
            return
        try:
            r = subprocess.run(cmd, env=clean_env(), capture_output=True, text=True, timeout=20)
            out = (r.stdout + r.stderr).strip()
        except (OSError, subprocess.SubprocessError) as ex:
            out = f"Erro ao rodar {cmd[0]}: {ex}"
        keep = ("renderer string", "version string", "vendor string", "direct rendering", "Device",
                "deviceName", "driverName", "deviceType", "apiVersion", "OpenGL renderer", "OpenGL version")
        head = [l for l in out.splitlines() if any(k in l for k in keep)]
        sel = "\n".join(head) if head else "(nenhuma linha de resumo; veja a saída completa abaixo)"
        env = {k: val for k, val in read_launch_env().items() if k in gpuinfo.GPU_ENV_KEYS}
        self.box.setPlainText("Placa escolhida no launcher: " + (", ".join(f"{k}={val}" for k, val in env.items())
                                                              or "automática") +
                              "\n\nRESUMO:\n" + sel + "\n\nSAÍDA COMPLETA:\n" + out)


def list_controllers() -> list[tuple[str, str, bool]]:
    """(nome, handlers, legivel) lidos de /proc/bus/input/devices."""
    out = []
    try:
        txt = Path("/proc/bus/input/devices").read_text(errors="replace")
    except OSError:
        return out
    for blk in txt.strip().split("\n\n"):
        n = re.search(r'N: Name="(.*)"', blk)
        h = re.search(r"H: Handlers=(.*)", blk)
        if not (n and h):
            continue
        hs = h.group(1).strip()
        if not re.search(r"\bjs\d+", hs):
            continue
        ev = re.search(r"\b(event\d+)", hs)
        ok = True
        if ev:
            ok = os.access(f"/dev/input/{ev.group(1)}", os.R_OK)
        out.append((n.group(1), hs, ok))
    return out


class SettingsPage(Page):
    changed = Signal()

    def __init__(self, cfg: GameConfig, art: QPixmap, switches: list):
        super().__init__(art)
        self.cfg = cfg
        self.switches = switches
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(PageHeader("System setup", "CONFIGURAÇÕES"))
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(14)
        outer.addWidget(scroll_of(inner), 1)
        self.saved = QLabel("")
        self.saved.setObjectName("status")
        outer.addWidget(self.saved)
        cfgv = lambda k, d: cfg.get("video", k, d)

        # --- placa de video
        c = Card("Placa de vídeo")
        gpus = gpuinfo.list_gpus()
        vk_ok, vk_msg = gpuinfo.vulkan_available()
        cur_r = cfgv("renderer", "opengl")
        if cur_r == "vulkan" and not vk_ok:
            cfg.set("video", "renderer", "opengl")
            cur_r = "opengl"
        rend = [("OpenGL (recomendado)", "opengl")] + ([("Vulkan (experimental)", "vulkan")] if vk_ok else []) + \
               [("Software do jogo (CPU)", "software")]
        r = combo(rend, cur_r)
        r.currentIndexChanged.connect(self._renderer(r))
        c.row("Renderizador (API)", r, "Resolução alta e xBR só funcionam no OpenGL. Vulkan aparece se o seu "
                                       "sistema tem driver Vulkan.")
        genv = read_launch_env()
        gitems = [("Automática (padrão do sistema)", "auto")] + \
                 [(f"{g['name']} · {g['kind']}", g["id"]) for g in gpus] + [("Processador (CPU, por software)", "cpu")]
        cur_g = genv.get("MMX5_GPU", "auto")
        gsel = combo(gitems, cur_g if any(x[1] == cur_g for x in gitems) else "auto")
        gsel.setFixedWidth(360)
        gsel.currentIndexChanged.connect(lambda: self._gpu(gsel.currentData(), gpus))
        c.row("Placa de vídeo (GPU)", gsel,
              "Em notebooks com duas placas, escolha a dedicada. 'Processador' roda tudo na CPU (bem mais lento).")
        lines = [f"• {g['name']}  ({g['kind']}, driver {g['driver'] or '?'})" for g in gpus] or \
                ["Nenhuma placa de vídeo detectada em /sys/class/drm."]
        lines.append("Vulkan: " + ("disponível — " if vk_ok else "indisponível — ") + vk_msg)
        gi = QLabel("\n".join(lines))
        gi.setObjectName("hint")
        gi.setWordWrap(True)
        c.full(gi)
        trow = QHBoxLayout()
        trow.setSpacing(8)
        for text, kind in (("Testar OpenGL", "gl"), ("Testar Vulkan", "vk")):
            b = SlantButton(text, "ghost")
            b.clicked.connect(lambda _=False, k=kind: GpuTestDialog(self, k).exec())
            if kind == "vk" and not vk_ok:
                b.setEnabled(False)
            trow.addWidget(b)
        trow.addStretch(1)
        tw = QWidget()
        tw.setLayout(trow)
        c.full(tw)
        v.addWidget(c)

        # --- resolucao e imagem
        c = Card("Resolução e imagem")
        cur_ir, cur_tf = str(cfgv("internal_resolution", "native")), cfgv("texture_filtering", "nearest")
        cur = ("orig" if (cur_ir, cur_tf) == ("native", "nearest") else
               "hd" if (cur_ir, cur_tf) == ("1080p", "xbr") else
               "max" if (cur_ir, cur_tf) == ("1440p", "xbr") else
               "soft" if (cur_ir, cur_tf) == ("1080p", "bilinear") else "custom")
        pre = combo([("Original (PS1)", "orig"), ("HD nítido (1080p + xBR)", "hd"),
                     ("HD máximo (1440p + xBR)", "max"), ("HD suave (1080p + bilinear)", "soft"),
                     ("Personalizado", "custom")], cur)
        c.row("Qualidade da imagem", pre,
              "Atalho que ajusta a resolução interna e o filtro de uma vez. O X5 é 2D: para suavizar os "
              "sprites é preciso resolução alta E o filtro xBR juntos.")
        ir = combo([("Nativa (PS1 original)", "native"), ("720p", "720p"), ("1080p (Full HD)", "1080p"),
                    ("1440p (2K)", "1440p"), ("4K", "4k"), ("5K", "5k"), ("8K", "8k"),
                    ("Resolução da tela", "display")], cur_ir)
        c.row("Resolução interna", ir)
        tf = combo([("Pixelado (original)", "nearest"), ("Suave (bilinear)", "bilinear"),
                    ("xBR (sprites mais lisos)", "xbr")], cur_tf)
        c.row("Filtro de textura", tf, "xBR só atua com resolução interna de 1080p ou mais.")

        def sync_pre():
            k = (ir.currentData(), tf.currentData())
            d = ("orig" if k == ("native", "nearest") else "hd" if k == ("1080p", "xbr") else
                 "max" if k == ("1440p", "xbr") else "soft" if k == ("1080p", "bilinear") else "custom")
            pre.blockSignals(True)
            pre.setCurrentIndex(pre.findData(d))
            pre.blockSignals(False)

        def on_ir():
            self._set("video", "internal_resolution", ir.currentData())
            sync_pre()

        def on_tf():
            self._set("video", "texture_filtering", tf.currentData())
            sync_pre()

        def on_pre():
            d = pre.currentData()
            vals = {"orig": ("native", "nearest"), "hd": ("1080p", "xbr"), "max": ("1440p", "xbr"),
                    "soft": ("1080p", "bilinear")}.get(d)
            if vals:
                ir.setCurrentIndex(ir.findData(vals[0]))
                tf.setCurrentIndex(tf.findData(vals[1]))

        ir.currentIndexChanged.connect(on_ir)
        tf.currentIndexChanged.connect(on_tf)
        pre.currentIndexChanged.connect(on_pre)
        c.row("Anti-aliasing", self._sw("video", "antialiasing", False))
        fm = combo([("Pixelado", "nearest"), ("Suave (bilinear)", "bilinear"), ("Nítido", "sharp"),
                    ("Bicúbico", "bicubic")], cfgv("fmv_filter", "bilinear"))
        fm.currentIndexChanged.connect(lambda: self._set("video", "fmv_filter", fm.currentData()))
        c.row("Filtro dos vídeos (FMV)", fm)
        note = QLabel("Mega Man X5 é um jogo 2D: sprites e cenários vêm de texturas pequenas do PS1, então "
                      "aumentar só a resolução não cria detalhe novo. O filtro xBR (com 1080p ou mais) é o que "
                      "suaviza esses desenhos. Para ver o efeito, jogue em tela cheia ou com a janela grande.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        c.full(note)
        v.addWidget(c)

        # --- tela
        c = Card("Tela")
        fs = combo([("Janela", "0"), ("Tela cheia (sem bordas)", "1")], str(cfgv("fullscreen", 0)))
        fs.currentIndexChanged.connect(lambda: self._set("video", "fullscreen", int(fs.currentData())))
        c.row("Modo de tela", fs, "Dentro do jogo: F11 ou Alt+Enter")
        ww = combo([("Automático", "0"), ("1280 px", "1280"), ("1600 px", "1600"), ("1920 px", "1920"),
                    ("2560 px", "2560"), ("3840 px", "3840")], str(cfgv("window_width", 0)))
        ww.currentIndexChanged.connect(self._winw(ww))
        c.row("Largura da janela", ww)
        vs = combo([("Ligado", "on"), ("Desligado (menor latência)", "immediate"),
                    ("Adaptativo", "adaptive")], cfgv("vsync", "on"))
        vs.currentIndexChanged.connect(lambda: self._set("video", "vsync", vs.currentData()))
        c.row("V-Sync", vs)
        crt = combo([("Nenhum (cru)", "raw"), ("CRT", "crt"), ("Composto", "composite"),
                     ("Trinitron", "trinitron")], cfgv("crt_filter", "raw"))
        crt.currentIndexChanged.connect(lambda: self._set("video", "crt_filter", crt.currentData()))
        c.row("Efeito de tela antiga", crt)
        c.row("Scanlines", self._sw("video", "scanlines", False))
        sl = SliderRow(0, 100, int(float(cfgv("scanline_strength", 0.35)) * 100), "{}%")
        sl.changed.connect(lambda x: self._set("video", "scanline_strength", round(x / 100, 2)))
        c.row("Força das scanlines", sl)
        c.row("Pular vídeos (FMV)", self._sw("video", "auto_skip_fmv", False))
        v.addWidget(c)

        # --- desempenho
        c = Card("Desempenho e áudio")
        c.row("Pular o logo da BIOS (HLE)", self._sw("video", "bios_hle", True))
        c.row("Entrada de baixa latência", self._sw("video", "low_latency_input", False))
        c.row("Thread de renderização", self._sw("video", "render_thread", False))
        c.row("Áudio de alta qualidade (SPU HQ)", self._sw("audio", "spu_hq", False))
        hint = QLabel("Widescreen, interpolação de quadros e limite de FPS ficam na aba MODS.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        c.full(hint)
        v.addWidget(c)

        # --- controle
        c = Card("Controle")
        self.ctrl_info = QLabel("")
        self.ctrl_info.setWordWrap(True)
        self.ctrl_info.setTextFormat(Qt.RichText)
        self.ctrl_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        c.full(self.ctrl_info)
        brow = QHBoxLayout()
        brow.setSpacing(8)
        b_cfg = SlantButton("Configurar controle", "primary")
        b_cfg.clicked.connect(self.open_wizard)
        b_test = SlantButton("Testar", "ghost")
        b_test.clicked.connect(lambda: ControllerTestDialog(self).exec())
        b_rm = SlantButton("Remover", "ghost")
        b_rm.clicked.connect(self.remove_mapping)
        b_ref = SlantButton("Atualizar", "ghost")
        b_ref.clicked.connect(self.refresh_controllers)
        for b in (b_cfg, b_test, b_rm, b_ref):
            brow.addWidget(b)
        brow.addStretch(1)
        bw = QWidget()
        bw.setLayout(brow)
        c.full(bw)
        self.map_status = QLabel("")
        self.map_status.setObjectName("hint")
        self.map_status.setWordWrap(True)
        self.map_status.setTextFormat(Qt.RichText)
        c.full(self.map_status)
        p1 = combo([("Automático (controle se houver)", "auto"), ("Sempre controle", "controller"),
                    ("Teclado", "keyboard")], read_launch_env().get("MMX5_P1_INPUT", "auto"))
        p1.currentIndexChanged.connect(lambda: self._p1(p1.currentData()))
        c.row("Entrada do jogador 1", p1,
              "O jogo usa UM dispositivo por jogador. 'Automático' usa o controle quando o Linux encontra um "
              "e o teclado quando não há nenhum.")
        dz = SliderRow(0, 32767, cfg.deadzone(), "{}")
        dz.s.setSingleStep(500)
        dz.changed.connect(self._deadzone)
        c.row("Zona morta do analógico", dz, "Padrão: 12000")
        compat = Switch(read_launch_env().get("SDL_JOYSTICK_HIDAPI") == "0")
        compat.toggled.connect(lambda on: self._env("SDL_JOYSTICK_HIDAPI", "0" if on else None))
        switches.append(compat)
        c.row("Modo compatibilidade (desliga HIDAPI)", compat,
              "Ligue se o controle aparece na lista mas o jogo não reage (comum com PS4/PS5/8BitDo).")
        self.map_edit = QLineEdit(read_launch_env().get("SDL_GAMECONTROLLERCONFIG", ""))
        self.map_edit.setPlaceholderText("Mapeamento SDL (avançado) — preenchido pelo 'Configurar controle'")
        self.map_edit.editingFinished.connect(
            lambda: self._env("SDL_GAMECONTROLLERCONFIG", self.map_edit.text().strip() or None))
        c.full(self.map_edit)
        lg = SlantButton("Ver log do último jogo", "ghost")
        lg.clicked.connect(lambda: LogDialog(self).exec())
        c.full(lg)
        rp = SlantButton("Gerar relatório de diagnóstico (para reportar problemas)", "ghost")
        rp.clicked.connect(lambda: ReportDialog(self).exec())
        c.full(rp)
        ob = SlantButton("Abrir pasta do jogo (input.ini)", "ghost")
        ob.clicked.connect(lambda: subprocess.Popen(
            ["xdg-open", str(GAME_DIR)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=clean_env()))
        c.full(ob)
        v.addWidget(c)
        v.addStretch(1)

        self._timer = QTimer(singleShot=True, interval=350)
        self._timer.timeout.connect(self._flush)
        self.refresh_controllers()
        self.refresh_mapping()
        apply_p1_device(cfg)

    # --- assistente de controle
    def open_wizard(self):
        w = ControllerWizard(self)
        w.saved.connect(self._wizard_saved)
        w.exec()

    def _wizard_saved(self):
        self.map_edit.setText(read_launch_env().get("SDL_GAMECONTROLLERCONFIG", ""))
        self.refresh_mapping()
        self.saved.setText("Mapeamento salvo ✓")

    def remove_mapping(self):
        self._env("SDL_GAMECONTROLLERCONFIG", None)
        try:
            PAD_JSON.unlink()
        except OSError:
            pass
        self.map_edit.clear()
        self.refresh_mapping()

    def refresh_mapping(self):
        try:
            name = json.loads(PAD_JSON.read_text()).get("name", "?")
            self.map_status.setText(f'<span style="color:#58e08a">Mapeamento próprio ativo: {name}</span>')
        except (OSError, ValueError):
            self.map_status.setText("Nenhum mapeamento próprio. Se o seu controle (ex.: 'USB gamepad' genérico) "
                                    "não funciona no jogo, clique em <b>Configurar controle</b>.")

    # helpers ---------------------------------------------------------
    def _sw(self, sect, key, default):
        s = Switch(bool(self.cfg.get(sect, key, default)))
        s.toggled.connect(lambda on: self._set(sect, key, bool(on)))
        self.switches.append(s)
        return s

    def _renderer(self, box):
        def f():
            val = box.currentData()
            if val == "vulkan":
                ensure_offer_vulkan()
            self._set("video", "renderer", val)
        return f

    def _gpu(self, choice, gpus):
        env = read_launch_env()
        for k in gpuinfo.GPU_ENV_KEYS:
            env.pop(k, None)
        env.update(gpuinfo.gpu_env(choice, gpus))
        write_launch_env(env)
        self.saved.setText("Salvo ✓")

    def _winw(self, box):
        def f():
            n = int(box.currentData())
            if n:
                self._set("video", "window_width", n)
            else:
                self.cfg.remove("video", "window_width")
                self._timer.start()
        return f

    def _set(self, sect, key, val):
        self.cfg.set(sect, key, val)
        self._timer.start()

    def _ini_int(self, key, default):
        try:
            m = re.search(rf"^\s*{key}\s*=\s*(\d+)", self.cfg.input_path.read_text(), re.M)
            return int(m.group(1)) if m else default
        except OSError:
            return default

    def _ini(self, key, val):
        try:
            txt = self.cfg.input_path.read_text()
        except OSError:
            txt = DEFAULT_INPUT_INI
        if re.search(rf"^\s*{key}\s*=", txt, re.M):
            txt = re.sub(rf"^(\s*{key}\s*=\s*)\S+", rf"\g<1>{val}", txt, flags=re.M)
        else:
            txt = txt.replace("[controller]", f"[controller]\n{key} = {val}", 1)
        write_atomic(self.cfg.input_path, txt)
        self.saved.setText("Salvo ✓")

    def _p1(self, choice):
        self._env("MMX5_P1_INPUT", choice)
        apply_p1_device(self.cfg)
        self._timer.start()

    def _env(self, key, val):
        env = read_launch_env()
        if val is None:
            env.pop(key, None)
        else:
            env[key] = val
        write_launch_env(env)
        self.saved.setText("Salvo ✓")

    def _deadzone(self, v):
        self.cfg.set_deadzone(int(v))
        self.saved.setText("Salvo ✓")

    def refresh_controllers(self):
        devs = list_controllers()
        if not devs:
            self.ctrl_info.setText(
                '<span style="color:#ffcc66">O Linux não detectou nenhum controle. Conecte o controle '
                '(ou ligue-o por Bluetooth) e clique em Atualizar. Enquanto isso o jogo usa o teclado.</span>')
            return
        lines = []
        bad = False
        for name, _h, ok in devs:
            bad |= not ok
            col = "#58e08a" if ok else "#ff8a8a"
            lines.append(f'<span style="color:{col}">{"✔" if ok else "✖"} {name}</span>')
        txt = "<br>".join(lines)
        if bad:
            txt += ('<br><span style="color:#ffcc66">Sem permissão para ler o controle. Rode no terminal '
                    '<b>sudo usermod -aG input $USER</b> e reinicie a sessão.</span>')
        else:
            txt += ('<br><span style="color:#8b94b0">Se o jogo não reagir, ligue o modo '
                    'compatibilidade ou use "Configurar controle".</span>')
        self.ctrl_info.setText(txt)

    def _flush(self):
        try:
            self.cfg.save()
            self.saved.setText("Salvo ✓")
        except OSError as e:
            self.saved.setText(f"Erro ao salvar: {e}")
        self.changed.emit()


MODS_DIR = BASE / "mods"
MOD_PKG_BEZEL = ("psx.presentation.bezel", "1.0.0", "bezel")
GAME_ID = "SLUS-01334"
DISC_SHA = "be731bc4b9d3211b9267a34b8a68c769199a15479b14004ff25b67cdfebe8af4"
FPS_CHOICES = [("Taxa do monitor", "display"), ("90 FPS", "90"), ("120 FPS", "120"), ("144 FPS", "144"),
               ("165 FPS", "165"), ("240 FPS", "240")]
TYPE_TAGS = {"texture-pack": "TEXTURAS", "bezel": "BEZEL", "patch": "PATCH"}


class ModInfo:
    def __init__(self, mid, name, version, author, desc, cover, kind, spec=None, tag="EXPERIMENTAL",
                 external=False, note="", extra=""):
        self.mid, self.name, self.version, self.author = mid, name, version, author
        self.desc, self.cover, self.kind, self.spec, self.tag = desc, cover, kind, spec, tag
        self.external, self.note, self.extra = external, note, extra
        self.mtype, self.dir, self.ext, self.error, self.template = "", None, {}, "", False


BUILTIN_MODS = [
    ModInfo("widescreen", "Widescreen 16:9", "1.0.0", "Incluso no jogo",
            "Alarga o campo de visão para telas 16:9: o fundo 2D, o HUD e a ativação dos inimigos "
            "acompanham a tela mais larga, sem esticar a imagem.",
            "cover_widescreen.png", "toggle", MOD_PKG_WIDE),
    ModInfo("interp", "Interpolação de quadros", "1.0.0", "Incluso no jogo",
            "Gera quadros intermediários para apresentar o jogo acima de 60 Hz. Só muda a suavidade da "
            "imagem: a lógica, o áudio e a velocidade do jogo continuam originais. Usa o OpenGL e desliga o V-Sync.",
            "cover_interp.png", "toggle", MOD_PKG_INTERP),
    ModInfo("fps", "Limite de FPS", "1.0.0", "Incluso no jogo",
            "Escolha a taxa de quadros da apresentação. Vale quando a Interpolação de quadros está ativada; "
            "'Taxa do monitor' acompanha o refresh da sua tela.",
            "cover_fps.png", "choice", MOD_PKG_INTERP),
]


def rounded_pix(pix: QPixmap, w: int, h: int, r: int) -> QPixmap:
    scaled = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(w, h)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, r, r)
    p.setClipPath(path)
    p.drawPixmap((w - scaled.width()) // 2, (h - scaled.height()) // 2, scaled)
    p.end()
    return out


WIDE_CFG = """# launcher: captura ampla
# Configuracao do sistema de captura de texturas (formato DuckStation).
# Sem este arquivo o runtime so' captura texturas >= 16x16 que passaram por um "upload" rastreado,
# e Mega Man X5 (2D, sprites pequenos) acaba nao gerando nenhum arquivo em dumps/.
DumpTexturePages: true
DumpC16Textures: true
DumpTextureWidthThreshold: 4
DumpTextureHeightThreshold: 4
"""


def pack_wide(d: Path) -> bool:
    try:
        return "DumpTexturePages: true" in (d / "config.yaml").read_text()
    except OSError:
        return False


def set_pack_wide(d: Path, on: bool) -> None:
    f = d / "config.yaml"
    try:
        if on:
            write_atomic(f, WIDE_CFG)
        elif f.exists() and "# launcher: captura ampla" in f.read_text():
            f.unlink()
        elif f.exists():                      # arquivo do jogador: so' desliga a chave
            write_atomic(f, f.read_text().replace("DumpTexturePages: true", "DumpTexturePages: false"))
    except OSError:
        pass


def load_art(name: str) -> QPixmap:
    """Arte do personagem: primeiro launcher_art/ (do jogador), depois a arte neutra embutida."""
    for d in (ART_DIR, ASSETS):
        p = QPixmap(str(d / f"{name}.png"))
        if not p.isNull():
            return p
    return QPixmap(1, 1)


def art_captions() -> dict:
    """Legendas opcionais do canto da arte: launcher_art/art.json = {"zero": ["pequeno", "GRANDE"], ...}."""
    cap = {"zero": ("", ""), "x": ("", ""), "sigma": ("", "")}
    try:
        data = json.loads((ART_DIR / "art.json").read_text(encoding="utf-8"))
        for k in cap:
            if isinstance(data.get(k), list) and len(data[k]) == 2:
                cap[k] = (str(data[k][0]), str(data[k][1]))
    except (OSError, ValueError, AttributeError):
        pass
    return cap


def ensure_offer_vulkan() -> None:
    """Faz o jogo oferecer o renderizador Vulkan (game/game.toml, [video] offer_vulkan = true)."""
    f = GAME_DIR / "game.toml"
    try:
        txt = f.read_text()
    except OSError:
        return
    if re.search(r"^\s*offer_vulkan\s*=\s*true", txt, re.M):
        return
    if re.search(r"^\s*offer_vulkan\s*=", txt, re.M):
        txt = re.sub(r"^(\s*offer_vulkan\s*=\s*)\w+", r"\g<1>true", txt, count=1, flags=re.M)
    elif re.search(r"^\[video\]\s*$", txt, re.M):
        txt = re.sub(r"^(\[video\]\s*)$", r"\1\noffer_vulkan = true", txt, count=1, flags=re.M)
    else:
        txt += "\n[video]\noffer_vulkan = true\n"
    try:
        write_atomic(f, txt)
    except OSError:
        pass


def render_report() -> str:
    """Resumo do renderizador usado na ultima partida (lido do log)."""
    try:
        lines = (GAME_DIR / "last_run.log").read_text(errors="replace").splitlines()
    except OSError:
        return ""
    out = []
    for l in lines:
        if "Vulkan renderer is not available in this build" in l:
            out.append('<span style="color:#ffcc66">Esta compilação não tem Vulkan: o jogo usou OpenGL. '
                       'Instale <b>libvulkan-dev</b> e <b>glslc</b> e use "Atualizar o jogo".</span>')
        elif "does not offer Vulkan" in l:
            out.append('<span style="color:#ffcc66">O jogo não oferece Vulkan (game.toml): usou OpenGL.</span>')
        elif "renderer backend requested:" in l or l.startswith("psxrecomp: renderer ="):
            out.append(l.replace("psxrecomp: ", ""))
        elif "OpenGL context created" in l:
            out.append(l.replace("psxrecomp: ", ""))
    return "<br>".join(dict.fromkeys(out))


def hd_disk_state(cfg_dir: Path) -> dict:
    """O que o runtime vai ler de verdade: game/mods/state.toml no disco."""
    st = load_toml(cfg_dir / "mods" / "state.toml")
    for f in st.get("feature", []):
        if f.get("package_id") == MOD_PKG_HD[0] and f.get("id") == MOD_PKG_HD[2]:
            return dict(present=True, enabled=bool(f.get("enabled")), pack=str(f.get("resources", {}).get("pack", "")),
                        dump=str(f.get("values", {}).get("dump", "")), repl=str(f.get("values", {}).get("replacements", "")))
    return dict(present=False, enabled=False, pack="", dump="", repl="")


def hd_run_report(pack: Path | None) -> str:
    """Resumo (rich text) da ultima partida: o plugin de texturas ativou? quantas capturas?"""
    log = GAME_DIR / "last_run.log"
    try:
        lines = log.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    hits = [l for l in lines if "HD textures" in l]
    n = 0
    if pack:
        try:
            n = sum(1 for f in (pack / "dumps").rglob("*.png"))
        except OSError:
            n = 0
    if not hits:
        return ('<span style="color:#ffcc66">Última partida: o mod de texturas <b>NÃO estava ligado</b> '
                '(nenhuma linha "HD textures" no log). Ligue-o na aba MODS antes de jogar.</span>')
    on_dump = "dumping on" in hits[-1]
    col = "#58e08a" if (not on_dump or n) else "#ffcc66"
    extra = "" if (not on_dump or n) else " — mas nada foi capturado: feche o jogo pela janela e confira o config.yaml."
    return f'<span style="color:{col}">Última partida: texturas ATIVAS ({"captura ligada" if on_dump else "só carregar"}); {n} arquivo(s) em dumps/{extra}</span>'


def slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", s.lower()).strip("-.")
    return s or "mod"


def ensure_default_mods() -> None:
    """Garante a pasta de exemplo do HD Texturas (recria se o jogador apagou)."""
    d = MODS_DIR / "hd-texturas"
    if (d / "mod.json").exists():
        return
    try:
        (d / "replacements").mkdir(parents=True, exist_ok=True)
        (d / "dumps").mkdir(parents=True, exist_ok=True)
        write_atomic(d / "mod.json", json.dumps(dict(
            type="texture-pack", name="HD Texturas", version="1.0.0", author="Você",
            description="Pacote de texturas HD. Capture as texturas originais, amplie e coloque em "
                        "replacements/.", cover="cover.png"), indent=2, ensure_ascii=False))
        if (ASSETS / "cover_hdtex.png").exists():
            shutil.copy(ASSETS / "cover_hdtex.png", d / "cover.png")
        set_pack_wide(d, True)
    except OSError:
        pass


def _hexbytes(s) -> bytes | None:
    try:
        t = re.sub(r"\s+", "", str(s))
        return bytes.fromhex(t) if t and len(t) % 2 == 0 else None
    except ValueError:
        return None


def validate_patch_mod(e: dict) -> str:
    opts = {}
    for o in e.get("options", []):
        if not isinstance(o, dict) or not re.fullmatch(r"[a-z0-9_-]+", str(o.get("id", ""))):
            return "opção sem 'id' válido (use a-z, 0-9, - e _)"
        t = o.get("type")
        if t not in ("boolean", "choice", "integer"):
            return f"opção '{o['id']}': type deve ser boolean, choice ou integer"
        if t == "choice" and not o.get("choices"):
            return f"opção '{o['id']}': faltam 'choices'"
        if t == "integer" and not ("min" in o and "max" in o):
            return f"opção '{o['id']}': integer precisa de 'min' e 'max'"
        opts[o["id"]] = o
    patches = e.get("patches", [])
    if not patches:
        return "nenhum patch em 'patches'"
    for i, p in enumerate(patches, 1):
        try:
            addr = int(str(p.get("address")), 0)
        except ValueError:
            return f"patch {i}: 'address' inválido (ex.: \"0x8001DE64\")"
        if not 0x80000000 <= addr < 0x80200000:
            return f"patch {i}: endereço fora de 0x80000000–0x801FFFFF"
        exp = _hexbytes(p.get("expected"))
        if exp is None:
            return f"patch {i}: 'expected' deve ser bytes em hexa (ex.: \"02 00 02 24\")"
        if "replace" in p:
            rep = _hexbytes(p["replace"])
            if rep is None or len(rep) != len(exp):
                return f"patch {i}: 'replace' deve ter o mesmo tamanho de 'expected'"
        elif "replace_from" not in p:
            return f"patch {i}: faltou 'replace' (ou 'replace_from')"
        for k in (p.get("when") or {}):
            if k not in opts:
                return f"patch {i}: 'when' usa a opção '{k}' que não existe"
    return ""


def parse_mod(d: Path) -> ModInfo | None:
    mj = d / "mod.json"
    if not mj.exists():
        return None
    try:
        data = json.loads(mj.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("o arquivo precisa ser um objeto { ... }")
    except (OSError, ValueError) as ex:
        m = ModInfo(f"ext:{d.name}", d.name, "?", "?", "", "", "toggle", None, tag="ERRO", external=True)
        m.dir, m.error = d, f"mod.json inválido: {ex}"
        return m
    mtype = data.get("type", "texture-pack")
    version = str(data.get("version", "1.0.0"))
    pid = f"user.{slug(str(data.get('id', d.name)))}"
    spec = {"texture-pack": MOD_PKG_HD, "bezel": MOD_PKG_BEZEL}.get(mtype, (pid, version, "main"))
    cover = d / str(data.get("cover", "cover.png"))
    m = ModInfo(f"ext:{d.name}", str(data.get("name", d.name)), version, str(data.get("author", "?")),
                str(data.get("description", "")), str(cover) if cover.exists() else "", "toggle", spec,
                tag=TYPE_TAGS.get(mtype, "?"), external=True, extra="hd" if mtype == "texture-pack" else "")
    m.mtype, m.dir, m.ext = mtype, d, data
    m.template = bool(data.get("template"))
    if mtype not in TYPE_TAGS:
        m.error = f"type '{mtype}' desconhecido (use texture-pack, bezel ou patch)"
    elif mtype == "bezel":
        art = d / str(data.get("artwork", "bezel.png"))
        if not art.exists():
            m.error = f"imagem do bezel não encontrada: {art.name}"
        elif not m.cover:
            m.cover = str(art)
    elif mtype == "patch":
        m.error = validate_patch_mod(data)
        if m.template:
            m.tag = "MODELO"
    return m


def load_external_mods() -> list[ModInfo]:
    out = []
    try:
        dirs = sorted((d for d in MODS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")),
                      key=lambda d: (d.name != "hd-texturas", d.name))
    except OSError:
        return out
    for d in dirs:
        m = parse_mod(d)
        if m:
            out.append(m)
    return out


def build_manifest(m: ModInfo) -> dict:
    e = m.ext
    man = {"format_version": 5, "id": m.spec[0], "version": m.version, "name": m.name,
           "author": m.author, "description": m.desc or m.name, "resolver": "declarative",
           "save_compatibility": "shared",
           "target": [{"game_id": GAME_ID, "disc_sha256": DISC_SHA}],
           "feature": [{"id": "main", "name": m.name, "description": m.desc or m.name,
                        "group": "Mods do jogador", "default_enabled": False}]}
    opts = []
    for o in e.get("options", []):
        od = {"feature": "main", "id": o["id"], "label": o.get("label", o["id"]), "type": o["type"]}
        if o["type"] == "integer":
            od.update(min=int(o["min"]), max=int(o["max"]), default=int(o.get("default", o["min"])))
            if "step" in o:
                od["step"] = int(o["step"])
        elif o["type"] == "boolean":
            od["default"] = "true" if str(o.get("default", False)).lower() in ("true", "1") else "false"
        else:
            od["default"] = str(o.get("default", o["choices"][0]["value"]))
            od["choice"] = [{"value": str(c["value"]), "label": str(c.get("label", c["value"]))}
                            for c in o["choices"]]
        opts.append(od)
    if opts:
        man["option"] = opts
    pats = []
    for p in e["patches"]:
        pd = {"feature": "main", "target": p.get("target", "main_exe"), "address": int(str(p["address"]), 0),
              "expected": " ".join(f"{b:02x}" for b in _hexbytes(p["expected"]))}
        if "replace" in p:
            pd["replace"] = " ".join(f"{b:02x}" for b in _hexbytes(p["replace"]))
        else:
            pd["replace_from"] = p["replace_from"]
        if p.get("when"):
            pd["when"] = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in p["when"].items()}
        pats.append(pd)
    man["patch"] = pats
    return man


def compile_patch_mods(mods: list[ModInfo]) -> None:
    """Gera game/mods/installed/<pacote>/<versao>/manifest.toml para cada mod 'patch' valido."""
    root = GAME_DIR / "mods" / "installed"
    wanted = set()
    for m in mods:
        if m.mtype != "patch" or m.error or m.template:
            continue
        wanted.add(m.spec[0])
        pkg = root / m.spec[0]
        try:
            if pkg.exists():
                for old in pkg.iterdir():
                    if old.is_dir() and old.name != m.version:
                        shutil.rmtree(old, ignore_errors=True)
            write_atomic(pkg / m.version / "manifest.toml", dump_toml(build_manifest(m)))
        except (OSError, TypeError, ValueError, KeyError) as ex:
            m.error = f"não consegui gerar o pacote: {ex}"
    try:                                  # remove pacotes de jogador que nao existem mais
        for d in root.glob("user.*"):
            if d.name not in wanted:
                shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass


class NewModDialog(QDialog):
    created = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novo mod")
        self.resize(460, 240)
        v = QVBoxLayout(self)
        v.setSpacing(12)
        info = QLabel("Cria uma pasta nova em <b>mods/</b> com um <b>mod.json</b> de modelo. Depois é só editar "
                      "os arquivos e clicar em <b>Recarregar</b> na aba MODS.")
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        info.setObjectName("hint")
        v.addWidget(info)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Nome do mod (ex.: Meu primeiro mod)")
        self.name.setFixedHeight(40)
        v.addWidget(self.name)
        self.kind = combo([("Texturas (trocar imagens)", "texture-pack"), ("Bezel (moldura de tela)", "bezel"),
                           ("Patch de bytes (avançado)", "patch")], "texture-pack")
        row = QHBoxLayout()
        row.addWidget(QLabel("Tipo"))
        row.addStretch(1)
        row.addWidget(self.kind)
        v.addLayout(row)
        self.err = QLabel("")
        self.err.setObjectName("status")
        v.addWidget(self.err)
        v.addStretch(1)
        b = QHBoxLayout()
        ok = SlantButton("Criar", "primary")
        ok.clicked.connect(self.create)
        cl = SlantButton("Cancelar", "ghost")
        cl.clicked.connect(self.reject)
        b.addWidget(ok)
        b.addWidget(cl)
        b.addStretch(1)
        v.addLayout(b)

    def create(self):
        name = self.name.text().strip()
        if not name:
            self.err.setText("Dê um nome ao mod.")
            return
        base = slug(name)
        d, n = MODS_DIR / base, 2
        while d.exists():
            d, n = MODS_DIR / f"{base}-{n}", n + 1
        kind = self.kind.currentData()
        data = dict(type=kind, name=name, version="1.0.0", author="Você",
                    description="Descreva aqui o que o seu mod faz.", cover="cover.png")
        try:
            d.mkdir(parents=True)
            if (ASSETS / "icon.png").exists():
                shutil.copy(ASSETS / "icon.png", d / "cover.png")
            if kind == "texture-pack":
                (d / "replacements").mkdir()
                (d / "dumps").mkdir()
            elif kind == "bezel":
                data["artwork"] = "bezel.png"
                img = QPixmap(1920, 1080)
                img.fill(QColor(12, 18, 28))
                p = QPainter(img)
                p.setPen(QPen(QColor("#f2b233"), 10))
                p.drawRect(20, 20, 1880, 1040)
                p.setPen(QColor("white"))
                p.setFont(QFont("Chakra Petch", 64, QFont.Bold))
                p.drawText(img.rect(), Qt.AlignCenter, name)
                p.end()
                img.save(str(d / "bezel.png"))
            else:
                data.update(template=True,
                            description="MODELO: edite 'patches' com endereços reais do jogo e apague a linha "
                                        "\"template\" para ativar.",
                            options=[dict(id="ativo", label="Ativo", type="boolean", default=True)],
                            patches=[dict(address="0x80010000", expected="00 00 00 00", replace="00 00 00 00",
                                          when=dict(ativo="true"))])
            write_atomic(d / "mod.json", json.dumps(data, indent=2, ensure_ascii=False))
        except OSError as ex:
            self.err.setText(f"Erro: {ex}")
            return
        subprocess.Popen(["xdg-open", str(d)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=clean_env())
        self.created.emit()
        self.accept()


class UpscaleDialog(QDialog):
    def __init__(self, parent=None, pack: Path | None = None):
        super().__init__(parent)
        self.pack = pack or (MODS_DIR / "hd-texturas")
        self.setWindowTitle("Ampliar texturas")
        self.resize(640, 460)
        v = QVBoxLayout(self)
        info = QLabel("Pega as texturas capturadas (pasta dumps/) e cria as versões ampliadas na pasta "
                      "replacements/ do mod, com o mesmo nome de arquivo. Na primeira vez baixa o Real-ESRGAN "
                      "(47 MB) e prepara o Python. A IA usa a placa de vídeo (Vulkan); sem ela o launcher usa o "
                      "método de pixel art.")
        info.setWordWrap(True)
        info.setObjectName("hint")
        v.addWidget(info)
        self.scale = combo([("2x", "2"), ("3x", "3"), ("4x", "4")], "4")
        self.mode = combo([("Automático (IA se possível)", "auto"), ("IA (Real-ESRGAN)", "esrgan"),
                           ("Pixel art (scale2x)", "scale2x"), ("Suave (lanczos)", "lanczos")], "auto")
        self.force = Switch(False)
        for lab, w in (("Ampliação", self.scale), ("Método", self.mode), ("Refazer as que já existem", self.force)):
            row = QHBoxLayout()
            row.addWidget(QLabel(lab))
            row.addStretch(1)
            row.addWidget(w)
            v.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family:'Share Tech Mono',monospace;")
        v.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.go = SlantButton("Ampliar agora", "primary")
        self.go.clicked.connect(self.start)
        cl = SlantButton("Fechar", "ghost")
        cl.clicked.connect(self.reject)
        row.addWidget(self.go)
        row.addWidget(cl)
        row.addStretch(1)
        v.addLayout(row)
        self.proc = None

    def start(self):
        script = BASE / "tools" / "upscale.sh"
        if not script.exists():
            self.log.setPlainText(f"Não achei {script}")
            return
        if not list((self.pack / "dumps").rglob("*.png")):
            self.log.setPlainText("Ainda não há texturas capturadas em:\n" + str(self.pack / "dumps") +
                                  "\n\nLigue 'Capturar texturas originais', jogue um pouco e FECHE o jogo "
                                  "(a captura termina ao sair).")
            return
        args = ["bash", str(script), "--pack", str(self.pack), "--scale", self.scale.currentData(),
                "--mode", self.mode.currentData()]
        if self.force.isChecked():
            args.append("--force")
        self.log.clear()
        self.go.setEnabled(False)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        from PySide6.QtCore import QProcessEnvironment
        qe = QProcessEnvironment()
        for k, val in clean_env().items():
            qe.insert(k, val)
        self.proc.setProcessEnvironment(qe)
        self.proc.readyReadStandardOutput.connect(
            lambda: self.log.appendPlainText(bytes(self.proc.readAllStandardOutput()).decode(errors="replace").rstrip()))
        self.proc.finished.connect(self._fin)
        self.proc.start(args[0], args[1:])

    def _fin(self, code, _):
        self.go.setEnabled(True)
        self.log.appendPlainText("\n=== CONCLUÍDO ===" if code == 0 else f"\n=== FALHOU (código {code}) ===")

    def done(self, r):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()
        super().done(r)


class ModCard(QFrame):
    clicked = Signal(int)

    def __init__(self, idx: int, mod: ModInfo, pix: QPixmap):
        super().__init__()
        self.idx = idx
        self.sel = False
        self.setObjectName("modcard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(96)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)
        cov = QLabel()
        cov.setPixmap(rounded_pix(pix, 112, 63, 2))
        cov.setFixedSize(112, 63)
        lay.addWidget(cov)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.name = QLabel(mod.name)
        self.name.setObjectName("modName")
        self.name.setWordWrap(True)
        self.sub = QLabel(f"v{mod.version}  ·  {mod.tag}")
        self.sub.setObjectName("hint")
        self.state = QLabel("")
        self.state.setObjectName("modState")
        col.addStretch(1)
        col.addWidget(self.name)
        col.addWidget(self.sub)
        col.addWidget(self.state)
        col.addStretch(1)
        lay.addLayout(col, 1)

    def set_selected(self, sel: bool):
        self.sel = sel
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        path = chamfer(r, 10, 10)
        p.setPen(QPen(THEME["accent"] if self.sel else PANEL_LINE, 2 if self.sel else 1.2))
        p.setBrush(QColor(21, 29, 42, 240) if self.sel else QColor(15, 21, 31, THEME["panel_alpha"]))
        p.drawPath(path)

    def mousePressEvent(self, e):
        self.clicked.emit(self.idx)


class ModsPage(Page):
    changed = Signal()
    rebuild_requested = Signal()

    def __init__(self, cfg: GameConfig):
        super().__init__(None)
        self.cfg = cfg
        self.accent = QColor("#4cc3ff")
        self.cur = 0
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        ph = PageHeader("Experimentais", "MODS")
        for text, fn in (("Novo mod", self._new), ("Recarregar", self.reload), ("Abrir pasta", self._open_dir)):
            b = SlantButton(text, "ghost")
            b.clicked.connect(fn)
            ph.extra.addWidget(b)
        outer.addWidget(ph)
        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, 1)

        listw = QWidget()
        self.list_lay = QVBoxLayout(listw)
        self.list_lay.setContentsMargins(0, 0, 8, 0)
        self.list_lay.setSpacing(10)
        sc = scroll_of(listw)
        sc.setMinimumWidth(380)
        sc.setMaximumWidth(440)
        body.addWidget(sc, 4)

        self.detail = Panel()
        _outer = QVBoxLayout(self.detail)
        _outer.setContentsMargins(6, 14, 6, 10)
        _inner = QWidget()
        dv = QVBoxLayout(_inner)
        dv.setContentsMargins(18, 4, 18, 8)
        dv.setSpacing(10)
        _outer.addWidget(scroll_of(_inner))
        self.d_cover = QLabel()
        self.d_cover.setAlignment(Qt.AlignCenter)
        self.d_cover.setFixedHeight(190)
        dv.addWidget(self.d_cover)
        self.d_name = QLabel("")
        self.d_name.setObjectName("pageTitle")
        self.d_meta = QLabel("")
        self.d_meta.setObjectName("subTitle")
        self.d_desc = QLabel("")
        self.d_desc.setWordWrap(True)
        self.d_desc.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        dv.addWidget(self.d_name)
        dv.addWidget(self.d_meta)
        dv.addWidget(self.d_desc)
        self.d_ctl = QHBoxLayout()
        self.d_ctl_lbl = QLabel("")
        self.switch = Switch(False)
        self.switch.toggled.connect(self._toggled)
        self.fps_combo = combo(FPS_CHOICES, "display")
        self.fps_combo.currentIndexChanged.connect(self._fps)
        self.d_ctl.addWidget(self.d_ctl_lbl)
        self.d_ctl.addStretch(1)
        self.d_ctl.addWidget(self.switch)
        self.d_ctl.addWidget(self.fps_combo)
        dv.addLayout(self.d_ctl)
        _ln = QFrame()
        _ln.setObjectName("sep")
        _ln.setFixedHeight(1)
        dv.addWidget(_ln)
        self.extra_lay = QVBoxLayout()
        self.extra_lay.setSpacing(8)
        dv.addLayout(self.extra_lay)
        self.d_note = QLabel("")
        self.d_note.setObjectName("hint")
        self.d_note.setWordWrap(True)
        self.d_note.setTextFormat(Qt.RichText)
        dv.addWidget(self.d_note)
        dv.addStretch(1)
        body.addWidget(self.detail, 6)

        self._timer = QTimer(singleShot=True, interval=350)
        self._timer.timeout.connect(self._flush)
        self.mods: list[ModInfo] = []
        self.cards: list[ModCard] = []
        self.reload()

    # ---------------------------------------------------------------- lista
    def reload(self):
        ensure_default_mods()
        self.mods = BUILTIN_MODS + load_external_mods()
        compile_patch_mods(self.mods)
        while self.list_lay.count():
            it = self.list_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.cards = []
        for i, m in enumerate(self.mods):
            pix = QPixmap(m.cover if m.external else str(ASSETS / m.cover))
            if pix.isNull():
                pix = QPixmap(str(ASSETS / "icon.png"))
            c = ModCard(i, m, pix)
            c.clicked.connect(self.select)
            self.cards.append(c)
            self.list_lay.addWidget(c)
        self.list_lay.addStretch(1)
        self.cur = min(self.cur, len(self.mods) - 1)
        self.select(self.cur)
        self.refresh_states()

    def set_accent(self, c: QColor):
        self.accent = c
        self.switch.accent = c
        self.switch.update()

    def _open_dir(self):
        MODS_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(MODS_DIR)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=clean_env())

    def _new(self):
        dlg = NewModDialog(self)
        dlg.created.connect(self.reload)
        dlg.exec()

    # ---------------------------------------------------------------- estado
    def _art(self, m):
        return str(m.dir / str(m.ext.get("artwork", "bezel.png")))

    def is_on(self, m: ModInfo) -> bool:
        if m.error or m.template:
            return False
        if not m.spec or not self.cfg.feature_enabled(m.spec):
            return False
        if m.mtype == "texture-pack":
            return self.cfg.feature_resource(MOD_PKG_HD, "pack") == str(m.dir)
        if m.mtype == "bezel":
            return self.cfg.feature_resource(MOD_PKG_BEZEL, "artwork") == self._art(m)
        return True

    def apply(self, m: ModInfo, on: bool):
        if m.mtype == "texture-pack":
            if on:
                for sub in ("replacements", "dumps"):
                    (m.dir / sub).mkdir(parents=True, exist_ok=True)
                if not (m.dir / "config.yaml").exists():
                    set_pack_wide(m.dir, True)
                self.cfg.set_feature(MOD_PKG_HD, True)
                self.cfg.set_feature_resource(MOD_PKG_HD, "pack", str(m.dir))
                for k, d in (("replacements", "true"), ("dump", "false")):
                    if not self.cfg.feature_value(MOD_PKG_HD, k, ""):
                        self.cfg.set_feature_value(MOD_PKG_HD, k, d)
            elif self.cfg.feature_resource(MOD_PKG_HD, "pack") == str(m.dir):
                self.cfg.set_feature(MOD_PKG_HD, False)
        elif m.mtype == "bezel":
            if on:
                self.cfg.set_feature(MOD_PKG_BEZEL, True)
                self.cfg.set_feature_resource(MOD_PKG_BEZEL, "artwork", self._art(m))
            elif self.cfg.feature_resource(MOD_PKG_BEZEL, "artwork") == self._art(m):
                self.cfg.set_feature(MOD_PKG_BEZEL, False)
        else:
            self.cfg.set_feature(m.spec, on)
            if on and m.mtype == "patch":
                for o in m.ext.get("options", []):
                    if not self.cfg.feature_value(m.spec, o["id"], ""):
                        d = o.get("default", o.get("min", 0) if o["type"] == "integer" else
                                  (o["choices"][0]["value"] if o["type"] == "choice" else False))
                        self.cfg.set_feature_value(m.spec, o["id"], str(d).lower() if isinstance(d, bool) else str(d))

    def refresh_states(self):
        for c, m in zip(self.cards, self.mods):
            if m.error:
                c.state.setText('<span style="color:#ff6b6b">⚠ COM ERRO</span>')
            elif m.template:
                c.state.setText('<span style="color:#8a96ab">MODELO · não aplicado</span>')
            elif m.kind == "choice":
                v = self.cfg.feature_value(MOD_PKG_INTERP, "rate", "display")
                on = self.cfg.feature_enabled(MOD_PKG_INTERP)
                lbl = "MONITOR" if v == "display" else f"{v} FPS"
                c.state.setText(f'<span style="color:#58e08a">● ATIVADO · {lbl}</span>' if on else
                                f'<span style="color:#8a96ab">○ DESATIVADO · {lbl}</span>')
            else:
                on = self.is_on(m)
                c.state.setText(f'<span style="color:{"#58e08a" if on else "#8a96ab"}">'
                                f'{"● ATIVADO" if on else "○ DESATIVADO"}</span>')

    # ---------------------------------------------------------------- detalhe
    def _clear_extra(self):
        def wipe(lay):
            while lay.count():
                it = lay.takeAt(0)
                w = it.widget()
                if w:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                elif it.layout():
                    wipe(it.layout())
        wipe(self.extra_lay)

    def select(self, i: int):
        if not self.mods:
            return
        self.cur = i
        m = self.mods[i]
        for k, c in enumerate(self.cards):
            c.set_selected(k == i)
        pix = QPixmap(m.cover if m.external else str(ASSETS / m.cover))
        if pix.isNull():
            pix = QPixmap(str(ASSETS / "icon.png"))
        self.d_cover.setPixmap(rounded_pix(pix, 338, 190, 10))
        self.d_name.setText(m.name)
        self.d_meta.setText(f"■ v{m.version} · {m.author.upper()} · {m.tag}")
        self.d_desc.setText(m.desc)
        note = ""
        if m.error:
            note = f'<span style="color:#ff6b6b">Problema neste mod: {m.error}</span>'
        elif m.template:
            note = ("Este é um <b>modelo</b>. Copie a pasta, edite o mod.json com endereços reais do jogo e apague "
                    "a linha <b>\"template\"</b> para poder ativar. Veja mods/LEIA-ME.md.")
        elif m.external:
            note = f"Pasta: {m.dir}"
        self.d_note.setText(note)
        self.switch.blockSignals(True)
        self.fps_combo.blockSignals(True)
        self.switch.setVisible(m.kind == "toggle")
        self.fps_combo.setVisible(m.kind == "choice")
        usable = not (m.error or m.template)
        if m.kind == "toggle":
            self.d_ctl_lbl.setText("Ativar este mod")
            self.switch.setEnabled(usable)
            self.switch.setChecked(self.is_on(m))
        else:
            self.d_ctl_lbl.setText("Limite de FPS")
            self.fps_combo.setCurrentIndex(max(0, self.fps_combo.findData(
                self.cfg.feature_value(MOD_PKG_INTERP, "rate", "display"))))
        self.switch.blockSignals(False)
        self.fps_combo.blockSignals(False)
        self.switch.accent = self.accent
        self._clear_extra()
        if m.external and usable:
            if m.mtype == "texture-pack":
                self._extra_hd(m)
            elif m.mtype == "bezel":
                lab = QLabel(f"Imagem: {m.ext.get('artwork', 'bezel.png')} — aparece nas bordas quando a tela "
                             "não é totalmente preenchida (por exemplo 4:3 em tela larga, sem o mod Widescreen).")
                lab.setWordWrap(True)
                lab.setObjectName("hint")
                self.extra_lay.addWidget(lab)
            elif m.mtype == "patch":
                self._extra_patch(m)
        if m.mid == "widescreen":
            self._extra_widescreen()

    def _extra_widescreen(self):
        man = GAME_DIR / "mods" / "bundled" / "mmx5.enhancement.widescreen" / "1.0.0" / "manifest.toml"
        try:
            has_opt = 'id = "aspect"' in man.read_text()
        except OSError:
            has_opt = False
        if not has_opt:
            lab = QLabel("Para escolher a proporção da tela, atualize o jogo (botão 'Atualizar o jogo' no mod "
                         "HD Texturas ou ./build_linux.sh): a versão compilada aqui não tem essa opção.")
            lab.setObjectName("hint")
            lab.setWordWrap(True)
            self.extra_lay.addWidget(lab)
            return
        cur = self.cfg.feature_value(MOD_PKG_WIDE, "aspect", "16:9")
        box = combo([("16:9 (padrão)", "16:9"), ("16:10 (bordas menores)", "16:10"),
                     ("3:2 (bordas ainda menores)", "3:2"), ("Seguir a janela (até 16:9)", "auto")], cur)
        box.currentIndexChanged.connect(lambda: self._ws_aspect(box.currentData()))
        self._row("Proporção da tela", box)
        lab = QLabel("Experimental. Se as bordas laterais mostrarem falhas visuais, uma proporção menor "
                     "(16:10 ou 3:2) esconde parte delas. Vale na próxima vez que você jogar.")
        lab.setObjectName("hint")
        lab.setWordWrap(True)
        self.extra_lay.addWidget(lab)

    def _ws_aspect(self, val):
        self.cfg.set_feature_value(MOD_PKG_WIDE, "aspect", val)
        self._timer.start()

    def _row(self, text, widget):
        r = QHBoxLayout()
        r.addWidget(QLabel(text))
        r.addStretch(1)
        r.addWidget(widget)
        self.extra_lay.addLayout(r)

    def _extra_hd(self, m):
        spec = MOD_PKG_HD
        mine = self.is_on(m)
        repl = Switch(mine and self.cfg.feature_value(spec, "replacements", "true") == "true")
        dump = Switch(mine and self.cfg.feature_value(spec, "dump", "false") == "true")
        for s in (repl, dump):
            s.accent = self.accent
        repl.toggled.connect(lambda on: self._hd_opt(m, "replacements", on))
        dump.toggled.connect(lambda on: self._hd_opt(m, "dump", on))
        wide = Switch(pack_wide(m.dir))
        wide.accent = self.accent
        wide.toggled.connect(lambda on: (set_pack_wide(m.dir, on), self._hd_refresh(m)))
        self._row("Carregar texturas HD (replacements/)", repl)
        self._row("Capturar texturas originais (dumps/)", dump)
        self._row("Captura ampla (recomendado)", wide)
        self.hd_count = QLabel("")
        self.hd_count.setObjectName("hint")
        self.hd_diag = QLabel("")
        self.hd_diag.setObjectName("status")
        self.hd_diag.setWordWrap(True)
        self.hd_diag.setTextFormat(Qt.RichText)
        self.extra_lay.addWidget(self.hd_count)
        self.extra_lay.addWidget(self.hd_diag)
        self.hd_rebuild = SlantButton("Atualizar o jogo (recompilar)", "primary")
        self.hd_rebuild.clicked.connect(self.rebuild_requested)
        self.extra_lay.addWidget(self.hd_rebuild)
        hb = QHBoxLayout()
        hb.setSpacing(8)
        for text, fn, var in (("Pasta dumps", lambda: self._open_sub(m, "dumps"), "ghost"),
                              ("Pasta replacements", lambda: self._open_sub(m, "replacements"), "ghost"),
                              ("Ampliar capturas…", lambda: self._upscale(m), "primary")):
            b = SlantButton(text, var)
            b.clicked.connect(fn)
            hb.addWidget(b)
        hb.addStretch(1)
        self.extra_lay.addLayout(hb)
        self._hd_refresh(m)

    def _hd_refresh(self, m):
        def n(sub):
            try:
                return sum(1 for f in (m.dir / sub).rglob("*") if f.is_file() and f.name != ".keep")
            except OSError:
                return 0
        self.hd_count.setText(f"Capturadas: {n('dumps')}  ·  Texturas HD: {n('replacements')}")
        if not pack_wide(m.dir):
            self.hd_count.setText(self.hd_count.text() + "  ·  captura ampla DESLIGADA: sprites pequenos não são salvos")
        msgs = []
        has_pkg = (GAME_DIR / "mods" / "bundled" / "psx.enhancement.hd-textures").exists()
        self.hd_rebuild.setVisible(not has_pkg)
        if not has_pkg:
            msgs.append('<span style="color:#ff6b6b"><b>O seu jogo foi compilado com uma versão antiga do framework, '
                        'que não tem o plugin de texturas HD</b> (game/mods/bundled/psx.enhancement.hd-textures '
                        'não existe). Por isso nada é capturado. Clique em <b>Atualizar o jogo</b> abaixo: ele '
                        'recompila com o framework novo (demora; precisa de internet e do disco).</span>')
        ds = hd_disk_state(GAME_DIR)
        if ds["enabled"] and ds["pack"] == str(m.dir):
            msgs.append(f'<span style="color:#58e08a">state.toml no disco: HD Texturas LIGADO '
                        f'(capturar={ds["dump"] or "false"}, carregar={ds["repl"] or "true"}).</span>')
        elif ds["enabled"]:
            msgs.append('<span style="color:#ffcc66">state.toml no disco: o HD Texturas está ligado, mas usando '
                        'OUTRA pasta de pacote.</span>')
        else:
            msgs.append('<span style="color:#ffcc66">state.toml no disco: HD Texturas <b>DESLIGADO</b> — o jogo '
                        'não vai capturar nada. Ligue "Ativar este mod" acima.</span>')
        rep = hd_run_report(m.dir)
        if rep:
            msgs.append(rep)
        self.hd_diag.setText("<br>".join(msgs))

    def _extra_patch(self, m):
        for o in m.ext.get("options", []):
            oid, t = o["id"], o["type"]
            cur = self.cfg.feature_value(m.spec, oid, "")
            default = o.get("default", False if t == "boolean" else o.get("min", 0) if t == "integer" else "")
            if t == "boolean":
                val = (cur or str(default)).lower() == "true"
                w = Switch(val)
                w.accent = self.accent
                w.toggled.connect(lambda on, oid=oid: self._opt(m, oid, "true" if on else "false"))
            elif t == "integer":
                w = SliderRow(int(o["min"]), int(o["max"]), int(cur or default), "{}")
                w.changed.connect(lambda x, oid=oid: self._opt(m, oid, str(int(x))))
            else:
                chs = [(str(c.get("label", c["value"])), str(c["value"])) for c in o["choices"]]
                w = combo(chs, cur or str(default or chs[0][1]))
                w.currentIndexChanged.connect(lambda _=0, w=w, oid=oid: self._opt(m, oid, w.currentData()))
            self._row(str(o.get("label", oid)), w)

    # ---------------------------------------------------------------- acoes
    def _sync_master(self, m):
        self.switch.blockSignals(True)
        self.switch.setChecked(self.is_on(m))
        self.switch.blockSignals(False)

    def _hd_opt(self, m, name, on):
        if not self.is_on(m):
            self.apply(m, True)
            self._sync_master(m)
        self.cfg.set_feature_value(MOD_PKG_HD, name, "true" if on else "false")
        self.refresh_states()
        self._timer.start()
        self._hd_refresh(m)

    def _opt(self, m, oid, val):
        self.cfg.set_feature_value(m.spec, oid, val)
        self._timer.start()

    def _open_sub(self, m, sub):
        (m.dir / sub).mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(m.dir / sub)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=clean_env())

    def _upscale(self, m):
        (m.dir / "replacements").mkdir(parents=True, exist_ok=True)
        UpscaleDialog(self, m.dir).exec()
        self._hd_refresh(m)

    def _toggled(self, on: bool):
        m = self.mods[self.cur]
        if m.kind != "toggle" or m.error or m.template:
            return
        self.apply(m, on)
        self.refresh_states()
        self._timer.start()
        if m.external:
            self.select(self.cur)

    def _fps(self):
        self.cfg.set_feature_value(MOD_PKG_INTERP, "rate", self.fps_combo.currentData())
        self.d_note.setText("Dica: ative também a 'Interpolação de quadros' para o limite valer."
                            if not self.cfg.feature_enabled(MOD_PKG_INTERP) else "")
        self.refresh_states()
        self._timer.start()

    def _flush(self):
        try:
            self.cfg.save()
        except OSError:
            pass
        self.changed.emit()


class InterfacePage(Page):
    changed = Signal()

    def __init__(self, prefs: dict, art: QPixmap, switches: list):
        super().__init__(art)
        self.prefs = prefs
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(PageHeader("Launcher style", "INTERFACE"))
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(14)
        outer.addWidget(scroll_of(inner), 1)
        row = QHBoxLayout()
        reset = SlantButton("Restaurar padrão")
        reset.setObjectName("ghost")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        outer.addLayout(row)
        self._widgets = {}

        c = Card("Cores")
        am = combo([("Automática por aba", "auto"), ("Cor personalizada", "custom")],
                   prefs["accent_mode"])
        am.currentIndexChanged.connect(lambda: self._p("accent_mode", am.currentData()))
        c.row("Cor de destaque", am)
        self.color_btn = QPushButton(prefs["accent_color"])
        self.color_btn.clicked.connect(self._pick_color)
        self._paint_color_btn()
        c.row("Cor personalizada", self.color_btn)
        st = combo([("Gradiente com brilho", "gradient"), ("Grade futurista", "grid"),
                    ("Cor sólida", "solid")], prefs["bg_style"])
        st.currentIndexChanged.connect(lambda: self._p("bg_style", st.currentData()))
        c.row("Estilo do fundo", st)
        gl = SliderRow(0, 100, prefs["glow"], "{}%")
        gl.changed.connect(lambda x: self._p("glow", x))
        c.row("Intensidade do brilho", gl)
        po = SliderRow(30, 100, prefs["panel_opacity"], "{}%")
        po.changed.connect(lambda x: self._p("panel_opacity", x))
        c.row("Opacidade dos painéis", po)
        rd = SliderRow(0, 28, prefs["radius"], "{}px")
        rd.changed.connect(lambda x: self._p("radius", x))
        c.row("Cantos cortados", rd)
        fs = SliderRow(80, 140, prefs["font_scale"], "{}%")
        fs.changed.connect(lambda x: self._p("font_scale", x))
        c.row("Tamanho do texto", fs)
        v.addWidget(c)

        c = Card("Personagens")
        side = combo([("Direita", "right"), ("Esquerda", "left"), ("Oculto", "hidden")], prefs["art_side"])
        side.currentIndexChanged.connect(lambda: self._p("art_side", side.currentData()))
        c.row("Posição da arte", side)
        sc = SliderRow(60, 130, prefs["art_scale"], "{}%")
        sc.changed.connect(lambda x: self._p("art_scale", x))
        c.row("Tamanho da arte", sc)
        fl = Switch(prefs["art_float"])
        fl.toggled.connect(lambda on: self._p("art_float", bool(on)))
        switches.append(fl)
        c.row("Personagem flutuando", fl)
        v.addWidget(c)

        c = Card("Transições")
        tr = combo([("Deslizar", "slide"), ("Desvanecer", "fade"), ("Zoom", "zoom"),
                    ("Nenhuma", "none")], prefs["transition"])
        tr.currentIndexChanged.connect(lambda: self._p("transition", tr.currentData()))
        c.row("Efeito ao trocar de aba", tr)
        du = SliderRow(100, 1200, prefs["duration"], "{} ms")
        du.s.setSingleStep(20)
        du.changed.connect(lambda x: self._p("duration", x))
        c.row("Duração", du)
        pa = Switch(prefs["parallax"])
        pa.toggled.connect(lambda on: self._p("parallax", bool(on)))
        switches.append(pa)
        c.row("Parallax (arte se move mais)", pa)
        v.addWidget(c)

        c = Card("Comportamento")
        op = combo([("Fechar o launcher", "close"), ("Manter aberto", "keep")], prefs["on_play"])
        op.currentIndexChanged.connect(lambda: self._p("on_play", op.currentData()))
        c.row("Ao iniciar o jogo", op)
        v.addWidget(c)
        v.addStretch(1)
        self._widgets.update(dict(am=am, st=st, gl=gl, po=po, rd=rd, fs=fs, side=side, sc=sc,
                                  fl=fl, tr=tr, du=du, pa=pa, op=op))

    def _p(self, k, v):
        self.prefs[k] = v
        self.changed.emit()

    def _paint_color_btn(self):
        col = QColor(self.prefs["accent_color"])
        fg = "#000" if col.lightness() > 140 else "#fff"
        self.color_btn.setStyleSheet(
            f"QPushButton{{background:{col.name()};color:{fg};border-radius:8px;padding:6px 16px;}}")
        self.color_btn.setText(col.name().upper())

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.prefs["accent_color"]), self, "Cor de destaque")
        if c.isValid():
            self.prefs["accent_color"] = c.name()
            self.prefs["accent_mode"] = "custom"
            self._widgets["am"].setCurrentIndex(self._widgets["am"].findData("custom"))
            self._paint_color_btn()
            self.changed.emit()

    def _reset(self):
        self.prefs.update(PREFS_DEFAULT)
        w = self._widgets
        w["am"].setCurrentIndex(w["am"].findData(self.prefs["accent_mode"]))
        w["st"].setCurrentIndex(w["st"].findData(self.prefs["bg_style"]))
        w["side"].setCurrentIndex(w["side"].findData(self.prefs["art_side"]))
        w["tr"].setCurrentIndex(w["tr"].findData(self.prefs["transition"]))
        w["op"].setCurrentIndex(w["op"].findData(self.prefs["on_play"]))
        for k, key in [("gl", "glow"), ("po", "panel_opacity"), ("rd", "radius"),
                       ("fs", "font_scale"), ("sc", "art_scale"), ("du", "duration")]:
            w[k].s.setValue(self.prefs[key])
        w["fl"].setChecked(self.prefs["art_float"])
        w["pa"].setChecked(self.prefs["parallax"])
        self._paint_color_btn()
        self.changed.emit()


# --------------------------------------------------------------------------- backdrop, host
STRIP = 16


class Backdrop(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.accent = QColor(PAGE_ACCENTS[0])
        self.style_name = "grid"
        self.glow = 0.7
        self.art_right = True
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(9, 13, 20))
        g.setColorAt(1, QColor(13, 19, 29))
        p.fillRect(self.rect(), g)
        if self.style_name != "solid":
            a = QColor(self.accent)
            cx = w * (0.8 if self.art_right else 0.2)
            rg = QRadialGradient(cx, h * 0.6, max(w, h) * 0.55)
            a.setAlpha(int(80 * self.glow))
            rg.setColorAt(0, a)
            a.setAlpha(0)
            rg.setColorAt(1, a)
            p.fillRect(self.rect(), rg)
            if self.style_name == "grid":
                p.setPen(QPen(QColor(255, 255, 255, 13)))
                step = 40
                for x in range(STRIP, w, step):
                    p.drawLine(x, 0, x, h)
                for y in range(0, h, step):
                    p.drawLine(0, y, w, y)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 9)))
                for i in range(-h, w, 46):
                    p.drawLine(i, h, i + h, 0)
        # tiras vermelhas nas laterais
        for x in (0, w - STRIP):
            p.fillRect(x, 0, STRIP, h, QColor(18, 10, 12))
            y = 0
            while y < h:
                p.fillRect(x + 3, y + 3, STRIP - 6, 18, QColor(206, 40, 40))
                p.fillRect(x + 3, y + 3, 3, 18, QColor(255, 110, 110))
                y += 24


class TransitionOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.layers = []   # (pix, QPointF pos, is_new, is_art)
        self.t = 0.0
        self.style = "slide"
        self.direction = 1
        self.parallax = True

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        t, W = self.t, self.width()
        for pix, pos, is_new, is_art in self.layers:
            if pix.isNull():
                continue
            f = (0.55 if self.parallax else 0.3) if is_art else 0.3
            sz = pix.deviceIndependentSize()
            op, dx, sc = 1.0, 0.0, 1.0
            if self.style == "slide":
                if is_new:
                    dx, op = self.direction * W * f * (1 - t), t
                else:
                    dx, op = -self.direction * W * f * t, 1 - t
            elif self.style == "fade":
                op = t if is_new else 1 - t
                if is_art:
                    sc = (0.94 + 0.06 * t) if is_new else (1 + 0.04 * t)
            elif self.style == "zoom":
                op = t if is_new else 1 - t
                sc = (0.88 + 0.12 * t) if is_new else (1 + 0.1 * t)
            p.save()
            p.setOpacity(max(0.0, min(1.0, op)))
            p.translate(pos.x() + sz.width() / 2 + dx, pos.y() + sz.height() / 2)
            p.scale(sc, sc)
            p.drawPixmap(QPointF(-sz.width() / 2, -sz.height() / 2), pix)
            p.restore()


class PageHost(QWidget):
    finished = Signal()

    def __init__(self, pages: list[Page], parent=None):
        super().__init__(parent)
        self.pages = pages
        self.cur = 0
        self.style = "slide"
        self.duration = 480
        self.parallax = True
        for i, pg in enumerate(pages):
            pg.setParent(self)
            pg.setVisible(i == 0)
        self.overlay = TransitionOverlay(self)
        self.overlay.hide()
        self.anim = QVariantAnimation(self)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._tick)
        self.anim.finished.connect(self._done)
        self._target = 0

    def resizeEvent(self, e):
        for pg in self.pages:
            pg.setGeometry(self.rect())
        self.overlay.setGeometry(self.rect())

    def _snap(self, pg: Page):
        pg.setGeometry(self.rect())
        pg.relayout()
        con = pg.content.grab()
        art = pg.art.grab() if (pg.has_art and pg.art.isVisible()) else QPixmap()
        return (con, QPointF(pg.content.mapTo(self, QPoint(0, 0))),
                art, QPointF(pg.art.mapTo(self, QPoint(0, 0))))

    def go(self, idx: int):
        if idx == self._target:
            return
        if self.anim.state() == QVariantAnimation.Running:
            self.anim.stop()
            self._done()
        old, new = self.pages[self.cur], self.pages[idx]
        self._target = idx
        if self.style == "none" or self.duration <= 0:
            old.hide()
            new.show()
            self.cur = idx
            self.finished.emit()
            return
        new.show()
        sn = self._snap(new)
        so = self._snap(old)
        old.hide()
        new.hide()
        ov = self.overlay
        ov.style, ov.parallax = self.style, self.parallax
        ov.direction = 1 if idx > self.cur else -1
        ov.layers = [(so[0], so[1], False, False), (so[2], so[3], False, True),
                     (sn[0], sn[1], True, False), (sn[2], sn[3], True, True)]
        ov.t = 0.0
        ov.setGeometry(self.rect())
        ov.show()
        ov.raise_()
        self.anim.setDuration(self.duration)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def _tick(self, v):
        self.overlay.t = float(v)
        self.overlay.update()

    def _done(self):
        self.overlay.hide()
        self.overlay.layers = []
        for i, pg in enumerate(self.pages):
            pg.setVisible(i == self._target)
        self.cur = self._target
        self.finished.emit()


class NavBar(QWidget):
    selected = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)
        self.accent = QColor(PAGE_ACCENTS[0])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(34, 14, 34, 14)
        lay.setSpacing(6)
        self.logo = QLabel()
        self.logo.setObjectName("logo")
        lay.addWidget(self.logo)
        lay.addSpacing(22)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.btns = []
        for i, t in enumerate(labels):
            b = SlantButton(t, "tab")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b._on = 1.0 if i == 0 else 0.0
            self.group.addButton(b, i)
            lay.addWidget(b)
            self.btns.append(b)
        lay.addStretch(1)
        self.ver = QLabel()
        self.ver.setObjectName("ver")
        lay.addWidget(self.ver)
        self.group.idClicked.connect(self.selected)
        self.set_accent(self.accent)

    def set_accent(self, c: QColor):
        self.accent = c
        self.logo.setText(f'<span style="color:{c.name()}">X</span><span style="color:#ffffff">5</span>')
        self.ver.setText(f'<span style="color:{c.name()}">■</span>  v{VERSION}')
        for b in self.btns:
            b.update()

    def move_to(self, i, animate=True):
        if 0 <= i < len(self.btns) and not self.btns[i].isChecked():
            self.btns[i].setChecked(True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(11, 16, 24, 235))
        p.setPen(QPen(QColor(150, 162, 182, 150), 2))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class BuildDialog(QDialog):
    def __init__(self, cmd: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compilando Mega Man X5 para Linux")
        self.resize(820, 480)
        v = QVBoxLayout(self)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family:monospace;")
        v.addWidget(self.log)
        self.btn = SlantButton("Cancelar", "ghost")
        self.btn.clicked.connect(self._cancel)
        v.addWidget(self.btn)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        from PySide6.QtCore import QProcessEnvironment
        qe = QProcessEnvironment()
        for k, v in clean_env().items():
            qe.insert(k, v)
        self.proc.setProcessEnvironment(qe)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._fin)
        self.ok = False
        self.proc.start(cmd[0], cmd[1:])

    def _read(self):
        self.log.appendPlainText(bytes(self.proc.readAllStandardOutput()).decode(errors="replace").rstrip())

    def _fin(self, code, _):
        self.ok = code == 0
        self.log.appendPlainText("\n=== CONCLUÍDO ===" if self.ok else f"\n=== FALHOU (código {code}) ===")
        self.btn.setText("Fechar")
        self.btn.clicked.disconnect()
        self.btn.clicked.connect(self.accept)

    def _cancel(self):
        self.proc.kill()
        self.reject()


# --------------------------------------------------------------------------- main window
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        icon = ASSETS / "icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.prefs = load_prefs()
        self.cfg = GameConfig(GAME_DIR)
        self.switches: list[Switch] = []
        self.resize(self.prefs["win_w"], self.prefs["win_h"])
        self.setMinimumSize(1000, 600)

        self.backdrop = Backdrop(self)
        arts = [load_art(n) for n in ("zero", "x", "sigma")]
        self.play_page = PlayPage(self.cfg, arts[0])
        self.set_page = SettingsPage(self.cfg, arts[1], self.switches)
        self.ui_page = InterfacePage(self.prefs, arts[2], self.switches)
        self.mods_page = ModsPage(self.cfg)
        self.pages = [self.play_page, self.set_page, self.mods_page, self.ui_page]
        cap = art_captions()
        self.play_page.art.caption = cap["zero"]
        self.set_page.art.caption = cap["x"]
        self.ui_page.art.caption = cap["sigma"]
        self.host = PageHost(self.pages)
        self.nav = NavBar(["JOGAR", "CONFIG", "MODS", "INTERFACE"])

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 0, 16, 0)
        root.setSpacing(0)
        root.addWidget(self.nav)
        root.addWidget(self.host, 1)

        self.accent = QColor(PAGE_ACCENTS[0])
        self.acc_anim = QVariantAnimation(self)
        self.acc_anim.valueChanged.connect(self._accent_tick)

        self.nav.selected.connect(self.switch)
        self.host.finished.connect(self._after_switch)
        self.ui_page.changed.connect(self.apply_prefs)
        self.play_page.settings_changed.connect(self._save_cfg)
        self.play_page.play_clicked.connect(self.on_play)
        self.set_page.changed.connect(self.play_page.refresh)
        self.mods_page.changed.connect(self.play_page.refresh)
        self.mods_page.rebuild_requested.connect(self._rebuild)

        self.clock = QTimer(self, interval=33)
        self.clock.timeout.connect(self._tick_art)
        self.clock.start()
        self.proc: subprocess.Popen | None = None
        self.watch = QTimer(self, interval=700)
        self.watch.timeout.connect(self._watch)
        for k in ("antialiasing_mode", "bloom", "dithering", "anisotropic_filtering"):
            self.cfg.remove("video", k)           # chaves antigas que o runtime ignora
        apply_p1_device(self.cfg)
        self._save_cfg()
        self.play_page.refresh_run_info()
        self.apply_prefs()

    # ---- theming
    def _accent_for(self, idx):
        if self.prefs["accent_mode"] == "custom":
            return QColor(self.prefs["accent_color"])
        return QColor(PAGE_ACCENTS[idx])

    def _accent_tick(self, c):
        self.accent = QColor(c)
        THEME["accent"] = self.accent
        self.backdrop.accent = self.accent
        self.backdrop.update()
        self.nav.set_accent(self.accent)
        self.pages[self.host._target].art.accent = self.accent
        for pg in self.pages:
            pg.art.accent = self.accent

    def stylesheet(self) -> str:
        p, a = self.prefs, self.accent
        fs = p["font_scale"] / 100.0
        acc = a.name()
        px = lambda n: int(n * fs)
        return f"""
        * {{ color:#e6ebf5; font-family:"Chakra Petch"; font-size:{px(13)}px; }}
        QWidget {{ background:transparent; }}
        QLabel#logo {{ font-size:{px(34)}px; font-weight:700; font-style:italic; }}
        QLabel#ver {{ font-family:"Share Tech Mono"; font-size:{px(13)}px; color:#9aa6ba; }}
        QLabel#caption {{ font-family:"Share Tech Mono"; color:{acc}; font-size:{px(13)}px; letter-spacing:2px; }}
        QFrame#capLine {{ background:{acc}; }}
        QLabel#bigTitle {{ font-size:{px(46)}px; font-weight:700; font-style:italic; letter-spacing:1px; }}
        QLabel#pageTitle {{ font-size:{px(28)}px; font-weight:700; font-style:italic; }}
        QLabel#subTitle {{ font-family:"Share Tech Mono"; color:#f2b233; font-size:{px(13)}px; letter-spacing:1px; }}
        QLabel#cardTitle {{ color:#c4cddc; font-size:{px(13)}px; font-weight:600; letter-spacing:2px; }}
        QLabel#cardSquare {{ background:{acc}; }}
        QFrame#cardLine {{ background:rgba(255,255,255,45); }}
        QFrame#sep {{ background:rgba(255,255,255,24); }}
        QLabel#rowLabel {{ font-size:{px(14)}px; font-weight:500; color:#dfe5f0; }}
        QLabel#segval {{ color:#f2b233; font-family:"Silkscreen"; font-size:{px(11)}px; }}
        QLabel#hint, QLabel#status {{ color:#8a96ab; font-size:{px(12)}px; }}
        QLabel#pressStart {{ font-family:"Share Tech Mono"; color:#f2b233; font-size:{px(14)}px; letter-spacing:2px; }}
        QLabel#modName {{ font-weight:700; font-size:{px(16)}px; }}
        QLabel#modState {{ font-family:"Share Tech Mono"; font-size:{px(12)}px; font-weight:700; }}
        QFrame#chip {{ background:rgba(255,255,255,14); border:none; }}
        QLabel#chipTitle {{ font-family:"Share Tech Mono"; color:#8a96ab; font-size:{px(11)}px; letter-spacing:1px; }}
        QLabel#chipVal {{ font-weight:700; font-size:{px(13)}px; }}
        QLineEdit {{ background:rgba(9,13,20,235); border:1px solid rgba(150,162,182,130); padding:6px 10px;
                     font-family:"Share Tech Mono"; font-size:{px(13)}px; border-radius:0; }}
        QLineEdit:focus {{ border-color:{acc}; }}
        QScrollBar:vertical {{ background:rgba(255,255,255,20); width:8px; margin:0; }}
        QScrollBar::handle:vertical {{ background:#e3e8f2; min-height:40px; }}
        QScrollBar::handle:vertical:hover {{ background:{acc}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        QToolTip {{ background:#0e1322; color:white; border:1px solid {acc}; padding:6px; }}
        QDialog, QMessageBox {{ background:#0b0f1d; }}
        QPlainTextEdit {{ background:#070a14; border:1px solid rgba(255,255,255,30); }}
        QPushButton {{ background:rgba(255,255,255,18); border:1px solid rgba(255,255,255,40); padding:6px 14px; }}
        """

    def apply_prefs(self):
        p = self.prefs
        self.accent = self._accent_for(self.host._target)
        THEME["accent"] = self.accent
        THEME["panel_alpha"] = int(255 * p["panel_opacity"] / 100)
        THEME["cut"] = 4.0 + p["radius"]
        self.backdrop.accent = self.accent
        self.backdrop.style_name = p["bg_style"]
        self.backdrop.glow = p["glow"] / 100
        self.backdrop.art_right = p["art_side"] != "left"
        self.backdrop.update()
        self.nav.set_accent(self.accent)
        for sw in self.switches:
            sw.accent = self.accent
            sw.update()
        for pg in self.pages:
            pg.apply_layout(p["art_side"], p["art_scale"] / 100)
            pg.art.accent = self.accent
            pg.art.float_on = p["art_float"]
        self.host.style = p["transition"]
        self.host.duration = p["duration"]
        self.host.parallax = p["parallax"]
        self.setStyleSheet(self.stylesheet())
        self.mods_page.set_accent(self.accent)
        for w in self.findChildren(QWidget):
            w.update()

    # ---- navigation
    def switch(self, idx: int):
        self.nav.move_to(idx)
        target = self._accent_for(idx)
        self.acc_anim.stop()
        self.acc_anim.setDuration(max(120, self.prefs["duration"]))
        self.acc_anim.setStartValue(self.accent)
        self.acc_anim.setEndValue(target)
        self.acc_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.acc_anim.start()
        self.host.go(idx)

    def _after_switch(self):
        self.accent = self._accent_for(self.host._target)
        THEME["accent"] = self.accent
        self.setStyleSheet(self.stylesheet())
        for sw in self.switches:
            sw.accent = self.accent
        self.mods_page.set_accent(self.accent)
        for w in self.findChildren(QWidget):
            w.update()

    def _tick_art(self):
        for pg in self.pages:
            pg.art.tick(0.033)

    def resizeEvent(self, e):
        self.backdrop.setGeometry(self.rect())
        self.backdrop.lower()
        super().resizeEvent(e)

    def closeEvent(self, e):
        self.prefs["win_w"], self.prefs["win_h"] = self.width(), self.height()
        save_prefs(self.prefs)
        super().closeEvent(e)

    # ---- game
    def _save_cfg(self):
        try:
            self.cfg.save()
        except OSError as ex:
            QMessageBox.warning(self, APP_NAME, f"Não consegui salvar as configurações:\n{ex}")

    def on_play(self):
        pg = self.play_page
        pg.refresh()
        if not pg.disc_ok:
            QMessageBox.warning(self, APP_NAME,
                                "Selecione um disco válido de Mega Man X5 (USA, SLUS-01334) "
                                "na aba JOGAR primeiro.")
            return
        apply_p1_device(self.cfg)
        self._save_cfg()
        if not RUNTIME.exists():
            self.run_build()
            return
        if not self._hd_preflight():
            return
        env = clean_env()
        try:
            logf = open(GAME_DIR / "last_run.log", "wb")
            self.proc = subprocess.Popen([str(RUNTIME), "--no-launcher"], cwd=str(GAME_DIR), env=env,
                                         stdout=logf, stderr=subprocess.STDOUT)
        except OSError as ex:
            QMessageBox.critical(self, APP_NAME, f"Não consegui iniciar o jogo:\n{ex}")
            return
        if self.prefs["on_play"] == "close":
            QTimer.singleShot(500, self.close)
        else:
            pg.play_btn.setEnabled(False)
            pg.play_btn.setText("JOGANDO…")
            self.watch.start()

    def _hd_preflight(self) -> bool:
        """Avisa se o jogador marcou capturar/carregar texturas mas o mod esta DESLIGADO no disco."""
        ds = hd_disk_state(GAME_DIR)
        wants = ds["present"] and not ds["enabled"] and "true" in (ds["dump"], ds["repl"])
        if not wants:
            return True
        r = QMessageBox.question(self, APP_NAME,
                                 "O mod HD Texturas está marcado para capturar/carregar texturas, mas está "
                                 "DESLIGADO — assim o jogo não captura nada.\n\nLigar agora e jogar?",
                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Yes:
            mp = self.mods_page
            for m in mp.mods:
                if m.mtype == "texture-pack" and not m.error:
                    mp.apply(m, True)
                    break
            self._save_cfg()
        return True

    def _watch(self):
        if self.proc and self.proc.poll() is not None:
            self.watch.stop()
            self.play_page.play_btn.setEnabled(True)
            self.play_page.refresh()
            self.play_page.refresh_run_info()
            self.mods_page.select(self.mods_page.cur)

    def _rebuild(self):
        if not self.play_page.disc_ok:
            QMessageBox.warning(self, APP_NAME, "Selecione primeiro o disco de Mega Man X5 (aba JOGAR) — a "
                                "recompilação precisa dele.")
            return
        r = QMessageBox.question(self, APP_NAME,
                                 "Vou recompilar o jogo com o framework mais novo (necessário para o mod de "
                                 "texturas HD).\n\n• Demora bastante (como na primeira vez) e precisa de internet.\n"
                                 "• O jogo atual é guardado em game/backup-antigo.\n• Só é trocado se a "
                                 "compilação terminar bem.\n\nContinuar?", QMessageBox.Yes | QMessageBox.No)
        if r == QMessageBox.Yes:
            self.run_build()

    def run_build(self):
        if not BUILD_SCRIPT.exists():
            QMessageBox.critical(self, APP_NAME, f"build_linux.sh não encontrado em:\n{BUILD_SCRIPT}")
            return
        cmd = ["bash", str(BUILD_SCRIPT), "--yes", "--disc", self.play_page.disc_edit.text()]
        dlg = BuildDialog(cmd, self)
        dlg.exec()
        self.play_page.refresh()
        self.mods_page.reload()
        if dlg.ok:
            QMessageBox.information(self, APP_NAME, "Compilação concluída. Clique em JOGAR!")


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("mmx5-launcher")
    from PySide6.QtGui import QFontDatabase
    for fn in sorted((ASSETS / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(fn))
    f = app.font()
    f.setFamilies(["Chakra Petch", "Noto Sans", "DejaVu Sans"])
    app.setFont(f)
    win = MainWindow()
    win.show()
    shot = os.environ.get("MMX5_SELFTEST_SHOT")
    if shot:   # modo de teste: captura cada aba e sai
        def run():
            def grab(i):
                win.grab().save(f"{shot}_{i}.png")
            for i in range(4):
                QTimer.singleShot(500 + i * 1100, (lambda k: lambda: win.switch(k))(i))
                QTimer.singleShot(500 + i * 1100 + 900, (lambda k: lambda: grab(k))(i))
            QTimer.singleShot(700, lambda: win.grab().save(f"{shot}_mid.png"))
            QTimer.singleShot(500 + 4 * 1100 + 300, app.quit)
        run()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
