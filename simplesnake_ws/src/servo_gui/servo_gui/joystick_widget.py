"""A round joystick widget controllable by mouse drag or the arrow keys.

Emits `moved(x, y)` with x, y in [-1, 1] (y-up positive) every time the
knob position changes, at a steady ~50 Hz while a key is held or the
mouse is dragging, and while springing back to center on release.
"""

from PyQt5.QtCore import Qt, QPointF, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen
from PyQt5.QtWidgets import QWidget

TICK_MS = 20          # ~50 Hz update rate
KEY_STEP = 0.06        # normalized units added per tick while a key is held
SPRING_STEP = 0.08     # normalized units removed per tick when idle


class JoystickWidget(QWidget):
    moved = pyqtSignal(float, float)

    def __init__(self, parent=None, size=240):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.StrongFocus)

        self._radius = size / 2 - 20
        self._center = QPointF(size / 2, size / 2)
        self._knob = QPointF(self._center)
        self._pos = [0.0, 0.0]
        self._dragging = False

        self._keys_held = {
            Qt.Key_Up: False,
            Qt.Key_Down: False,
            Qt.Key_Left: False,
            Qt.Key_Right: False,
        }

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(TICK_MS)

    # ---------------- timer-driven update ----------------
    def _on_tick(self):
        if self._dragging:
            return  # the mouse is in direct control while dragging

        any_key = any(self._keys_held.values())
        if any_key:
            dx = dy = 0.0
            if self._keys_held[Qt.Key_Up]:
                dy += KEY_STEP
            if self._keys_held[Qt.Key_Down]:
                dy -= KEY_STEP
            if self._keys_held[Qt.Key_Right]:
                dx += KEY_STEP
            if self._keys_held[Qt.Key_Left]:
                dx -= KEY_STEP
            x = max(-1.0, min(1.0, self._pos[0] + dx))
            y = max(-1.0, min(1.0, self._pos[1] + dy))
        else:
            x = self._spring_toward_zero(self._pos[0])
            y = self._spring_toward_zero(self._pos[1])

        self._apply_position(x, y)

    @staticmethod
    def _spring_toward_zero(v):
        if abs(v) <= SPRING_STEP:
            return 0.0
        return v - SPRING_STEP * (1 if v > 0 else -1)

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
        self.setFocus()
        self._update_from_mouse(event.pos())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_from_mouse(event.pos())

    def mouseReleaseEvent(self, event):
        self._dragging = False
        # the timer's spring-back branch takes over from here

    def _update_from_mouse(self, pos):
        dx = pos.x() - self._center.x()
        dy = self._center.y() - pos.y()
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > self._radius:
            scale = self._radius / dist
            dx *= scale
            dy *= scale
        self._apply_position(dx / self._radius, dy / self._radius)

    # ---------------- keyboard control ----------------
    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        if event.key() in self._keys_held:
            self._keys_held[event.key()] = True
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        if event.key() in self._keys_held:
            self._keys_held[event.key()] = False
        else:
            super().keyReleaseEvent(event)

    # ---------------- painting ----------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QPen(QColor("#555555"), 2))
        painter.setBrush(QBrush(QColor("#20242c")))
        painter.drawEllipse(self._center, self._radius, self._radius)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#4da6ff")))
        painter.drawEllipse(self._knob, 16, 16)
