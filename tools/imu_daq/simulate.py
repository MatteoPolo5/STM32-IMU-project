"""Generates a SYNTHETIC log in the firmware's binary format.

Meant for developing/testing the analysis tools without hardware (and for CI).
It is NOT a substitute for real measurements: never report its numbers as results.
"""
from __future__ import annotations

import numpy as np

from .analysis import ACCEL_LSB_PER_G, GYRO_LSB_PER_DPS
from .protocol import FRAME_SIZE, SYNC, crc16_rows


def simulate(duration_s: float = 10.0, rate_hz: float = 1000.0, cpu_hz: float = 84e6,
             jitter_rms_us: float = 0.25, drop_prob: float = 0.0, corrupt_prob: float = 0.0,
             tilt_deg: float = 3.0, gyro_bias_dps=(0.8, -0.5, 0.3), acc_noise_mg: float = 4.0,
             gyro_noise_dps: float = 0.05, seed: int = 0, t0_cycles: int = 0xFFFF_0000,
             banner: bool = True) -> bytes:
    rng = np.random.default_rng(seed)
    n = int(duration_s * rate_hz)
    seq = np.arange(n, dtype=np.uint32)
    ideal = cpu_hz / rate_hz
    # tick timestamps: ideal grid + ISR-entry jitter (never accumulates)
    t_tick = (t0_cycles + np.round(seq * ideal + rng.normal(0, jitter_rms_us * cpu_hz / 1e6, n))).astype(np.int64)
    t_done = t_tick + np.round(rng.normal(380e-6 * cpu_hz, 3e-6 * cpu_hz, n)).astype(np.int64)

    tilt = np.deg2rad(tilt_deg)
    acc = np.array([np.sin(tilt), 0.0, np.cos(tilt)]) + rng.normal(0, acc_noise_mg / 1e3, (n, 3))
    gyro = np.array(gyro_bias_dps) + rng.normal(0, gyro_noise_dps, (n, 3))
    temp = np.full(n, (25.0 - 36.53) * 340.0) + rng.normal(0, 2, n)
    counts = np.empty((n, 7), dtype=np.int16)
    counts[:, 0:3] = np.clip(np.round(acc * ACCEL_LSB_PER_G[0]), -32768, 32767)
    counts[:, 3] = np.round(temp)
    counts[:, 4:7] = np.clip(np.round(gyro * GYRO_LSB_PER_DPS[0]), -32768, 32767)
    u = counts.astype(np.int16).view(np.uint16)
    raw = np.empty((n, 14), dtype=np.uint8)
    raw[:, 0::2] = (u >> 8).astype(np.uint8)
    raw[:, 1::2] = (u & 0xFF).astype(np.uint8)

    frames = np.zeros((n, FRAME_SIZE), dtype=np.uint8)
    frames[:, 0], frames[:, 1] = SYNC[0], SYNC[1]
    for k, (col, v) in enumerate([(2, seq), (6, (t_tick & 0xFFFFFFFF).astype(np.uint32)),
                                  (10, (t_done & 0xFFFFFFFF).astype(np.uint32))]):
        for b in range(4):
            frames[:, col + b] = ((v >> (8 * b)) & 0xFF).astype(np.uint8)
    kept = rng.random(n) >= drop_prob
    dropped_ctr = np.cumsum(~kept).astype(np.uint16)
    frames[:, 14] = (dropped_ctr & 0xFF).astype(np.uint8)
    frames[:, 15] = (dropped_ctr >> 8).astype(np.uint8)
    frames[:, 16:30] = raw
    crc = crc16_rows(frames[:, 2:30])
    frames[:, 30], frames[:, 31] = (crc & 0xFF).astype(np.uint8), (crc >> 8).astype(np.uint8)

    frames = frames[kept]
    if corrupt_prob > 0:
        bad = rng.random(len(frames)) < corrupt_prob
        pos = rng.integers(2, 30, bad.sum())
        frames[np.flatnonzero(bad), pos] ^= 0x55
    out = frames.tobytes()
    if banner:
        out = b"\r\nE3-DAQ fw=sim rate=%d\r\nSTREAM\r\n" % int(rate_hz) + out
    return out
