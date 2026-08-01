"""
IPC message schemas for the Cymbal distributed service architecture.

All on-wire formats use big-endian byte order (network byte order) to match
the existing S-BUS service protocol (sbus_reader.pyx / sbus_service.py).

Socket paths (defaults — all configurable via config.json):
  /run/cymbal/sbus.sock        — S-BUS decoder → controller (existing)
  /run/cymbal/telemetry.sock   — telemetry sidecar → consumers  (Phase 3)
  /run/cymbal/health.sock      — per-service health status       (Phase 5)

Magic bytes identify the message type on the socket so a receiver can discard
unexpected datagrams without crashing.

Usage (publisher side):
    from cymbal.controller.ipc_schemas import TelemetrySnapshotSchema
    payload = TelemetrySnapshotSchema.pack(
        lat=33.415, lon=-111.831, alt_msl=450.0, alt_agl=150.0,
        groundspeed_ms=28.0, track_degrees=45.0,
        fix_quality=1, satellites=9,
        address="1234 E Main St, Mesa, AZ 85201",
        timestamp=time.monotonic(),
    )
    sock.sendto(payload, reader_path)

Usage (consumer side):
    payload, _ = sock.recvfrom(TelemetrySnapshotSchema.SIZE)
    snap = TelemetrySnapshotSchema.unpack(payload)
    lat = snap['lat']
"""

import struct
import time


# ---------------------------------------------------------------------------
# TelemetrySnapshot
# ---------------------------------------------------------------------------
#
# Field layout (big-endian, 198 bytes):
#   magic          4s   — b'TELE'
#   lat            d    — latitude, decimal degrees (NaN if no fix)
#   lon            d    — longitude, decimal degrees (NaN if no fix)
#   alt_msl        d    — altitude MSL in metres (NaN if unknown)
#   alt_agl        d    — altitude AGL in metres (NaN if unknown)
#   groundspeed_ms d    — ground speed m/s (NaN if unknown)
#   track_degrees  d    — GPS ground track, degrees from N clockwise (NaN if unknown)
#   fix_quality    B    — GPS fix quality: 0=none, 1=GPS, 2=DGPS
#   satellites     B    — number of satellites in use
#   timestamp      d    — monotonic seconds at the time of the GPS read
#   address        128s — nearest street address, null-padded UTF-8, max 127 chars

_TELE_STRUCT = struct.Struct('!4s6dBBd128s')

_TELE_MAGIC  = b'TELE'
_ADDR_MAX    = 127       # max address bytes (leaving 1 byte for null)

_NAN = float('nan')


class TelemetrySnapshotSchema:
    """
    Packs and unpacks TelemetrySnapshot IPC datagrams.

    Total size: 198 bytes.
    """

    MAGIC = _TELE_MAGIC
    SIZE  = _TELE_STRUCT.size   # should be 198

    @staticmethod
    def pack(
        lat:            float,
        lon:            float,
        alt_msl:        float,
        alt_agl:        float,
        groundspeed_ms: float,
        track_degrees:  float,
        fix_quality:    int,
        satellites:     int,
        address:        str,
        timestamp:      float,
    ) -> bytes:
        """
        Serialise a telemetry snapshot to bytes.

        ``address`` is truncated to 127 bytes (UTF-8) and null-padded to 128.
        NaN is the canonical sentinel for unavailable float fields.
        """
        addr_bytes = address.encode('utf-8')[:_ADDR_MAX]
        addr_field = addr_bytes + b'\x00' * (128 - len(addr_bytes))
        return _TELE_STRUCT.pack(
            _TELE_MAGIC,
            lat, lon, alt_msl, alt_agl, groundspeed_ms, track_degrees,
            fix_quality & 0xFF,
            satellites  & 0xFF,
            timestamp,
            addr_field,
        )

    @staticmethod
    def unpack(data: bytes) -> dict:
        """
        Deserialise a TelemetrySnapshot datagram.

        Returns a dict with keys matching the pack() parameter names, plus
        a 'valid' key that is False if the magic bytes do not match.
        """
        if len(data) < _TELE_STRUCT.size:
            return {'valid': False}
        (
            magic,
            lat, lon, alt_msl, alt_agl, groundspeed_ms, track_degrees,
            fix_quality, satellites,
            timestamp,
            addr_field,
        ) = _TELE_STRUCT.unpack_from(data)
        return {
            'valid':          magic == _TELE_MAGIC,
            'lat':            lat,
            'lon':            lon,
            'alt_msl':        alt_msl,
            'alt_agl':        alt_agl,
            'groundspeed_ms': groundspeed_ms,
            'track_degrees':  track_degrees,
            'fix_quality':    fix_quality,
            'satellites':     satellites,
            'timestamp':      timestamp,
            'address':        addr_field.rstrip(b'\x00').decode('utf-8', errors='replace'),
        }


# ---------------------------------------------------------------------------
# HealthStatus
# ---------------------------------------------------------------------------
#
# Field layout (big-endian, 64 bytes):
#   magic            4s   — b'HLTH'
#   service_name     32s  — null-padded ASCII service name (max 31 chars)
#   uptime_sec       d    — seconds since the service started
#   last_data_age_ms d    — milliseconds since last successful data update
#   error_count      I    — cumulative error/warning counter since start
#   timestamp        d    — monotonic seconds at time of emission

_HLTH_STRUCT = struct.Struct('!4s32sddId')

_HLTH_MAGIC      = b'HLTH'
_SVC_NAME_MAX    = 31


class HealthStatusSchema:
    """
    Packs and unpacks HealthStatus IPC datagrams.

    Total size: 64 bytes.
    """

    MAGIC = _HLTH_MAGIC
    SIZE  = _HLTH_STRUCT.size   # should be 64

    @staticmethod
    def pack(
        service_name:    str,
        uptime_sec:      float,
        last_data_age_ms: float,
        error_count:     int,
        timestamp:       float,
    ) -> bytes:
        name_bytes = service_name.encode('ascii')[:_SVC_NAME_MAX]
        name_field = name_bytes + b'\x00' * (32 - len(name_bytes))
        return _HLTH_STRUCT.pack(
            _HLTH_MAGIC,
            name_field,
            uptime_sec,
            last_data_age_ms,
            error_count & 0xFFFFFFFF,
            timestamp,
        )

    @staticmethod
    def unpack(data: bytes) -> dict:
        if len(data) < _HLTH_STRUCT.size:
            return {'valid': False}
        (
            magic,
            name_field,
            uptime_sec,
            last_data_age_ms,
            error_count,
            timestamp,
        ) = _HLTH_STRUCT.unpack_from(data)
        return {
            'valid':            magic == _HLTH_MAGIC,
            'service_name':     name_field.rstrip(b'\x00').decode('ascii', errors='replace'),
            'uptime_sec':       uptime_sec,
            'last_data_age_ms': last_data_age_ms,
            'error_count':      error_count,
            'timestamp':        timestamp,
        }


# ---------------------------------------------------------------------------
# GimbalCommand  (reserved for Phase 3+ / bidirectional control channel)
# ---------------------------------------------------------------------------
#
# Field layout (big-endian, 52 bytes):
#   magic      4s   — b'GCMD'
#   gimbal_id  16s  — null-padded ASCII gimbal identifier (max 15 chars)
#   pitch      d    — target pitch degrees (NaN = no change)
#   roll       d    — target roll degrees  (NaN = no change)
#   yaw        d    — target yaw degrees   (NaN = no change)
#   timestamp  d    — monotonic seconds at time of command

_GCMD_STRUCT = struct.Struct('!4s16s4d')

_GCMD_MAGIC    = b'GCMD'
_GIMBAL_ID_MAX = 15


class GimbalCommandSchema:
    """
    Packs and unpacks GimbalCommand IPC datagrams.

    Total size: 52 bytes.

    Note: GimbalCommand is defined here for completeness but not yet consumed
    by any service.  It will be used when gimbal actuation is moved behind a
    command socket in a future phase.
    """

    MAGIC = _GCMD_MAGIC
    SIZE  = _GCMD_STRUCT.size   # should be 52

    @staticmethod
    def pack(
        gimbal_id: str,
        pitch:     float,
        roll:      float,
        yaw:       float,
        timestamp: float,
    ) -> bytes:
        id_bytes = gimbal_id.encode('ascii')[:_GIMBAL_ID_MAX]
        id_field = id_bytes + b'\x00' * (16 - len(id_bytes))
        return _GCMD_STRUCT.pack(
            _GCMD_MAGIC,
            id_field,
            pitch, roll, yaw,
            timestamp,
        )

    @staticmethod
    def unpack(data: bytes) -> dict:
        if len(data) < _GCMD_STRUCT.size:
            return {'valid': False}
        (
            magic,
            id_field,
            pitch, roll, yaw,
            timestamp,
        ) = _GCMD_STRUCT.unpack_from(data)
        return {
            'valid':     magic == _GCMD_MAGIC,
            'gimbal_id': id_field.rstrip(b'\x00').decode('ascii', errors='replace'),
            'pitch':     pitch,
            'roll':      roll,
            'yaw':       yaw,
            'timestamp': timestamp,
        }


# ---------------------------------------------------------------------------
# ControllerState  (controller → video sidecar: POI / target data)
# ---------------------------------------------------------------------------
#
# Field layout (big-endian, 45 bytes):
#   magic          4s   — b'CTRL'
#   poi_locked     B    — 1 if a POI is currently locked, 0 otherwise
#   poi_lat        d    — target latitude, decimal degrees (NaN if not locked)
#   poi_lon        d    — target longitude, decimal degrees (NaN if not locked)
#   poi_alt_msl    d    — target terrain elevation, metres MSL (NaN if unknown)
#   slant_range_m  d    — 3D aircraft→target distance, metres (NaN if unknown)
#   timestamp      d    — monotonic seconds at time of publish

_CTRL_STRUCT = struct.Struct('!4sBddddd')

_CTRL_MAGIC = b'CTRL'


class ControllerStateSchema:
    """
    Packs and unpacks ControllerState IPC datagrams.

    Published by CymbalController to /run/cymbal/controller.sock.reader
    whenever the POI state changes or on each control loop iteration when
    a POI is locked.

    Total size: 45 bytes.
    """

    MAGIC = _CTRL_MAGIC
    SIZE  = _CTRL_STRUCT.size

    @staticmethod
    def pack(
        poi_locked:    bool,
        poi_lat:       float,
        poi_lon:       float,
        poi_alt_msl:   float,
        slant_range_m: float,
        timestamp:     float,
    ) -> bytes:
        return _CTRL_STRUCT.pack(
            _CTRL_MAGIC,
            1 if poi_locked else 0,
            poi_lat,
            poi_lon,
            poi_alt_msl,
            slant_range_m,
            timestamp,
        )

    @staticmethod
    def unpack(data: bytes) -> dict:
        if len(data) < _CTRL_STRUCT.size:
            return {'valid': False}
        (
            magic,
            poi_locked_byte,
            poi_lat,
            poi_lon,
            poi_alt_msl,
            slant_range_m,
            timestamp,
        ) = _CTRL_STRUCT.unpack_from(data)
        return {
            'valid':         magic == _CTRL_MAGIC,
            'poi_locked':    bool(poi_locked_byte),
            'poi_lat':       poi_lat,
            'poi_lon':       poi_lon,
            'poi_alt_msl':   poi_alt_msl,
            'slant_range_m': slant_range_m,
            'timestamp':     timestamp,
        }


# ---------------------------------------------------------------------------
# Socket path constants (defaults — all overridable via config.json)
# ---------------------------------------------------------------------------

SOCKET_SBUS_PATH       = '/run/cymbal/sbus.sock'        # S-BUS decoder (existing)
SOCKET_TELEMETRY_PATH  = '/run/cymbal/telemetry.sock'   # telemetry sidecar (Phase 3)
SOCKET_HEALTH_PATH     = '/run/cymbal/health.sock'      # health status (Phase 5)
SOCKET_CONTROLLER_PATH = '/run/cymbal/controller.sock'  # controller state → video
