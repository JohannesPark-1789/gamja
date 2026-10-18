"""악보(MusicXML) 를 원래 음높이·음 길이 그대로 합성해 WAV 로 만든다. 악보 데이터 검증용.

오르골 미리듣기(--preview)는 이조·옥타브 접기 뒤의 '구멍' 소리이고, 이것은 악보 자체의 소리다.
  - 전체: 파트마다 좌우로 벌려 오르간 비슷한 지속음으로.
  - --solo: 파트를 하나씩 차례로(사이에 1초 쉼) 이어 붙인 파일도 만든다.

예:  python tools/render_reference.py songs/abide-with-me/score.musicxml --out out/ref --solo
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SR = 44100


def _tone(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n) / SR
    env = np.minimum(1, t / 0.02) * np.minimum(1, (dur - t) / 0.06).clip(0, 1) * (0.85 + 0.15 * np.exp(-t * 3))
    s = (np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(4 * np.pi * freq * t)
         + 0.25 * np.sin(6 * np.pi * freq * t) + 0.12 * np.sin(8 * np.pi * freq * t))
    return s * env


def part_events(score_path: Path):
    """[(파트 이름, [(시작 4분음표, 길이 4분음표, midi)])], bpm"""
    from music21 import converter, tempo

    s = converter.parse(str(score_path))
    mms = list(s.recurse().getElementsByClass(tempo.MetronomeMark))
    bpm = float(mms[0].getQuarterBPM()) if mms else 80.0
    parts = []
    for i, p in enumerate(s.parts):
        evs = []
        for n in p.stripTies().flatten().notes:
            if n.duration.isGrace:
                continue
            for pitch in getattr(n, "pitches", (n.pitch,)):
                evs.append((float(n.offset), float(n.quarterLength), int(pitch.midi)))
        parts.append((p.partName or f"Part {i + 1}", evs))
    return parts, bpm


def render(parts, bpm: float, pans=None, tail: float = 1.0) -> np.ndarray:
    spb = 60.0 / bpm
    end = max((o + q for _, evs in parts for o, q, _ in evs), default=0.0)
    n = int((end * spb + tail) * SR)
    out = np.zeros((n, 2))
    k = len(parts)
    for i, (_, evs) in enumerate(parts):
        pan = pans[i] if pans else (0.5 if k == 1 else 0.15 + 0.7 * i / (k - 1))
        g = np.array([np.cos(pan * np.pi / 2), np.sin(pan * np.pi / 2)])
        for o, q, m in evs:
            st = int(o * spb * SR)
            s = _tone(440.0 * 2 ** ((m - 69) / 12), q * spb)
            e = min(n, st + len(s))
            out[st:e] += s[:e - st, None] * g
    return out


def write_wav(x: np.ndarray, path: Path) -> Path:
    x = x / max(1e-9, np.abs(x).max()) * 0.85
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="악보를 원래 음높이로 합성(검증용)")
    ap.add_argument("score")
    ap.add_argument("--out", required=True)
    ap.add_argument("--solo", action="store_true", help="파트를 하나씩 차례로 이어 붙인 파일도 만든다")
    ap.add_argument("--bpm", type=float, default=None)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    parts, bpm = part_events(Path(a.score))
    bpm = a.bpm or bpm
    print("parts:", ", ".join(f"{n}({len(e)})" for n, e in parts), f"| {bpm:.0f} bpm")
    write_wav(render(parts, bpm), out / "reference_all.wav")
    if a.solo:
        gap = np.zeros((SR, 2))
        chunks = []
        for name, evs in parts:
            chunks += [render([(name, evs)], bpm, pans=[0.5]), gap]
        write_wav(np.vstack(chunks), out / "reference_solo_parts.wav")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
