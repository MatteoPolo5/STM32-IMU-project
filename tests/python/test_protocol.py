from pathlib import Path

import numpy as np

from imu_daq import protocol as p

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "frame_vector.txt"


def load_golden():
    kv = {}
    for line in GOLDEN.read_text().splitlines():
        if line and not line.startswith("#"):
            k, v = line.split("=")
            kv[k] = v
    return kv


def make_sample(i: int) -> p.Sample:
    return p.Sample(seq=i, t_tick=(0xFFFFFF00 + i * 84000) & 0xFFFFFFFF, t_done=0, dropped=0,
                    raw=bytes((i * 7 + k) & 0xFF for k in range(14)))


def test_crc_check_value():
    assert p.crc16(b"123456789") == 0x29B1


def test_vectorised_crc_matches_scalar():
    rng = np.random.default_rng(1)
    rows = rng.integers(0, 256, (50, 28), dtype=np.uint8)
    for r, c in zip(rows, p.crc16_rows(rows)):
        assert p.crc16(bytes(r)) == int(c)


def test_golden_vector_matches_firmware_format():
    kv = load_golden()
    s = p.Sample(int(kv["seq"], 16), int(kv["t_tick"], 16), int(kv["t_done"], 16),
                 int(kv["dropped"], 16), bytes.fromhex(kv["raw"]))
    assert s.pack().hex().upper() == kv["frame"]


def test_parse_roundtrip_with_banner_and_garbage():
    frames = b"".join(make_sample(i).pack() for i in range(200))
    stream = b"\r\nE3-DAQ fw=test\r\nSTREAM\r\n" + frames[:96] + b"\x00\xA5\x5A\x01" + frames[96:]  # between frames 2 and 3
    log = p.parse(stream)
    assert len(log) == 200
    assert list(log.seq) == list(range(200))
    assert log.n_bad_crc == 1  # the injected fake sync word


def test_corrupted_frame_is_rejected_and_stream_resyncs():
    frames = bytearray(b"".join(make_sample(i).pack() for i in range(50)))
    frames[10 * 32 + 20] ^= 0xFF  # corrupt frame #10
    log = p.parse(bytes(frames))
    assert len(log) == 49
    assert 10 not in set(log.seq.tolist())
    assert log.n_bad_crc == 1


def test_truncated_final_frame_is_ignored():
    data = b"".join(make_sample(i).pack() for i in range(5))[:-7]
    assert len(p.parse(data)) == 4


def test_sync_word_inside_payload_is_not_a_frame():
    s = p.Sample(1, 2, 3, 0, bytes([0xA5, 0x5A] + [0] * 12))
    log = p.parse(s.pack() * 3)
    assert len(log) == 3 and log.n_bad_crc == 0


def test_imu_counts_are_signed_big_endian():
    raw = bytes([0xFF, 0xFE, 0x00, 0x10, 0x80, 0x00, 0, 0, 0, 0, 0, 0, 0x7F, 0xFF])
    log = p.parse(p.Sample(0, 0, 0, 0, raw).pack())
    assert log.imu_counts()[0].tolist() == [-2, 16, -32768, 0, 0, 0, 32767]


def test_empty_and_short_input():
    assert len(p.parse(b"")) == 0
    assert len(p.parse(b"\xA5\x5A")) == 0
