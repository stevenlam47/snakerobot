"""A round joystick display widget.

Position can be driven two ways:
- Directly, by dragging it with the mouse.
- Externally, via `external_set(x, y)`, which MainWindow calls once per
  control tick based on whichever key set (WASD or IJKL) applies to this
  particular joystick. Keyboard is handled globally by MainWindow rather
  than per-widget focus, because Qt can only give one widget keyboard
  focus at a time - and we need two joysticks driven by two different
  key sets simultaneously.
"""

from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen
from PyQt5.QtWidgets import QWidget


class JoystickWidget(QWidget):
    moved = pyqtSignal(float, float)

    def __init__(self, parent=None, size=220):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.NoFocus)  # keyboard is handled globally, not per-widget

        self._radius = size / 2 - 20
        self._center = QPointF(size / 2, size / 2)
        self._knob = QPointF(self._center)
        self._pos = [0.0, 0.0]
        self._dragging = False

    def position(self):
        return tuple(self._pos)

    def is_dragging(self):
        return self._dragging

    def external_set(self, x, y):
        """Called by MainWindow's control tick when this widget isn't
        currently being mouse-dragged (keyboard-driven, or springing
        back to center)."""
        if self._dragging:
            return
        self._apply_position(x, y)

    def _apply_position(self, x, y):
        self._pos = [x, y]
        self._knob = QPointF(
            self._center.x() + x * self._radius,
            self._center.y() - y * self._radius,  # screen y is flipped
        )
        self.update()
        self.moved.emit(x, y)

    # ---------------- mouse control ----------------
    def mousePressEvent(self, event):
        self._dragging = True
        self._update_from_mouse(event.pos())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_from_mouse(event.pos())

    def mouseReleaseEvent(self, event):
        self._dragging = False
        # MainWindow's control tick takes over spring-back from here

    def _update_from_mouse(self, pos):
        dx = pos.x() - self._center.x()
        dy = self._center.y() - pos.y()
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > self._radius:
            scale = self._radius / dist
            dx *= scale
            dy *= scale
        self._apply_position(dx / self._radius, dy / self._radius)

    # ---------------- painting ----------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QPen(QColor("#555555"), 2))
        painter.setBrush(QBrush(QColor("#20242c")))
        painter.drawEllipse(self._center, self._radius, self._radius)

        painter.setPen(Qt.NoPen)
        knob_color = QColor("#4da6ff") if self.isEnabled() else QColor("#666666")
        painter.setBrush(QBrush(knob_color))
        painter.drawEllipse(self._knob, 16, 16)
