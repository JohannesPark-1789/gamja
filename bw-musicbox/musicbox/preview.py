"""오르골 미리듣기: 박스별 배치 결과 → MIDI + 오르골 음색 합성 WAV.

실제로 뚫릴 구멍 그대로(이조·옥타브 접기·박스 배정 반영) 소리를 낸다.
  - MIDI: 박스마다 트랙 하나, GM 10번 Music Box 음색.
  - WAV : 빗살 소리를 흉내 낸 감쇠 사인파 합성. 박스 1은 왼쪽, 2는 오른쪽 등으로 벌려 둔다.
          같은 빗살을 최소 간격보다 빨리 다시 치면 둘째 음을 약하게 낸다(실제 오르골처럼).

의존성: numpy(music21 설치 시 함께 설치됨). MIDI·WAV 는 표준 라이브러리로 쓴다.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import numpy as np

from .arrange import Placed
from .spec import StripSpec

SR = 44100


def _comb_pitch(spec: StripSpec, base_midi: int) -> dict[int, int]:
    """트랙 번호 → 발음 MIDI 번호."""
    return {track: midi for midi, track in spec.midi_table(base_midi).items()}


# ---------------------------------------------------------------- MIDI
def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def write_midi(boxes: list[list[Placed]], spec: StripSpec, bpm: float, path: Path,
               base_midi: int = 60, program: int = 10, note_beats: float = 1.0) -> Path:
    """박스마다 트랙 하나인 SMF type 1. 음 길이는 note_beats 박(오르골은 길이가 없으므로 고정)."""
    tpq = 480
    pitch = _comb_pitch(spec, base_midi)
    tracks = []
    # 템포 트랙
    us = int(round(60_000_000 / bpm))
    t0 = b"\x00\xff\x51\x03" + us.to_bytes(3, "big") + b"\x00\xff\x58\x04\x04\x02\x18\x08" + b"\x00\xff\x2f\x00"
    tracks.append(t0)
    for bi, box in enumerate(boxes):
        ch = bi % 16 if bi < 9 else (bi + 1) % 16  # 채널 10(드럼) 회피
        evs = []
        hits = sorted(box, key=lambda q: q.beat)
        for i, p in enumerate(hits):
            on = int(round(p.beat * tpq))
            nxt = next((q.beat for q in hits[i + 1:] if q.track == p.track), None)
            length = note_beats if nxt is None else min(note_beats, nxt - p.beat)
            off = on + max(1, int(length * tpq) - 1)   # 같은 음 다음 타격 직전에 끝낸다
            evs.append((on, 1, bytes([0x90 | ch, pitch[p.track], 90])))
            evs.append((off, 0, bytes([0x80 | ch, pitch[p.track], 0])))
        evs.sort(key=lambda e: (e[0], e[1]))
        name = f"Box {bi + 1}".encode()
        data = b"\x00\xff\x03" + _vlq(len(name)) + name + b"\x00" + bytes([0xC0 | ch, program])
        last = 0
        for t, _, msg in evs:
            data += _vlq(t - last) + msg
            last = t
        data += b"\x00\xff\x2f\x00"
        tracks.append(data)
    out = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), tpq)
    for tr in tracks:
        out += b"MTrk" + struct.pack(">I", len(tr)) + tr
    path = Path(path)
    path.write_bytes(out)
    return path


# ---------------------------------------------------------------- 합성
def _tine(freq: float, dur: float, strength: float = 1.0) -> np.ndarray:
    """빗살 한 번 튕긴 소리. 낮은 음일수록 오래 울린다."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    decay = np.clip(2.6 - (freq - 260) / 900, 0.5, 2.6)  # 초
    env = np.exp(-t * (4.6 / decay))
    attack = np.minimum(1.0, t / 0.002)
    s = (np.sin(2 * np.pi * freq * t)
         + 0.25 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 6)
         + 0.12 * np.sin(2 * np.pi * 5.4 * freq * t) * np.exp(-t * 25)   # 금속성 비조화 배음
         + 0.06 * np.sin(2 * np.pi * 9.1 * freq * t) * np.exp(-t * 60))
    return s * env * attack * strength


def render_wav(boxes: list[list[Placed]], spec: StripSpec, bpm: float, path: Path,
               base_midi: int = 60, tail: float = 2.5) -> Path:
    pitch = _comb_pitch(spec, base_midi)
    sec_per_beat = 60.0 / bpm
    min_gap_beats = spec.min_same_track_gap / spec.beat_mm
    end_beat = max((p.beat for b in boxes for p in b), default=0.0)
    n = int((end_beat * sec_per_beat + tail) * SR)
    L = np.zeros(n)
    R = np.zeros(n)
    nb = len(boxes)
    for bi, box in enumerate(boxes):
        pan = 0.5 if nb == 1 else 0.2 + 0.6 * bi / (nb - 1)   # 0=왼쪽, 1=오른쪽
        gl, gr = np.cos(pan * np.pi / 2), np.sin(pan * np.pi / 2)
        last_hit: dict[int, float] = {}
        voice = np.zeros(n)
        hits = sorted(box, key=lambda p: p.beat)
        # 같은 빗살의 다음 타격 시각(앞 소리를 끊기 위해)
        next_same: dict[int, float] = {}
        for i, p in enumerate(hits):
            nxt = next((q.beat for q in hits[i + 1:] if q.track == p.track), None)
            next_same[i] = nxt
        for i, p in enumerate(hits):
            strength = 1.0
            prev = last_hit.get(p.track)
            if prev is not None and p.beat - prev < min_gap_beats - 1e-9:
                strength = 0.3 * (p.beat - prev) / min_gap_beats + 0.1  # 빗살이 덜 돌아와 약하게
            last_hit[p.track] = p.beat
            st = int(p.beat * sec_per_beat * SR)
            dur = tail
            if next_same[i] is not None:
                dur = min(dur, (next_same[i] - p.beat) * sec_per_beat + 0.01)
            s = _tine(440.0 * 2 ** ((pitch[p.track] - 69) / 12), dur, strength)
            if next_same[i] is not None and len(s) > 64:
                s[-64:] *= np.linspace(1, 0, 64)  # 다음 타격 직전 댐퍼
            e = min(n, st + len(s))
            voice[st:e] += s[:e - st]
        L += voice * gl
        R += voice * gr
    peak = max(1e-9, np.abs(L).max(), np.abs(R).max())
    stereo = (np.vstack([L, R]).T / peak * 0.85 * 32767).astype(np.int16)
    path = Path(path)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    return path
