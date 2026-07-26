"""
S-BUS Channel Mapper

Maps raw S-BUS channel numbers to gimbal control functions and operating
modes, using the channel assignments and angle ranges from config.

Operating modes (selected by ch_mode_select, channel 5 by default):
  MANUAL    = 0  — S-BUS channels directly set gimbal angles.
  STABILIZE = 1  — IMU stabilizes gimbals; S-BUS provides trim offsets.
  TRACK     = 2  — GPS + POI geometry drives gimbals; S-BUS provides trim.

Mode selection from a 3-position switch on ch_mode_select:
  Raw < 600          → MANUAL
  Raw 600 – 1400     → STABILIZE
  Raw > 1400         → TRACK

POI lock (ch_poi_lock, channel 10 by default):
  Rising edge (low→high, threshold 1400) locks the current GPS position as
  the point-of-interest.  The trigger is edge-detected so brief switch
  activation does not hold the lock state.

Channel normalization uses the Futaba 172/992/1811 convention (matching
SBUSDecoder.get_channel_normalized).
"""

from libc.math cimport fabs
import logging

logger = logging.getLogger(__name__)

# Mode constants — also used in main.pyx
MODE_MANUAL    = 0
MODE_STABILIZE = 1
MODE_TRACK     = 2

# S-BUS raw value thresholds for mode switch
_MODE_LOW_THRESHOLD  = 600
_MODE_HIGH_THRESHOLD = 1400
_POI_LOCK_THRESHOLD  = 1400

# Futaba endpoints (matching sbus_decoder.pyx)
_CH_MIN = 172
_CH_MID = 992
_CH_MAX = 1811


cdef class ChannelMapper:
    """
    Maps S-BUS channels to gimbal commands and controller modes.

    initialize() must be called before any other method.
    """

    def __init__(self):
        self.ch_camera_pitch   = 6
        self.ch_camera_yaw     = 7
        self.ch_spotlight_pitch = 8
        self.ch_spotlight_yaw  = 9
        self.ch_mode_select    = 5
        self.ch_poi_lock       = 10

        self._cam_pitch_min  = -90.0
        self._cam_pitch_max  =  30.0
        self._cam_yaw_min    = -90.0
        self._cam_yaw_max    =  90.0
        self._spot_pitch_min = -90.0
        self._spot_pitch_max =  30.0
        self._spot_yaw_min   = -180.0
        self._spot_yaw_max   =  180.0

        self._prev_poi_raw = 0

    cpdef bint initialize(self, object config):
        """
        Apply channel assignments and angle ranges from a ChannelMapConfig.

        Args:
            config: ChannelMapConfig dataclass instance.

        Returns:
            True always (validates nothing that can fail at runtime).
        """
        self.ch_camera_pitch    = config.camera_pitch
        self.ch_camera_yaw      = config.camera_yaw
        self.ch_spotlight_pitch = config.spotlight_pitch
        self.ch_spotlight_yaw   = config.spotlight_yaw
        self.ch_mode_select     = config.mode_select
        self.ch_poi_lock        = config.poi_lock

        self._cam_pitch_min  = config.camera_pitch_range[0]
        self._cam_pitch_max  = config.camera_pitch_range[1]
        self._cam_yaw_min    = config.camera_yaw_range[0]
        self._cam_yaw_max    = config.camera_yaw_range[1]
        self._spot_pitch_min = config.spotlight_pitch_range[0]
        self._spot_pitch_max = config.spotlight_pitch_range[1]
        self._spot_yaw_min   = config.spotlight_yaw_range[0]
        self._spot_yaw_max   = config.spotlight_yaw_range[1]

        logger.info(
            f"ChannelMapper configured: cam_pitch=ch{self.ch_camera_pitch}, "
            f"cam_yaw=ch{self.ch_camera_yaw}, "
            f"spot_pitch=ch{self.ch_spotlight_pitch}, "
            f"spot_yaw=ch{self.ch_spotlight_yaw}, "
            f"mode=ch{self.ch_mode_select}, poi_lock=ch{self.ch_poi_lock}"
        )
        return True

    cpdef dict get_gimbal_commands(self, object sbus):
        """
        Read the configured channels and return gimbal angle commands.

        Args:
            sbus: SBUSReader instance (or any object with get_channel(n)).

        Returns:
            Dict with keys:
              camera_pitch   (float, degrees)
              camera_yaw     (float, degrees)
              spotlight_pitch (float, degrees)
              spotlight_yaw  (float, degrees)
        """
        cdef double cam_pitch, cam_yaw, spot_pitch, spot_yaw

        cam_pitch = self.map_channel_to_angle(
            sbus.get_channel(self.ch_camera_pitch),
            self._cam_pitch_min, self._cam_pitch_max,
        )
        cam_yaw = self.map_channel_to_angle(
            sbus.get_channel(self.ch_camera_yaw),
            self._cam_yaw_min, self._cam_yaw_max,
        )
        spot_pitch = self.map_channel_to_angle(
            sbus.get_channel(self.ch_spotlight_pitch),
            self._spot_pitch_min, self._spot_pitch_max,
        )
        spot_yaw = self.map_channel_to_angle(
            sbus.get_channel(self.ch_spotlight_yaw),
            self._spot_yaw_min, self._spot_yaw_max,
        )
        return {
            'camera_pitch':    cam_pitch,
            'camera_yaw':      cam_yaw,
            'spotlight_pitch': spot_pitch,
            'spotlight_yaw':   spot_yaw,
        }

    cpdef int get_mode_index(self, object sbus):
        """
        Return the current mode index from the mode-select channel.

        Returns:
            MODE_MANUAL (0), MODE_STABILIZE (1), or MODE_TRACK (2).
        """
        cdef int raw = sbus.get_channel(self.ch_mode_select)
        if raw < _MODE_LOW_THRESHOLD:
            return MODE_MANUAL
        elif raw > _MODE_HIGH_THRESHOLD:
            return MODE_TRACK
        else:
            return MODE_STABILIZE

    cpdef bint get_poi_lock_triggered(self, object sbus):
        """
        Detect a rising edge on the POI-lock switch channel.

        Returns:
            True exactly once when the switch transitions low → high.
        """
        cdef int raw = sbus.get_channel(self.ch_poi_lock)
        cdef bint triggered = (self._prev_poi_raw < _POI_LOCK_THRESHOLD
                               and raw >= _POI_LOCK_THRESHOLD)
        self._prev_poi_raw = raw
        return triggered

    cpdef double map_channel_to_angle(self, int raw_value,
                                      double min_angle, double max_angle):
        """
        Map a raw 11-bit S-BUS value to an angle within [min_angle, max_angle].

        Uses the Futaba 172 / 1811 full-travel range.
        Center (992) maps to the midpoint of [min_angle, max_angle].

        Args:
            raw_value:  Raw channel value 0–2047.
            min_angle:  Output angle at channel minimum.
            max_angle:  Output angle at channel maximum.

        Returns:
            Angle in degrees, clamped to [min_angle, max_angle].
        """
        cdef double t, angle

        # Normalise raw_value to 0.0 – 1.0 using Futaba travel endpoints
        t = (raw_value - _CH_MIN) / float(_CH_MAX - _CH_MIN)
        if t < 0.0:
            t = 0.0
        if t > 1.0:
            t = 1.0

        angle = min_angle + t * (max_angle - min_angle)
        return angle
