# Hardware setup

## Parts

| Part | Notes |
|---|---|
| NUCLEO-F446RE | STM32F446RE, Cortex-M4F @ 84 MHz (configured), ST-LINK/V2-1 on board |
| MPU6050 breakout (GY-521) | I2C, 3.3 V logic. Has 4.7 kΩ pull-ups on board |
| 4 jumper wires | female-female or as needed |
| USB cable | powers the board, programs it and carries the serial stream |

## Wiring

| MPU6050 pin | Nucleo pin | Notes |
|---|---|---|
| VCC | 3V3 | do not use 5V unless your breakout has a regulator and level shifting |
| GND | GND | |
| SCL | PB8 (**D15**, Arduino header) | I2C1_SCL, AF4 |
| SDA | PB9 (**D14**, Arduino header) | I2C1_SDA, AF4 |
| AD0 | GND | I2C address 0x68 (leave floating/high -> 0x69, change `kMpuAddress`) |
| INT | not connected | reserved for a future data-ready interrupt |

The serial stream uses USART2 (PA2) which is wired to the ST-LINK virtual COM port by default
(solder bridges SB13/SB14 closed). The user LED LD2 (PA5) toggles once per second of streamed data.

## Build and flash

```bash
sudo apt install cmake ninja-build gcc-arm-none-eabi openocd     # Ubuntu / WSL
cmake --preset firmware
cmake --build --preset firmware                  # -> build/firmware/firmware/imu_daq.{elf,bin,hex}

cmake --build --preset firmware --target flash   # OpenOCD + ST-LINK
```

Alternatives: copy `imu_daq.bin` onto the `NODE_F446RE` USB drive that appears when the board is plugged in, or use
STM32CubeProgrammer. The first configure downloads the CMSIS headers from GitHub (needs network access).

Options: `-DSAMPLE_RATE_HZ=200`, `-DI2C_CLOCK_HZ=100000`, `-DUART_BAUD=921600`, `-DUSE_HSE_BYPASS=ON`,
and `-DMPU_ACCEL_FS_SEL=1`, `-DMPU_GYRO_FS_SEL=1` (pass them to `cmake --preset firmware`).

## First run checklist

1. Open the serial port (any terminal, 460800 8N1): you should see
   `E3-DAQ fw=... rate=1000Hz i2c=400kHz baud=460800 clk=HSI who_am_i=0x68` followed by `STREAM` and then binary garbage.
2. LD2 blinks once per second.
3. From `tools/`: `python -m imu_daq capture --port <port> --duration 10`, then
   `python -m imu_daq analyze ../data/capture.bin` should report 0 lost frames.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `FATAL: MPU6050 not responding` | wiring (SDA/SCL swapped, no 3V3/GND), wrong address, no pull-ups |
| `who_am_i=0x70/0x72/0x98` | clone or MPU6500/9250 on the breakout: usually works, register map is compatible |
| LD2 never blinks, no banner | wrong serial port / baud, or the clock failed: try without `USE_HSE_BYPASS` |
| frames lost at 1 kHz | I2C not really at 400 kHz (long wires, weak pull-ups), UART link overloaded, ring overflow: inspect `daq::g_stats` in GDB |
| `crc_errors > 0` | UART baud mismatch (HSI accuracy), noisy USB cable/hub |
| everything stops after some seconds | I2C bus lock-up: the watchdog should recover it (`watchdog_aborts` in `g_stats`) |

## Debugging with GDB

```bash
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg &
arm-none-eabi-gdb build/firmware-debug/firmware/imu_daq.elf   # configure with --preset firmware-debug
(gdb) target extended-remote :3333
(gdb) monitor reset halt
(gdb) load
(gdb) continue
# Ctrl-C, then:
(gdb) print daq::g_stats
```
