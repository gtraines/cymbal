# API Documentation

## Overview

The Cymbal Airborne Gimbal Control System provides a Python API for controlling dual gimbals on fixed-wing drones. The system consists of three main components:

1. **Storm32Controller** - Camera gimbal control via Storm32bgc
2. **SpotlightController** - Spotlight gimbal control via servos
3. **MPU6050** - IMU sensor for stabilization

## Camera Gimbal API

### Storm32Controller

Control interface for Storm32bgc brushless gimbal controller.

#### Constructor

```python
Storm32Controller(
    port: str = "/dev/ttyAMA0",
    baudrate: int = 115200,
    timeout: float = 1.0
)
```

**Parameters:**
- `port` (str): Serial port path (default: "/dev/ttyAMA0")
- `baudrate` (int): Communication speed (default: 115200)
- `timeout` (float): Serial timeout in seconds (default: 1.0)

#### Methods

##### connect()

```python
def connect() -> bool
```

Establish serial connection to Storm32 controller.

**Returns:** `bool` - True if connection successful, False otherwise

**Example:**
```python
controller = Storm32Controller()
if controller.connect():
    print("Connected!")
```

##### disconnect()

```python
def disconnect() -> None
```

Close serial connection.

##### set_angle()

```python
def set_angle(pitch: float, roll: float, yaw: float) -> bool
```

Set gimbal angles.

**Parameters:**
- `pitch` (float): Pitch angle in degrees (-90 to +90)
- `roll` (float): Roll angle in degrees (-90 to +90)
- `yaw` (float): Yaw angle in degrees (-180 to +180)

**Returns:** `bool` - True if command sent successfully

**Example:**
```python
controller.set_angle(pitch=30, roll=0, yaw=45)
```

##### set_speed()

```python
def set_speed(pitch_speed: float, roll_speed: float, yaw_speed: float) -> bool
```

Set gimbal rotation speeds.

**Parameters:**
- `pitch_speed` (float): Pitch rotation speed in degrees/second
- `roll_speed` (float): Roll rotation speed in degrees/second
- `yaw_speed` (float): Yaw rotation speed in degrees/second

**Returns:** `bool` - True if command sent successfully

##### center()

```python
def center() -> bool
```

Center the gimbal (all axes to 0 degrees).

**Returns:** `bool` - True if successful

##### get_status()

```python
def get_status() -> Optional[dict]
```

Get current gimbal status.

**Returns:** `dict` or `None` - Status information dictionary

**Example:**
```python
status = controller.get_status()
print(f"Pitch: {status['pitch']}, Yaw: {status['yaw']}")
```

## Spotlight Gimbal API

### SpotlightController

Control interface for spotlight gimbal using servos and MPU6050.

#### Constructor

```python
SpotlightController(
    pitch_pin: int = 17,
    yaw_pin: int = 27,
    i2c_address: int = 0x68,
    i2c_bus: int = 1,
    use_stabilization: bool = True
)
```

**Parameters:**
- `pitch_pin` (int): GPIO pin for pitch servo (default: 17)
- `yaw_pin` (int): GPIO pin for yaw servo (default: 27)
- `i2c_address` (int): MPU6050 I2C address (default: 0x68)
- `i2c_bus` (int): I2C bus number (default: 1)
- `use_stabilization` (bool): Enable IMU-based stabilization (default: True)

#### Methods

##### initialize()

```python
def initialize() -> bool
```

Initialize GPIO and IMU sensor.

**Returns:** `bool` - True if initialization successful

##### set_position()

```python
def set_position(pitch: float, yaw: float) -> bool
```

Set spotlight gimbal position.

**Parameters:**
- `pitch` (float): Pitch angle in degrees (-90 to +90)
- `yaw` (float): Yaw angle in degrees (-180 to +180)

**Returns:** `bool` - True if successful

**Example:**
```python
controller.set_position(pitch=30, yaw=45)
```

##### set_speed()

```python
def set_speed(pitch_speed: float, yaw_speed: float) -> bool
```

Set spotlight gimbal rotation speeds.

**Parameters:**
- `pitch_speed` (float): Pitch speed (-100 to +100, 0 = stop)
- `yaw_speed` (float): Yaw speed (-100 to +100, 0 = stop)

**Returns:** `bool` - True if successful

##### stop()

```python
def stop() -> bool
```

Stop all gimbal movement.

**Returns:** `bool` - True if successful

##### center()

```python
def center() -> bool
```

Center the gimbal (all axes to 0 degrees).

**Returns:** `bool` - True if successful

##### get_orientation()

```python
def get_orientation() -> Optional[Tuple[float, float]]
```

Get current orientation from IMU.

**Returns:** `Tuple[float, float]` or `None` - (pitch, roll) in degrees

**Example:**
```python
pitch, roll = controller.get_orientation()
print(f"Pitch: {pitch:.2f}°, Roll: {roll:.2f}°")
```

##### stabilize()

```python
def stabilize() -> bool
```

Perform one stabilization update using IMU feedback.

**Returns:** `bool` - True if stabilization performed

##### close()

```python
def close() -> None
```

Shutdown controller and cleanup resources.

## IMU Sensor API

### MPU6050

Interface for MPU6050 6-axis IMU sensor.

#### Constructor

```python
MPU6050(address: int = 0x68, bus: int = 1)
```

**Parameters:**
- `address` (int): I2C address (default: 0x68)
- `bus` (int): I2C bus number (default: 1)

#### Methods

##### initialize()

```python
def initialize() -> bool
```

Initialize the MPU6050 sensor.

**Returns:** `bool` - True if initialization successful

##### get_acceleration()

```python
def get_acceleration() -> Tuple[float, float, float]
```

Get acceleration values in g (gravity units).

**Returns:** `Tuple[float, float, float]` - (x, y, z) acceleration in g

**Example:**
```python
ax, ay, az = mpu.get_acceleration()
print(f"Acceleration: X={ax:.2f}g, Y={ay:.2f}g, Z={az:.2f}g")
```

##### get_gyroscope()

```python
def get_gyroscope() -> Tuple[float, float, float]
```

Get gyroscope values in degrees per second.

**Returns:** `Tuple[float, float, float]` - (x, y, z) angular velocity in deg/s

##### get_temperature()

```python
def get_temperature() -> float
```

Get temperature reading from sensor.

**Returns:** `float` - Temperature in Celsius

##### calibrate()

```python
def calibrate(samples: int = 100) -> bool
```

Calibrate the sensor by averaging readings while stationary.

**Parameters:**
- `samples` (int): Number of samples to average (default: 100)

**Returns:** `bool` - True if calibration successful

##### get_orientation()

```python
def get_orientation() -> Tuple[float, float]
```

Calculate pitch and roll angles from accelerometer.

**Returns:** `Tuple[float, float]` - (pitch, roll) in degrees

##### close()

```python
def close() -> None
```

Close I2C bus connection.

## Main Controller API

### GimbalController

Main controller for dual gimbal system.

#### Constructor

```python
GimbalController(config: SystemConfig)
```

**Parameters:**
- `config` (SystemConfig): System configuration object

#### Methods

##### initialize()

```python
def initialize() -> bool
```

Initialize both gimbal controllers.

**Returns:** `bool` - True if initialization successful

##### center_all()

```python
def center_all() -> None
```

Center both gimbals.

##### set_camera_position()

```python
def set_camera_position(pitch: float, roll: float, yaw: float) -> bool
```

Set camera gimbal position.

**Parameters:**
- `pitch` (float): Pitch angle in degrees
- `roll` (float): Roll angle in degrees
- `yaw` (float): Yaw angle in degrees

**Returns:** `bool` - True if successful

##### set_spotlight_position()

```python
def set_spotlight_position(pitch: float, yaw: float) -> bool
```

Set spotlight gimbal position.

**Parameters:**
- `pitch` (float): Pitch angle in degrees
- `yaw` (float): Yaw angle in degrees

**Returns:** `bool` - True if successful

##### sync_gimbals()

```python
def sync_gimbals(pitch: float, yaw: float) -> None
```

Synchronize both gimbals to the same orientation.

**Parameters:**
- `pitch` (float): Pitch angle in degrees
- `yaw` (float): Yaw angle in degrees

##### run_stabilization_loop()

```python
def run_stabilization_loop(update_rate: float = 0.1) -> None
```

Run continuous stabilization loop for spotlight gimbal.

**Parameters:**
- `update_rate` (float): Update interval in seconds (default: 0.1 = 10Hz)

##### get_status()

```python
def get_status() -> dict
```

Get status of both gimbals.

**Returns:** `dict` - Status information dictionary

##### shutdown()

```python
def shutdown() -> None
```

Shutdown gimbal system.

## Configuration API

### SystemConfig

System configuration management.

#### Class Methods

##### load()

```python
@classmethod
def load(cls, config_path: str) -> SystemConfig
```

Load configuration from JSON file.

**Parameters:**
- `config_path` (str): Path to configuration file

**Returns:** `SystemConfig` - Configuration object

##### save()

```python
def save(self, config_path: str) -> None
```

Save configuration to JSON file.

**Parameters:**
- `config_path` (str): Path to save configuration file

## Context Manager Support

All controller classes support Python context managers for automatic resource management:

```python
# Camera gimbal
with Storm32Controller() as camera:
    camera.set_angle(30, 0, 45)

# Spotlight gimbal
with SpotlightController() as spotlight:
    spotlight.set_position(30, 45)

# IMU sensor
with MPU6050() as mpu:
    pitch, roll = mpu.get_orientation()
```

## Complete Example

```python
from cymbal.utils.config import SystemConfig
from cymbal.main import GimbalController

# Load configuration
config = SystemConfig.load('/etc/cymbal/config.json')

# Create controller
controller = GimbalController(config)

# Initialize system
if controller.initialize():
    # Center both gimbals
    controller.center_all()
    
    # Synchronized movement
    controller.sync_gimbals(pitch=30, yaw=45)
    
    # Individual control
    controller.set_camera_position(pitch=30, roll=0, yaw=45)
    controller.set_spotlight_position(pitch=30, yaw=45)
    
    # Get status
    status = controller.get_status()
    print(status)
    
    # Shutdown
    controller.shutdown()
```

## Error Handling

All methods that can fail return `bool` or `Optional` types. Always check return values:

```python
controller = Storm32Controller()

if not controller.connect():
    print("Failed to connect to gimbal")
    exit(1)

if not controller.set_angle(30, 0, 45):
    print("Failed to set gimbal angle")

controller.disconnect()
```

## Thread Safety

The controllers are **not thread-safe**. If you need to control gimbals from multiple threads, implement your own locking mechanism:

```python
import threading

class ThreadSafeGimbalController:
    def __init__(self, controller):
        self.controller = controller
        self.lock = threading.Lock()
    
    def set_position(self, pitch, yaw):
        with self.lock:
            return self.controller.set_position(pitch, yaw)
```

## Logging

The package uses Python's standard `logging` module. Configure logging in your application:

```python
import logging

# Set log level
logging.basicConfig(level=logging.INFO)

# Or configure for specific modules
logging.getLogger('cymbal.camera_gimbal').setLevel(logging.DEBUG)
```

## Performance Considerations

- **Serial Communication:** Storm32 commands take ~10-50ms
- **I2C Communication:** MPU6050 reads take ~1-5ms
- **PWM Control:** Servo updates are near-instant (<1ms)
- **Stabilization Loop:** Recommended rate is 10-50Hz (0.02-0.1s interval)

## Limitations

- Storm32 MAVLink protocol is simplified (placeholder implementation)
- Stabilization uses basic proportional control (no full PID)
- No multi-threading support built-in
- Limited error recovery mechanisms

## Future Enhancements

- Full MAVLink protocol implementation
- PID controller for stabilization
- Thread-safe operations
- Data logging and telemetry
- Remote control interface (network, RC receiver)
- Computer vision integration for target tracking
