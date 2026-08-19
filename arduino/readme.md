ESP32 Dual-Joystick 4-Servo Serial Bus Controller

An Arduino-based control system utilizing an **ESP32 WROOM-32** to drive up to **4 Feetech ST3215 serial bus servos** in continuous rotation (Wheel Mode) using **two analog joysticks** and an **Emergency Stop safety button**.

---

## 🚀 Features
* **Serial Bus Communication:** Communicates with Feetech ST3215 servos via high-speed UART (`Serial2` at 1,000,000 baud).
* **Dual Joystick Control:** Smoothly maps 4 independent analog axes to 4 distinct servo IDs (1 through 4).
* **Built-in Deadzones:** Prevents drift when joysticks are resting at the center.
* **Emergency Stop:** Dedicated hardware button (using internal pull-ups) that instantly halts all motor motion when pressed.
* **ESP32 Optimized:** Uses safe `ADC1` pins to avoid conflicts if Wi-Fi or Bluetooth are enabled.

---

## 📌 Pin Mapping & Wiring

| Component | Pin / Port | ESP32 WROOM-32 GPIO | Notes |
| :--- | :--- | :--- | :--- |
| **Servo Bus (RX)** | RX2 | **GPIO 16** | Receives data from servo daisy chain |
| **Servo Bus (TX)** | TX2 | **GPIO 17** | Sends commands to servo daisy chain |
| **Joystick 1 (X-Axis)** | Analog Out | **GPIO 32** | Controls Servo ID 1 |
| **Joystick 1 (Y-Axis)** | Analog Out | **GPIO 33** | Controls Servo ID 2 |
| **Joystick 2 (X-Axis)** | Analog Out | **GPIO 34** | Controls Servo ID 3 |
| **Joystick 2 (Y-Axis)** | Analog Out | **GPIO 35** | Controls Servo ID 4 |
| **Emergency Stop** | Digital Button | **GPIO 25** | Connects to button pin (other side to GND) |

> ⚠️ **Important Power Warning:** Feetech ST3215 bus servos draw significant current under load. **Do not** power the servos directly from the ESP32's 5V pin. Use an external 7.4V–12V power supply for the servos, and **make sure the GND of the external power supply is tied directly to a GND pin on the ESP32.**

---

## 🛠️ Software Requirements

### Dependencies
1. **Arduino IDE** (with the ESP32 board package installed via Board Manager).
2. **SCServo Library** (for Feetech STS/SMS protocol serial servos). You can install this via the Arduino Library Manager by searching for `SCServo`.
