import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from imu_daq import analysis as an
from imu_daq import calibration as cal
from imu_daq.protocol import Sample

TOOLS = Path(__file__).resolve().parents[2] / "tools"

B_TRUE = np.array([0.07, -0.05, 0.08])   # offsets [g]
K_TRUE = np.array([1.002, 0.997, 1.004])  # scale multipliers


def reading(u):
    """Raw accelerometer reading for a true specific force u [g]: raw = bias + u / k."""
    return B_TRUE + np.asarray(u, dtype=float) / K_TRUE


def six_means():
    m = {}
    for i, axis in enumerate("xyz"):
        for sign in "+-":
            u = np.zeros(3)
            u[i] = 1.0 if sign == "+" else -1.0
            m[sign + axis] = reading(u)
    return m


def test_six_position_recovers_bias_and_scale():
    fit = cal.fit_accel_six_position(six_means())
    assert fit.bias_g == pytest.approx(B_TRUE, abs=1e-12)
    assert fit.scale == pytest.approx(K_TRUE, abs=1e-12)


def test_calibrated_norm_is_one_in_an_arbitrary_orientation():
    fit = cal.fit_accel_six_position(six_means())
    u = np.array([[0.3, -0.5, np.sqrt(1 - 0.34)]])
    raw = reading(u[0])[None, :]
    assert abs(cal.norm_error_mg(raw)) > 20                        # uncalibrated: clearly off
    assert cal.norm_error_mg(cal.apply_accel(raw, fit)) == pytest.approx(0.0, abs=1e-9)


def test_wrong_orientation_is_rejected():
    m = six_means()
    m["+x"], m["-x"] = m["-x"], m["+x"]            # files swapped
    with pytest.raises(ValueError, match="orientation"):
        cal.fit_accel_six_position(m)


def test_missing_position_is_rejected():
    m = six_means()
    del m["-z"]
    with pytest.raises(ValueError, match="missing"):
        cal.fit_accel_six_position(m)


def test_tilt_warning():
    m = six_means()
    m["+z"] = m["+z"] + np.array([0.5, 0.0, 0.0])
    assert any("+z" in w for w in cal.tilt_warnings(m))


def test_allan_white_noise_arw():
    rng = np.random.default_rng(1)
    fs, sigma = 1000.0, 0.1                       # deg/s rms per sample
    x = rng.normal(0.0, sigma, 600_000)
    tau, adev = an.allan_deviation(x, fs)
    s = an.allan_summary(tau, adev)
    expected = sigma / np.sqrt(fs) * 60.0         # deg/sqrt(h)
    assert s["arw_deg_per_sqrt_h"] == pytest.approx(expected, rel=0.1)
    assert s["slope_at_1s"] == pytest.approx(-0.5, abs=0.1)


def test_allan_flags_missing_minimum():
    # Pure white noise: the curve keeps falling, so no bias-instability minimum must be reported, whatever the seed.
    for seed in range(10):
        x = np.random.default_rng(seed).normal(0.0, 0.1, 60_000)
        tau, adev = an.allan_deviation(x, 1000.0)
        assert not an.allan_summary(tau, adev)["bias_instability_observed"], seed


def test_allan_finds_a_minimum_when_there_is_one():
    rng = np.random.default_rng(3)
    n, fs = 600_000, 1000.0
    x = rng.normal(0.0, 0.1, n) + np.cumsum(rng.normal(0.0, 1.7e-5, n))   # white noise + rate random walk (minimum expected near 10 s)
    tau, adev = an.allan_deviation(x, fs)
    s = an.allan_summary(tau, adev)
    assert s["bias_instability_observed"]
    assert 3.0 < s["bias_instability_tau_s"] <= 200.0


def _frames(acc_g, gyro_dps, n=3000, rate=1000, seed=0):
    """Static log: constant reading + a little noise, packed with the real frame format."""
    rng = np.random.default_rng(seed)
    out = bytearray()
    for k in range(n):
        a = np.round((np.asarray(acc_g) + rng.normal(0, 0.002, 3)) * 16384).astype(">i2")
        g = np.round((np.asarray(gyro_dps) + rng.normal(0, 0.02, 3)) * 131).astype(">i2")
        t = np.array([int((25.0 - 36.53) * 340)], dtype=">i2")
        raw = a.tobytes() + t.tobytes() + g.tobytes()   # big-endian int16, as the sensor sends them
        out += Sample(seq=k, t_tick=int(k * 84e6 / rate), t_done=int(k * 84e6 / rate) + 32000, dropped=0, raw=raw).pack()
    return bytes(out)


def test_calibrate_cli_end_to_end(tmp_path):
    files = {}
    gyro = [-1.0, -1.5, 0.3]
    for pos, u in {"+x": [1, 0, 0], "-x": [-1, 0, 0], "+y": [0, 1, 0], "-y": [0, -1, 0],
                   "+z": [0, 0, 1], "-z": [0, 0, -1]}.items():
        f = tmp_path / f"{pos[1]}{'p' if pos[0] == '+' else 'n'}.bin"
        f.write_bytes(_frames(reading(u), gyro, seed=len(files)))
        files[pos] = f
    held = tmp_path / "held.bin"
    held.write_bytes(_frames(reading([0.3, -0.5, np.sqrt(0.66)]), gyro, seed=9))
    out = tmp_path / "calib.json"
    cmd = [sys.executable, "-I", "-c",
           f"import sys; sys.path.insert(0, {str(TOOLS)!r}); from imu_daq.cli import main; sys.exit(main())",
           "calibrate", "--xp", str(files["+x"]), "--xn", str(files["-x"]), "--yp", str(files["+y"]),
           "--yn", str(files["-y"]), "--zp", str(files["+z"]), "--zn", str(files["-z"]),
           "--validate", str(held), "--trim", "0.5", "--out", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    res = json.loads(out.read_text())
    assert res["accel_bias_g"] == pytest.approx(B_TRUE, abs=2e-3)
    assert res["accel_scale"] == pytest.approx(K_TRUE, abs=2e-3)
    assert res["gyro_bias_dps"] == pytest.approx(gyro, abs=0.02)
    h = res["held_out"][str(held)]
    assert abs(h["norm_error_mg_before"]) > 20
    assert abs(h["norm_error_mg_after"]) < 5
