"""
ServoGimbalAdapter — wraps SpotlightController as a GimbalBase.

Maps the generic set_axes({"pitch": p, "yaw": y}) interface onto
SpotlightController.set_position().  The "roll" axis is not supported
and is silently ignored when passed.

Default roles: ["spotlight"]
Default axes:
    pitch  [-90.0, 90.0]
    yaw    [-180.0, 180.0]

The adapter also exposes stabilize() directly so the orchestrator can
call it during STABILIZE mode.

Usage::

    from cymbal.gimbals.servo_adapter import ServoGimbalAdapter

    gimbal = ServoGimbalAdapter(
        gimbal_id="spotlight_1",
        pitch_pin=17,
        yaw_pin=27,
    )
    gimbal.initialize()
    gimbal.set_axes({"pitch": 0.0, "yaw": 45.0})
    gimbal.shutdown()
"""

import logging

from cymbal.gimbals.base cimport GimbalBase
from cymbal.spotlight_gimbal.servo_controller cimport SpotlightController
from cymbal.spotlight_gimbal.servo_controller import SpotlightController as _SpotlightControllerPy

logger = logging.getLogger(__name__)

_DEFAULT_AXES = {
    "pitch": [-90.0, 90.0],
    "yaw":   [-180.0, 180.0],
}


cdef class ServoGimbalAdapter(GimbalBase):
    """
    GimbalBase implementation backed by GPIO PWM servo control (SpotlightController).

    Supports stabilization via MPU6050 when use_stabilization=True.

    Args:
        gimbal_id:         Unique identifier string.
        pitch_pin:         BCM GPIO pin for pitch servo.
        yaw_pin:           BCM GPIO pin for yaw servo.
        i2c_address:       MPU6050 I2C address (default 0x68).
        i2c_bus:           I2C bus number (default 1).
        use_stabilization: Enable IMU-based stabilization (default True).
        roles:             List of role strings (default ["spotlight"]).
        axes:              Axis limits dict; defaults to standard servo ranges.
    """

    def __init__(
        self,
        str gimbal_id,
        int pitch_pin = 17,
        int yaw_pin = 27,
        int i2c_address = 0x68,
        int i2c_bus = 1,
        bint use_stabilization = True,
        list roles = None,
        dict axes = None,
    ):
        super().__init__(
            gimbal_id=gimbal_id,
            roles=roles if roles is not None else ["spotlight"],
            axes=axes if axes is not None else dict(_DEFAULT_AXES),
        )
        self.pitch_pin = pitch_pin
        self.yaw_pin = yaw_pin
        self.i2c_address = i2c_address
        self.i2c_bus = i2c_bus
        self.use_stabilization = use_stabilization
        self._controller = _SpotlightControllerPy(
            pitch_pin=pitch_pin,
            yaw_pin=yaw_pin,
            i2c_address=i2c_address,
            i2c_bus=i2c_bus,
            use_stabilization=use_stabilization,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    cpdef bint initialize(self):
        """Initialize GPIO and MPU6050 IMU."""
        try:
            result = self._controller.initialize()
            if result:
                logger.info(
                    f"[{self.gimbal_id}] Servo gimbal initialized "
                    f"(pitch={self.pitch_pin}, yaw={self.yaw_pin})"
                )
            else:
                logger.warning(f"[{self.gimbal_id}] Servo gimbal initialize() returned False")
            return result
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] Servo gimbal initialize error: {e}")
            return False

    cpdef void shutdown(self):
        """Stop servos and release pigpio resources."""
        try:
            self._controller.close()
            logger.info(f"[{self.gimbal_id}] Servo gimbal shutdown")
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] Servo gimbal shutdown error: {e}")

    # ------------------------------------------------------------------
    # Motion control
    # ------------------------------------------------------------------

    cpdef bint center(self):
        """Center both axes to 0 degrees."""
        try:
            result = self._controller.center()
            logger.debug(f"[{self.gimbal_id}] center() -> {result}")
            return result
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] center error: {e}")
            return False

    cpdef bint set_axes(self, dict values):
        """
        Set gimbal position.  Accepts "pitch" and/or "yaw".
        Unknown axis names (e.g. "roll") are silently ignored.

        Args:
            values: e.g. {"pitch": -30.0, "yaw": 90.0}

        Returns:
            True if command was dispatched.
        """
        cdef double pitch, yaw

        pitch = values.get("pitch", 0.0)
        yaw   = values.get("yaw",   0.0)

        for key in values:
            if key not in ("pitch", "yaw"):
                logger.debug(
                    f"[{self.gimbal_id}] set_axes: axis '{key}' not supported, ignored"
                )

        try:
            result = self._controller.set_position(pitch, yaw)
            return result
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] set_axes error: {e}")
            return False

    cpdef bint stabilize(self):
        """
        Run one stabilization cycle via the IMU.

        Returns:
            True if stabilization was applied.
        """
        try:
            return self._controller.stabilize()
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] stabilize error: {e}")
            return False

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    cpdef dict get_status(self):
        """Return current servo/IMU status."""
        cdef dict status = {
            "gimbal_id": self.gimbal_id,
            "roles": self.roles,
            "connected": self._controller.is_initialized(),
        }
        try:
            orientation = self._controller.get_orientation()
            if orientation is not None:
                pitch, roll = orientation
                status["orientation"] = {"pitch": pitch, "roll": roll}
            status["target_pitch"] = self._controller.target_pitch
            status["target_yaw"]   = self._controller.target_yaw
        except Exception as e:
            logger.debug(f"[{self.gimbal_id}] get_status warning: {e}")
        return status
