#include <SCServo.h>

SMS_STS st;

const int DATA_PIN = 4;           // Servo data line

// Joystick Pins
const int ANALOG_X_PIN = 1;       // Pin 1 -> VRX (Motor 1 Joystick)
const int ANALOG_Y_PIN = 2;       // Pin 2 -> VRY (Motor 2 Joystick)
const int ANALOG_BUTTON_PIN = 3;  // Pin 3 -> Joystick Switch (Emergency Stop)

// 4 Original Button Pins (Matched to your code)
const int BTN_M1_CW = 7; 
const int BTN_M1_CCW = 8; 
const int BTN_M2_CW = 9; 
const int BTN_M2_CCW = 10; 

const byte M1_ID = 1; 
const byte M2_ID = 2; 

void setup() {
  Serial.begin(115200);
  delay(500);
  
  // Initialize all button and switch inputs with internal pull-ups
  pinMode(ANALOG_BUTTON_PIN, INPUT_PULLUP);
  pinMode(BTN_M1_CW, INPUT_PULLUP);
  pinMode(BTN_M1_CCW, INPUT_PULLUP);
  pinMode(BTN_M2_CW, INPUT_PULLUP);
  pinMode(BTN_M2_CCW, INPUT_PULLUP);

  // ST3215 Factory Default Baud Rate is 1000000 (1 Mbps)
  Serial1.begin(1000000, SERIAL_8N1, DATA_PIN, DATA_PIN);
  st.pSerial = &Serial1;
  
  // Set ESP32-S3 ADC attenuation for full 3.3V range
  analogSetAttenuation(ADC_11db);
  
  delay(1000); 

  st.WheelMode(M1_ID);
  st.WheelMode(M2_ID);
  Serial.println("Combined Joystick & Button Control Initialized");
}

void loop() {
  int speedX = 0;
  int speedY = 0;

  // --- MOTOR 1 CONTROL (Buttons on Pins 7 & 8 override Joystick X) ---
  if (digitalRead(BTN_M1_CW) == LOW) {
    speedX = 500;
  } else if (digitalRead(BTN_M1_CCW) == LOW) {
    speedX = -500;
  } else {
    // Use Joystick X-axis if no button is pressed
    int rawX = analogRead(ANALOG_X_PIN);
    speedX = map(rawX, 0, 4095, 500, -500); // Inverted left/right
    
    int deadzone = 150;
    if (abs(speedX) < deadzone) {
      speedX = 0;
    }
  }

  // --- MOTOR 2 CONTROL (Buttons on Pins 9 & 10 override Joystick Y) ---
  if (digitalRead(BTN_M2_CW) == LOW) {
    speedY = 500;
  } else if (digitalRead(BTN_M2_CCW) == LOW) {
    speedY = -500;
  } else {
    // Use Joystick Y-axis if no button is pressed
    int rawY = analogRead(ANALOG_Y_PIN);
    speedY = map(rawY, 0, 4095, -500, 500);
    
    int deadzone = 150;
    if (abs(speedY) < deadzone) {
      speedY = 0;
    }
  }

  // --- EMERGENCY STOP (Joystick button on Pin 3 cuts all motion) ---
  if (digitalRead(ANALOG_BUTTON_PIN) == LOW) {
    speedX = 0;
    speedY = 0;
  }

  // Send calculated speed commands to the servos
  st.WriteSpe(M1_ID, speedX); 
  st.WriteSpe(M2_ID, speedY); 

  delay(20);
}