"""
GimbalBase — abstract base extension type for all gimbal backends.

All gimbal adapter implementations (Storm32, GPIO servo, SimpleBGC, etc.) must
subclass this type and implement each cpdef method.

Attributes:
    gimbal_id:  Caller-assigned unique identifier string (e.g. "camera_1").
    roles:      List of role strings this gimbal fulfils.
                Common values: "camera", "spotlight", "camera+spotlight".
    axes:       Dict mapping axis name → [min_degrees, max_degrees].
                e.g. {"pitch": [-90.0, 30.0], "yaw": [-90.0, 90.0]}

Example subclass::

    from cymbal.gimbals.base cimport GimbalBase

    cdef class MyGimbalAdapter(GimbalBase):
        cpdef bint initialize(self):
            ...
"""

import logging

logger = logging.getLogger(__name__)


cdef class GimbalBase:
    """
    Abstract base class for all gimbal adapters.

    Concrete subclasses must override every cpdef method.  Calls to the
    base implementations log a warning and return a safe no-op value.
    """

    def __init__(self, str gimbal_id, list roles, dict axes):
        """
        Args:
            gimbal_id: Unique string identifier for this gimbal instance.
            roles:     List of role strings, e.g. ["camera"] or ["spotlight"].
            axes:      Dict of axis_name -> [min_deg, max_deg] pairs.
        """
        self.gimbal_id = gimbal_id
        self.roles = roles
        self.axes = axes

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    cpdef bint initialize(self):
        """
        Connect to the physical gimbal and prepare it for use.

        Returns:
            True if initialization succeeded.
        """
        logger.warning(f"[{self.gimbal_id}] GimbalBase.initialize() not overridden")
        return False

    cpdef void shutdown(self):
        """Release hardware resources cleanly."""
        logger.warning(f"[{self.gimbal_id}] GimbalBase.shutdown() not overridden")

    # ------------------------------------------------------------------
    # Motion control
    # ------------------------------------------------------------------

    cpdef bint center(self):
        """
        Move all axes to their neutral / centre position.

        Returns:
            True if the command was accepted.
        """
        logger.warning(f"[{self.gimbal_id}] GimbalBase.center() not overridden")
        return False

    cpdef bint set_axes(self, dict values):
        """
        Set one or more axes to target angles.

        Unknown axis names are silently skipped; the subclass should log
        a debug message and continue rather than raising.

        Args:
            values: Dict of axis_name → target_angle_degrees.
                    e.g. {"pitch": -30.0, "yaw": 45.0}

        Returns:
            True if at least one axis command was dispatched successfully.
        """
        logger.warning(f"[{self.gimbal_id}] GimbalBase.set_axes() not overridden")
        return False

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    cpdef dict get_status(self):
        """
        Return a snapshot of gimbal state as a plain dict.

        Keys vary by backend but should include at minimum:
            "gimbal_id", "roles", "connected" / "initialized".

        Returns:
            Status dict, or a minimal error dict on failure.
        """
        return {
            "gimbal_id": self.gimbal_id,
            "roles": self.roles,
            "axes": self.axes,
            "connected": False,
            "warning": "get_status() not overridden",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def has_role(self, str role) -> bool:
        """Return True if this gimbal fulfils the given role."""
        return role in self.roles

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"id={self.gimbal_id!r}, roles={self.roles!r}, "
            f"axes={list(self.axes.keys())!r})"
        )
