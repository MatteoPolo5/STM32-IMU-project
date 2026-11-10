"""Guided capture for the six-position calibration (T13).

Run from the tools/ folder with the board connected:
    python3 capture_calibration.py --port /dev/ttyACM0

For each position it tells which axis of the IMU board must point UP (against gravity), waits for Enter, captures
30 s and moves on. It ends with one extra capture in a tilted position that is NOT used in the fit, then runs
`imu_daq calibrate`. Files go to ../data/cal_*.bin and the result to ../results/calibration.json.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
STEPS = [
    ("xp", "l'asse X (la freccia X stampata sulla breakout) verso l'ALTO"),
    ("xn", "l'asse X verso il BASSO (freccia X che punta al tavolo)"),
    ("yp", "l'asse Y (freccia Y) verso l'ALTO"),
    ("yn", "l'asse Y verso il BASSO"),
    ("zp", "la breakout PIATTA, lato componenti verso l'ALTO (Z in alto)"),
    ("zn", "la breakout PIATTA capovolta, lato componenti verso il BASSO (Z in basso)"),
]
HELD = ("held", "la breakout appoggiata su uno spigolo, inclinata di circa 45 gradi in una direzione qualsiasi")


def valid_frames(path: Path) -> int:
    sys.path.insert(0, str(HERE))
    from imu_daq.protocol import parse

    return len(parse(path.read_bytes())) if path.exists() else 0


def capture(port: str, name: str, seconds: int) -> Path:
    out = DATA / f"cal_{name}.bin"
    cmd = [sys.executable, "-m", "imu_daq", "capture", "--port", port, "--duration", str(seconds), "--out", str(out)]
    subprocess.run(cmd, cwd=HERE, check=True)
    return out


def capture_checked(port: str, name: str, seconds: int) -> Path:
    """Capture and verify that frames really arrived; if not, stop and let the user fix the cause and retry."""
    while True:
        out = capture(port, name, seconds)
        n = valid_frames(out)
        if n >= 0.9 * seconds * 1000:
            print(f"      ok: {n} frame validi\n")
            return out
        print(f"\n      ATTENZIONE: {n} frame validi su circa {seconds * 1000} attesi.")
        print("      Controlla: LED sulla breakout acceso? fili SDA/SCL/VCC/GND ben inseriti? Poi premi il tasto RESET")
        print("      della scheda e aspetta un secondo.")
        input("      Premi Invio per RIPETERE questa posizione (Ctrl-C per uscire)... ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--only", nargs="*", help="repeat only these positions, e.g. --only yn zp zn held (others are kept)")
    a = ap.parse_args()

    print("Appoggia la breakout su un oggetto fermo e stabile (libro, scatola). Non toccarla durante la cattura.")
    print("Non scollegare i fili: muovi solo la breakout. Aspetta qualche secondo dopo ogni spostamento.\n")
    files = {name: DATA / f"cal_{name}.bin" for name, _ in STEPS + [HELD]}
    for name, text in STEPS + [HELD]:
        if a.only is not None and name not in a.only:
            print(f"[{name}] gia' presente, salto ({valid_frames(files[name])} frame validi)")
            continue
        input(f"[{name}] Metti {text}.\n      Quando e' ferma premi Invio... ")
        input("      (aspetto 3 secondi che si fermi) Premi Invio per iniziare... ")
        files[name] = capture_checked(a.port, name, a.seconds)

    bad = [n for n, f in files.items() if valid_frames(f) < 1000]
    if bad:
        print(f"errore: catture mancanti o vuote: {bad}. Ripeti con --only {' '.join(bad)}")
        return 1

    out = HERE.parent / "results" / "calibration.json"
    cmd = [sys.executable, "-m", "imu_daq", "calibrate",
           "--xp", str(files["xp"]), "--xn", str(files["xn"]), "--yp", str(files["yp"]),
           "--yn", str(files["yn"]), "--zp", str(files["zp"]), "--zn", str(files["zn"]),
           "--validate", str(files["held"]), "--out", str(out)]
    return subprocess.run(cmd, cwd=HERE).returncode


if __name__ == "__main__":
    raise SystemExit(main())