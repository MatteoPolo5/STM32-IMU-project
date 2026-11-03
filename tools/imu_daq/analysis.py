"""Timing, loss and IMU statistics computed from a parsed log."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .protocol import ParsedLog

# MPU6050 sensitivities for the firmware defaults (+-2 g, +-250 deg/s).
ACCEL_LSB_PER_G = {0: 16384.0, 1: 8192.0, 2: 4096.0, 3: 2048.0}
GYRO_LSB_PER_DPS = {0: 131.0, 1: 65.5, 2: 32.8, 3: 16.4}
G0 = 9.80665


def wrapped_diff_u32(x: np.ndarray) -> np.ndarray:
    """Differences of a free-running 32-bit counter, correct across wrap-around."""
    x = x.astype(np.uint32)
    return (x[1:] - x[:-1]).astype(np.uint32)  # uint32 arithmetic wraps modulo 2^32


@dataclass
class Scaled:
    t: np.ndarray        # [s] time of the timer tick, relative to the first sample
    acc_g: np.ndarray    # (N, 3) [g]
    gyro_dps: np.ndarray # (N, 3) [deg/s]
    temp_c: np.ndarray   # (N,)  [deg C]


def scale(log: ParsedLog, cpu_hz: float, accel_fs: int = 0, gyro_fs: int = 0) -> Scaled:
    counts = log.imu_counts().astype(np.float64)
    t_cycles = np.concatenate(([0], np.cumsum(wrapped_diff_u32(log.t_tick), dtype=np.uint64)))
    return Scaled(
        t=t_cycles.astype(np.float64) / cpu_hz,
        acc_g=counts[:, 0:3] / ACCEL_LSB_PER_G[accel_fs],
        temp_c=counts[:, 3] / 340.0 + 36.53,
        gyro_dps=counts[:, 4:7] / GYRO_LSB_PER_DPS[gyro_fs],
    )


@dataclass
class LossReport:
    frames_received: int
    frames_expected: int
    frames_lost: int
    loss_percent: float
    duplicate_or_reordered: int
    gap_count: int
    longest_gap: int
    crc_errors: int
    garbage_bytes: int
    firmware_dropped_last: int  # final value of the firmware's own `dropped` counter


def loss_report(log: ParsedLog) -> LossReport:
    n = len(log)
    if n == 0:
        return LossReport(0, 0, 0, 0.0, 0, 0, 0, log.n_bad_crc, log.n_garbage_bytes, 0)
    seq = log.seq.astype(np.int64)
    d = np.diff(seq)
    bad_order = int(np.count_nonzero(d <= 0))
    gaps = d[d > 1] - 1
    expected = int(seq.max() - seq.min() + 1)
    lost = int(gaps.sum())
    return LossReport(
        frames_received=n, frames_expected=expected, frames_lost=lost,
        loss_percent=100.0 * lost / expected, duplicate_or_reordered=bad_order,
        gap_count=int(gaps.size), longest_gap=int(gaps.max()) if gaps.size else 0,
        crc_errors=log.n_bad_crc, garbage_bytes=log.n_garbage_bytes,
        firmware_dropped_last=int(log.dropped[-1]),
    )


def _percentiles(x: np.ndarray, qs=(50, 99, 99.9)) -> dict:
    return {f"p{q:g}": float(np.percentile(x, q)) for q in qs}


@dataclass
class TimingReport:
    rate_hz_nominal: float
    rate_hz_measured: float
    interval_us: dict = field(default_factory=dict)   # tick-to-tick interval statistics
    jitter_us: dict = field(default_factory=dict)     # deviation from the ideal interval
    latency_us: dict = field(default_factory=dict)    # tick -> DMA complete
    n_intervals: int = 0


def timing_report(log: ParsedLog, rate_hz: float, cpu_hz: float) -> TimingReport:
    """Uses only consecutive samples (seq diff == 1) so that lost frames do not pollute the jitter."""
    ideal_cycles = cpu_hz / rate_hz
    cycles = wrapped_diff_u32(log.t_tick).astype(np.float64)
    consecutive = np.diff(log.seq.astype(np.int64)) == 1
    iv = cycles[consecutive]
    to_us = 1e6 / cpu_hz
    rep = TimingReport(rate_hz_nominal=rate_hz, rate_hz_measured=float("nan"), n_intervals=int(iv.size))
    if iv.size == 0:
        return rep
    err = (iv - ideal_cycles) * to_us
    rep.rate_hz_measured = cpu_hz / float(iv.mean())
    rep.interval_us = {"mean": float(iv.mean() * to_us), "std": float(iv.std() * to_us),
                       "min": float(iv.min() * to_us), "max": float(iv.max() * to_us)}
    abs_err = np.abs(err)
    rep.jitter_us = {"mean": float(err.mean()), "rms": float(np.sqrt(np.mean(err ** 2))),
                     "peak_to_peak": float(err.max() - err.min()), "max_abs": float(abs_err.max()),
                     **{k: float(np.percentile(abs_err, q)) for k, q in (("abs_p99", 99), ("abs_p99.9", 99.9))}}
    lat = wrapped_diff_u32_pairs(log.t_tick, log.t_done).astype(np.float64) * to_us
    rep.latency_us = {"mean": float(lat.mean()), "std": float(lat.std()), "min": float(lat.min()),
                      "max": float(lat.max()), **_percentiles(lat)}
    return rep


def wrapped_diff_u32_pairs(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """b - a modulo 2^32, element-wise."""
    return (b.astype(np.uint32) - a.astype(np.uint32)).astype(np.uint32)


@dataclass
class ImuReport:
    n_samples: int
    acc_mean_g: list
    acc_std_mg: list
    acc_norm_mean_g: float
    acc_norm_error_mg: float
    gyro_mean_dps: list     # = bias if the board was stationary
    gyro_std_dps: list
    temp_mean_c: float


def imu_report(s: Scaled) -> ImuReport:
    norm = np.linalg.norm(s.acc_g, axis=1)
    return ImuReport(
        n_samples=len(s.t),
        acc_mean_g=s.acc_g.mean(axis=0).round(5).tolist(),
        acc_std_mg=(s.acc_g.std(axis=0) * 1e3).round(3).tolist(),
        acc_norm_mean_g=float(norm.mean()),
        acc_norm_error_mg=float((norm.mean() - 1.0) * 1e3),
        gyro_mean_dps=s.gyro_dps.mean(axis=0).round(5).tolist(),
        gyro_std_dps=s.gyro_dps.std(axis=0).round(5).tolist(),
        temp_mean_c=float(s.temp_c.mean()),
    )


def allan_deviation(x: np.ndarray, rate_hz: float, n_taus: int = 25):
    """Overlapping Allan deviation of a rate signal `x` sampled at `rate_hz`.

    Returns (tau [s], adev). Uses the cumulative-sum formulation, O(N) per tau.
    """
    n = len(x)
    theta = np.concatenate(([0.0], np.cumsum(x))) / rate_hz  # integrated angle
    m_max = n // 3
    if m_max < 1:
        return np.array([]), np.array([])
    ms = np.unique(np.logspace(0, np.log10(m_max), n_taus).astype(int))
    taus, adev = [], []
    for m in ms:
        d = theta[2 * m:] - 2 * theta[m:-m] + theta[:-2 * m]
        taus.append(m / rate_hz)
        adev.append(np.sqrt(0.5 * np.mean(d ** 2)) / (m / rate_hz))
    return np.asarray(taus), np.asarray(adev)
