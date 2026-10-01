"""Reusable widgets for the toolkit UI."""

import math

from jeffy.controls import library
from jeffy.core import color
from jeffy.ui.qt import QtCore, QtGui, QtWidgets

AXES = ["x", "-x", "y", "-y", "z", "-z"]


# ---------------------------------------------------------------------------
# Small factories
# ---------------------------------------------------------------------------
def button(text, callback=None, tooltip=None, height=26):
    widget = QtWidgets.QPushButton(text)
    widget.setMinimumHeight(height)
    if tooltip:
        widget.setToolTip(tooltip)
    if callback:
        widget.clicked.connect(lambda *_args: callback())
    return widget


def spin(value=1.0, minimum=0.0, maximum=1000.0, decimals=2, step=0.1, tooltip=None):
    if decimals == 0:
        widget = QtWidgets.QSpinBox()
        widget.setRange(int(minimum), int(maximum))
        widget.setValue(int(value))
        widget.setSingleStep(max(1, int(step)))
    else:
        widget = QtWidgets.QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setSingleStep(step)
        widget.setValue(value)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def combo(items, current=None, tooltip=None):
    widget = QtWidgets.QComboBox()
    widget.addItems([str(i) for i in items])
    if current is not None and str(current) in [str(i) for i in items]:
        widget.setCurrentIndex([str(i) for i in items].index(str(current)))
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def check(text, value=False, tooltip=None):
    widget = QtWidgets.QCheckBox(text)
    widget.setChecked(value)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def line_edit(text="", placeholder="", tooltip=None):
    widget = QtWidgets.QLineEdit(text)
    widget.setPlaceholderText(placeholder)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def label(text, bold=False, wrap=True):
    widget = QtWidgets.QLabel(text)
    widget.setWordWrap(wrap)
    if bold:
        font = widget.font()
        font.setBold(True)
        widget.setFont(font)
    return widget


def hline():
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setFrameShadow(QtWidgets.QFrame.Sunken)
    return line


def row(*items, stretch=False):
    """Horizontal layout widget. Items can be widgets or ``(text, widget)``."""
    container = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    for item in items:
        if isinstance(item, tuple):
            layout.addWidget(QtWidgets.QLabel(item[0]))
            layout.addWidget(item[1], 1)
        elif isinstance(item, str):
            layout.addWidget(QtWidgets.QLabel(item))
        else:
            layout.addWidget(item, 1)
    if stretch:
        layout.addStretch(1)
    return container


def grid(buttons, columns=3):
    """Grid of widgets."""
    container = QtWidgets.QWidget()
    layout = QtWidgets.QGridLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    for index, widget in enumerate(buttons):
        layout.addWidget(widget, index // columns, index % columns)
    return container


def value_of(widget):
    """Generic value getter for the factory widgets."""
    if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
        return widget.value()
    if isinstance(widget, QtWidgets.QComboBox):
        return widget.currentText()
    if isinstance(widget, QtWidgets.QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QtWidgets.QLineEdit):
        return widget.text()
    if isinstance(widget, QtWidgets.QPlainTextEdit):
        return widget.toPlainText()
    raise TypeError("Unsupported widget %r" % widget)


# ---------------------------------------------------------------------------
# Collapsible section
# ---------------------------------------------------------------------------
class Section(QtWidgets.QWidget):
    """A collapsible group of widgets with a clickable header."""

    def __init__(self, title, expanded=True, parent=None):
        super(Section, self).__init__(parent)
        self.toggle = QtWidgets.QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.toggle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; padding: 4px; "
                                  "background-color: rgba(255, 255, 255, 18); text-align: left; }")
        self.toggle.toggled.connect(self._on_toggle)

        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(6, 4, 6, 6)
        self.content_layout.setSpacing(4)
        self.content.setVisible(expanded)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)

    def _on_toggle(self, checked):
        self.toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        self.content.setVisible(checked)

    def add(self, widget):
        self.content_layout.addWidget(widget)
        return widget


class Page(QtWidgets.QScrollArea):
    """Scrollable page made of sections."""

    TITLE = "Page"

    def __init__(self, parent=None):
        super(Page, self).__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        container = QtWidgets.QWidget()
        self.layout_ = QtWidgets.QVBoxLayout(container)
        self.layout_.setContentsMargins(4, 4, 4, 4)
        self.layout_.setSpacing(6)
        self.setWidget(container)
        self.build()
        self.layout_.addStretch(1)

    def build(self):
        raise NotImplementedError

    def section(self, title, expanded=True):
        widget = Section(title, expanded)
        self.layout_.addWidget(widget)
        return widget


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
class ColorPalette(QtWidgets.QWidget):
    """Maya index colour swatches + custom RGB. Emits ``colorPicked``."""

    colorPicked = QtCore.Signal(object)

    def __init__(self, columns=16, parent=None):
        super(ColorPalette, self).__init__(parent)
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for index in range(1, 32):
            rgb = color.INDEX_RGB[index]
            swatch = QtWidgets.QPushButton()
            swatch.setFixedSize(18, 18)
            swatch.setToolTip("Index %d" % index)
            swatch.setStyleSheet("background-color: rgb(%d, %d, %d); border: 1px solid #222;"
                                 % tuple(int(c * 255) for c in rgb))
            swatch.clicked.connect(lambda *_args, value=index: self.colorPicked.emit(value))
            layout.addWidget(swatch, (index - 1) // columns, (index - 1) % columns)
        custom = QtWidgets.QPushButton("RGB")
        custom.setFixedHeight(18)
        custom.setToolTip("Pick any RGB colour")
        custom.clicked.connect(self._pick_rgb)
        layout.addWidget(custom, 31 // columns, 31 % columns, 1, 2)

    def _pick_rgb(self):
        picked = QtWidgets.QColorDialog.getColor(QtGui.QColor(255, 255, 0), self)
        if picked.isValid():
            self.colorPicked.emit((picked.redF(), picked.greenF(), picked.blueF()))


# ---------------------------------------------------------------------------
# Shape gallery
# ---------------------------------------------------------------------------
_YAW = math.radians(25.0)
_TILT = math.radians(55.0)


def _project(point):
    """Camera looking down at the shape (tilted top view, slightly turned)."""
    x, y, z = point
    x1 = x * math.cos(_YAW) - z * math.sin(_YAW)
    z1 = x * math.sin(_YAW) + z * math.cos(_YAW)
    return x1, z1 * math.sin(_TILT) - y * math.cos(_TILT)


def _sample_curve(curve):
    points = list(curve["points"])
    if curve.get("periodic"):
        points = points + points[:1]
    if curve.get("degree", 1) == 1 or len(points) < 3:
        return points
    # Chaikin smoothing gives a good approximation of cubic curves for icons
    for _iteration in range(3):
        smoothed = [points[0]] if not curve.get("periodic") else []
        for a, b in zip(points, points[1:]):
            smoothed.append(tuple(a[i] * 0.75 + b[i] * 0.25 for i in range(3)))
            smoothed.append(tuple(a[i] * 0.25 + b[i] * 0.75 for i in range(3)))
        if not curve.get("periodic"):
            smoothed.append(points[-1])
        else:
            smoothed.append(smoothed[0])
        points = smoothed
    return points


def shape_icon(name, size=56):
    """Render a library shape into a ``QIcon``."""
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtGui.QColor(45, 45, 45))
    try:
        curves = library.get_shape(name)
    except KeyError:
        return QtGui.QIcon(pixmap)
    projected = [[_project(p) for p in _sample_curve(c)] for c in curves]
    flat = [p for curve in projected for p in curve]
    if not flat:
        return QtGui.QIcon(pixmap)
    min_x = min(p[0] for p in flat)
    max_x = max(p[0] for p in flat)
    min_y = min(p[1] for p in flat)
    max_y = max(p[1] for p in flat)
    extent = max(max_x - min_x, max_y - min_y) or 1.0
    margin = size * 0.12
    scale = (size - 2 * margin) / extent
    offset_x = (size - (max_x - min_x) * scale) / 2.0
    offset_y = (size - (max_y - min_y) * scale) / 2.0
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(120, 200, 255))
    pen.setWidthF(1.5)
    painter.setPen(pen)
    for curve in projected:
        poly = QtGui.QPolygonF([QtCore.QPointF((x - min_x) * scale + offset_x, (y - min_y) * scale + offset_y)
                                for x, y in curve])
        painter.drawPolyline(poly)
    painter.end()
    return QtGui.QIcon(pixmap)


class ShapeGallery(QtWidgets.QListWidget):
    """Icon grid of every library shape."""

    def __init__(self, parent=None):
        super(ShapeGallery, self).__init__(parent)
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setIconSize(QtCore.QSize(48, 48))
        self.setGridSize(QtCore.QSize(78, 78))
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setMovement(QtWidgets.QListView.Static)
        self.setWordWrap(True)
        self.setMinimumHeight(180)
        self.refresh()

    def refresh(self):
        current = self.current_shape()
        self.clear()
        for name in library.list_shapes():
            item = QtWidgets.QListWidgetItem(shape_icon(name), name)
            item.setToolTip(name)
            self.addItem(item)
        self.select_shape(current or "circle")

    def current_shape(self):
        item = self.currentItem()
        return item.text() if item else None

    def select_shape(self, name):
        matches = self.findItems(name, QtCore.Qt.MatchExactly)
        if matches:
            self.setCurrentItem(matches[0])


class VectorWidget(QtWidgets.QWidget):
    def __init__(self, value=(0.0, 1.0, 0.0), parent=None):
        super(VectorWidget, self).__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.spins = []
        for v in value:
            box = spin(v, -1000.0, 1000.0, 3, 0.1)
            layout.addWidget(box)
            self.spins.append(box)

    def value(self):
        return tuple(s.value() for s in self.spins)
