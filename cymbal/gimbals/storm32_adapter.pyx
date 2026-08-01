"""
Storm32GimbalAdapter — wraps Storm32Controller as a GimbalBase.

Maps the generic set_axes({"pitch": p, "roll": r, "yaw": y}) interface onto
Storm32Controller.set_angle(), and delegates lifecycle to connect/disconnect.

Default roles: ["camera"]
Default axes:
    pitch  [-90.0, 90.0]
    roll   [-90.0, 90.0]
    yaw    [-180.0, 180.0]

Usage::

    from cymbal.gimbals.storm32_adapter import Storm32GimbalAdapter

    gimbal = Storm32GimbalAdapter(
        gimbal_id="camera_1",
        port="/dev/ttyAMA0",
        baudrate=115200,
    )
    gimbal.initialize()
    gimbal.set_axes({"pitch": -30.0, "yaw": 45.0})
    gimbal.shutdown()
"""

import logging

from cymbal.gimbals.base cimport GimbalBase
from cymbal.camera_gimbal.storm32_controller cimport Storm32Controller
from cymbal.camera_gimbal.storm32_controller import Storm32Controller as _Storm32ControllerPy

logger = logging.getLogger(__name__)

_DEFAULT_AXES = {
    "pitch": [-90.0, 90.0],
    "roll":  [-90.0, 90.0],
    "yaw":   [-180.0, 180.0],
}


cdef class Storm32GimbalAdapter(GimbalBase):
    """
    GimbalBase implementation backed by a Storm32bgc brushless gimbal controller.

    Axis commands are forwarded as Storm32 angle commands.  The "roll" axis
    defaults to 0.0 when not supplied in set_axes().

    Args:
        gimbal_id:  Unique identifier string.
        port:       Serial port path (e.g. "/dev/ttyAMA0").
        baudrate:   Serial baudrate (default 115200).
        timeout:    Serial read timeout in seconds (default 1.0).
        roles:      List of role strings (default ["camera"]).
        axes:       Axis limits dict; defaults to standard Storm32 ranges.
    """

    def __init__(
        self,
        str gimbal_id,
        str port = "/dev/ttyAMA0",
        int baudrate = 115200,
        double timeout = 1.0,
        list roles = None,
        dict axes = None,
    ):
        super().__init__(
            gimbal_id=gimbal_id,
            roles=roles if roles is not None else ["camera"],
            axes=axes if axes is not None else dict(_DEFAULT_AXES),
        )
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._controller = _Storm32ControllerPy(
            port=port, baudrate=baudrate, timeout=timeout
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    cpdef bint initialize(self):
        """Connect to Storm32 controller via serial."""
        try:
            result = self._controller.connect()
            if result:
                logger.info(f"[{self.gimbal_id}] Storm32 connected on {self.port}")
            else:
                logger.warning(f"[{self.gimbal_id}] Storm32 connect() returned False")
            return result
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] Storm32 initialize error: {e}")
            return False

    cpdef void shutdown(self):
        """Disconnect serial connection."""
        try:
            self._controller.disconnect()
            logger.info(f"[{self.gimbal_id}] Storm32 disconnected")
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] Storm32 shutdown error: {e}")

    # ------------------------------------------------------------------
    # Motion control
    # ------------------------------------------------------------------

    cpdef bint center(self):
        """Send center command (all axes to 0 degrees)."""
        try:
            result = self._controller.center()
            logger.debug(f"[{self.gimbal_id}] center() -> {result}")
            return result
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] center error: {e}")
            return False

    cpdef bint set_axes(self, dict values):
        """
        Set gimbal angles.  Accepts any combination of "pitch", "roll", "yaw".
        Missing axes default to 0.0.  Unknown axis names are silently ignored.

        Args:
            values: e.g. {"pitch": -30.0, "yaw": 45.0}

        Returns:
            True if command was dispatched.
        """
        cdef double pitch, roll, yaw

        pitch = values.get("pitch", 0.0)
        roll  = values.get("roll",  0.0)
        yaw   = values.get("yaw",   0.0)

        # Log unknown keys
        for key in values:
            if key not in ("pitch", "roll", "yaw"):
                logger.debug(
                    f"[{self.gimbal_id}] set_axes: unknown axis '{key}' ignored"
                )

        try:
            result = self._controller.set_angle(pitch, roll, yaw)
            return result
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] set_axes error: {e}")
            return False

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    cpdef dict get_status(self):
        """Delegate to Storm32Controller.get_status(), augmented with id/roles."""
        cdef dict base_status
        try:
            base_status = self._controller.get_status() or {}
        except Exception as e:
            logger.error(f"[{self.gimbal_id}] get_status error: {e}")
            base_status = {}

        base_status["gimbal_id"] = self.gimbal_id
        base_status["roles"] = self.roles
        base_status["connected"] = self._controller.is_connected()
        return base_status
