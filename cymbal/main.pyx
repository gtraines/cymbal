"""
Main control application for dual gimbal system.

Coordinates control of both camera and spotlight gimbals from a Raspberry Pi 3B+.
"""

import time
import logging
import signal
import sys
from typing import Optional
from cymbal.camera_gimbal.storm32_controller cimport Storm32Controller
from cymbal.camera_gimbal.storm32_controller import Storm32Controller
from cymbal.spotlight_gimbal.servo_controller cimport SpotlightController
from cymbal.spotlight_gimbal.servo_controller import SpotlightController
from cymbal.utils.config import SystemConfig


cdef class GimbalController:
    """
    Main controller for dual gimbal system.
    
    Manages both camera gimbal (Storm32bgc) and spotlight gimbal (servos).
    """
    
    cdef object config
    cdef object logger
    cdef Storm32Controller camera_gimbal
    cdef SpotlightController spotlight_gimbal
    cdef public bint running
    
    def __init__(self, config: SystemConfig):
        """
        Initialize gimbal controller.
        
        Args:
            config: System configuration
        """
        self.config = config
        self.logger = self._setup_logging()
        
        # Initialize controllers
        self.camera_gimbal = None
        self.spotlight_gimbal = None
        
        self.running = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('/var/log/cymbal.log')
            ]
        )
        
        return logging.getLogger(__name__)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown()
        sys.exit(0)
    
    cpdef bint initialize(self):
        """
        Initialize both gimbal controllers.
        
        Returns:
            True if initialization successful, False otherwise
        """
        self.logger.info("Initializing gimbal control system...")
        
        try:
            # Initialize camera gimbal
            cam_config = self.config.camera_gimbal
            self.camera_gimbal = Storm32Controller(
                port=cam_config.serial_port,
                baudrate=cam_config.baudrate,
                timeout=cam_config.timeout
            )
            
            if not self.camera_gimbal.connect():
                self.logger.warning("Failed to connect to camera gimbal")
                self.camera_gimbal = None
            else:
                self.logger.info("Camera gimbal connected")
            
            # Initialize spotlight gimbal
            spot_config = self.config.spotlight_gimbal
            self.spotlight_gimbal = SpotlightController(
                pitch_pin=spot_config.pitch_pin,
                yaw_pin=spot_config.yaw_pin,
                i2c_address=spot_config.i2c_address,
                i2c_bus=spot_config.i2c_bus,
                use_stabilization=spot_config.use_stabilization
            )
            
            if not self.spotlight_gimbal.initialize():
                self.logger.warning("Failed to initialize spotlight gimbal")
                self.spotlight_gimbal = None
            else:
                self.logger.info("Spotlight gimbal initialized")
            
            # Check if at least one gimbal is operational
            if self.camera_gimbal is None and self.spotlight_gimbal is None:
                self.logger.error("No gimbals initialized successfully")
                return False
            
            self.logger.info("Gimbal control system initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize gimbal system: {e}")
            return False
    
    cpdef void center_all(self):
        """Center both gimbals."""
        self.logger.info("Centering all gimbals...")
        
        if self.camera_gimbal:
            self.camera_gimbal.center()
        
        if self.spotlight_gimbal:
            self.spotlight_gimbal.center()
    
    cpdef bint set_camera_position(self, double pitch, double roll, double yaw):
        """
        Set camera gimbal position.
        
        Args:
            pitch: Pitch angle in degrees
            roll: Roll angle in degrees
            yaw: Yaw angle in degrees
            
        Returns:
            True if successful, False otherwise
        """
        if not self.camera_gimbal:
            self.logger.warning("Camera gimbal not available")
            return False
        
        return self.camera_gimbal.set_angle(pitch, roll, yaw)
    
    cpdef bint set_spotlight_position(self, double pitch, double yaw):
        """
        Set spotlight gimbal position.
        
        Args:
            pitch: Pitch angle in degrees
            yaw: Yaw angle in degrees
            
        Returns:
            True if successful, False otherwise
        """
        if not self.spotlight_gimbal:
            self.logger.warning("Spotlight gimbal not available")
            return False
        
        return self.spotlight_gimbal.set_position(pitch, yaw)
    
    cpdef void sync_gimbals(self, double pitch, double yaw):
        """
        Synchronize both gimbals to the same orientation.
        
        Args:
            pitch: Pitch angle in degrees
            yaw: Yaw angle in degrees
        """
        self.logger.debug(f"Syncing gimbals to pitch={pitch}, yaw={yaw}")
        
        if self.camera_gimbal:
            self.camera_gimbal.set_angle(pitch, 0, yaw)
        
        if self.spotlight_gimbal:
            self.spotlight_gimbal.set_position(pitch, yaw)
    
    cpdef void run_stabilization_loop(self, double update_rate = 0.1):
        """
        Run continuous stabilization loop for spotlight gimbal.
        
        Args:
            update_rate: Update interval in seconds (default: 0.1 = 10Hz)
        """
        if not self.spotlight_gimbal or not self.spotlight_gimbal.use_stabilization:
            self.logger.warning("Stabilization not available")
            return
        
        self.logger.info("Starting stabilization loop...")
        self.running = True
        
        try:
            while self.running:
                self.spotlight_gimbal.stabilize()
                time.sleep(update_rate)
                
        except KeyboardInterrupt:
            self.logger.info("Stabilization loop interrupted")
        finally:
            self.running = False
    
    cpdef dict get_status(self):
        """
        Get status of both gimbals.
        
        Returns:
            Dictionary with status information
        """
        cdef dict status = {
            'camera_gimbal': None,
            'spotlight_gimbal': None
        }
        
        if self.camera_gimbal:
            status['camera_gimbal'] = self.camera_gimbal.get_status()
        
        if self.spotlight_gimbal:
            status['spotlight_gimbal'] = {
                'orientation': self.spotlight_gimbal.get_orientation(),
                'target_pitch': self.spotlight_gimbal.target_pitch,
                'target_yaw': self.spotlight_gimbal.target_yaw
            }
        
        return status
    
    cpdef void shutdown(self):
        """Shutdown gimbal system."""
        self.logger.info("Shutting down gimbal control system...")
        self.running = False
        
        if self.camera_gimbal:
            self.camera_gimbal.disconnect()
        
        if self.spotlight_gimbal:
            self.spotlight_gimbal.close()
        
        self.logger.info("Gimbal control system shutdown complete")


def main():
    """Main entry point."""
    # Load configuration
    config = SystemConfig.load('/etc/cymbal/config.json')
    
    # Create and initialize controller
    controller = GimbalController(config)
    
    if not controller.initialize():
        print("Failed to initialize gimbal system")
        return 1
    
    # Center gimbals on startup
    controller.center_all()
    
    print("Gimbal control system ready")
    print("Press Ctrl+C to exit")
    
    try:
        # Run stabilization loop if available
        controller.run_stabilization_loop()
    except KeyboardInterrupt:
        pass
    finally:
        controller.shutdown()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
