"""
Spotlight Gimbal Controller

Controls a 2-axis spotlight gimbal using 360-degree continuous rotation servos
with MPU6050 IMU for stabilization.
"""

import time
import logging
from typing import Optional, Tuple
from cymbal.sensors.mpu6050 cimport MPU6050
from cymbal.sensors.mpu6050 import MPU6050

try:
    import pigpio
except ImportError:
    pigpio = None

logger = logging.getLogger(__name__)


cdef class SpotlightController:
    """
    Controller for spotlight gimbal using two 360-degree servos.
    
    Uses PWM control via GPIO pins and MPU6050 for orientation feedback
    and stabilization.
    """
    
    def __init__(
        self,
        int pitch_pin = 17,
        int yaw_pin = 27,
        int i2c_address = 0x68,
        int i2c_bus = 1,
        bint use_stabilization = True
    ):
        """
        Initialize spotlight gimbal controller.
        
        Args:
            pitch_pin: GPIO pin for pitch servo (default: 17)
            yaw_pin: GPIO pin for yaw servo (default: 27)
            i2c_address: MPU6050 I2C address (default: 0x68)
            i2c_bus: I2C bus number (default: 1)
            use_stabilization: Enable IMU-based stabilization
        """
        # Initialize constants
        self.SERVO_MIN_PULSE = 1000
        self.SERVO_MAX_PULSE = 2000
        self.SERVO_CENTER_PULSE = 1500
        
        self.pitch_pin = pitch_pin
        self.yaw_pin = yaw_pin
        self.use_stabilization = use_stabilization
        
        self.pi = None
        self.mpu = None
        
        # Current target positions
        self.target_pitch = 0.0
        self.target_yaw = 0.0
        
        # Current PWM values
        self.pitch_pwm = self.SERVO_CENTER_PULSE
        self.yaw_pwm = self.SERVO_CENTER_PULSE
        
        # Initialize IMU if stabilization is enabled
        if use_stabilization:
            self.mpu = MPU6050(address=i2c_address, bus=i2c_bus)
    
    cpdef bint initialize(self):
        """
        Initialize GPIO and IMU sensor.
        
        Returns:
            True if initialization successful, False otherwise
        """
        if pigpio is None:
            logger.error("pigpio not available. Install with: sudo apt-get install pigpio python3-pigpio")
            return False
        
        try:
            # Initialize pigpio
            self.pi = pigpio.pi()
            if not self.pi.connected:
                logger.error("Failed to connect to pigpio daemon")
                return False
            
            # Set GPIO modes
            self.pi.set_mode(self.pitch_pin, pigpio.OUTPUT)
            self.pi.set_mode(self.yaw_pin, pigpio.OUTPUT)
            
            # Initialize servos to center position
            self.pi.set_servo_pulsewidth(self.pitch_pin, self.SERVO_CENTER_PULSE)
            self.pi.set_servo_pulsewidth(self.yaw_pin, self.SERVO_CENTER_PULSE)
            
            logger.info(f"Servos initialized on GPIO pins {self.pitch_pin}, {self.yaw_pin}")
            
            # Initialize IMU if enabled
            if self.use_stabilization and self.mpu:
                if not self.mpu.initialize():
                    logger.warning("Failed to initialize MPU6050, stabilization disabled")
                    self.use_stabilization = False
                else:
                    # Calibrate the IMU
                    self.mpu.calibrate()
                    logger.info("MPU6050 initialized and calibrated")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize spotlight controller: {e}")
            return False
    
    cpdef bint is_initialized(self):
        """Check if controller is initialized."""
        return self.pi is not None and self.pi.connected
    
    cpdef bint set_position(self, double pitch, double yaw):
        """
        Set spotlight gimbal position.
        
        Args:
            pitch: Pitch angle in degrees (-90 to +90)
            yaw: Yaw angle in degrees (-180 to +180)
            
        Returns:
            True if command sent successfully, False otherwise
        """
        cdef int pitch_pulse, yaw_pulse
        
        if not self.is_initialized():
            logger.error("Cannot set position: Controller not initialized")
            return False
        
        try:
            # Clamp values to valid ranges
            if pitch < -90:
                pitch = -90
            elif pitch > 90:
                pitch = 90
                
            if yaw < -180:
                yaw = -180
            elif yaw > 180:
                yaw = 180
            
            self.target_pitch = pitch
            self.target_yaw = yaw
            
            # Convert angles to PWM pulse widths
            self.pitch_pwm = self._angle_to_pulse(pitch, -90, 90)
            self.yaw_pwm = self._angle_to_pulse(yaw, -180, 180)
            
            # Set servo positions
            self.pi.set_servo_pulsewidth(self.pitch_pin, self.pitch_pwm)
            self.pi.set_servo_pulsewidth(self.yaw_pin, self.yaw_pwm)
            
            logger.debug(f"Set position - Pitch: {pitch}° ({self.pitch_pwm}µs), Yaw: {yaw}° ({self.yaw_pwm}µs)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set position: {e}")
            return False
    
    cpdef bint set_speed(self, double pitch_speed, double yaw_speed):
        """
        Set spotlight gimbal rotation speeds.
        
        For 360-degree servos, this directly controls rotation speed.
        
        Args:
            pitch_speed: Pitch rotation speed (-100 to +100, 0 = stop)
            yaw_speed: Yaw rotation speed (-100 to +100, 0 = stop)
            
        Returns:
            True if command sent successfully, False otherwise
        """
        cdef int pitch_pulse, yaw_pulse
        
        if not self.is_initialized():
            logger.error("Cannot set speed: Controller not initialized")
            return False
        
        try:
            # Clamp speeds to valid range
            if pitch_speed < -100:
                pitch_speed = -100
            elif pitch_speed > 100:
                pitch_speed = 100
                
            if yaw_speed < -100:
                yaw_speed = -100
            elif yaw_speed > 100:
                yaw_speed = 100
            
            # Convert speed to PWM pulse width
            pitch_pulse = self.SERVO_CENTER_PULSE + int(pitch_speed * 5)  # ±500µs range
            yaw_pulse = self.SERVO_CENTER_PULSE + int(yaw_speed * 5)
            
            self.pi.set_servo_pulsewidth(self.pitch_pin, pitch_pulse)
            self.pi.set_servo_pulsewidth(self.yaw_pin, yaw_pulse)
            
            logger.debug(f"Set speed - Pitch: {pitch_speed}%, Yaw: {yaw_speed}%")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set speed: {e}")
            return False
    
    cpdef bint stop(self):
        """
        Stop all gimbal movement.
        
        Returns:
            True if successful, False otherwise
        """
        return self.set_speed(0, 0)
    
    cpdef bint center(self):
        """
        Center the gimbal (all axes to 0 degrees).
        
        Returns:
            True if successful, False otherwise
        """
        return self.set_position(0, 0)
    
    cpdef object get_orientation(self):
        """
        Get current orientation from IMU.
        
        Returns:
            Tuple of (pitch, roll) in degrees or None if IMU not available
        """
        if not self.use_stabilization or not self.mpu or not self.mpu.is_initialized():
            return None
        
        try:
            return self.mpu.get_orientation()
        except Exception as e:
            logger.error(f"Failed to get orientation: {e}")
            return None
    
    cpdef bint stabilize(self):
        """
        Perform one stabilization update using IMU feedback.
        
        Returns:
            True if stabilization performed, False otherwise
        """
        cdef double pitch, roll
        cdef double correction_pitch, correction_yaw
        cdef double stabilized_pitch, stabilized_yaw
        
        if not self.use_stabilization:
            return False
        
        orientation = self.get_orientation()
        if orientation is None:
            return False
        
        pitch, roll = orientation
        
        # Simple stabilization: counteract detected tilt
        correction_pitch = -pitch * 0.5  # Proportional correction
        correction_yaw = -roll * 0.5
        
        # Apply corrections to maintain target position
        stabilized_pitch = self.target_pitch + correction_pitch
        stabilized_yaw = self.target_yaw + correction_yaw
        
        return self.set_position(stabilized_pitch, stabilized_yaw)
    
    cdef int _angle_to_pulse(self, double angle, double min_angle, double max_angle):
        """
        Convert angle to PWM pulse width.
        
        Args:
            angle: Angle in degrees
            min_angle: Minimum angle
            max_angle: Maximum angle
            
        Returns:
            PWM pulse width in microseconds
        """
        cdef double normalized
        cdef int pulse
        
        # Normalize angle to 0-1 range
        normalized = (angle - min_angle) / (max_angle - min_angle)
        
        # Map to pulse width range
        pulse = self.SERVO_MIN_PULSE + int(normalized * (self.SERVO_MAX_PULSE - self.SERVO_MIN_PULSE))
        
        return pulse
    
    cpdef void close(self):
        """Shutdown controller and cleanup resources."""
        try:
            if self.pi:
                # Stop servos
                self.pi.set_servo_pulsewidth(self.pitch_pin, 0)
                self.pi.set_servo_pulsewidth(self.yaw_pin, 0)
                self.pi.stop()
                logger.info("Spotlight controller shutdown")
            
            if self.mpu:
                self.mpu.close()
                
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
