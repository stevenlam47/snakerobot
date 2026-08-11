"""A QPushButton that only fires after being held down for `hold_ms`.

Releasing early cancels the action, so a stray click can't accidentally
send the servos homing.
"""

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import QPushButton


class LongPressButton(QPushButton):
    longPressed = pyqtSignal()

    def __init__(self, text, hold_ms=1000, parent=None):
        super().__init__(text, parent)
        self._base_text = text
        self._hold_ms = hold_ms

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)

        self.pressed.connect(self._start_hold)
        self.released.connect(self._cancel_hold)

    def _start_hold(self):
        self.setText("Hold to confirm...")
        self._timer.start(self._hold_ms)

    def _cancel_hold(self):
        if self._timer.isActive():
            self._timer.stop()
            self.setText(self._base_text)

    def _fire(self):
        self.setText(self._base_text)
        self.longPressed.emit()
