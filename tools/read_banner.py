"""Print the firmware banner (E3-DAQ ...) after a reset.

    python3 read_banner.py [--port /dev/ttyACM0]
Run it, then press the black RESET button on the board within 15 s. Expected: a line with who_am_i=0x68 followed by STREAM.
"""
import argparse
import time

import serial

ap = argparse.ArgumentParser()
ap.add_argument("--port", default="/dev/ttyACM0")
a = ap.parse_args()

s = serial.Serial(a.port, 460800, timeout=0.2)
s.reset_input_buffer()
print("Premi RESET sulla scheda ora (hai 15 s)...")
buf = b""
t = time.time() + 15
t_after = None
while time.time() < t:
    buf += s.read(256)
    i = buf.find(b"E3-DAQ")
    if i >= 0:
        if t_after is None:
            t_after = time.time() + 1.5          # keep reading a moment after the banner start
        rest = buf[i:]
        if b"STREAM" in rest or b"FATAL" in rest or time.time() > t_after:
            break
i = buf.find(b"E3-DAQ")
if i >= 0:
    print(buf[i:i + 260].decode("ascii", "replace"))
elif buf:
    print("RESET non visto: nessun banner E3-DAQ. Ricevuti %d byte; inizio: %r" % (len(buf), buf[:80]))
else:
    print("nessun byte ricevuto in 15 s")