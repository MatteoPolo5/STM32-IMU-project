"""Gyro bias after repeated resets, board flat and still (does the bias change at every start-up?).

    python3 reset_bias_test.py --port /dev/ttyACM0 [--n 5] [--seconds 30]

Leave the IMU board flat and untouched. For each round the script asks you to press the black RESET button, waits for the
firmware to restart, captures, and prints the mean gyro bias and die temperature of that round. At the end it prints the
spread between rounds. Files: ../data/rst_<k>.bin
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from imu_daq import analysis as an  # noqa: E402
from imu_daq.protocol import parse  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--trim", type=float, default=3.0, help="seconds dropped at start and end of each capture")
    a = ap.parse_args()

    rows = []
    for k in range(1, a.n + 1):
        input(f"[{k}/{a.n}] IMU piatta e ferma. Premi il tasto RESET della scheda, poi premi Invio qui... ")
        time.sleep(1.5)  # firmware restart and banner
        out = HERE.parent / "data" / f"rst_{k}.bin"
        subprocess.run([sys.executable, "-m", "imu_daq", "capture", "--port", a.port, "--duration", str(a.seconds),
                        "--out", str(out)], cwd=HERE, check=True)
        log = parse(out.read_bytes())
        if len(log) < 0.9 * a.seconds * 1000:
            print(f"      ATTENZIONE: solo {len(log)} frame validi: round scartato (controlla i fili e ripeti)")
            continue
        sc = an.scale(log, 84e6)
        keep = (sc.t >= a.trim) & (sc.t <= sc.t[-1] - a.trim)
        g = sc.gyro_dps[keep].mean(axis=0)
        h = keep.sum() // 2
        g1, g2 = sc.gyro_dps[keep][:h].mean(axis=0), sc.gyro_dps[keep][h:].mean(axis=0)
        t = float(sc.temp_c[keep].mean())
        rows.append((g, t))
        print(f"      gyro bias [deg/s] {np.round(g, 4).tolist()}  T {t:.2f} C  | 1a meta - 2a meta: {np.round(g1 - g2, 4).tolist()}\n")

    if len(rows) < 2:
        print("troppi pochi round validi")
        return 1
    G = np.array([r[0] for r in rows]); T = np.array([r[1] for r in rows])
    print("round validi:", len(rows))
    print("media [deg/s]:    ", np.round(G.mean(axis=0), 4).tolist())
    print("spread tra reset: ", np.round(G.max(axis=0) - G.min(axis=0), 4).tolist(), "(max - min)")
    print("temperatura: %.2f .. %.2f C" % (T.min(), T.max()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())