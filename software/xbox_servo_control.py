import pygame
import serial
import time

# ============================================
# CONFIGURATION - ADJUST THESE VALUES
# ============================================

# Find your ESP32 serial port:
# Linux:   /dev/ttyUSB0, /dev/ttyACM0
# macOS:   /dev/cu.usbserial-XXXX
# Windows: COM3, COM5, etc.
SERIAL_PORT = "/dev/ttyUSB0"  # CHANGE THIS!

# Baud rate (must match Arduino sketch)
BAUD_RATE = 921600

# Joystick deadzone (0.0 to 1.0)
# Higher = less sensitive near center
DEADZONE = 0.1

# Maximum servo speed (0 to 500)
MAX_SPEED = 500

# Direction inversion - set True to reverse direction
INVERT = {
    "left_x": True,   # M1
    "left_y": False,  # M2
    "right_x": True,  # M3
    "right_y": False, # M4
}

# ============================================
# DO NOT MODIFY BELOW THIS LINE
# ============================================

def map_axis(value, invert=False):
    """Convert joystick axis to servo speed."""
    if abs(value) < DEADZONE:
        return 0
    
    magnitude = (abs(value) - DEADZONE) / (1.0 - DEADZONE)
    speed = int(magnitude * MAX_SPEED)
    
    if value < 0:
        speed = -speed
    
    if invert:
        speed = -speed
    
    return speed

def main():
    pygame.init()
    pygame.joystick.init()
    
    if pygame.joystick.get_count() == 0:
        print("❌ No joystick found!")
        print("   Connect Xbox controller and restart.")
        return
    
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"✅ Controller: {joystick.get_name()}")
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
        time.sleep(1)
        print(f"✅ Serial port {SERIAL_PORT} opened")
    except serial.SerialException as e:
        print(f"❌ Serial port error: {e}")
        print("   Check port name and close Arduino Serial Monitor")
        return
    
    print("\n🎮 CONTROL ACTIVE!")
    print("   Left Stick: M1 (X), M2 (Y)")
    print("   Right Stick: M3 (X), M4 (Y)")
    print("   A Button: Emergency Stop")
    print("   Ctrl+C: Exit\n")
    
    try:
        while True:
            pygame.event.pump()
            
            left_x = joystick.get_axis(0)
            left_y = joystick.get_axis(1)
            right_x = joystick.get_axis(3)
            right_y = joystick.get_axis(4)
            
            speed1 = map_axis(left_x, INVERT["left_x"])
            speed2 = map_axis(left_y, INVERT["left_y"])
            speed3 = map_axis(right_x, INVERT["right_x"])
            speed4 = map_axis(right_y, INVERT["right_y"])
            
            if joystick.get_button(0):
                speed1 = speed2 = speed3 = speed4 = 0
            
            cmd = f"{speed1},{speed2},{speed3},{speed4}\n"
            ser.write(cmd.encode())
            
            print(f"M1:{speed1:4d}  M2:{speed2:4d}  M3:{speed3:4d}  M4:{speed4:4d}", end='\r')
            
            time.sleep(0.005)
            
    except KeyboardInterrupt:
        ser.write(b"0,0,0,0\n")
        print("\n\n⏹️  Stopped all servos")
    finally:
        ser.close()
        pygame.quit()

if __name__ == "__main__":
    main()
