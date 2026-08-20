"""Records the combined 4-axis jog path since the last Set Zero, and
plays it back in reverse when Go to Zero is triggered, so the rig
retraces the same route home instead of cutting straight there.

This only owns the *intermediate* waypoints. The final short hop to the
exact zero position is still handled by the firmware's own /go_zero +
/homing_status handshake, which is more precise than anything a ~50 Hz
Python loop could guarantee.

Note: this retraces the *commanded* path (the sequence of positions the
GUI asked for), not a frame-perfect replay of the physical motion - for
routing cables or avoiding obstacles that's exactly what's needed, but
it isn't a millisecond-exact recording of the servos' actual movement.
"""

import time

SAMPLE_PERIOD_S = 0.15       # minimum time between recorded waypoints
CHANGE_EPSILON = 0.04        # minimum combined-axis change to record a new one
ARRIVE_TOLERANCE = 0.08      # normalized units - how close counts as "there"
WAYPOINT_TIMEOUT_S = 2.5     # safety fallback if a waypoint is never reached
MAX_WAYPOINTS = 5000         # hard cap so a very long session can't grow forever

IDLE = 'idle'
RETRACING = 'retracing'
FINAL_HOMING = 'final_homing'


class PathRetrace:
    def __init__(self):
        self.state = IDLE
        self.path = []
        self._last_sample_t = 0.0
        self._queue = []
        self._current_target = None
        self._deadline = None

    def clear(self):
        self.path = []
        self._queue = []
        self._current_target = None
        self.state = IDLE

    def remaining(self):
        return len(self._queue)

    def record(self, lx, ly, ux, uy):
        """Call once per control tick while jogging is allowed."""
        now = time.monotonic()
        if now - self._last_sample_t < SAMPLE_PERIOD_S:
            return
        sample = (lx, ly, ux, uy)
        if self.path:
            last = self.path[-1]
            changed = max(abs(a - b) for a, b in zip(sample, last))
            if changed < CHANGE_EPSILON:
                return
        self.path.append(sample)
        if len(self.path) > MAX_WAYPOINTS:
            self.path.pop(0)
        self._last_sample_t = now

    def start(self):
        """Begin a retrace. Returns False if there's nothing recorded
        (caller should just send /go_zero directly in that case)."""
        if not self.path:
            return False
        self._queue = list(reversed(self.path))
        self._current_target = None
        self.state = RETRACING
        return True

    def step(self, feedback_lx, feedback_ly, feedback_ux, feedback_uy):
        """Call once per control tick while state == RETRACING.

        Returns:
          - a (lx, ly, ux, uy) tuple when a NEW waypoint should be published
          - the string 'final' when the queue is exhausted (caller should
            publish /go_zero and the state becomes FINAL_HOMING)
          - None when nothing new needs to happen this tick
        """
        now = time.monotonic()

        if self._current_target is None:
            if not self._queue:
                self.state = FINAL_HOMING
                return 'final'
            self._current_target = self._queue.pop(0)
            self._deadline = now + WAYPOINT_TIMEOUT_S
            return self._current_target

        tx, ty, ux_t, uy_t = self._current_target
        err = max(
            abs(feedback_lx - tx), abs(feedback_ly - ty),
            abs(feedback_ux - ux_t), abs(feedback_uy - uy_t),
        )
        if err <= ARRIVE_TOLERANCE or now >= self._deadline:
            self._current_target = None  # advance to next waypoint next tick
        return None

    def finish(self):
        """Call once the firmware reports /homing_status has gone back
        to False after a FINAL_HOMING leg - the rig is actually home."""
        self.clear()
