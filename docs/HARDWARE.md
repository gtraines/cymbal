# Hardware Wiring Reference

## Raspberry Pi 3B+ GPIO Pinout

```
                    Raspberry Pi 3B+
                    ================
                         3.3V  (1) (2)  5V
           I2C SDA / GPIO 2  (3) (4)  5V
           I2C SCL / GPIO 3  (5) (6)  GND
                    GPIO 4  (7) (8)  GPIO 14 (UART TX)
                       GND  (9) (10) GPIO 15 (UART RX)
                   GPIO 17 (11) (12) GPIO 18
                   GPIO 27 (13) (14) GND
                   GPIO 22 (15) (16) GPIO 23
                      3.3V (17) (18) GPIO 24
                   GPIO 10 (19) (20) GND
                    GPIO 9 (21) (22) GPIO 25
                   GPIO 11 (23) (24) GPIO 8
                       GND (25) (26) GPIO 7
                    GPIO 0 (27) (28) GPIO 1
                    GPIO 5 (29) (30) GND
                    GPIO 6 (31) (32) GPIO 12
                   GPIO 13 (33) (34) GND
                   GPIO 19 (35) (36) GPIO 16
                   GPIO 26 (37) (38) GPIO 20
                       GND (39) (40) GPIO 21
```

## Connection Tables

### Storm32bgc Camera Gimbal

| Raspberry Pi | Wire | Storm32bgc |
|--------------|------|------------|
| GPIO 14 (Pin 8) | TX | RX |
| GPIO 15 (Pin 10) | RX | TX |
| GND (Pin 6, 9, 14, 20, 25, 30, 34, 39) | GND | GND |

**Protocol:** UART/Serial at 115200 baud

### Spotlight Gimbal Servos

| Raspberry Pi | Wire Color | Connection |
|--------------|------------|------------|
| GPIO 17 (Pin 11) | Orange/Yellow | Pitch Servo Signal |
| GPIO 27 (Pin 13) | Orange/Yellow | Yaw Servo Signal |
| 5V (Pin 2, 4) * | Red | Servo VCC (via external PSU) |
| GND (Pin 6, 9, 14, etc.) | Brown/Black | Servo GND |

**Protocol:** PWM (1000-2000µs pulses)
**Note:** Use external 5V power supply for servos (2A+ recommended)

### MPU6050 IMU Sensor

| Raspberry Pi | Wire | MPU6050 |
|--------------|------|---------|
| GPIO 2 (Pin 3) | SDA | SDA |
| GPIO 3 (Pin 5) | SCL | SCL |
| 3.3V (Pin 1, 17) | VCC | VCC |
| GND (Pin 6, 9, 14, etc.) | GND | GND |

**Protocol:** I2C at 400kHz
**I2C Address:** 0x68 (default) or 0x69 (AD0 high)

## Complete Wiring Diagram

```
                         +5V External Power Supply
                              |
                              +----------+
                              |          |
                         [Servo 1]  [Servo 2]
                         (Pitch)    (Yaw)
                           |           |
                           |           |
                  +--------+-----------+---------+
                  |                              |
              RPi GPIO                       RPi GND (Common Ground)
                  |                              |
           Pin 11 (GPIO 17)              Pin 6 or others
           Pin 13 (GPIO 27)
                  |
                  |
        +---------+----------+
        |                    |
    I2C Bus              UART
        |                    |
    Pin 3 (SDA)          Pin 8 (TX)
    Pin 5 (SCL)          Pin 10 (RX)
        |                    |
        |                    |
    [MPU6050]            [Storm32bgc]
        |                    |
    Pin 1 (3.3V)         External Power
    Pin 6 (GND)          GND to RPi GND
```

## Power Considerations

### Raspberry Pi Power
- **Input:** 5V 2.5A via micro-USB or GPIO
- **GPIO 5V Output:** Limited to ~1.5A total (fused)
- **GPIO 3.3V Output:** Limited to ~50mA

### Servo Power
- **Per Servo:** Typically 100-500mA under load, up to 1-2A at stall
- **Recommendation:** Use dedicated 5V power supply (3A+) for servos
- **Important:** Connect servo ground to RPi ground (common ground)

### MPU6050 Power
- **Operating Voltage:** 3.3V or 5V (check module)
- **Current:** ~3-5mA typical
- **Power Source:** RPi 3.3V pin is sufficient

## Safety Notes

1. **Never connect servo power directly to RPi 5V pins** - Use external power supply
2. **Common Ground:** Always connect grounds between RPi and external devices
3. **Signal Levels:** RPi GPIO is 3.3V - ensure servo and sensor compatibility
4. **ESD Protection:** Handle electronics on anti-static mat or wrist strap
5. **Hot Swapping:** Power off before connecting/disconnecting components

## Testing Individual Components

### Test UART (Storm32bgc)
```bash
# Install minicom
sudo apt-get install minicom

# Test serial port (disconnect Storm32 first)
minicom -b 115200 -o -D /dev/ttyAMA0
```

### Test I2C (MPU6050)
```bash
# Scan I2C bus
sudo i2cdetect -y 1

# Should show device at 0x68:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 00:          -- -- -- -- -- -- -- -- -- -- -- -- --
# ...
# 60: -- -- -- -- -- -- -- -- 68 -- -- -- -- -- -- --
```

### Test GPIO/PWM (Servos)
```bash
# Test with pigpio
pigs s 17 1500  # Set GPIO 17 to 1500µs (center)
pigs s 27 1500  # Set GPIO 27 to 1500µs (center)
pigs s 17 0     # Turn off GPIO 17
pigs s 27 0     # Turn off GPIO 27
```

## Mounting Considerations

When mounting on fixed-wing drone:

1. **Vibration Isolation:** Use dampening mounts for MPU6050
2. **Wire Management:** Secure all wires to prevent snagging
3. **Orientation:** Note IMU orientation for correct pitch/roll readings
4. **Access:** Ensure USB/GPIO ports remain accessible for programming
5. **Weight Distribution:** Balance weight for stable flight
6. **Protection:** Weather-proof enclosure for outdoor use

## References

- [Raspberry Pi GPIO Documentation](https://www.raspberrypi.org/documentation/hardware/raspberrypi/gpio/README.md)
- [MPU6050 Datasheet](https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/)
- [Storm32bgc Documentation](https://github.com/gtraines/storm32bgc)
- [Servo PWM Signals](http://www.servodatabase.com/servo-articles/what-is-pwm-signal)
