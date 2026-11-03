import numpy as np
import pytest

from imu_daq import analysis as an
from imu_daq.protocol import parse
from imu_daq.simulate import simulate

CPU = 84e6


def test_clean_log_has_no_loss_and_ideal_rate():
    log = parse(simulate(10, 1000, seed=1))
    loss = an.loss_report(log)
    assert (loss.frames_lost, loss.crc_errors, loss.duplicate_or_reordered) == (0, 0, 0)
    tim = an.timing_report(log, 1000, CPU)
    assert tim.rate_hz_measured == pytest.approx(1000.0, rel=1e-6)
    assert tim.jitter_us["rms"] < 1.0


def test_counter_wraparound_is_handled():
    # simulate() starts the DWT counter 0x10000 cycles before the 32-bit wrap.
    log = parse(simulate(5, 1000, seed=2, t0_cycles=0xFFFF_0000))
    assert (np.diff(log.t_tick.astype(np.int64)) < 0).any()  # the raw counter really wrapped
    assert an.timing_report(log, 1000, CPU).rate_hz_measured == pytest.approx(1000.0, rel=1e-6)


def test_loss_accounting_matches_firmware_counter():
    log = parse(simulate(30, 1000, drop_prob=0.01, corrupt_prob=0.002, seed=3))
    loss = an.loss_report(log)
    # every lost frame is either dropped by the firmware (counter) or corrupted on the wire (CRC)
    assert loss.frames_lost == loss.firmware_dropped_last + loss.crc_errors
    assert loss.gap_count > 0


def test_jitter_ignores_gaps():
    log = parse(simulate(20, 1000, drop_prob=0.05, seed=4, jitter_rms_us=0.2))
    tim = an.timing_report(log, 1000, CPU)
    assert tim.jitter_us["rms"] < 1.0  # a lost frame must not show up as a 2 ms interval


def test_static_imu_statistics():
    log = parse(simulate(20, 1000, seed=5, tilt_deg=0.0, gyro_bias_dps=(1.0, -2.0, 0.5)))
    imu = an.imu_report(an.scale(log, CPU))
    assert imu.acc_norm_mean_g == pytest.approx(1.0, abs=2e-3)
    assert imu.gyro_mean_dps == pytest.approx([1.0, -2.0, 0.5], abs=0.02)


def test_allan_deviation_of_white_noise_falls_as_inverse_sqrt_tau():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1.0, 200_000)
    tau, adev = an.allan_deviation(x, 100.0)
    slope = np.polyfit(np.log10(tau[:10]), np.log10(adev[:10]), 1)[0]
    assert slope == pytest.approx(-0.5, abs=0.1)
