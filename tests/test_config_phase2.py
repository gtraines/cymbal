"""
Unit tests for expanded SystemConfig (Phase 2 additions).
"""

import json
import os
import tempfile
import unittest


class TestSystemConfigNewSections(unittest.TestCase):

    def test_default_config_has_gps_section(self):
        from cymbal.config.config import SystemConfig, GPSConfig
        cfg = SystemConfig.load('/nonexistent/path/config.json')
        self.assertIsInstance(cfg.gps, GPSConfig)
        self.assertEqual(cfg.gps.port, '/dev/ttyUSB0')
        self.assertEqual(cfg.gps.baudrate, 9600)
        self.assertTrue(cfg.gps.use_terrain_db)

    def test_default_config_has_geo_section(self):
        from cymbal.config.config import SystemConfig, GeoConfig
        cfg = SystemConfig.load('/nonexistent/path/config.json')
        self.assertIsInstance(cfg.geo, GeoConfig)
        self.assertTrue(cfg.geo.enabled)

    def test_default_config_has_osd_section(self):
        from cymbal.config.config import SystemConfig, OSDConfig
        cfg = SystemConfig.load('/nonexistent/path/config.json')
        self.assertIsInstance(cfg.osd, OSDConfig)
        self.assertTrue(cfg.osd.enabled)
        self.assertFalse(cfg.osd.show_sbus_channels)

    def test_default_config_has_sbus_section(self):
        from cymbal.config.config import SystemConfig, SBUSConfig
        cfg = SystemConfig.load('/nonexistent/path/config.json')
        self.assertIsInstance(cfg.sbus, SBUSConfig)
        self.assertEqual(cfg.sbus.gpio_pin, 4)
        self.assertEqual(cfg.sbus.failsafe_action, 'center')

    def test_default_config_has_channel_map_section(self):
        from cymbal.config.config import SystemConfig, ChannelMapConfig
        cfg = SystemConfig.load('/nonexistent/path/config.json')
        self.assertIsInstance(cfg.channel_map, ChannelMapConfig)
        self.assertEqual(cfg.channel_map.camera_pitch, 6)
        self.assertEqual(cfg.channel_map.mode_select, 5)

    def test_round_trip_json_preserves_new_sections(self):
        from cymbal.config.config import SystemConfig
        cfg = SystemConfig.load('/nonexistent/path/config.json')
        cfg.gps.port = '/dev/ttyUSB1'
        cfg.geo.enabled = False
        cfg.sbus.gpio_pin = 18

        d = cfg.to_dict()
        self.assertEqual(d['gps']['port'], '/dev/ttyUSB1')
        self.assertFalse(d['geo']['enabled'])
        self.assertEqual(d['sbus']['gpio_pin'], 18)

    def test_load_from_json_file_parses_new_sections(self):
        from cymbal.config.config import SystemConfig

        data = {
            "camera_gimbal": {"serial_port": "/dev/ttyAMA0", "baudrate": 115200, "timeout": 1.0},
            "spotlight_gimbal": {"pitch_pin": 17, "yaw_pin": 27, "i2c_address": 104,
                                 "i2c_bus": 1, "use_stabilization": True},
            "gps": {"port": "/dev/ttyUSB2", "baudrate": 4800, "update_rate_hz": 10,
                    "terrain_db_path": "/tmp/srtm", "use_terrain_db": False,
                    "min_fix_quality": 2},
            "geo": {"address_db_path": "/tmp/addr.db", "search_radius_deg": 0.02,
                    "enabled": True},
            "osd": {"enabled": False, "font_scale": 1.0, "font_thickness": 2,
                    "text_color": [0, 255, 0], "background_color": [0, 0, 0],
                    "background_alpha": 0.7, "show_sbus_channels": True},
            "sbus": {"gpio_pin": 22, "socket_path": "/run/cymbal/sbus2.sock",
                     "failsafe_action": "center", "frame_timeout_ms": 50,
                     "enabled": True},
            "channel_map": {"camera_pitch": 1, "camera_yaw": 2,
                            "spotlight_pitch": 3, "spotlight_yaw": 4,
                            "mode_select": 5, "poi_lock": 6,
                            "camera_pitch_range": [-45.0, 45.0],
                            "camera_yaw_range": [-60.0, 60.0],
                            "spotlight_pitch_range": [-45.0, 45.0],
                            "spotlight_yaw_range": [-90.0, 90.0]},
            "log_level": "DEBUG",
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            cfg = SystemConfig.load(tmp_path)
            self.assertEqual(cfg.gps.port, '/dev/ttyUSB2')
            self.assertEqual(cfg.gps.baudrate, 4800)
            self.assertFalse(cfg.gps.use_terrain_db)
            self.assertEqual(cfg.geo.address_db_path, '/tmp/addr.db')
            self.assertFalse(cfg.osd.enabled)
            self.assertTrue(cfg.osd.show_sbus_channels)
            self.assertEqual(cfg.sbus.gpio_pin, 22)
            self.assertEqual(cfg.channel_map.camera_pitch, 1)
            self.assertEqual(cfg.channel_map.camera_pitch_range, [-45.0, 45.0])
            self.assertEqual(cfg.log_level, 'DEBUG')
        finally:
            os.unlink(tmp_path)


if __name__ == '__main__':
    unittest.main()
