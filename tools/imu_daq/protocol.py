"""Binary frame format of the firmware (see docs/protocol.md and firmware/include/protocol.hpp).

    offset size field
       0    2   sync   0xA5 0x5A
       2    4   seq    sample counter (increments on every timer tick)
       6    4   t_tick DWT cycle counter at timer-interrupt entry
      10    4   t_done DWT cycle counter when the I2C DMA finished
      14    2   dropped cumulative lost samples (mod 65536)
      16   14   raw    MPU6050 regs 0x3B..0x48, big-endian: ax ay az temp gx gy gz
      30    2   crc16  CRC-16/CCITT-FALSE over bytes 2..29
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

FRAME_SIZE = 32
SYNC = b"\xA5\x5A"
PAYLOAD_SIZE = 14
CRC_COVER = slice(2, 30)  # bytes covered by the CRC


# --------------------------------------------------------------------------- CRC
def _make_table() -> np.ndarray:
    table = np.zeros(256, dtype=np.uint16)
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        table[i] = crc
    return table


_CRC_TABLE = _make_table()


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection, no final XOR)."""
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ int(_CRC_TABLE[(crc >> 8) ^ b])
    return crc


def crc16_rows(rows: np.ndarray) -> np.ndarray:
    """Vectorised CRC over each row of an (N, L) uint8 array."""
    crc = np.full(rows.shape[0], 0xFFFF, dtype=np.uint16)
    for col in range(rows.shape[1]):
        idx = (crc >> 8) ^ rows[:, col].astype(np.uint16)
        crc = ((crc << 8) & 0xFFFF).astype(np.uint16) ^ _CRC_TABLE[idx]
    return crc


# ------------------------------------------------------------------ pack / parse
@dataclass
class Sample:
    seq: int
    t_tick: int
    t_done: int
    dropped: int
    raw: bytes  # 14 bytes

    def pack(self) -> bytes:
        """Reference serialiser (used by the simulator and the tests)."""
        if len(self.raw) != PAYLOAD_SIZE:
            raise ValueError("raw payload must be 14 bytes")
        body = struct.pack("<IIIH", self.seq, self.t_tick, self.t_done, self.dropped) + self.raw
        return SYNC + body + struct.pack("<H", crc16(body))


@dataclass
class ParsedLog:
    seq: np.ndarray       # uint32
    t_tick: np.ndarray    # uint32 (DWT cycles, wraps every 2^32 / f_cpu seconds)
    t_done: np.ndarray    # uint32
    dropped: np.ndarray   # uint16
    raw: np.ndarray       # (N, 14) uint8
    n_bad_crc: int        # sync found but CRC wrong (corrupted frames)
    n_garbage_bytes: int  # bytes that did not belong to any valid frame (banner, noise, lost frames)

    def __len__(self) -> int:
        return len(self.seq)

    def imu_counts(self) -> np.ndarray:
        """(N, 7) int16 array: ax ay az temp gx gy gz (raw sensor counts)."""
        hi = self.raw[:, 0::2].astype(np.uint16)
        lo = self.raw[:, 1::2].astype(np.uint16)
        return ((hi << 8) | lo).astype(np.int16)


def parse(data: bytes | np.ndarray) -> ParsedLog:
    """Finds and validates frames in a raw byte stream.

    Robust to a text banner at the start, truncated frames and byte corruption:
    candidates are located by the sync word and accepted only if the CRC matches.
    """
    buf = np.frombuffer(data, dtype=np.uint8) if isinstance(data, (bytes, bytearray)) else data
    n = len(buf)
    empty = ParsedLog(np.zeros(0, np.uint32), np.zeros(0, np.uint32), np.zeros(0, np.uint32),
                      np.zeros(0, np.uint16), np.zeros((0, PAYLOAD_SIZE), np.uint8), 0, n)
    if n < FRAME_SIZE:
        return empty

    cand = np.flatnonzero((buf[:-1] == SYNC[0]) & (buf[1:] == SYNC[1]))
    cand = cand[cand + FRAME_SIZE <= n]
    if cand.size == 0:
        return empty

    frames = buf[cand[:, None] + np.arange(FRAME_SIZE)[None, :]]  # (M, 32)
    stored = frames[:, 30].astype(np.uint16) | (frames[:, 31].astype(np.uint16) << 8)
    ok = crc16_rows(frames[:, CRC_COVER]) == stored

    # Drop candidates that overlap an already accepted frame (a sync word inside a payload).
    good_pos = cand[ok]
    keep = []
    last_end = -1
    for p in good_pos:
        if p >= last_end:
            keep.append(p)
            last_end = p + FRAME_SIZE
    good_pos = np.asarray(keep, dtype=np.int64)

    # A sync pattern that fails the CRC only counts as a corrupted frame when it does not
    # lie inside a frame we accepted (A5 5A can legitimately occur in a payload or timestamp).
    bad_pos = cand[~ok]
    if good_pos.size:
        j = np.searchsorted(good_pos, bad_pos, side="right") - 1
        inside = (j >= 0) & (bad_pos < good_pos[np.maximum(j, 0)] + FRAME_SIZE)
        bad_pos = bad_pos[~inside]
    n_bad = int(bad_pos.size)
    if good_pos.size == 0:
        empty.n_bad_crc = n_bad
        return empty

    fr = buf[good_pos[:, None] + np.arange(FRAME_SIZE)[None, :]]
    u32 = lambda a, b: (  # noqa: E731
        fr[:, a].astype(np.uint32) | (fr[:, a + 1].astype(np.uint32) << 8)
        | (fr[:, a + 2].astype(np.uint32) << 16) | (fr[:, b].astype(np.uint32) << 24))
    return ParsedLog(
        seq=u32(2, 5),
        t_tick=u32(6, 9),
        t_done=u32(10, 13),
        dropped=(fr[:, 14].astype(np.uint16) | (fr[:, 15].astype(np.uint16) << 8)),
        raw=fr[:, 16:30].copy(),
        n_bad_crc=n_bad,
        n_garbage_bytes=int(n - good_pos.size * FRAME_SIZE),
    )
