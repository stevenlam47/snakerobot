// ST3215 dual-axis servo controller over micro-ROS (serial transport)
//
// Topics:
//   sub  /servo_cmd    geometry_msgs/Point   x,y in [-1, 1] -> jog offset from zero
//   sub  /set_zero     std_msgs/Empty        store current position as the new zero
//   sub  /go_zero      std_msgs/Empty        drive back to zero and hold until arrived
//   pub  /servo_feedback geometry_msgs/Point x,y = live angle (radians) relative to zero
//   pub  /homing_status std_msgs/Bool        true while a go_zero move is in progress
//
// Wiring:
//   ESP32-S3 USB connector -> PC, enumerates as /dev/ttyACM0, used ONLY for
//     the micro-ROS agent link. On boards with a native USB peripheral this
//     runs over GPIO19/20; on boards with an external USB-UART bridge chip
//     (e.g. CH343, shows as idVendor=1a86 in dmesg) it runs over UART0
//     instead and GPIO19/20 are free for other use. Check platformio.ini's
//     ARDUINO_USB_MODE/ARDUINO_USB_CDC_ON_BOOT flags match your board.
//   ESP32-S3 UART1 -> ST3215 servo bus (half-duplex, single data line):
//     SERVO_RX_PIN / SERVO_TX_PIN below, tied together per the ST3215 driver
//     circuit (or straight into a Waveshare servo driver board if you have one).
//   Servo IDs must already be set to 1 (X axis) and 2 (Y axis) before this runs -
//     see the "change servo ID" note in the README.

#include <Arduino.h>
#include <micro_ros_platformio.h>

#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>

#include <std_msgs/msg/empty.h>
#include <std_msgs/msg/bool.h>
#include <geometry_msgs/msg/point.h>

#include <SCServo.h>

// ---------------- user configuration ----------------
#define SERVO_RX_PIN 17
#define SERVO_TX_PIN 18
#define SERVO_BAUD   1000000

#define SERVO_ID_X 1
#define SERVO_ID_Y 2

#define TICKS_MIN     0
#define TICKS_MAX     4095
#define TICKS_CENTER  2048
#define MAX_JOG_DEG   90.0f              // max deflection from zero, in degrees
#define TICKS_PER_DEG (4096.0f / 360.0f)

#define MOVE_SPEED 1500                  // steps/sec, tune to taste
#define MOVE_ACC   50

#define ARRIVE_TOLERANCE_TICKS 15
#define FEEDBACK_PERIOD_MS 100
// ------------------------------------------------------

SMS_STS servo;

rcl_node_t node;
rcl_allocator_t allocator;
rclc_support_t support;
rclc_executor_t executor;

rcl_subscription_t sub_cmd;
rcl_subscription_t sub_set_zero;
rcl_subscription_t sub_go_zero;

rcl_publisher_t pub_feedback;
rcl_publisher_t pub_homing;

geometry_msgs__msg__Point msg_cmd;
std_msgs__msg__Empty msg_set_zero;
std_msgs__msg__Empty msg_go_zero;
geometry_msgs__msg__Point msg_feedback;
std_msgs__msg__Bool msg_homing;

rcl_timer_t timer;

volatile bool homing = false;
int32_t zero_x = TICKS_CENTER;
int32_t zero_y = TICKS_CENTER;
int32_t target_x = TICKS_CENTER;
int32_t target_y = TICKS_CENTER;

#define RCCHECK(fn)     { rcl_ret_t temp_rc = fn; if (temp_rc != RCL_RET_OK) { error_loop(); } }
#define RCSOFTCHECK(fn) { rcl_ret_t temp_rc = fn; (void)temp_rc; }

void error_loop() {
  while (true) {
    delay(100);
  }
}

int32_t clamp_ticks(int32_t v) {
  if (v < TICKS_MIN) return TICKS_MIN;
  if (v > TICKS_MAX) return TICKS_MAX;
  return v;
}

void move_servo(uint8_t id, int32_t pos_ticks) {
  servo.WritePosEx(id, clamp_ticks(pos_ticks), MOVE_SPEED, MOVE_ACC);
}

// returns -1 if the read failed
int32_t read_pos(uint8_t id) {
  if (servo.FeedBack(id) == -1) return -1;
  return servo.ReadPos(-1);
}

// ---------------- subscription callbacks ----------------
void cmd_callback(const void *msgin) {
  if (homing) return;  // ignore manual jog while a go-to-zero move is active

  const geometry_msgs__msg__Point *m = (const geometry_msgs__msg__Point *)msgin;
  float jx = m->x;
  float jy = m->y;
  if (jx > 1.0f) jx = 1.0f; if (jx < -1.0f) jx = -1.0f;
  if (jy > 1.0f) jy = 1.0f; if (jy < -1.0f) jy = -1.0f;

  int32_t offset_x = (int32_t)(jx * MAX_JOG_DEG * TICKS_PER_DEG);
  int32_t offset_y = (int32_t)(jy * MAX_JOG_DEG * TICKS_PER_DEG);

  target_x = clamp_ticks(zero_x + offset_x);
  target_y = clamp_ticks(zero_y + offset_y);

  move_servo(SERVO_ID_X, target_x);
  move_servo(SERVO_ID_Y, target_y);
}

void set_zero_callback(const void *msgin) {
  (void)msgin;
  int32_t p;
  p = read_pos(SERVO_ID_X);
  if (p != -1) zero_x = p;
  p = read_pos(SERVO_ID_Y);
  if (p != -1) zero_y = p;

  target_x = zero_x;
  target_y = zero_y;
}

void go_zero_callback(const void *msgin) {
  (void)msgin;
  homing = true;
  target_x = zero_x;
  target_y = zero_y;
  move_servo(SERVO_ID_X, target_x);
  move_servo(SERVO_ID_Y, target_y);
}

// ---------------- timer: feedback + homing state machine ----------------
void timer_callback(rcl_timer_t *timer_, int64_t last_call_time) {
  (void)last_call_time;
  if (timer_ == NULL) return;

  int32_t pos_x = read_pos(SERVO_ID_X);
  int32_t pos_y = read_pos(SERVO_ID_Y);

  if (homing) {
    bool arrived_x = (pos_x != -1) && (abs(pos_x - target_x) <= ARRIVE_TOLERANCE_TICKS);
    bool arrived_y = (pos_y != -1) && (abs(pos_y - target_y) <= ARRIVE_TOLERANCE_TICKS);
    if (arrived_x && arrived_y) {
      homing = false;
    }
  }

  msg_homing.data = homing;
  RCSOFTCHECK(rcl_publish(&pub_homing, &msg_homing, NULL));

  if (pos_x != -1) {
    msg_feedback.x = (pos_x - TICKS_CENTER) / TICKS_PER_DEG * (M_PI / 180.0);
  }
  if (pos_y != -1) {
    msg_feedback.y = (pos_y - TICKS_CENTER) / TICKS_PER_DEG * (M_PI / 180.0);
  }
  msg_feedback.z = 0.0;
  RCSOFTCHECK(rcl_publish(&pub_feedback, &msg_feedback, NULL));
}

void setup() {
  // servo bus (UART1) - separate from the USB link used for micro-ROS
  Serial1.begin(SERVO_BAUD, SERIAL_8N1, SERVO_RX_PIN, SERVO_TX_PIN);
  servo.pSerial = &Serial1;
  delay(500);

  // micro-ROS over native USB CDC (/dev/ttyACM0 on the PC side)
  Serial.begin(115200);
  set_microros_serial_transports(Serial);
  delay(2000);

  allocator = rcl_get_default_allocator();
  RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
  RCCHECK(rclc_node_init_default(&node, "servo_gui_firmware", "", &support));

  RCCHECK(rclc_subscription_init_default(
      &sub_cmd, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Point),
      "/servo_cmd"));

  RCCHECK(rclc_subscription_init_default(
      &sub_set_zero, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Empty),
      "/set_zero"));

  RCCHECK(rclc_subscription_init_default(
      &sub_go_zero, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Empty),
      "/go_zero"));

  RCCHECK(rclc_publisher_init_default(
      &pub_feedback, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Point),
      "/servo_feedback"));

  RCCHECK(rclc_publisher_init_default(
      &pub_homing, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool),
      "/homing_status"));

  RCCHECK(rclc_timer_init_default(
      &timer, &support, RCL_MS_TO_NS(FEEDBACK_PERIOD_MS), timer_callback));

  executor = rclc_executor_get_zero_initialized_executor();
  RCCHECK(rclc_executor_init(&executor, &support.context, 4, &allocator));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_cmd, &msg_cmd, &cmd_callback, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_set_zero, &msg_set_zero, &set_zero_callback, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_go_zero, &msg_go_zero, &go_zero_callback, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_timer(&executor, &timer));

  // seed "zero" with wherever the servos happen to be powered up at
  int32_t p;
  p = read_pos(SERVO_ID_X);
  if (p != -1) zero_x = p;
  p = read_pos(SERVO_ID_Y);
  if (p != -1) zero_y = p;
  target_x = zero_x;
  target_y = zero_y;
}

void loop() {
  RCSOFTCHECK(rclc_executor_spin_some(&executor, RCL_MS_TO_NS(20)));
}