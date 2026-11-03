# Wire protocol

The firmware streams fixed-size binary frames over the ST-LINK virtual COM port
(USART2, 8N1, default 460800 baud). After reset it first prints a short ASCII banner
ending with `STREAM\r\n`, then only frames.

```
offset  size  field     description
------  ----  --------  -------------------------------------------------------------
   0     2    sync      0xA5 0x5A
   2     4    seq       sample counter, little-endian. Increments on EVERY timer tick,
                        also when the sample is dropped -> gaps in seq reveal losses.
   6     4    t_tick    DWT->CYCCNT captured at timer-interrupt entry (84 MHz core clock)
  10     4    t_done    DWT->CYCCNT captured when the I2C DMA transfer completed
  14     2    dropped   cumulative number of samples lost inside the firmware (mod 65536)
  16    14    raw       MPU6050 registers 0x3B..0x48 exactly as read (big-endian int16):
                        ACCEL_X, ACCEL_Y, ACCEL_Z, TEMP, GYRO_X, GYRO_Y, GYRO_Z
  30     2    crc16     CRC-16/CCITT-FALSE over bytes 2..29, little-endian
```

* 32 bytes per frame -> 32 kB/s at 1 kHz = 69 % of a 460800 baud link.
* CRC-16/CCITT-FALSE: polynomial 0x1021, init 0xFFFF, no reflection, no final XOR;
  check value for `"123456789"` is `0x29B1` (verified at compile time in `protocol.hpp`).
* The payload is kept in the sensor's byte order so the MCU never touches it; the host converts
  counts to physical units (`tools/imu_daq/analysis.py`, `tools/matlab/analyze_log.m`).

## Why these fields

| Field | Purpose |
|---|---|
| `seq` | detect lost frames anywhere in the chain (tick overrun, ring overflow, UART corruption) |
| `t_tick` | measure real sampling jitter, independent of the PC and of UART timing |
| `t_done - t_tick` | acquisition latency (timer event -> data in RAM) |
| `dropped` | tells *where* the loss happened: `lost = dropped (firmware) + crc errors (link)` |
| `crc16` | resynchronise after corruption without guessing |

## Conversion to physical units

| Quantity | Formula (firmware defaults) |
|---|---|
| acceleration | `counts / 16384` g (`MPU_ACCEL_FS_SEL = 0`, ±2 g) |
| angular rate | `counts / 131` deg/s (`MPU_GYRO_FS_SEL = 0`, ±250 deg/s) |
| temperature | `counts / 340 + 36.53` °C |
| time | `(t_tick - t_tick[0]) / 84e6` s (unwrap the 32-bit counter: it wraps every 51 s) |

## Golden vector

`tests/golden/frame_vector.txt` holds one sample and its expected 32-byte frame. The C++ unit test and
the Python test both check it, so the firmware and the host tools cannot silently diverge.
