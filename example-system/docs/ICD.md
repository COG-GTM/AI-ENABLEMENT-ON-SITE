# Interface control document: sensor node

Synthetic example. Section numbers are referenced by requirements and tests.

## 1. Electrical

| Signal | MCU pin | Direction | Level | Notes |
| --- | --- | --- | --- | --- |
| VDD | - | - | 3.3 V | LDO from battery |
| IMU_SCK | PA5 | out | 3.3 V | SPI clock, 1 MHz |
| IMU_MOSI | PA7 | out | 3.3 V | |
| IMU_MISO | PA6 | in | 3.3 V | |
| IMU_CS | PA4 | out | 3.3 V | Active low |
| IMU_INT | PB0 | in | 3.3 V | Data-ready, rising edge |
| TEMP_SCL | PB6 | out | 3.3 V | I2C, 100 kHz, 4.7 k pull-up |
| TEMP_SDA | PB7 | bidir | 3.3 V | I2C, 4.7 k pull-up |
| UPLINK_TX | PA2 | out | 3.3 V | UART 115200 8N1 |
| UPLINK_RX | PA3 | in | 3.3 V | Reserved |

## 2. IMU (part `parts/imu-a.json`)

- SPI mode 3, MSB first, 16-bit registers, read = address | 0x80.
- Accelerometer range +/- 4 g, 16-bit signed, 8192 LSB/g.
- Gyro range +/- 500 dps, 16-bit signed, 65.5 LSB/dps.
- Data-ready interrupt on IMU_INT at the configured output data rate (100 Hz).
- WHO_AM_I register 0x0F returns 0x6A.

## 3. Temperature sensor (part `parts/temp-x.json`)

- I2C address 0x48, 12-bit two's-complement, 0.0625 C/LSB, register 0x00.
- Conversion time 30 ms; sampled at 1 Hz (SN-REQ-002).

## 4. Uplink packet (16 bytes, big-endian)

| Byte | Field | Type | Units / notes |
| --- | --- | --- | --- |
| 0 | SYNC | u8 | Always 0xA5 |
| 1 | FLAGS | u8 | bit0 = FAULT, bit1 = IMU_REINIT, bits 2-7 reserved 0 |
| 2-3 | SEQ | u16 | Wraps 65535 -> 0 (SN-REQ-009) |
| 4-5 | ACC_X | i16 | Filtered, raw LSB |
| 6-7 | ACC_Y | i16 | Filtered, raw LSB |
| 8-9 | ACC_Z | i16 | Filtered, raw LSB |
| 10-11 | GYRO_Z | i16 | Filtered, raw LSB |
| 12-13 | TEMP | i16 | Centi-degrees C (2350 = 23.50 C) |
| 14-15 | CRC | u16 | CRC-16/CCITT-FALSE over bytes 0-13 (SN-REQ-006) |

Reference vector (SEQ=1, ACC_Z=8192, TEMP=2350, all else 0):
`a5 00 00 01 00 00 00 00 20 00 00 00 09 2e 77 6a`. Both `tests/test_packet.py::test_known_vector`
and `tests/test_firmware.c::test_known_vector` assert this exact byte string.

## 5. Timing

Loop period 10 ms (100 Hz). Budget per loop in `TIMING.md`.
