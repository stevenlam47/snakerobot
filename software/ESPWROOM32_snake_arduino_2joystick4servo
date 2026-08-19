#include <SCServo.h>

SMS_STS st;

// Servo Bus Pins (RX2 and TX2)
const int S_RXD = 16;
const int S_TXD = 17;

// Joystick Pins (Safe ADC1 pins)
const int JOYSTICK_1_X = 32;     // Joystick 1 X-axis -> Servo 1 (Pin 32)
const int JOYSTICK_1_Y = 33;     // Joystick 1 Y-axis -> Servo 2 (Pin 33)
const int JOYSTICK_2_X = 34;     // Joystick 2 X-axis -> Servo 3 (Pin 34)
const int JOYSTICK_2_Y = 35;     // Joystick 2 Y-axis -> Servo 4 (Pin 35)

// Emergency Stop Button
const int ANALOG_BUTTON_PIN = 25;  

// Servo IDs
const byte M1_ID = 1; 
const byte M2_ID = 2; 
const byte M3_ID = 3; 
const byte M4_ID = 4; 

void setup() {
  Serial.begin(115200);
  delay(500);

  // Initialize emergency stop button input with internal pull-up
  pinMode(ANALOG_BUTTON_PIN, INPUT_PULLUP);

  // Initialize Serial2 for Servo Bus (Pins 16 & 17)
  Serial2.begin(1000000, SERIAL_8N1, S_RXD, S_TXD);
  st.pSerial = &Serial2;

  // Set ESP32 ADC attenuation for full 3.3V range
  analogSetAttenuation(ADC_11db);

  delay(1000); 

  // Initialize all 4 servos in Wheel Mode (continuous rotation)
  st.WheelMode(M1_ID);
  st.WheelMode(M2_ID);
  st.WheelMode(M3_ID);
  st.WheelMode(M4_ID);

  Serial.println("4-Servo & Dual Joystick Control Initialized via Serial2");
}

void loop() {
  int speed1 = 0;
  int speed2 = 0;
  int speed3 = 0;
  int speed4 = 0;
  int deadzone = 150;

  // --- Joystick 1 X-axis -> Servo 1 (Pin 32) ---
  int raw1 = analogRead(JOYSTICK_1_X);
  speed1 = map(raw1, 0, 4095, 500, -500); 
  if (abs(speed1) < deadzone) {
    speed1 = 0;
  }

  // --- Joystick 1 Y-axis -> Servo 2 (Pin 33) ---
  int raw2 = analogRead(JOYSTICK_1_Y);
  speed2 = map(raw2, 0, 4095, -500, 500); 
  if (abs(speed2) < deadzone) {
    speed2 = 0;
  }

  // --- Joystick 2 X-axis -> Servo 3 (Pin 34) ---
  int raw3 = analogRead(JOYSTICK_2_X);
  speed3 = map(raw3, 0, 4095, 500, -500); 
  if (abs(speed3) < deadzone) {
    speed3 = 0;
  }

  // --- Joystick 2 Y-axis -> Servo 4 (Pin 35) ---
  int raw4 = analogRead(JOYSTICK_2_Y);
  speed4 = map(raw4, 0, 4095, -500, 500); 
  if (abs(speed4) < deadzone) {
    speed4 = 0;
  }

  // --- EMERGENCY STOP (Button on Pin 25 cuts all motion) ---
  if (digitalRead(ANALOG_BUTTON_PIN) == LOW) {
    speed1 = 0;
    speed2 = 0;
    speed3 = 0;
    speed4 = 0;
  }

  // Send calculated speed commands to all 4 servos
  st.WriteSpe(M1_ID, speed1); 
  st.WriteSpe(M2_ID, speed2); 
  st.WriteSpe(M3_ID, speed3); 
  st.WriteSpe(M4_ID, speed4); 

  // Telemetry output for debugging
  Serial.print("M1: "); Serial.print(speed1);
  Serial.print(" | M2: "); Serial.print(speed2);
  Serial.print(" | M3: "); Serial.print(speed3);
  Serial.print(" | M4: "); Serial.println(speed4);

  delay(20);
}
