# 4-servo ST3215 rig: dual joystick + path-retrace zero-homing GUI
(micro-ROS + ROS 2 Jazzy)

Two joints, four servos, controlled from one PyQt5 GUI over micro-ROS:

- **Lower joint** (servo IDs 1=X, 2=Y) — jog with **WASD** or mouse-drag
- **Upper joint** (servo IDs 3=X, 4=Y) — jog with **IJKL** or mouse-drag
- **Space bar** — emergency stop, freezes all four servos in place
- **Set Zero** — stores current position of all four as the new zero
- **Go to Zero** (press and hold ~1s) — retraces your jog path in
  reverse, then hands off to the firmware for a precise final approach

You do **not** need an IP address anywhere in this project — everything
runs over the serial transport through `/dev/ttyACM0`. IP only matters
if you later switch the firmware to the WiFi/UDP transport.

## Folder tree

```
project-root/
├── README.md
├── esp32_servo_firmware/              # PlatformIO project
│   ├── platformio.ini
│   └── src/
│       └── main.cpp
└── ros2_ws/
    └── src/
        └── servo_gui/                 # ament_python ROS 2 package
            ├── package.xml
            ├── setup.py
            ├── setup.cfg
            ├── resource/
            │   └── servo_gui          # empty ament index marker
            └── servo_gui/
                ├── __init__.py        # REQUIRED - without this,
                │                      #   find_packages() silently
                │                      #   ships zero .py files
                ├── gui_node.py        # rclpy node + PyQt5 window
                ├── joystick_widget.py # mouse-drag / externally-driven joystick
                ├── long_press_button.py
                └── path_retrace.py    # jog-path recording + reverse replay
```

Place `esp32_servo_firmware/` and `ros2_ws/` (or just the `servo_gui/`
package inside your own workspace's `src/`) wherever suits your setup —
they don't need to be nested together.

## How the pieces fit together

| Topic | Type | Direction | Purpose |
|---|---|---|---|
| `/servo_cmd_lower` | `geometry_msgs/Point` | GUI → firmware | lower-joint jog target, x/y in [-1, 1] |
| `/servo_cmd_upper` | `geometry_msgs/Point` | GUI → firmware | upper-joint jog target, x/y in [-1, 1] |
| `/set_zero` | `std_msgs/Empty` | GUI → firmware | store current pos of all 4 as zero; also clears e-stop |
| `/go_zero` | `std_msgs/Empty` | GUI → firmware | drive all 4 to zero, hold until arrived |
| `/estop` | `std_msgs/Empty` | GUI → firmware | freeze all 4 at current position immediately |
| `/servo_feedback_lower` | `geometry_msgs/Point` | firmware → GUI | lower joint angle (radians, relative to zero) |
| `/servo_feedback_upper` | `geometry_msgs/Point` | firmware → GUI | upper joint angle (radians, relative to zero) |
| `/homing_status` | `std_msgs/Bool` | firmware → GUI | true while a go_zero move is in progress |
| `/estop_status` | `std_msgs/Bool` | firmware → GUI | true while an emergency stop is active |

## 0. Hardware / servo prep (one-time)

- Set servo IDs: **1** = lower X, **2** = lower Y, **3** = upper X,
  **4** = upper Y. Use the SCServo library's ID-change sketch,
  connecting one servo at a time before wiring all four onto the shared
  bus. Factory default ID is `1`, so only one servo starts out correct.
- All four servos share the same half-duplex data line into
  `SERVO_RX_PIN` / `SERVO_TX_PIN` in `main.cpp` (GPIO17/18 by default —
  no wiring changes needed from the 2-servo version, just the extra IDs).
- Power all four servos from a separate 6–8.4V supply, **not** the
  ESP32's 5V/3.3V rail, and tie all grounds together.

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
source install/local_setup.bash    # re-source after the build - required,
                                    # the agent package doesn't exist yet
                                    # the first time you sourced above
```

Add both sourcing lines to `~/.bashrc` so every new terminal has them:

```bash
echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc
echo 'source ~/microros_ws/install/local_setup.bash' >> ~/.bashrc
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

Check `platformio.ini`'s `ARDUINO_USB_MODE` / `ARDUINO_USB_CDC_ON_BOOT`
flags match your board — see "Known environment gotchas" below.

## 4. Start the micro-ROS agent

Source build:

```bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200
```

Docker:

```bash
docker run -it --rm --device=/dev/ttyACM0 --net=host \
  microros/micro-ros-agent:jazzy serial --dev /dev/ttyACM0 -b 115200
```

Sanity-check from another terminal:

```bash
ros2 topic list
# expect: /servo_cmd_lower /servo_cmd_upper /set_zero /go_zero /estop
#         /servo_feedback_lower /servo_feedback_upper /homing_status /estop_status
```

## 5. Build and run the GUI

```bash
sudo apt install python3-pyqt5 python3-numpy

cd ros2_ws          # or wherever your colcon workspace root is
source /opt/ros/jazzy/setup.bash
colcon build --packages-select servo_gui
source install/setup.bash
ros2 run servo_gui servo_gui_node
```

## 6. Using it

- **Lower joint** — WASD, or click-drag the left joystick.
- **Upper joint** — IJKL, or click-drag the right joystick.
- Either joystick springs back to center on release; center = the last
  zero you set.
- **Space bar** — emergency stop. All four servos freeze at their
  current position immediately, both joysticks and Go to Zero lock out,
  and any in-progress retrace is discarded. The only way to resume is
  **Set Zero**.
- **Set Zero** — single click. Stores current position of all four
  servos as the new zero, clears the recorded jog path, and releases
  an emergency stop if one is active.
- **Go to Zero** — press and hold ~1 second. If you've moved the rig
  since the last Set Zero, it **retraces your jog path in reverse**,
  waypoint by waypoint, waiting at each one before advancing; once the
  path is exhausted (or if there was no recorded path at all) it hands
  off to the firmware's own precise homing for the final approach.
  Everything stays locked out until it's fully home.

### About the path retrace

The GUI samples the combined 4-axis commanded position roughly every
150ms while you're jogging (only recording a new waypoint if it's
moved enough to matter), starting fresh every time you press Set Zero.
On Go to Zero, it walks that list backwards, sending each waypoint and
waiting until feedback shows the rig is close enough (or a ~2.5s
per-waypoint timeout passes, as a safety fallback) before moving to the
next one.

This retraces the **commanded** path — the sequence of positions you
asked for — not a frame-by-frame recording of the physical motion.
For routing cables or avoiding obstacles along a known-safe route,
that's exactly what you want; it's just not millisecond-identical to
the original movement.

Tunables live at the top of `path_retrace.py`:
`SAMPLE_PERIOD_S`, `CHANGE_EPSILON`, `ARRIVE_TOLERANCE`,
`WAYPOINT_TIMEOUT_S`, `MAX_WAYPOINTS`.

## Troubleshooting

- **No `/dev/ttyACM0`**: check VMware's Removable Devices menu (step
  2) and run `ls -l /dev/ttyACM*` / `dmesg | tail` after plugging in.
- **Agent runs but the ESP32 never connects (only `/parameter_events`
  and `/rosout` show up in `ros2 topic list`)**: that's the CLI's own
  temporary node, not your firmware — it means no micro-ROS client has
  ever connected. Reset the ESP32-S3 *after* the agent is already
  running (the client only attempts its handshake once, at boot), and
  make sure nothing else (a leftover Serial Monitor tab, an old
  `pio device monitor`) has the port open.
- **Servos jitter or don't reach target**: lower `MOVE_SPEED` /
  `MOVE_ACC` in `main.cpp`, and confirm the ID 1/2/3/4 assignment from
  step 0.
- **GUI opens but nothing responds to keys**: this version doesn't need
  a widget to be focused — WASD/IJKL/Space are caught application-wide.
  If keys still don't register, check the terminal for an eventFilter
  traceback (rare, but would show up there).

### Known environment gotchas (found the hard way)

- **PlatformIO's Python venv can silently break `colcon`/`ros2`.** If
  `~/.bashrc` unconditionally puts `~/.platformio/penv/bin` on `PATH`,
  `colcon build` and `ros2 run` can end up running under PlatformIO's
  Python instead of the system one — builds "succeed" but only ship
  egg-info metadata with zero actual `.py` files, or `ros2 run` fails
  with `ModuleNotFoundError` for packages you know are installed
  (`numpy` is a classic victim, since `rclpy` pulls it in transitively).
  Fix: turn that `.bashrc` line into an on-demand alias instead of an
  automatic export, so a fresh terminal defaults to system Python:
  ```bash
  # instead of: export PATH="$HOME/.platformio/penv/bin:$PATH"
  alias pio-env='export PATH="$HOME/.platformio/penv/bin:$PATH"'
  ```
- **A missing `__init__.py` fails silently.** `setuptools.find_packages()`
  only recognizes `servo_gui/servo_gui/` as an importable package if it
  contains `__init__.py`. Without it, `colcon build` reports success but
  installs zero `.py` files — always worth an `ls` check if `ros2 run`
  claims a package doesn't exist right after a "successful" build.
- **Check which USB chip your board actually uses.** `dmesg | tail`
  after plugging in: `idVendor=303a` is Espressif's native USB
  peripheral (GPIO19/20); `idVendor=1a86` is a WCH CH34x bridge chip on
  the regular UART0 pins instead. `ARDUINO_USB_MODE` /
  `ARDUINO_USB_CDC_ON_BOOT` in `platformio.ini` must match whichever one
  your specific board has, or the firmware will run but transmit on
  pins nothing is actually connected to.

## Extending this

- Persist the zero offset across power cycles with the ESP32
  `Preferences` (NVS) library instead of keeping it in RAM.
- Swap the `geometry_msgs/Point` feedback topics for a proper
  `sensor_msgs/JointState` once you're comfortable with
  `micro_ros_utilities_create_message_memory` — useful if you add
  more joints later.
- The e-stop currently freezes with torque still applied (holds
  position). If you'd rather it go limp, send a torque-disable command
  to all four servos in `estop_callback()` instead of re-writing their
  current position.
- Save a completed path (`self.retrace.path` right before a Go to Zero
  clears it) to disk if you ever want to replay a specific route on
  demand rather than only "the last one recorded."

## Git commit procedure

If this isn't a git repo yet:

```bash
cd project-root          # wherever esp32_servo_firmware/ and ros2_ws/ live
git init
git branch -m main
```

Create (or fix) `.gitignore` at the project root — build artifacts and
caches don't belong in version control:

```bash
cat > .gitignore << 'GITIGNORE'
# ROS 2 / colcon
ros2_ws/build/
ros2_ws/install/
ros2_ws/log/
**/__pycache__/
*.pyc

# PlatformIO
esp32_servo_firmware/.pio/
.pio/

# editor/OS cruft
.vscode/
.DS_Store
GITIGNORE
```

(If you uploaded a file literally named `_gitignore`, that's almost
certainly this file with its leading dot stripped somewhere along the
way — rename it back: `mv _gitignore .gitignore`.)

Stage and commit:

```bash
git add .gitignore README.md esp32_servo_firmware/ ros2_ws/src/servo_gui/
git status                       # double-check nothing from build/install/log snuck in
git commit -m "4-servo dual-joint rig: WASD/IJKL joysticks, e-stop, path-retrace homing"
```

If you already have a remote:

```bash
git remote add origin <your-repo-url>   # only if not already set
git push -u origin main
```

Going forward, a reasonable habit for this project is one commit per
working milestone (e.g. "firmware: 4-servo e-stop", "gui: dual joystick
input", "gui: path retrace") rather than one giant commit — makes it
much easier to `git bisect` back to a known-good state if a later
change breaks something on real hardware.
