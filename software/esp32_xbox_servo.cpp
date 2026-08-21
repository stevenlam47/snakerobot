#include <SCServo.h>

// ============================================
// CONFIGURATION - ADJUST THESE VALUES
// ============================================
SMS_STS st;

// Servo Bus Pins (ESP32 hardware serial 2)
const int S_RXD = 16;    // RX pin
const int S_TXD = 17;    // TX pin

// Physical emergency stop button (optional)
const int ANALOG_BUTTON_PIN = 25;  // GPIO 25

// Servo IDs - change if your servos have different IDs
const byte M1_ID = 1;
const byte M2_ID = 2;
const byte M3_ID = 3;
const byte M4_ID = 4;

// Safety timeout - stop if no command received
const unsigned long TIMEOUT_MS = 300;  // 300ms

// ============================================
// DO NOT MODIFY BELOW THIS LINE
// ============================================
int speed1 = 0, speed2 = 0, speed3 = 0, speed4 = 0;
unsigned long lastCommandTime = 0;

void setup() {
  Serial.begin(921600);  // High-speed serial to laptop
  delay(500);
  
  pinMode(ANALOG_BUTTON_PIN, INPUT_PULLUP);
  
  Serial2.begin(1000000, SERIAL_8N1, S_RXD, S_TXD);
  st.pSerial = &Serial2;
  
  st.WheelMode(M1_ID);
  st.WheelMode(M2_ID);
  st.WheelMode(M3_ID);
  st.WheelMode(M4_ID);
  
  Serial.println("ESP32 ready!");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    
    int s1, s2, s3, s4;
    if (sscanf(line.c_str(), "%d,%d,%d,%d", &s1, &s2, &s3, &s4) == 4) {
      speed1 = constrain(s1, -500, 500);
      speed2 = constrain(s2, -500, 500);
      speed3 = constrain(s3, -500, 500);
      speed4 = constrain(s4, -500, 500);
      lastCommandTime = millis();
    }
  }
  
  // Safety stop
  if (millis() - lastCommandTime > TIMEOUT_MS) {
    speed1 = speed2 = speed3 = speed4 = 0;
  }
  
  if (digitalRead(ANALOG_BUTTON_PIN) == LOW) {
    speed1 = speed2 = speed3 = speed4 = 0;
  }
  
  st.WriteSpe(M1_ID, speed1);
  st.WriteSpe(M2_ID, speed2);
  st.WriteSpe(M3_ID, speed3);
  st.WriteSpe(M4_ID, speed4);
  
  delay(5);
}
