"""Componentes visuais do launcher (tema 'X5 tech'): abas inclinadas, cartoes com cantos
cortados, barras segmentadas, seletor com setas, switch ON/OFF."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QVariantAnimation, QEasingCurve, QTimer
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPolygonF)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

AMBER = QColor("#f2b233")
GREEN = QColor("#58e08a")
RED = QColor("#ff6b6b")
MUTED = QColor("#8a96ab")
PANEL_LINE = QColor(190, 202, 220, 120)

# estado compartilhado do tema (a janela principal atualiza)
THEME = {"accent": QColor("#f2b233"), "panel_alpha": 205, "slant": 0.28, "cut": 16.0}

F_UI, F_MONO, F_PIX = "Chakra Petch", "Share Tech Mono", "Silkscreen"


def font(family: str, px: int, weight=QFont.Normal, italic=False, spacing=0.0) -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(weight)
    f.setItalic(italic)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


def chamfer(rect: QRectF, tr=14.0, bl=14.0) -> QPainterPath:
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    p = QPainterPath()
    p.moveTo(x, y)
    p.lineTo(x + w - tr, y)
    p.lineTo(x + w, y + tr)
    p.lineTo(x + w, y + h)
    p.lineTo(x + bl, y + h)
    p.lineTo(x, y + h - bl)
    p.closeSubpath()
    return p


def slant_poly(r: QRectF, s: float) -> QPolygonF:
    return QPolygonF([QPointF(r.left() + s, r.top()), QPointF(r.right(), r.top()),
                      QPointF(r.right() - s, r.bottom()), QPointF(r.left(), r.bottom())])


# --------------------------------------------------------------------------- botoes inclinados
class SlantButton(QPushButton):
    """variants: tab | primary | ghost | play"""

    def __init__(self, text="", variant="ghost", parent=None):
        super().__init__(text, parent)
        self.variant = variant
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._hover = 0.0
        self._on = 1.0 if self.isChecked() else 0.0
        self._ha = QVariantAnimation(self, duration=140)
        self._ha.valueChanged.connect(lambda v: self._set("_hover", v))
        self._ca = QVariantAnimation(self, duration=240)
        self._ca.setEasingCurve(QEasingCurve.OutCubic)
        self._ca.valueChanged.connect(lambda v: self._set("_on", v))
        self.toggled.connect(self._toggled)
        self._sheen = 0.0
        if variant == "play":
            self._sa = QVariantAnimation(self, duration=2600, loopCount=-1)
            self._sa.setStartValue(-0.3)
            self._sa.setEndValue(1.3)
            self._sa.valueChanged.connect(lambda v: self._set("_sheen", v))
            self._sa.start()
        h = {"tab": 38, "primary": 40, "ghost": 36, "play": 58}[variant]
        self.setFixedHeight(h)
        if variant in ("ghost", "primary"):
            self.setMinimumWidth(self.fontMetrics().horizontalAdvance(text) + 56)

    def _set(self, name, v):
        setattr(self, name, float(v))
        self.update()

    def _toggled(self, on):
        self._ca.stop()
        self._ca.setStartValue(self._on)
        self._ca.setEndValue(1.0 if on else 0.0)
        self._ca.start()

    def enterEvent(self, e):
        self._ha.stop()
        self._ha.setStartValue(self._hover)
        self._ha.setEndValue(1.0)
        self._ha.start()

    def leaveEvent(self, e):
        self._ha.stop()
        self._ha.setStartValue(self._hover)
        self._ha.setEndValue(0.0)
        self._ha.start()

    def sizeHint(self):
        w = self.fontMetrics().horizontalAdvance(self.text()) + 56
        if self.variant == "tab":
            w = max(96, w)
        return QSize(w, self.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        acc = THEME["accent"]
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        s = r.height() * THEME["slant"]
        poly = slant_poly(r, s)
        v = self.variant
        if v == "tab":
            base, fg0 = QColor(31, 39, 51), QColor(150, 162, 182)
            fill = mix(base, acc, self._on)
            fill = mix(fill, QColor(255, 255, 255, 255), 0.08 * self._hover * (1 - self._on))
            fg = mix(fg0, QColor(10, 14, 20), self._on)
            f = font(F_UI, 13, QFont.DemiBold, spacing=1.2)
        elif v == "primary":
            fill = mix(QColor(90, 68, 24), QColor(120, 90, 30), self._hover)
            fg = AMBER
            f = font(F_UI, 13, QFont.Bold, spacing=1.5)
        elif v == "play":
            fill = mix(AMBER.darker(105), AMBER.lighter(112), self._hover)
            fg = QColor(18, 14, 6)
            f = font(F_UI, 26, QFont.Bold, italic=True, spacing=12)
        else:
            fill = mix(QColor(27, 35, 47), QColor(44, 56, 74), self._hover)
            fg = mix(QColor(165, 176, 195), QColor(255, 255, 255), self._hover)
            f = font(F_UI, 12, QFont.Medium, italic=False, spacing=0.4)
        if not self.isEnabled():
            fill = mix(fill, QColor(20, 24, 30), 0.6)
            fg = mix(fg, QColor(70, 78, 92), 0.6)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPolygon(poly)
        if v == "play":
            # brilho que passa pelo botao
            path = QPainterPath()
            path.addPolygon(poly)
            p.setClipPath(path)
            x = r.left() + self._sheen * r.width()
            g = QLinearGradient(x - 70, 0, x + 70, 0)
            g.setColorAt(0, QColor(255, 255, 255, 0))
            g.setColorAt(0.5, QColor(255, 255, 255, 120))
            g.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(g)
            p.drawPolygon(slant_poly(QRectF(x - 70, r.top(), 140, r.height()), s))
            p.setClipping(False)
        p.setFont(f)
        p.setPen(fg)
        p.drawText(r.adjusted(s * 0.6, 0, -s * 0.6, 0), Qt.AlignCenter, self.text())


# --------------------------------------------------------------------------- switch
class Switch(QAbstractButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(104, 28)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=150)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._go)
        self.accent = AMBER

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    def _go(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        en = self.isEnabled()
        txt = "ON" if self.isChecked() else "OFF"
        col = AMBER if self.isChecked() else QColor(125, 135, 152)
        if not en:
            col = QColor(80, 88, 100)
        p.setFont(font(F_UI, 12, QFont.Bold, spacing=1.5))
        p.setPen(col)
        p.drawText(QRectF(0, 0, 40, self.height()), Qt.AlignRight | Qt.AlignVCenter, txt)
        tr = QRectF(48, 3, 52, 22)
        s = 5.0
        p.setPen(QPen(mix(QColor(90, 100, 118), AMBER, self._pos), 1.4))
        p.setBrush(mix(QColor(24, 31, 42), QColor(88, 66, 20), self._pos))
        p.drawPolygon(slant_poly(tr, s))
        kw = 22.0
        kx = tr.left() + 3 + (tr.width() - kw - 6) * self._pos
        p.setPen(Qt.NoPen)
        p.setBrush(mix(QColor(160, 170, 188), AMBER, self._pos) if en else QColor(70, 78, 90))
        p.drawPolygon(slant_poly(QRectF(kx, tr.top() + 3, kw, tr.height() - 6), 4))


# --------------------------------------------------------------------------- barra segmentada
class SegBar(QWidget):
    valueChanged = Signal(int)

    def __init__(self, lo=0, hi=100, val=0, parent=None):
        super().__init__(parent)
        self.lo, self.hi, self._v, self._step = lo, hi, val, 1
        self.setFixedHeight(24)
        self.setMinimumWidth(180)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setRange(self, lo, hi):
        self.lo, self.hi = lo, hi
        self.update()

    def setSingleStep(self, s):
        self._step = max(1, int(s))

    def value(self):
        return self._v

    def setValue(self, v):
        v = max(self.lo, min(self.hi, int(v)))
        if v != self._v:
            self._v = v
            self.update()
            self.valueChanged.emit(v)

    def _n(self):
        span = self.hi - self.lo + 1
        return span if span <= 10 else 10

    def _from_x(self, x):
        n = self._n()
        small = (self.hi - self.lo + 1) <= 10
        seg_w = self.width() / n
        if small:
            return self.lo + max(0, min(n - 1, int(x / seg_w)))
        t = max(0.0, min(1.0, x / max(1, self.width())))
        return int(round(self.lo + t * (self.hi - self.lo)))

    def mousePressEvent(self, e):
        self.setValue(self._from_x(e.position().x()))

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self.setValue(self._from_x(e.position().x()))

    def wheelEvent(self, e):
        self.setValue(self._v + (self._step if e.angleDelta().y() > 0 else -self._step))
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = self._n()
        small = (self.hi - self.lo + 1) <= 10
        filled = (self._v - self.lo + 1) if small else int(round((self._v - self.lo) / max(1, self.hi - self.lo) * n))
        gap = 5.0
        w = (self.width() - gap * (n - 1)) / n
        h = self.height() - 8
        for i in range(n):
            x = i * (w + gap)
            r = QRectF(x, 4, w, h)
            on = i < filled
            if on:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(242, 178, 51, 60))
                p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 3, 3)
                p.setBrush(AMBER)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(42, 50, 63))
            p.drawRoundedRect(r, 2, 2)


class SliderRow(QWidget):
    changed = Signal(int)

    def __init__(self, lo, hi, val, fmt="{}", parent=None):
        super().__init__(parent)
        self.fmt = fmt
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        self.s = SegBar(lo, hi, val)
        self.lbl = QLabel(fmt.format(val))
        self.lbl.setObjectName("segval")
        self.lbl.setMinimumWidth(62)
        self.lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.s, 1)
        lay.addWidget(self.lbl)
        self.s.valueChanged.connect(self._ch)

    def _ch(self, v):
        self.lbl.setText(self.fmt.format(v))
        self.changed.emit(v)

    def value(self):
        return self.s.value()


# --------------------------------------------------------------------------- seletor com setas
class ArrowSelect(QWidget):
    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[tuple[str, object]] = []
        self._i = 0
        self.setFixedHeight(42)
        self.setFixedWidth(250)
        self.setCursor(Qt.PointingHandCursor)

    def addItem(self, label, data=None):
        self._items.append((label, data))
        self.update()

    def count(self):
        return len(self._items)

    def currentIndex(self):
        return self._i

    def currentData(self):
        return self._items[self._i][1] if self._items else None

    def findData(self, d):
        for i, (_, x) in enumerate(self._items):
            if x == d:
                return i
        return -1

    def setCurrentIndex(self, i):
        if not self._items:
            return
        i = i % len(self._items)
        if i != self._i:
            self._i = i
            self.update()
            self.currentIndexChanged.emit(i)

    def mousePressEvent(self, e):
        x = e.position().x()
        self.setCurrentIndex(self._i - 1 if x < self.width() * 0.5 else self._i + 1)

    def wheelEvent(self, e):
        self.setCurrentIndex(self._i + (-1 if e.angleDelta().y() > 0 else 1))
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(QPen(QColor(120, 132, 152, 170), 1.2))
        p.setBrush(QColor(11, 16, 23, 230))
        p.drawRect(r)
        acc = THEME["accent"]
        p.setPen(Qt.NoPen)
        p.setBrush(acc if self.isEnabled() else QColor(70, 78, 90))
        cy = r.center().y()
        p.drawPolygon(QPolygonF([QPointF(r.left() + 20, cy - 6), QPointF(r.left() + 20, cy + 6), QPointF(r.left() + 11, cy)]))
        p.drawPolygon(QPolygonF([QPointF(r.right() - 20, cy - 6), QPointF(r.right() - 20, cy + 6), QPointF(r.right() - 11, cy)]))
        p.setFont(font(F_UI, 13, QFont.DemiBold))
        p.setPen(QColor(232, 236, 245))
        txt = self._items[self._i][0] if self._items else ""
        area = r.adjusted(32, 0, -32, 0)
        txt = p.fontMetrics().elidedText(txt, Qt.ElideRight, int(area.width()))
        p.drawText(area, Qt.AlignCenter, txt)


def combo(items, current):
    c = ArrowSelect()
    for label, data in items:
        c.addItem(label, data)
    c.setCurrentIndex(max(0, c.findData(current)))
    return c


# --------------------------------------------------------------------------- cartao
class Card(QFrame):
    """Painel com cantos cortados (topo-direita / base-esquerda) e titulo com linha."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.cut = 16.0
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 18, 24, 18)
        v.setSpacing(8)
        if title:
            hd = QHBoxLayout()
            hd.setSpacing(10)
            sq = QLabel()
            sq.setObjectName("cardSquare")
            sq.setFixedSize(8, 8)
            t = QLabel(title.upper())
            t.setObjectName("cardTitle")
            ln = QFrame()
            ln.setObjectName("cardLine")
            ln.setFixedHeight(1)
            ln.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            hd.addWidget(sq)
            hd.addWidget(t)
            hd.addWidget(ln, 1, Qt.AlignVCenter)
            v.addLayout(hd)
            v.addSpacing(4)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(0)
        self.grid.setColumnStretch(1, 1)
        v.addLayout(self.grid)
        self._r = 0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        cut = THEME["cut"]
        path = chamfer(r, cut, cut)
        p.setPen(QPen(PANEL_LINE, 1.4))
        p.setBrush(QColor(15, 21, 31, THEME["panel_alpha"]))
        p.drawPath(path)
        p.setPen(QPen(THEME["accent"], 2))
        p.drawLine(QPointF(r.right() - cut, r.top()), QPointF(r.right(), r.top() + cut))

    def _sep(self):
        ln = QFrame()
        ln.setObjectName("sep")
        ln.setFixedHeight(1)
        self.grid.addWidget(ln, self._r, 0, 1, 2)
        self._r += 1

    def row(self, label: str, widget: QWidget, hint: str = ""):
        lab = QLabel(label)
        lab.setObjectName("rowLabel")
        lab.setWordWrap(True)
        lab.setMinimumHeight(54)
        self.grid.addWidget(lab, self._r, 0, Qt.AlignVCenter)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(widget)
        self.grid.addLayout(wrap, self._r, 1)
        if hint:
            lab.setToolTip(hint)
            widget.setToolTip(hint)
        self._r += 1
        self._sep()
        return widget

    def full(self, widget: QWidget):
        self.grid.addWidget(widget, self._r, 0, 1, 2)
        self._r += 1
