// 4-servo, 2-joint ST3215 controller over micro-ROS (serial transport)
//
// Physical layout:
//   Lower joint: servo ID 1 = X axis, servo ID 2 = Y axis
//   Upper joint: servo ID 3 = X axis, servo ID 4 = Y axis
//   All four share the same half-duplex servo bus.
//
// Topics:
//   sub  /servo_cmd_lower  geometry_msgs/Point  x,y in [-1,1] -> lower joint jog offset
//   sub  /servo_cmd_upper  geometry_msgs/Point  x,y in [-1,1] -> upper joint jog offset
//   sub  /set_zero         std_msgs/Empty       store current position of all 4 as zero,
//                                               and release an emergency stop if active
//   sub  /go_zero          std_msgs/Empty       drive all 4 back to zero, hold until arrived
//                                               (ignored while an emergency stop is active)
//   sub  /estop             std_msgs/Empty      freeze all 4 servos at their CURRENT position
//                                               immediately, and lock out /servo_cmd_* until
//                                               /set_zero is received
//   pub  /servo_feedback_lower geometry_msgs/Point  lower joint angle (radians) rel. to zero
//   pub  /servo_feedback_upper geometry_msgs/Point  upper joint angle (radians) rel. to zero
//   pub  /homing_status     std_msgs/Bool       true while a go_zero move is in progress
//   pub  /estop_status      std_msgs/Bool       true while an emergency stop is active
//
// Wiring:
//   ESP32-S3 USB connector -> PC, enumerates as /dev/ttyACM0, used ONLY for
//     the micro-ROS agent link. On boards with a native USB peripheral this
//     runs over GPIO19/20; on boards with an external USB-UART bridge chip
//     (e.g. CH343, shows as idVendor=1a86 in dmesg) it runs over UART0
//     instead and GPIO19/20 are free for other use. Check platformio.ini's
//     ARDUINO_USB_MODE/ARDUINO_USB_CDC_ON_BOOT flags match your board.
//   ESP32-S3 UART1 -> ST3215 servo bus (half-duplex, single data line):
//     SERVO_RX_PIN / SERVO_TX_PIN below. All four servos share this one
//     bus - only their IDs differ.
//   All four servo IDs must already be set (1/2/3/4) before this runs -
//     see the "change servo ID" note in the README.

// ESP32-WROOM-32 (classic, no native USB) -> PC via external USB-UART
// bridge chip (CP2102 or CH340 depending on your dev board), enumerates
// as /dev/ttyUSB0, used ONLY for the micro-ROS agent link.

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
#define SERVO_RX_PIN 16
#define SERVO_TX_PIN 17
//#define DATA_PIN 4
#define SERVO_BAUD   1000000

#define SERVO_ID_LOWER_X 1
#define SERVO_ID_LOWER_Y 2
#define SERVO_ID_UPPER_X 3
#define SERVO_ID_UPPER_Y 4

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

rcl_subscription_t sub_cmd_lower;
rcl_subscription_t sub_cmd_upper;
rcl_subscription_t sub_set_zero;
rcl_subscription_t sub_go_zero;
rcl_subscription_t sub_estop;

rcl_publisher_t pub_feedback_lower;
rcl_publisher_t pub_feedback_upper;
rcl_publisher_t pub_homing;
rcl_publisher_t pub_estop_status;

geometry_msgs__msg__Point msg_cmd_lower;
geometry_msgs__msg__Point msg_cmd_upper;
std_msgs__msg__Empty msg_set_zero;
std_msgs__msg__Empty msg_go_zero;
std_msgs__msg__Empty msg_estop;
geometry_msgs__msg__Point msg_feedback_lower;
geometry_msgs__msg__Point msg_feedback_upper;
std_msgs__msg__Bool msg_homing;
std_msgs__msg__Bool msg_estop_status;

rcl_timer_t timer;

volatile bool homing = false;
volatile bool estop = false;

int32_t zero_lx = TICKS_CENTER, zero_ly = TICKS_CENTER;
int32_t zero_ux = TICKS_CENTER, zero_uy = TICKS_CENTER;
int32_t target_lx = TICKS_CENTER, target_ly = TICKS_CENTER;
int32_t target_ux = TICKS_CENTER, target_uy = TICKS_CENTER;

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
void cmd_lower_callback(const void *msgin) {
  if (homing || estop) return;

  const geometry_msgs__msg__Point *m = (const geometry_msgs__msg__Point *)msgin;
  float jx = m->x, jy = m->y;
  if (jx > 1.0f) jx = 1.0f; if (jx < -1.0f) jx = -1.0f;
  if (jy > 1.0f) jy = 1.0f; if (jy < -1.0f) jy = -1.0f;

  target_lx = clamp_ticks(zero_lx + (int32_t)(jx * MAX_JOG_DEG * TICKS_PER_DEG));
  target_ly = clamp_ticks(zero_ly + (int32_t)(jy * MAX_JOG_DEG * TICKS_PER_DEG));

  move_servo(SERVO_ID_LOWER_X, target_lx);
  move_servo(SERVO_ID_LOWER_Y, target_ly);
}

void cmd_upper_callback(const void *msgin) {
  if (homing || estop) return;

  const geometry_msgs__msg__Point *m = (const geometry_msgs__msg__Point *)msgin;
  float jx = m->x, jy = m->y;
  if (jx > 1.0f) jx = 1.0f; if (jx < -1.0f) jx = -1.0f;
  if (jy > 1.0f) jy = 1.0f; if (jy < -1.0f) jy = -1.0f;

  target_ux = clamp_ticks(zero_ux + (int32_t)(jx * MAX_JOG_DEG * TICKS_PER_DEG));
  target_uy = clamp_ticks(zero_uy + (int32_t)(jy * MAX_JOG_DEG * TICKS_PER_DEG));

  move_servo(SERVO_ID_UPPER_X, target_ux);
  move_servo(SERVO_ID_UPPER_Y, target_uy);
}

void set_zero_callback(const void *msgin) {
  (void)msgin;
  int32_t p;
  p = read_pos(SERVO_ID_LOWER_X); if (p != -1) zero_lx = p;
  p = read_pos(SERVO_ID_LOWER_Y); if (p != -1) zero_ly = p;
  p = read_pos(SERVO_ID_UPPER_X); if (p != -1) zero_ux = p;
  p = read_pos(SERVO_ID_UPPER_Y); if (p != -1) zero_uy = p;

  target_lx = zero_lx; target_ly = zero_ly;
  target_ux = zero_ux; target_uy = zero_uy;

  estop = false;  // Set Zero is also how you release an emergency stop
}

void go_zero_callback(const void *msgin) {
  (void)msgin;
  if (estop) return;  // must clear the e-stop (via /set_zero) first

  homing = true;
  target_lx = zero_lx; target_ly = zero_ly;
  target_ux = zero_ux; target_uy = zero_uy;

  move_servo(SERVO_ID_LOWER_X, target_lx);
  move_servo(SERVO_ID_LOWER_Y, target_ly);
  move_servo(SERVO_ID_UPPER_X, target_ux);
  move_servo(SERVO_ID_UPPER_Y, target_uy);
}

void estop_callback(const void *msgin) {
  (void)msgin;
  estop = true;
  homing = false;

  // freeze every servo exactly where it is right now
  int32_t p;
  p = read_pos(SERVO_ID_LOWER_X); if (p != -1) { target_lx = p; move_servo(SERVO_ID_LOWER_X, p); }
  p = read_pos(SERVO_ID_LOWER_Y); if (p != -1) { target_ly = p; move_servo(SERVO_ID_LOWER_Y, p); }
  p = read_pos(SERVO_ID_UPPER_X); if (p != -1) { target_ux = p; move_servo(SERVO_ID_UPPER_X, p); }
  p = read_pos(SERVO_ID_UPPER_Y); if (p != -1) { target_uy = p; move_servo(SERVO_ID_UPPER_Y, p); }
}

// ---------------- timer: feedback + homing state machine ----------------
void timer_callback(rcl_timer_t *timer_, int64_t last_call_time) {
  (void)last_call_time;
  if (timer_ == NULL) return;

  int32_t pos_lx = read_pos(SERVO_ID_LOWER_X);
  int32_t pos_ly = read_pos(SERVO_ID_LOWER_Y);
  int32_t pos_ux = read_pos(SERVO_ID_UPPER_X);
  int32_t pos_uy = read_pos(SERVO_ID_UPPER_Y);

  if (homing) {
    bool arrived =
        (pos_lx != -1) && (abs(pos_lx - target_lx) <= ARRIVE_TOLERANCE_TICKS) &&
        (pos_ly != -1) && (abs(pos_ly - target_ly) <= ARRIVE_TOLERANCE_TICKS) &&
        (pos_ux != -1) && (abs(pos_ux - target_ux) <= ARRIVE_TOLERANCE_TICKS) &&
        (pos_uy != -1) && (abs(pos_uy - target_uy) <= ARRIVE_TOLERANCE_TICKS);
    if (arrived) homing = false;
  }

  msg_homing.data = homing;
  RCSOFTCHECK(rcl_publish(&pub_homing, &msg_homing, NULL));
  msg_estop_status.data = estop;
  RCSOFTCHECK(rcl_publish(&pub_estop_status, &msg_estop_status, NULL));

  if (pos_lx != -1) msg_feedback_lower.x = (pos_lx - TICKS_CENTER) / TICKS_PER_DEG * (M_PI / 180.0);
  if (pos_ly != -1) msg_feedback_lower.y = (pos_ly - TICKS_CENTER) / TICKS_PER_DEG * (M_PI / 180.0);
  msg_feedback_lower.z = 0.0;
  RCSOFTCHECK(rcl_publish(&pub_feedback_lower, &msg_feedback_lower, NULL));

  if (pos_ux != -1) msg_feedback_upper.x = (pos_ux - TICKS_CENTER) / TICKS_PER_DEG * (M_PI / 180.0);
  if (pos_uy != -1) msg_feedback_upper.y = (pos_uy - TICKS_CENTER) / TICKS_PER_DEG * (M_PI / 180.0);
  msg_feedback_upper.z = 0.0;
  RCSOFTCHECK(rcl_publish(&pub_feedback_upper, &msg_feedback_upper, NULL));
}

void setup() {
  // servo bus (UART1) - separate from the USB link used for micro-ROS
  Serial1.begin(SERVO_BAUD, SERIAL_8N1, SERVO_RX_PIN, SERVO_TX_PIN);
  servo.pSerial = &Serial1;
  delay(500);

  Serial.begin(115200);
  set_microros_serial_transports(Serial);
  delay(2000);

  allocator = rcl_get_default_allocator();
  RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
  RCCHECK(rclc_node_init_default(&node, "servo_gui_firmware", "", &support));

  RCCHECK(rclc_subscription_init_default(
      &sub_cmd_lower, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Point),
      "/servo_cmd_lower"));

  RCCHECK(rclc_subscription_init_default(
      &sub_cmd_upper, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Point),
      "/servo_cmd_upper"));

  RCCHECK(rclc_subscription_init_default(
      &sub_set_zero, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Empty),
      "/set_zero"));

  RCCHECK(rclc_subscription_init_default(
      &sub_go_zero, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Empty),
      "/go_zero"));

  RCCHECK(rclc_subscription_init_default(
      &sub_estop, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Empty),
      "/estop"));

  RCCHECK(rclc_publisher_init_default(
      &pub_feedback_lower, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Point),
      "/servo_feedback_lower"));

  RCCHECK(rclc_publisher_init_default(
      &pub_feedback_upper, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Point),
      "/servo_feedback_upper"));

  RCCHECK(rclc_publisher_init_default(
      &pub_homing, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool),
      "/homing_status"));

  RCCHECK(rclc_publisher_init_default(
      &pub_estop_status, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool),
      "/estop_status"));

  RCCHECK(rclc_timer_init_default(
      &timer, &support, RCL_MS_TO_NS(FEEDBACK_PERIOD_MS), timer_callback));

  executor = rclc_executor_get_zero_initialized_executor();
  RCCHECK(rclc_executor_init(&executor, &support.context, 6, &allocator));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_cmd_lower, &msg_cmd_lower, &cmd_lower_callback, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_cmd_upper, &msg_cmd_upper, &cmd_upper_callback, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_set_zero, &msg_set_zero, &set_zero_callback, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_go_zero, &msg_go_zero, &go_zero_callback, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_estop, &msg_estop, &estop_callback, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_timer(&executor, &timer));

  // seed "zero" with wherever the servos happen to be powered up at
  int32_t p;
  p = read_pos(SERVO_ID_LOWER_X); if (p != -1) zero_lx = p;
  p = read_pos(SERVO_ID_LOWER_Y); if (p != -1) zero_ly = p;
  p = read_pos(SERVO_ID_UPPER_X); if (p != -1) zero_ux = p;
  p = read_pos(SERVO_ID_UPPER_Y); if (p != -1) zero_uy = p;
  target_lx = zero_lx; target_ly = zero_ly;
  target_ux = zero_ux; target_uy = zero_uy;
}

void loop() {
  RCSOFTCHECK(rclc_executor_spin_some(&executor, RCL_MS_TO_NS(20)));
}
