# ST3215 servo joystick + zero-homing GUI (micro-ROS + ROS 2 Jazzy)

Two parts:

1. `esp32_servo_firmware/` — PlatformIO project. Runs on the ESP32-S3,
   talks micro-ROS over USB serial (`/dev/ttyACM0`), drives two ST3215
   servos over UART1.
2. `ros2_ws/src/servo_gui/` — ROS 2 Python package with a PyQt5 GUI:
   joystick (mouse + arrow keys), "Set Zero", and a long-press
   "Go to Zero".

You do **not** need an IP address anywhere in this project — everything
runs over the serial transport through `/dev/ttyACM0`. IP only matters
if you later switch the firmware to the WiFi/UDP transport.

## 0. Hardware / servo prep (one-time)

- Set one servo's ID to `1` (X axis) and the other to `2` (Y axis).
  Waveshare's SCServo library ships a small "change ID" sketch for
  this — connect one servo at a time and run it before wiring both
  onto the same bus. Factory default ID is `1`, so you only need to
  change one of them.
- Wire both servos onto the same half-duplex data line, into
  `SERVO_RX_PIN` / `SERVO_TX_PIN` in `main.cpp` (GPIO17/GPIO18 by
  default — chosen specifically to avoid GPIO19/20, which the
  ESP32-S3 uses internally for native USB).
- Power the servos from a separate 6–8.4V supply, **not** the ESP32's
  5V/3.3V rail, and tie all grounds together.

## 1. Install ROS 2 Jazzy + micro-ROS agent in the VM

```bash
# (skip if ROS 2 Jazzy is already installed)
sudo apt update
sudo apt install ros-jazzy-desktop python3-colcon-common-extensions

# Build the micro-ROS agent (source build, one-time)
source /opt/ros/jazzy/setup.bash
mkdir -p ~/microros_ws/src
cd ~/microros_ws
git clone -b jazzy https://github.com/micro-ROS/micro_ros_setup.git src/micro_ros_setup
rosdep update
rosdep install --from-paths src --ignore-src -y
colcon build
source install/local_setup.bash
ros2 run micro_ros_setup create_agent_ws.sh
ros2 run micro_ros_setup build_agent.sh
```

If you have Docker in the VM instead, this replaces the whole block
above and you can skip straight to step 4:

```bash
docker pull microros/micro-ros-agent:jazzy
```

## 2. VM / USB permissions

- In VMware: **VM menu → Removable Devices →** find the ESP32-S3 →
  **Connect (Disconnect from host)**, so the VM (not your host OS)
  owns the USB device.
- Add your user to the `dialout` group so you don't need `sudo` for
  every serial command, then log out/in (or reboot the VM):

```bash
sudo usermod -aG dialout $USER
```

## 3. Build and flash the firmware

Open `esp32_servo_firmware/` as a PlatformIO project in VS Code
(**PlatformIO: Open Project**), then:

```bash
cd esp32_servo_firmware
pio run                 # build
pio run -t upload       # flash over /dev/ttyACM0
```

If `board = esp32-s3-devkitc-1` in `platformio.ini` doesn't match your
exact board, it usually still works for any generic ESP32-S3-N8R8
dev board — flash size/PSRAM only matter if you outgrow the defaults.
If upload or the serial monitor can't find the port, uncomment the
`upload_port` / `monitor_port` lines in `platformio.ini`.

## 4. Start the micro-ROS agent

Source build:

```bash
source ~/microros_ws/install/local_setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200
```

Docker:

```bash
docker run -it --rm --device=/dev/ttyACM0 --net=host \
  microros/micro-ros-agent:jazzy serial --dev /dev/ttyACM0 -b 115200
```

Power-cycle or press reset on the ESP32-S3 right after starting the
agent — you should see it report a successful client connection.
Sanity-check from another terminal:

```bash
source /opt/ros/jazzy/setup.bash
ros2 topic list
# expect: /servo_cmd /set_zero /go_zero /servo_feedback /homing_status
ros2 topic echo /servo_feedback
```

## 5. Build and run the GUI

```bash
sudo apt install python3-pyqt5

cd ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select servo_gui
source install/setup.bash
ros2 run servo_gui servo_gui_node
```

## 6. Using it

- **Joystick** — click and drag with the mouse, or click it once to
  focus it and use the arrow keys. Either way it springs back to
  center on release, and center = the last zero you set.
- **Set Zero** — single click. Stores the servos' current position as
  the new zero reference for both the joystick and homing.
- **Go to Zero** — press and hold for ~1 second. The button shows
  "Hold to confirm..." while you hold it; releasing early cancels.
  Once confirmed, the joystick and Set Zero button disable themselves
  and the status line reads "homing..." until the firmware reports
  it has arrived, at which point the UI unlocks itself automatically.

## Troubleshooting

- **No `/dev/ttyACM0`**: check VMware's Removable Devices menu (step
  2) and run `ls -l /dev/ttyACM*` / `dmesg | tail` after plugging in.
- **Agent connects but no topics appear**: reset the ESP32-S3 after
  the agent is already running — the firmware only announces itself
  once, right after `set_microros_serial_transports` succeeds.
- **Servos jitter or don't reach target**: lower `MOVE_SPEED` /
  `MOVE_ACC` in `main.cpp`, and confirm the ID-1/ID-2 assignment from
  step 0.
- **GUI window opens but joystick keys don't respond**: click inside
  the joystick circle first — Qt only routes key events to a focused
  widget.

## Extending this

- Persist the zero offset across power cycles with the ESP32
  `Preferences` (NVS) library instead of keeping it in RAM.
- Swap the `/servo_feedback` `geometry_msgs/Point` for a proper
  `sensor_msgs/JointState` once you're comfortable with
  `micro_ros_utilities_create_message_memory` — useful if you add
  more axes later.
- Add a torque-enable/disable topic so the servos can be moved by
  hand when idle.
