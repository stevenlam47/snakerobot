#!/usr/bin/env python3
"""Custom ROS 2 GUI node for the two-axis ST3215 servo rig.

- Joystick (mouse drag or arrow keys) jogs the servos in real time.
- "Set Zero" stores the current position as the new zero.
- "Go to Zero" requires a ~1s hold; once confirmed it commands the
  servos back to zero and the UI stays locked out until the firmware
  reports it has arrived.
"""

import math
import sys

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Empty
from geometry_msgs.msg import Point

from PyQt5.QtCore import QTimer
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

ROS_SPIN_PERIOD_MS = 20  # 50 Hz
GO_ZERO_HOLD_MS = 1000


class ServoGuiNode(Node):
    """Owns every publisher/subscriber; the Qt window drives it."""

    def __init__(self):
        super().__init__('servo_gui_node')

        self.cmd_pub = self.create_publisher(Point, '/servo_cmd', 10)
        self.set_zero_pub = self.create_publisher(Empty, '/set_zero', 10)
        self.go_zero_pub = self.create_publisher(Empty, '/go_zero', 10)

        self.create_subscription(Point, '/servo_feedback', self._on_feedback, 10)
        self.create_subscription(Bool, '/homing_status', self._on_homing_status, 10)

        self.homing = False
        self.feedback_cb = None   # set by MainWindow
        self.homing_cb = None     # set by MainWindow

    def publish_cmd(self, x, y):
        msg = Point()
        msg.x = float(x)
        msg.y = float(y)
        msg.z = 0.0
        self.cmd_pub.publish(msg)

    def send_set_zero(self):
        self.set_zero_pub.publish(Empty())

    def send_go_zero(self):
        self.go_zero_pub.publish(Empty())

    def _on_feedback(self, msg):
        if self.feedback_cb:
            self.feedback_cb(msg)

    def _on_homing_status(self, msg):
        self.homing = msg.data
        if self.homing_cb:
            self.homing_cb(msg.data)


class MainWindow(QMainWindow):
    def __init__(self, node: ServoGuiNode):
        super().__init__()
        self.node = node
        self.node.feedback_cb = self.on_feedback
        self.node.homing_cb = self.on_homing_status

        self.setWindowTitle('ST3215 servo control - micro-ROS')
        self.resize(420, 560)

        central = QWidget()
        layout = QVBoxLayout(central)

        self.status_label = QLabel('Status: idle')
        layout.addWidget(self.status_label)

        self.pos_label = QLabel('X: --   Y: --')
        layout.addWidget(self.pos_label)

        self.joystick = JoystickWidget(size=260)
        self.joystick.moved.connect(self.on_joystick_moved)
        jog_row = QHBoxLayout()
        jog_row.addStretch()
        jog_row.addWidget(self.joystick)
        jog_row.addStretch()
        layout.addLayout(jog_row)

        hint = QLabel('Drag the joystick or use the arrow keys (click it first)')
        hint.setStyleSheet('color: gray; font-size: 11px;')
        layout.addWidget(hint)

        btn_row = QHBoxLayout()

        self.set_zero_btn = QPushButton('Set Zero')
        self.set_zero_btn.clicked.connect(self.on_set_zero)
        btn_row.addWidget(self.set_zero_btn)

        self.go_zero_btn = LongPressButton('Go to Zero (hold)', hold_ms=GO_ZERO_HOLD_MS)
        self.go_zero_btn.longPressed.connect(self.on_go_zero)
        btn_row.addWidget(self.go_zero_btn)

        layout.addLayout(btn_row)

        self.setCentralWidget(central)
        self.joystick.setFocus()

        # Pump rclpy from inside the Qt event loop instead of a separate
        # thread - keeps every ROS callback on the same thread as the UI,
        # so it's always safe to touch widgets directly from them.
        self.ros_timer = QTimer(self)
        self.ros_timer.timeout.connect(self.spin_once)
        self.ros_timer.start(ROS_SPIN_PERIOD_MS)

    def spin_once(self):
        rclpy.spin_once(self.node, timeout_sec=0.0)

    def on_joystick_moved(self, x, y):
        if self.node.homing:
            return  # ignore manual jog while a go-to-zero move is active
        self.node.publish_cmd(x, y)

    def on_set_zero(self):
        self.node.send_set_zero()
        self.status_label.setText('Status: zero position set')

    def on_go_zero(self):
        self.node.send_go_zero()
        self.status_label.setText('Status: homing to zero...')

    def on_feedback(self, msg: Point):
        x_deg = math.degrees(msg.x)
        y_deg = math.degrees(msg.y)
        self.pos_label.setText(f'X: {x_deg:.1f}°   Y: {y_deg:.1f}°')

    def on_homing_status(self, homing: bool):
        self.joystick.setEnabled(not homing)
        self.set_zero_btn.setEnabled(not homing)
        if homing:
            self.status_label.setText('Status: homing... please wait')
        else:
            self.status_label.setText('Status: idle')


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
