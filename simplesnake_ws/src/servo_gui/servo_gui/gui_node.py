#!/usr/bin/env python3
"""Custom ROS 2 GUI node for a 4-servo, 2-joint ST3215 rig.

- Lower-joint joystick: WASD keys, or mouse drag on the widget.
- Upper-joint joystick: IJKL keys, or mouse drag on the widget.
- Space bar: emergency stop - freezes all four servos in place and
  locks out jogging until you press Set Zero.
- "Set Zero": stores the current position of all four servos as zero,
  clears the recorded path, and releases an emergency stop if active.
- "Go to Zero" (press and hold ~1s): retraces the recorded jog path in
  reverse, waypoint by waypoint, then hands off to the firmware's own
  precise homing for the final approach to the exact zero position.
"""

import math
import sys

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Empty
from geometry_msgs.msg import Point

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from servo_gui.joystick_widget import JoystickWidget
from servo_gui.long_press_button import LongPressButton
from servo_gui.path_retrace import PathRetrace, IDLE, RETRACING, FINAL_HOMING

CONTROL_PERIOD_MS = 20      # ~50 Hz for both ROS spin and joystick driving
GO_ZERO_HOLD_MS = 1000
KEY_STEP = 0.06
SPRING_STEP = 0.08
MAX_JOG_DEG = 90.0          # MUST match MAX_JOG_DEG in the firmware's main.cpp


class ServoGuiNode(Node):
    """Owns every publisher/subscriber; the Qt window drives it."""

    def __init__(self):
        super().__init__('servo_gui_node')

        self.cmd_lower_pub = self.create_publisher(Point, '/servo_cmd_lower', 10)
        self.cmd_upper_pub = self.create_publisher(Point, '/servo_cmd_upper', 10)
        self.set_zero_pub = self.create_publisher(Empty, '/set_zero', 10)
        self.go_zero_pub = self.create_publisher(Empty, '/go_zero', 10)
        self.estop_pub = self.create_publisher(Empty, '/estop', 10)

        self.create_subscription(Point, '/servo_feedback_lower', self._on_feedback_lower, 10)
        self.create_subscription(Point, '/servo_feedback_upper', self._on_feedback_upper, 10)
        self.create_subscription(Bool, '/homing_status', self._on_homing_status, 10)
        self.create_subscription(Bool, '/estop_status', self._on_estop_status, 10)

        self.homing = False
        self.estop_active = False
        self.feedback_lower = (0.0, 0.0)  # normalized (degrees / MAX_JOG_DEG)
        self.feedback_upper = (0.0, 0.0)

        self.homing_cb = None   # set by MainWindow: fn(was_homing, is_homing)
        self.estop_cb = None    # set by MainWindow: fn(active)

    def publish_cmd_lower(self, x, y):
        self._publish_point(self.cmd_lower_pub, x, y)

    def publish_cmd_upper(self, x, y):
        self._publish_point(self.cmd_upper_pub, x, y)

    @staticmethod
    def _publish_point(pub, x, y):
        msg = Point()
        msg.x = float(x)
        msg.y = float(y)
        msg.z = 0.0
        pub.publish(msg)

    def send_set_zero(self):
        self.set_zero_pub.publish(Empty())

    def send_go_zero(self):
        self.go_zero_pub.publish(Empty())

    def send_estop(self):
        self.estop_pub.publish(Empty())

    def _on_feedback_lower(self, msg):
        self.feedback_lower = (math.degrees(msg.x) / MAX_JOG_DEG,
                                math.degrees(msg.y) / MAX_JOG_DEG)

    def _on_feedback_upper(self, msg):
        self.feedback_upper = (math.degrees(msg.x) / MAX_JOG_DEG,
                                math.degrees(msg.y) / MAX_JOG_DEG)

    def _on_homing_status(self, msg):
        was_homing = self.homing
        self.homing = msg.data
        if self.homing_cb:
            self.homing_cb(was_homing, self.homing)

    def _on_estop_status(self, msg):
        self.estop_active = msg.data
        if self.estop_cb:
            self.estop_cb(self.estop_active)


class MainWindow(QMainWindow):
    def __init__(self, node: ServoGuiNode):
        super().__init__()
        self.node = node
        self.node.homing_cb = self.on_homing_status
        self.node.estop_cb = self.on_estop_status

        self.setWindowTitle('4-servo ST3215 rig control - micro-ROS')
        self.resize(760, 640)

        self._keys_lower = {'up': False, 'down': False, 'left': False, 'right': False}
        self._keys_upper = {'up': False, 'down': False, 'left': False, 'right': False}
        self._key_map_lower = {Qt.Key_W: 'up', Qt.Key_S: 'down', Qt.Key_A: 'left', Qt.Key_D: 'right'}
        self._key_map_upper = {Qt.Key_I: 'up', Qt.Key_K: 'down', Qt.Key_J: 'left', Qt.Key_L: 'right'}

        self.retrace = PathRetrace()
        self._pending_go_zero = False  # true from the moment /go_zero is sent
                                        # until the firmware confirms /homing_status,
                                        # so there's no gap where jogging sneaks in

        central = QWidget()
        outer = QVBoxLayout(central)

        self.status_label = QLabel('Status: idle')
        outer.addWidget(self.status_label)

        self.pos_label = QLabel('Lower X: --  Y: --    Upper X: --  Y: --')
        outer.addWidget(self.pos_label)

        joy_row = QHBoxLayout()

        lower_col = QVBoxLayout()
        lower_col.addWidget(QLabel('Lower joint - WASD'))
        self.joy_lower = JoystickWidget(size=220)
        lower_col.addWidget(self.joy_lower)
        joy_row.addLayout(lower_col)

        upper_col = QVBoxLayout()
        upper_col.addWidget(QLabel('Upper joint - IJKL'))
        self.joy_upper = JoystickWidget(size=220)
        upper_col.addWidget(self.joy_upper)
        joy_row.addLayout(upper_col)

        outer.addLayout(joy_row)

        hint = QLabel('WASD / IJKL or mouse-drag each joystick. Space = emergency stop.')
        hint.setStyleSheet('color: gray; font-size: 11px;')
        outer.addWidget(hint)

        btn_row = QHBoxLayout()
        self.set_zero_btn = QPushButton('Set Zero')
        self.set_zero_btn.setFocusPolicy(Qt.NoFocus)
        self.set_zero_btn.clicked.connect(self.on_set_zero)
        btn_row.addWidget(self.set_zero_btn)

        self.go_zero_btn = LongPressButton('Go to Zero (hold)', hold_ms=GO_ZERO_HOLD_MS)
        self.go_zero_btn.setFocusPolicy(Qt.NoFocus)
        self.go_zero_btn.longPressed.connect(self.on_go_zero)
        btn_row.addWidget(self.go_zero_btn)
        outer.addLayout(btn_row)

        self.setCentralWidget(central)

        # Keyboard is handled globally (application-wide event filter) so
        # WASD and IJKL can both be held down at once, regardless of which
        # widget technically has Qt focus at that moment.
        QApplication.instance().installEventFilter(self)

        self.control_timer = QTimer(self)
        self.control_timer.timeout.connect(self.on_control_tick)
        self.control_timer.start(CONTROL_PERIOD_MS)

    # ---------------- global keyboard ----------------
    def eventFilter(self, obj: QObject, event):
        if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
            if event.key() == Qt.Key_Space:
                self.on_estop()
                return True
            if event.key() in self._key_map_lower:
                self._keys_lower[self._key_map_lower[event.key()]] = True
                return True
            if event.key() in self._key_map_upper:
                self._keys_upper[self._key_map_upper[event.key()]] = True
                return True
        elif event.type() == QEvent.KeyRelease and not event.isAutoRepeat():
            if event.key() in self._key_map_lower:
                self._keys_lower[self._key_map_lower[event.key()]] = False
                return True
            if event.key() in self._key_map_upper:
                self._keys_upper[self._key_map_upper[event.key()]] = False
                return True
        return super().eventFilter(obj, event)

    # ---------------- main control loop ----------------
    def on_control_tick(self):
        rclpy.spin_once(self.node, timeout_sec=0.0)

        locked = (self.node.estop_active or self.node.homing
                  or self._pending_go_zero or self.retrace.state != IDLE)

        if not locked:
            lx, ly = self._drive(self.joy_lower, self._keys_lower)
            ux, uy = self._drive(self.joy_upper, self._keys_upper)
            self.node.publish_cmd_lower(lx, ly)
            self.node.publish_cmd_upper(ux, uy)
            self.retrace.record(lx, ly, ux, uy)
        elif self.retrace.state == RETRACING:
            self._step_retrace()

        self._apply_lockout()
        self._update_position_label()

    def _drive(self, joy: JoystickWidget, keys: dict):
        if joy.is_dragging():
            return joy.position()
        x, y = joy.position()
        if any(keys.values()):
            dx = (KEY_STEP if keys['right'] else 0.0) - (KEY_STEP if keys['left'] else 0.0)
            dy = (KEY_STEP if keys['up'] else 0.0) - (KEY_STEP if keys['down'] else 0.0)
            x = max(-1.0, min(1.0, x + dx))
            y = max(-1.0, min(1.0, y + dy))
        else:
            x = self._spring(x)
            y = self._spring(y)
        joy.external_set(x, y)
        return joy.position()

    @staticmethod
    def _spring(v):
        if abs(v) <= SPRING_STEP:
            return 0.0
        return v - SPRING_STEP * (1 if v > 0 else -1)

    def _step_retrace(self):
        result = self.retrace.step(*self.node.feedback_lower, *self.node.feedback_upper)
        if result == 'final':
            self.node.send_go_zero()
            self._pending_go_zero = True
            self.status_label.setText('Status: final approach to zero...')
        elif result is not None:
            lx, ly, ux, uy = result
            self.node.publish_cmd_lower(lx, ly)
            self.node.publish_cmd_upper(ux, uy)
            self.status_label.setText(
                f'Status: retracing path ({self.retrace.remaining()} waypoints left)')

    def _update_position_label(self):
        lx, ly = self.node.feedback_lower
        ux, uy = self.node.feedback_upper
        self.pos_label.setText(
            f'Lower X: {lx * MAX_JOG_DEG:.1f}°  Y: {ly * MAX_JOG_DEG:.1f}°    '
            f'Upper X: {ux * MAX_JOG_DEG:.1f}°  Y: {uy * MAX_JOG_DEG:.1f}°'
        )

    # ---------------- button / key actions ----------------
    def on_set_zero(self):
        self.node.send_set_zero()
        self.retrace.clear()
        self._pending_go_zero = False
        self.status_label.setText('Status: zero position set')

    def on_go_zero(self):
        if self.node.estop_active:
            self.status_label.setText('Status: clear the emergency stop (Set Zero) before homing')
            return
        started = self.retrace.start()
        if started:
            self.status_label.setText('Status: retracing path...')
        else:
            self.node.send_go_zero()
            self._pending_go_zero = True
            self.status_label.setText('Status: homing to zero...')

    def on_estop(self):
        self.node.send_estop()
        self.retrace.clear()
        self._pending_go_zero = False
        self.status_label.setText('Status: EMERGENCY STOP - press Set Zero to resume')

    # ---------------- status callbacks (fired during ROS spin) ----------------
    def on_homing_status(self, was_homing: bool, is_homing: bool):
        if is_homing:
            self._pending_go_zero = False  # firmware confirmed, no longer just "pending"
        if was_homing and not is_homing:
            # a go_zero cycle just completed
            if self.retrace.state == FINAL_HOMING:
                self.retrace.finish()
            self.status_label.setText('Status: idle')

    def on_estop_status(self, active: bool):
        if not active and self.status_label.text().startswith('Status: EMERGENCY'):
            self.status_label.setText('Status: idle')

    def _apply_lockout(self):
        locked = (self.node.estop_active or self.node.homing
                  or self._pending_go_zero or self.retrace.state != IDLE)
        self.joy_lower.setEnabled(not locked)
        self.joy_upper.setEnabled(not locked)
        self.go_zero_btn.setEnabled(not locked)
        # Set Zero stays enabled even when locked - it's the only way to
        # clear an emergency stop.


def main():
    rclpy.init()
    node = ServoGuiNode()

    app = QApplication(sys.argv)
    window = MainWindow(node)
    window.show()

    exit_code = app.exec_()

    node.destroy_node()
    rclpy.shutdown()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
