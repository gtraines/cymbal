"""
MPU6050 IMU Sensor Interface

Provides interface to the MPU6050 6-axis accelerometer and gyroscope
for gimbal stabilization and orientation sensing.
"""

from libc.math cimport atan2, sqrt, M_PI
import time
import logging
from typing import Optional, Tuple

try:
    import smbus2 as smbus
except ImportError:
    try:
        import smbus
    except ImportError:
        smbus = None

logger = logging.getLogger(__name__)


cdef class MPU6050:
    """
    Interface for MPU6050 6-axis IMU sensor.
    
    Provides accelerometer and gyroscope data for gimbal stabilization.
    Communicates via I2C bus.
    """
    
    def __init__(self, int address = 0x68, int bus = 1):
        """
        Initialize MPU6050 sensor.
        
        Args:
            address: I2C address (default: 0x68)
            bus: I2C bus number (default: 1 for Raspberry Pi)
        """
        # Initialize register constants
        self.PWR_MGMT_1 = 0x6B
        self.SMPLRT_DIV = 0x19
        self.CONFIG = 0x1A
        self.GYRO_CONFIG = 0x1B
        self.ACCEL_CONFIG = 0x1C
        self.INT_ENABLE = 0x38
        
        self.ACCEL_XOUT_H = 0x3B
        self.ACCEL_YOUT_H = 0x3D
        self.ACCEL_ZOUT_H = 0x3F
        self.TEMP_OUT_H = 0x41
        self.GYRO_XOUT_H = 0x43
        self.GYRO_YOUT_H = 0x45
        self.GYRO_ZOUT_H = 0x47
        
        self.DEFAULT_ADDRESS = 0x68
        
        self.address = address
        self.bus_num = bus
        self.bus = None
        self._is_initialized = False
        
        # Calibration offsets
        self.accel_offset = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        self.gyro_offset = {'x': 0.0, 'y': 0.0, 'z': 0.0}
    
    cpdef bint initialize(self):
        """
        Initialize the MPU6050 sensor.
        
        Returns:
            True if initialization successful, False otherwise
        """
        if smbus is None:
            logger.error("smbus not available. Install python3-smbus or smbus2")
            return False
        
        try:
            self.bus = smbus.SMBus(self.bus_num)
            
            # Wake up the MPU6050 (it starts in sleep mode)
            self.bus.write_byte_data(self.address, self.PWR_MGMT_1, 0x00)
            time.sleep(0.1)
            
            # Set sample rate divider
            self.bus.write_byte_data(self.address, self.SMPLRT_DIV, 0x07)
            
            # Configure digital low pass filter
            self.bus.write_byte_data(self.address, self.CONFIG, 0x06)
            
            # Set gyroscope range to ±250 deg/s
            self.bus.write_byte_data(self.address, self.GYRO_CONFIG, 0x00)
            
            # Set accelerometer range to ±2g
            self.bus.write_byte_data(self.address, self.ACCEL_CONFIG, 0x00)
            
            self._is_initialized = True
            logger.info(f"MPU6050 initialized at address 0x{self.address:02X}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize MPU6050: {e}")
            self._is_initialized = False
            return False
    
    cpdef bint is_initialized(self):
        """Check if sensor is initialized."""
        return self._is_initialized
    
    cdef int read_raw_data(self, int register):
        """
        Read raw 16-bit data from sensor register.
        
        Args:
            register: Register address to read from
            
        Returns:
            16-bit signed integer value
        """
        cdef int high, low, value
        
        if not self.bus:
            raise RuntimeError("MPU6050 not initialized")
        
        # Read high and low bytes
        high = self.bus.read_byte_data(self.address, register)
        low = self.bus.read_byte_data(self.address, register + 1)
        
        # Combine bytes into 16-bit value
        value = (high << 8) | low
        
        # Convert to signed value
        if value > 32768:
            value = value - 65536
        
        return value
    
    cpdef tuple get_acceleration(self):
        """
        Get acceleration values in g (gravity units).
        
        Returns:
            Tuple of (x, y, z) acceleration in g
        """
        cdef int accel_x, accel_y, accel_z
        cdef double accel_scale = 16384.0
        cdef double x, y, z
        
        if not self.is_initialized():
            raise RuntimeError("MPU6050 not initialized")
        
        # Read raw values
        accel_x = self.read_raw_data(self.ACCEL_XOUT_H)
        accel_y = self.read_raw_data(self.ACCEL_YOUT_H)
        accel_z = self.read_raw_data(self.ACCEL_ZOUT_H)
        
        # Convert to g (for ±2g range: sensitivity = 16384 LSB/g)
        x = (accel_x / accel_scale) - self.accel_offset['x']
        y = (accel_y / accel_scale) - self.accel_offset['y']
        z = (accel_z / accel_scale) - self.accel_offset['z']
        
        return (x, y, z)
    
    cpdef tuple get_gyroscope(self):
        """
        Get gyroscope values in degrees per second.
        
        Returns:
            Tuple of (x, y, z) angular velocity in deg/s
        """
        cdef int gyro_x, gyro_y, gyro_z
        cdef double gyro_scale = 131.0
        cdef double x, y, z
        
        if not self.is_initialized():
            raise RuntimeError("MPU6050 not initialized")
        
        # Read raw values
        gyro_x = self.read_raw_data(self.GYRO_XOUT_H)
        gyro_y = self.read_raw_data(self.GYRO_YOUT_H)
        gyro_z = self.read_raw_data(self.GYRO_ZOUT_H)
        
        # Convert to deg/s (for ±250 deg/s range: sensitivity = 131 LSB/(deg/s))
        x = (gyro_x / gyro_scale) - self.gyro_offset['x']
        y = (gyro_y / gyro_scale) - self.gyro_offset['y']
        z = (gyro_z / gyro_scale) - self.gyro_offset['z']
        
        return (x, y, z)
    
    cpdef double get_temperature(self):
        """
        Get temperature reading from sensor.
        
        Returns:
            Temperature in Celsius
        """
        cdef int raw_temp
        cdef double temperature
        
        if not self.is_initialized():
            raise RuntimeError("MPU6050 not initialized")
        
        raw_temp = self.read_raw_data(self.TEMP_OUT_H)
        # Convert to Celsius
        temperature = (raw_temp / 340.0) + 36.53
        return temperature
    
    cpdef bint calibrate(self, int samples = 100):
        """
        Calibrate the sensor by averaging readings while stationary.
        
        Args:
            samples: Number of samples to average for calibration
            
        Returns:
            True if calibration successful, False otherwise
        """
        cdef int i
        cdef double accel_x, accel_y, accel_z
        cdef double gyro_x, gyro_y, gyro_z
        cdef dict accel_sum = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        cdef dict gyro_sum = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        
        if not self.is_initialized():
            logger.error("Cannot calibrate: MPU6050 not initialized")
            return False
        
        logger.info(f"Calibrating MPU6050 with {samples} samples...")
        
        try:
            for i in range(samples):
                # Read accelerometer
                accel_x = self.read_raw_data(self.ACCEL_XOUT_H) / 16384.0
                accel_y = self.read_raw_data(self.ACCEL_YOUT_H) / 16384.0
                accel_z = self.read_raw_data(self.ACCEL_ZOUT_H) / 16384.0
                
                accel_sum['x'] += accel_x
                accel_sum['y'] += accel_y
                accel_sum['z'] += accel_z - 1.0  # Subtract 1g for Z axis
                
                # Read gyroscope
                gyro_x = self.read_raw_data(self.GYRO_XOUT_H) / 131.0
                gyro_y = self.read_raw_data(self.GYRO_YOUT_H) / 131.0
                gyro_z = self.read_raw_data(self.GYRO_ZOUT_H) / 131.0
                
                gyro_sum['x'] += gyro_x
                gyro_sum['y'] += gyro_y
                gyro_sum['z'] += gyro_z
                
                time.sleep(0.01)
            
            # Calculate averages
            self.accel_offset['x'] = accel_sum['x'] / samples
            self.accel_offset['y'] = accel_sum['y'] / samples
            self.accel_offset['z'] = accel_sum['z'] / samples
            
            self.gyro_offset['x'] = gyro_sum['x'] / samples
            self.gyro_offset['y'] = gyro_sum['y'] / samples
            self.gyro_offset['z'] = gyro_sum['z'] / samples
            
            logger.info("MPU6050 calibration complete")
            logger.debug(f"Accel offsets: {self.accel_offset}")
            logger.debug(f"Gyro offsets: {self.gyro_offset}")
            return True
            
        except Exception as e:
            logger.error(f"Calibration failed: {e}")
            return False
    
    cpdef tuple get_orientation(self):
        """
        Calculate pitch and roll angles from accelerometer.
        
        Returns:
            Tuple of (pitch, roll) in degrees
        """
        cdef double accel_x, accel_y, accel_z
        cdef double pitch, roll
        
        accel_x, accel_y, accel_z = self.get_acceleration()
        
        # Calculate pitch and roll using C math functions
        pitch = atan2(accel_y, sqrt(accel_x**2 + accel_z**2)) * 180.0 / M_PI
        roll = atan2(-accel_x, accel_z) * 180.0 / M_PI
        
        return (pitch, roll)
    
    cpdef void close(self):
        """Close I2C bus connection."""
        if self.bus:
            self.bus.close()
            self._is_initialized = False
            logger.info("MPU6050 connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
