"""
Cython header file for MPU6050
"""

cdef class MPU6050:
    cdef readonly int PWR_MGMT_1
    cdef readonly int SMPLRT_DIV
    cdef readonly int CONFIG
    cdef readonly int GYRO_CONFIG
    cdef readonly int ACCEL_CONFIG
    cdef readonly int INT_ENABLE
    cdef readonly int ACCEL_XOUT_H
    cdef readonly int ACCEL_YOUT_H
    cdef readonly int ACCEL_ZOUT_H
    cdef readonly int TEMP_OUT_H
    cdef readonly int GYRO_XOUT_H
    cdef readonly int GYRO_YOUT_H
    cdef readonly int GYRO_ZOUT_H
    cdef readonly int DEFAULT_ADDRESS
    
    cdef public int address
    cdef public int bus_num
    cdef object bus
    cdef bint _is_initialized
    cdef public object accel_offset
    cdef public object gyro_offset
    
    cpdef bint initialize(self)
    cpdef bint is_initialized(self)
    cdef int read_raw_data(self, int register)
    cpdef tuple get_acceleration(self)
    cpdef tuple get_gyroscope(self)
    cpdef double get_temperature(self)
    cpdef bint calibrate(self, int samples=*)
    cpdef tuple get_orientation(self)
    cpdef void close(self)
