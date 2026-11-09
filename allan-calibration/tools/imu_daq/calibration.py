"""Static calibration of the MPU6050 from short captures with the board at rest.

Accelerometer: six-position method. The board rests with each axis pointing up (+) and down (-) in turn, so
the true specific force on that axis is +1 g and -1 g. For axis i, with mean readings r+ and r-:

    bias_i  = (r+ + r-) / 2          (offset, in g)
    scale_i = 2 / (r+ - r-)          (multiplier; 1.0 means the sensitivity is exactly nominal)
    a_cal   = scale * (a_raw - bias)

This is a diagonal model: offset and per-axis sensitivity only. Axis misalignment (non-orthogonality) is not
estimated; the held-out check reports how much error is left.

Gyroscope: bias only (mean at rest). Scale factor would need a known rotation and is not calibrated.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

POSITIONS = ("+x", "-x", "+y", "-y", "+z", "-z")


@dataclass
class AccelCal:
    bias_g: np.ndarray   # (3,)
    scale: np.ndarray    # (3,)


def fit_accel_six_position(means: dict) -> AccelCal:
    """`means[pos]` is the mean accelerometer reading [g] (3 values) with that axis pointing up/down."""
    for pos in POSITIONS:
        if pos not in means:
            raise ValueError(f"missing position {pos}")
    bias = np.zeros(3)
    scale = np.zeros(3)
    for i, axis in enumerate("xyz"):
        up = float(np.asarray(means["+" + axis])[i])
        down = float(np.asarray(means["-" + axis])[i])
        # Sanity check: the axis pointing up must read about +1 g, pointing down about -1 g.
        if not (0.8 < up < 1.2) or not (-1.2 < down < -0.8):
            raise ValueError(
                f"axis {axis}: readings {up:+.3f} g (+{axis}) and {down:+.3f} g (-{axis}) are not about +1 g / -1 g; "
                "check the orientation and the order of the files")
        bias[i] = 0.5 * (up + down)
        scale[i] = 2.0 / (up - down)
    return AccelCal(bias_g=bias, scale=scale)


def apply_accel(acc_g: np.ndarray, cal: AccelCal) -> np.ndarray:
    return (np.asarray(acc_g) - cal.bias_g) * cal.scale


def norm_error_mg(acc_g: np.ndarray) -> float:
    """Mean of |a| minus 1 g, in mg."""
    return float((np.linalg.norm(np.asarray(acc_g), axis=1).mean() - 1.0) * 1e3)


def tilt_warnings(means: dict, max_off_axis_g: float = 0.25) -> list:
    """Positions where the board is clearly not aligned with the axis (large off-axis components)."""
    out = []
    for pos in POSITIONS:
        i = "xyz".index(pos[1])
        m = np.asarray(means[pos], dtype=float)
        off = np.delete(m, i)
        if np.max(np.abs(off)) > max_off_axis_g:
            out.append(f"{pos}: off-axis component up to {np.max(np.abs(off)):.2f} g (board not level)")
    return out
