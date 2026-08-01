"""
SimpleBGCGimbalAdapter — stub for future SimpleBGC 32-bit controller support.

SimpleBGC (also known as AlexMos BGC) is a popular 3-axis brushless gimbal
controller that communicates via its own serial binary protocol.

This stub:
- Implements the GimbalBase interface so the type can be imported and used
  in configuration without a compilation error.
- Raises NotImplementedError on every operation so integration failures are
  obvious at runtime rather than silent.
- Documents the expected constructor signature for the real implementation.

Future implementation notes:
- Serial protocol: SimpleBGC API v2 binary frames (see SimpleBGC Serial API
  documentation v2.x).
- Key commands needed: CMD_SET_ANGLES (67), CMD_CONTROL (67), CMD_GET_ANGLES (18).
- Python library options: ``sbgc-api`` or custom framing (1-byte start, 1-byte
  command_id, 1-byte payload_size, N bytes payload, 1-byte checksum).

Usage::

    from cymbal.gimbals.simplebgc_stub import SimpleBGCGimbalAdapter

    gimbal = SimpleBGCGimbalAdapter(
        gimbal_id="camera_bgc",
        port="/dev/ttyUSB0",
        baudrate=115200,
    )
    # Raises NotImplementedError until a real implementation is provided.
    gimbal.initialize()
"""

import logging

from cymbal.gimbals.base cimport GimbalBase

logger = logging.getLogger(__name__)

_DEFAULT_AXES = {
    "pitch": [-90.0, 90.0],
    "roll":  [-90.0, 90.0],
    "yaw":   [-180.0, 180.0],
}

_NOT_IMPL_MSG = (
    "SimpleBGCGimbalAdapter is a stub.  "
    "Implement SimpleBGC serial protocol support before use."
)


cdef class SimpleBGCGimbalAdapter(GimbalBase):
    """
    Stub GimbalBase implementation for SimpleBGC 32-bit controller.

    Every method raises NotImplementedError.  Replace this class with a
    concrete implementation once the SimpleBGC serial protocol is wired up.

    Args:
        gimbal_id:  Unique identifier string.
        port:       Serial port path (e.g. "/dev/ttyUSB0").
        baudrate:   Serial baudrate (default 115200).
        roles:      List of role strings (default ["camera"]).
        axes:       Axis limits dict; defaults to 3-axis Storm32-style ranges.
    """

    def __init__(
        self,
        str gimbal_id,
        str port = "/dev/ttyUSB0",
        int baudrate = 115200,
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
        logger.warning(
            f"[{gimbal_id}] SimpleBGCGimbalAdapter is a stub — "
            "not implemented; all operations will raise NotImplementedError"
        )

    cpdef bint initialize(self):
        raise NotImplementedError(_NOT_IMPL_MSG)

    cpdef void shutdown(self):
        raise NotImplementedError(_NOT_IMPL_MSG)

    cpdef bint center(self):
        raise NotImplementedError(_NOT_IMPL_MSG)

    cpdef bint set_axes(self, dict values):
        raise NotImplementedError(_NOT_IMPL_MSG)

    cpdef dict get_status(self):
        return {
            "gimbal_id": self.gimbal_id,
            "roles": self.roles,
            "connected": False,
            "error": _NOT_IMPL_MSG,
        }
