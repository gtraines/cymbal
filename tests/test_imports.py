"""
Basic import tests for cymbal airborne gimbal modules.

These tests verify that all modules can be imported without errors.
"""

import unittest


class TestImports(unittest.TestCase):
    """Test that all modules can be imported."""
    
    def test_import_storm32_controller(self):
        """Test importing Storm32Controller."""
        from cymbal.camera_gimbal import Storm32Controller
        self.assertIsNotNone(Storm32Controller)
    
    def test_import_spotlight_controller(self):
        """Test importing SpotlightController."""
        from cymbal.spotlight_gimbal import SpotlightController
        self.assertIsNotNone(SpotlightController)
    
    def test_import_mpu6050(self):
        """Test importing MPU6050."""
        from cymbal.sensors import MPU6050
        self.assertIsNotNone(MPU6050)
    
    def test_import_config(self):
        """Test importing configuration classes."""
        from cymbal.utils.config import SystemConfig
        self.assertIsNotNone(SystemConfig)
    
    def test_import_main(self):
        """Test importing main controller."""
        from cymbal.main import GimbalController
        self.assertIsNotNone(GimbalController)


if __name__ == '__main__':
    unittest.main()
