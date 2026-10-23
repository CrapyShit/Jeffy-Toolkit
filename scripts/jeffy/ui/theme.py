"""The eye of the Jeff Inventory window: the Proto Yeff logo and its states.

The window keeps Maya's own grey style. Only its header is custom: a soft
dot-matrix strip where the **eye** shows what the belt is doing:

``idle``     a light eye with a square of light,
``loading``  green: the square shears into the sigil while a command runs,
``fault``    red: the two halves slipped apart (the last command failed).

The shelf icons in ``icons/`` are drawn by the same code (in the logo's full
colours) by ``tools/make_icons.py``.
"""

import os
import weakref

from jeffy.ui.qt import QtCore, QtGui, QtWidgets

# the logo's own colours (icons)
LOGO_BLACK = "#0b0b0b"
LOGO_LIME = "#c8ff1a"
LOGO_WHITE = "#f2f2ec"
LOGO_RED = "#f04e23"

# the window: muted versions that sit in Maya's grey
BANNER = "#373737"
UNLIT = "#414141"
DIM = "#8c8c8c"
SOFT_WHITE = "#cfcfca"
SOFT_LIME = "#a7bd58"
SOFT_RED = "#c46f55"

IDLE, LOADING, FAULTED = "idle", "loading", "fault"
STATES = (IDLE, LOADING, FAULTED)
#: shear of the two eye halves, in eye widths
SHEAR = {IDLE: 0.0, LOADING: 0.07, FAULTED: 0.13}
LOGO_COLORS = {IDLE: (LOGO_WHITE, LOGO_LIME), LOADING: (LOGO_LIME, None), FAULTED: (LOGO_RED, None)}
SOFT_COLORS = {IDLE: (SOFT_WHITE, SOFT_LIME), LOADING: (SOFT_LIME, None), FAULTED: (SOFT_RED, None)}
STATE_TEXT = {IDLE: "Idle", LOADING: "Working...", FAULTED: "Fault"}

ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "icons")

_BANNERS = weakref.WeakSet()
_STATE = {"value": IDLE}


# ---------------------------------------------------------------------------
# The eye
# ---------------------------------------------------------------------------
def _color(value):
    return QtGui.QColor(value)


def eye_width(rect, state, fit=None):
    """Width of the eye (unsheared) so the ``fit`` state's eye fills ``rect``."""
    fit = fit or state
    width = rect.width() / (1.0 + 2.0 * SHEAR[fit])
    return min(width, rect.height() / 0.46)


def paint_eye(painter, rect, state=LOADING, fit=None, colors=None, cut=None):
    """Paint the eye in ``rect`` (QRectF).

    :param fit: size the eye as if it were this state (keeps the size constant across states)
    :param colors: ``{state: (eye colour, light colour)}`` (default: the logo's)
    :param cut: colour of the cut-outs (``None`` clears them: transparent)
    """
    eye_color, light_color = (colors or LOGO_COLORS)[state]
    width = eye_width(rect, state, fit)
    a, b = width / 2.0, width * 0.23
    cx, cy = rect.center().x(), rect.center().y()
    shift = SHEAR[state] * width

    painter.save()
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(_color(eye_color))
    for dx, direction in ((shift, -1.0), (-shift, 1.0)):  # upper half slides right, lower half left
        half = QtGui.QPainterPath()
        half.moveTo(cx - a + dx, cy)
        half.quadTo(cx + dx, cy + direction * 2.0 * b, cx + a + dx, cy)
        half.closeSubpath()
        painter.drawPath(half)

    def hole(x, y, w, h):
        if cut is None:
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
            painter.fillRect(QtCore.QRectF(x, y, w, h), QtCore.Qt.black)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
        else:
            painter.fillRect(QtCore.QRectF(x, y, w, h), _color(cut))

    if state == IDLE:  # a square of light
        frame, light = width * 0.25, width * 0.16
        hole(cx - frame / 2.0, cy - frame / 2.0, frame, frame)
        painter.fillRect(QtCore.QRectF(cx - light / 2.0, cy - light / 2.0, light, light), _color(light_color))
    else:  # the sigil: two stepped blocks, slipping with the halves on a fault
        bw, bh = width * 0.19, width * 0.13
        slip = (shift - SHEAR[LOADING] * width) if state == FAULTED else 0.0
        hole(cx + slip, cy - bh, bw, bh)
        hole(cx - bw - slip, cy, bw, bh)
    painter.restore()


def eye_pixmap(size, state=LOADING, tile=True):
    """A square pixmap of the logo eye (``tile``: on a rounded black tile)."""
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    margin = 0.0
    if tile:
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(_color(LOGO_BLACK))
        radius = size * 0.18
        painter.drawRoundedRect(QtCore.QRectF(0, 0, size, size), radius, radius)
        margin = size * 0.08
    paint_eye(painter, QtCore.QRectF(margin, margin, size - 2 * margin, size - 2 * margin), state,
              cut=LOGO_BLACK if tile else None)
    painter.end()
    return pixmap


def eye_icon(state=LOADING):
    icon = QtGui.QIcon()
    for size in (16, 24, 32, 48, 64):
        icon.addPixmap(eye_pixmap(size, state))
    return icon


# ---------------------------------------------------------------------------
# State (the window header shows it)
# ---------------------------------------------------------------------------
def state():
    return _STATE["value"]


def set_state(value):
    """Show ``idle``, ``loading`` or ``fault`` on every open banner (repainted right away)."""
    if value not in STATES:
        raise ValueError("Unknown state %r" % value)
    _STATE["value"] = value
    for banner in list(_BANNERS):
        try:
            banner.repaint()
        except RuntimeError:  # deleted with its window
            pass


def status_color(error):
    """Colour of a panel's result message."""
    return SOFT_RED if error else SOFT_LIME


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
class EyeBanner(QtWidgets.QWidget):
    """The header: the eye on a soft dot-matrix strip, the state and version on the right."""

    PITCH = 3
    DOT = 2

    def __init__(self, title="", parent=None):
        super(EyeBanner, self).__init__(parent)
        self.title = title
        self.setFixedHeight(12 * self.PITCH + 4)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._cache = {}
        _BANNERS.add(self)

    def _render(self, width, height, current):
        pitch, dot = self.PITCH, self.DOT
        columns, rows = max(int(width // pitch), 1), max(int(height // pitch), 1)
        mask = QtGui.QImage(min(columns, 40), rows, QtGui.QImage.Format_ARGB32_Premultiplied)
        mask.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(mask)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        paint_eye(painter, QtCore.QRectF(2, 1, 30, rows - 2), current, fit=FAULTED, colors=SOFT_COLORS)
        painter.end()

        pixmap = QtGui.QPixmap(width, height)
        pixmap.fill(_color(BANNER))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        ox, oy = (width - columns * pitch) / 2.0, (height - rows * pitch) / 2.0
        for row in range(rows):
            for column in range(columns):
                color = QtGui.QColor.fromRgba(mask.pixel(column, row)) if column < mask.width() else None
                if color is not None and color.alpha() > 110:
                    color.setAlpha(255)
                else:
                    color = _color(UNLIT)
                painter.setBrush(color)
                painter.drawRect(QtCore.QRectF(ox + column * pitch, oy + row * pitch, dot, dot))
        painter.end()
        return pixmap

    def paintEvent(self, _event):
        current = state()
        key = (self.width(), self.height(), current)
        if key not in self._cache:
            self._cache = {key: self._render(self.width(), self.height(), current)}
        painter = QtGui.QPainter(self)
        painter.drawPixmap(0, 0, self._cache[key])
        right = QtCore.QRectF(0, 0, self.width() - 10, self.height())
        painter.setPen(_color(SOFT_COLORS[current][0] if current != IDLE else DIM))
        painter.drawText(right.adjusted(0, -7, 0, -7), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                         STATE_TEXT[current])
        painter.setPen(_color(DIM))
        painter.drawText(right.adjusted(0, 7, 0, 7), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self.title)
        painter.end()


def apply(widget):
    """The window's icon (the rest of the window keeps Maya's style)."""
    widget.setWindowIcon(eye_icon(LOADING))
