"""The Proto Yeff look of the Jeff Inventory window.

* Palette: near black, lime, off-white, and a red-orange for faults.
* The **eye** logo and its three states, which the window header shows live:

  ``idle``     a white eye with a square of light,
  ``loading``  lime: the square shears into the sigil while a build runs,
  ``fault``    red: the two halves slipped apart (the last command failed).

* :class:`EyeBanner`: the header, a dot-matrix display (eye + JEFF).
* :func:`stylesheet`: the Qt style of the window (scoped to it, Maya keeps its own).

Everything is drawn with Qt (no image files are needed at runtime); the shelf
icons in ``icons/`` are rendered from the same code by ``tools/make_icons.py``.
"""

import os
import tempfile
import weakref

from jeffy.ui.qt import QtCore, QtGui, QtWidgets

BLACK = "#0b0b0b"
PANEL = "#111111"
RAISED = "#191919"
LINE = "#2b2b2b"
UNLIT = "#1b1d17"
DIM = "#80807a"
TEXT = "#e6e6df"
WHITE = "#f2f2ec"
LIME = "#c8ff1a"
LIME_SOFT = "#dcff6b"
FAULT = "#f04e23"
MONO = "'JetBrains Mono', 'Cascadia Mono', Consolas, 'Courier New', monospace"

IDLE, LOADING, FAULTED = "idle", "loading", "fault"
STATES = (IDLE, LOADING, FAULTED)
#: shear of the two eye halves, in eye widths
SHEAR = {IDLE: 0.0, LOADING: 0.07, FAULTED: 0.13}
EYE_COLOR = {IDLE: WHITE, LOADING: LIME, FAULTED: FAULT}
STATE_TEXT = {IDLE: "IDLE", LOADING: "LOADING", FAULTED: "FAULT"}

ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "icons")
SHELF_ICON = "jeffy_eye.png"

#: the banner's letters, one character per dot (12 dots tall, 3 dot strokes)
GLYPHS = {
    "J": ("...######", "...######", "......###", "......###", "......###", "......###", "......###", "......###",
          "###...###", "###...###", ".#######.", "..#####.."),
    "E": ("#########", "#########", "###......", "###......", "#######..", "#######..", "###......", "###......",
          "###......", "###......", "#########", "#########"),
    "F": ("#########", "#########", "###......", "###......", "#######..", "#######..", "###......", "###......",
          "###......", "###......", "###......", "###......"),
}

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


def paint_eye(painter, rect, state=LOADING, fit=None, color=None, cut=None):
    """Paint the eye in ``rect`` (QRectF).

    :param fit: size the eye as if it were this state (keeps the size constant across states)
    :param color: eye colour (default: the state's)
    :param cut: colour of the cut-outs (``None`` clears them: transparent)
    """
    width = eye_width(rect, state, fit)
    a, b = width / 2.0, width * 0.23
    cx, cy = rect.center().x(), rect.center().y()
    shift = SHEAR[state] * width
    fill = _color(color or EYE_COLOR[state])

    painter.save()
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(fill)
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
        painter.fillRect(QtCore.QRectF(cx - light / 2.0, cy - light / 2.0, light, light), _color(LIME))
    else:  # the sigil: two stepped blocks, slipping with the halves on a fault
        bw, bh = width * 0.19, width * 0.13
        slip = (shift - SHEAR[LOADING] * width) if state == FAULTED else 0.0
        hole(cx + slip, cy - bh, bw, bh)
        hole(cx - bw - slip, cy, bw, bh)
    painter.restore()


def eye_pixmap(size, state=LOADING, tile=True):
    """A square pixmap of the eye (``tile``: on a rounded black tile, like the logo cards)."""
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    if tile:
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(_color(BLACK))
        radius = size * 0.18
        painter.drawRoundedRect(QtCore.QRectF(0, 0, size, size), radius, radius)
        margin = size * 0.08
    else:
        margin = 0.0
    paint_eye(painter, QtCore.QRectF(margin, margin, size - 2 * margin, size - 2 * margin), state,
              cut=BLACK if tile else None)
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


# ---------------------------------------------------------------------------
# Dot-matrix banner
# ---------------------------------------------------------------------------
class EyeBanner(QtWidgets.QWidget):
    """The header: the eye and JEFF lit on a dot-matrix display, the state on the right."""

    PITCH = 4
    DOT = 3

    def __init__(self, subtitle="INVENTORY", version="", parent=None):
        super(EyeBanner, self).__init__(parent)
        self.subtitle = subtitle
        self.version = version
        self.setFixedHeight(16 * self.PITCH + 2)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._cache = {}
        _BANNERS.add(self)

    def _mask(self, columns, rows, current):
        """Low resolution image of the lit cells (one pixel per dot)."""
        image = QtGui.QImage(columns, rows, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        eye_rect = QtCore.QRectF(1, 1, 40, rows - 2)
        paint_eye(painter, eye_rect, current, fit=FAULTED)
        painter.end()
        lime = _color(LIME).rgba()
        x = 45
        top = max((rows - len(GLYPHS["J"])) // 2, 0)
        for letter in "JEFF":  # blocky dot letters, like the YEFF wordmark
            glyph = GLYPHS[letter]
            for row, line in enumerate(glyph):
                for column, cell in enumerate(line):
                    if cell == "#" and x + column < columns and top + row < rows:
                        image.setPixel(x + column, top + row, lime)
            x += len(glyph[0]) + 2
        return image

    def _render(self, width, height, current):
        pitch, dot = self.PITCH, self.DOT
        columns, rows = max(int(width // pitch), 1), max(int(height // pitch), 1)
        mask = self._mask(min(columns, 90), rows, current)
        pixmap = QtGui.QPixmap(width, height)
        pixmap.fill(_color(BLACK))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        ox, oy = (width - columns * pitch) / 2.0, (height - rows * pitch) / 2.0
        lit = []
        for row in range(rows):
            for column in range(columns):
                color = QtGui.QColor.fromRgba(mask.pixel(column, row)) if column < mask.width() else None
                if color is not None and color.alpha() > 110:
                    color.setAlpha(255)
                    lit.append((column, row, color))
                else:
                    painter.setBrush(_color(UNLIT))
                    painter.drawRect(QtCore.QRectF(ox + column * pitch, oy + row * pitch, dot, dot))
        for column, row, color in lit:  # glow
            glow = QtGui.QColor(color)
            glow.setAlpha(34)
            painter.setBrush(glow)
            centre = QtCore.QPointF(ox + column * pitch + dot / 2.0, oy + row * pitch + dot / 2.0)
            painter.drawEllipse(centre, pitch * 1.3, pitch * 1.3)
        for column, row, color in lit:
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
        font = mono_font(11)
        font.setBold(True)
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 2.0)
        painter.setFont(font)
        right = QtCore.QRectF(0, 0, self.width() - 12, self.height())
        painter.setPen(_color(EYE_COLOR[current] if current != IDLE else DIM))
        painter.drawText(right.adjusted(0, -9, 0, -9), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                         "[ %s ]" % STATE_TEXT[current])
        painter.setPen(_color(DIM))
        painter.drawText(right.adjusted(0, 9, 0, 9), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                         ("%s  %s" % (self.subtitle, self.version)).strip())
        painter.end()


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
def mono_font(pixel_size=11):
    font = QtGui.QFont("Consolas")
    if hasattr(font, "setFamilies"):
        font.setFamilies(["JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New"])
    font.setStyleHint(QtGui.QFont.Monospace)
    font.setPixelSize(pixel_size)
    return font


def title(text):
    widget = QtWidgets.QLabel(text.upper())
    widget.setObjectName("jeffyTitle")
    return widget


def hint(text):
    widget = QtWidgets.QLabel(text)
    widget.setObjectName("jeffyHint")
    widget.setWordWrap(True)
    return widget


def status_color(error):
    return FAULT if error else LIME


# ---------------------------------------------------------------------------
# Style sheet
# ---------------------------------------------------------------------------
_QSS = """
QWidget { background-color: %(BLACK)s; color: %(TEXT)s; font-family: %(MONO)s; font-size: 11px; }
QScrollArea, QStackedWidget, QSplitter { border: none; }
QSplitter::handle { background-color: %(LINE)s; width: 1px; }
QLabel { background: transparent; }
QLabel#jeffyTitle { color: %(WHITE)s; font-size: 17px; font-weight: bold; letter-spacing: 3px; padding-top: 2px; }
QLabel#jeffyHint { color: %(DIM)s; }
QLabel#jeffyEditing { background-color: rgba(200, 255, 26, 28); border-left: 3px solid %(LIME)s; padding: 5px;
                      color: %(TEXT)s; }

QListWidget#jeffyToolList { background-color: %(PANEL)s; border: none; border-right: 1px solid %(LINE)s;
                            outline: 0; padding: 6px 0px; }
QListWidget#jeffyToolList::item { padding: 4px 6px; border: none; color: %(TEXT)s; }
QListWidget#jeffyToolList::item:selected { background-color: %(LIME)s; color: %(BLACK)s; }
QListWidget#jeffyToolList::item:hover:!selected { background-color: %(RAISED)s; color: %(LIME)s; }

QPushButton { background-color: %(RAISED)s; border: 1px solid %(LINE)s; padding: 4px 10px; color: %(TEXT)s; }
QPushButton:hover { border-color: %(LIME)s; color: %(LIME)s; }
QPushButton:pressed { background-color: %(LIME)s; color: %(BLACK)s; }
QPushButton:disabled { color: #4a4a46; border-color: #202020; }
QPushButton#jeffyPrimary { background-color: %(LIME)s; border: 1px solid %(LIME)s; color: %(BLACK)s;
                           font-weight: bold; letter-spacing: 3px; }
QPushButton#jeffyPrimary:hover { background-color: %(LIME_SOFT)s; color: %(BLACK)s; }
QPushButton#jeffyPrimary:pressed { background-color: %(WHITE)s; }
QPushButton#jeffyDanger:hover { border-color: %(FAULT)s; color: %(FAULT)s; }
QPushButton#jeffyDanger:pressed { background-color: %(FAULT)s; color: %(BLACK)s; }

QToolButton { background-color: %(RAISED)s; border: 1px solid %(LINE)s; padding: 2px 6px; color: %(TEXT)s; }
QToolButton:hover { border-color: %(LIME)s; color: %(LIME)s; }
QToolButton:pressed { background-color: %(LIME)s; color: %(BLACK)s; }
QToolButton#jeffySection { background: transparent; border: none; border-bottom: 1px solid %(LINE)s;
                           color: %(LIME)s; font-weight: bold; letter-spacing: 2px; padding: 7px 2px 4px 0px;
                           text-align: left; }
QToolButton#jeffySection:hover { color: %(LIME_SOFT)s; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background-color: #0e0e0e; border: 1px solid %(LINE)s; padding: 3px 5px; color: %(TEXT)s;
    selection-background-color: %(LIME)s; selection-color: %(BLACK)s; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-color: %(LIME)s; }
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover { border-color: #444; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox::down-arrow { image: url(%(ARROW_DOWN_LIME)s); width: 8px; height: 5px; }
QComboBox QAbstractItemView { background-color: %(PANEL)s; border: 1px solid %(LINE)s; outline: 0;
                              selection-background-color: %(LIME)s; selection-color: %(BLACK)s; }
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: %(RAISED)s; border: none; width: 14px; }
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover { background-color: #262626; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(%(ARROW_UP)s); width: 6px; height: 4px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(%(ARROW_DOWN)s); width: 6px; height: 4px; }

QCheckBox { spacing: 6px; background: transparent; }
QCheckBox::indicator { width: 10px; height: 10px; border: 1px solid %(DIM)s; background-color: #0e0e0e; }
QCheckBox::indicator:hover { border-color: %(LIME)s; }
QCheckBox::indicator:checked { background-color: %(LIME)s; border-color: %(LIME)s; }

QTreeWidget, QListWidget { background-color: %(PANEL)s; border: 1px solid %(LINE)s; outline: 0;
                           alternate-background-color: #151515; }
QTreeWidget::item, QListWidget::item { padding: 3px 2px; }
QTreeWidget::item:selected, QListWidget::item:selected { background-color: %(LIME)s; color: %(BLACK)s; }
QTreeWidget::item:hover:!selected, QListWidget::item:hover:!selected { color: %(LIME)s; }
QHeaderView::section { background-color: %(BLACK)s; color: %(DIM)s; border: none;
                       border-bottom: 1px solid %(LINE)s; padding: 4px; letter-spacing: 1px; }

QScrollBar:vertical { background: transparent; width: 8px; margin: 0px; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 0px; }
QScrollBar::handle { background-color: #2e2e2e; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background-color: %(LIME)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QTabWidget::pane { border: none; border-top: 1px solid %(LINE)s; }
QTabBar::tab { background: transparent; color: %(DIM)s; padding: 5px 12px; border: none; }
QTabBar::tab:selected { color: %(LIME)s; border-bottom: 2px solid %(LIME)s; }

QToolTip { background-color: %(BLACK)s; color: %(TEXT)s; border: 1px solid %(LIME)s; padding: 4px; }
"""


def _arrow(name, color, width, height, down):
    """A small triangle image for the style sheet (written once per session in the temp folder)."""
    folder = os.path.join(tempfile.gettempdir(), "jeffy_ui")
    path = os.path.join(folder, "%s.png" % name)
    if not os.path.isfile(path):
        if not os.path.isdir(folder):
            os.makedirs(folder)
        scale = 4  # drawn large, then smoothed down
        image = QtGui.QImage(width * scale, height * scale, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(_color(color))
        w, h = width * scale, height * scale
        if down:
            points = [QtCore.QPointF(0, 0), QtCore.QPointF(w, 0), QtCore.QPointF(w / 2.0, h)]
        else:
            points = [QtCore.QPointF(0, h), QtCore.QPointF(w, h), QtCore.QPointF(w / 2.0, 0)]
        painter.drawPolygon(QtGui.QPolygonF(points))
        painter.end()
        image.scaled(width * 2, height * 2, QtCore.Qt.IgnoreAspectRatio,
                     QtCore.Qt.SmoothTransformation).save(path)
    return path.replace("\\", "/")


def stylesheet():
    values = dict((key, value) for key, value in globals().items() if key.isupper() and isinstance(value, str))
    values["ARROW_DOWN_LIME"] = _arrow("arrow_down_lime", LIME, 8, 5, True)
    values["ARROW_DOWN"] = _arrow("arrow_down", DIM, 6, 4, True)
    values["ARROW_UP"] = _arrow("arrow_up", DIM, 6, 4, False)
    return _QSS % values


def apply(widget):
    """Give ``widget`` (the window) the Proto Yeff style. Its children inherit it; Maya keeps its own."""
    widget.setStyleSheet(stylesheet())
    widget.setWindowIcon(eye_icon(LOADING))
