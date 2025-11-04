"""
Cython header file for SpotlightController
"""

from airborne_gimbal.sensors.mpu6050 cimport MPU6050

cdef class SpotlightController:
    cdef readonly int SERVO_MIN_PULSE
    cdef readonly int SERVO_MAX_PULSE
    cdef readonly int SERVO_CENTER_PULSE
    
    cdef public int pitch_pin
    cdef public int yaw_pin
    cdef public bint use_stabilization
    
    cdef object pi
    cdef MPU6050 mpu
    
    cdef public double target_pitch
    cdef public double target_yaw
    
    cdef public int pitch_pwm
    cdef public int yaw_pwm
    
    cpdef bint initialize(self)
    cpdef bint is_initialized(self)
    cpdef bint set_position(self, double pitch, double yaw)
    cpdef bint set_speed(self, double pitch_speed, double yaw_speed)
    cpdef bint stop(self)
    cpdef bint center(self)
    cpdef object get_orientation(self)
    cpdef bint stabilize(self)
    cdef int _angle_to_pulse(self, double angle, double min_angle, double max_angle)
    cpdef void close(self)
