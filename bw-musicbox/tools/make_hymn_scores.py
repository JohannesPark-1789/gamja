"""찬송가 4성부 데이터(텍스트) → MusicXML (파트 4개: S, A, T, B).

데이터 출처: Hymnary.org 에 올라온 EVENTIDE(W. H. Monk, 1861) MusicXML 의 음표를 성부별로 옮긴 것.
선율·화성 모두 1861년 작품으로 저작권 만료. 가사는 포함하지 않는다.

실행: python tools/make_hymn_scores.py
"""

import re
from pathlib import Path

from music21 import chord, key, metadata, meter, note, stream, tempo

ROOT = Path(__file__).resolve().parents[1] / "songs"
DUR = {"w": 4.0, "h": 2.0, "q": 1.0, "e": 0.5}
VOICE_NAMES = {"P1v1": "Soprano", "P1v2": "Alto", "P2v1": "Tenor", "P2v2": "Bass"}


def parse_voices(text: str) -> dict[str, list[list[tuple[str, float]]]]:
    """{voice: [measure -> [(pitch, quarterLength), ...]]}"""
    voices: dict[str, list[list[tuple[str, float]]]] = {v: [] for v in VOICE_NAMES}
    for line in text.strip().splitlines():
        m = re.match(r"m(\d+)\s+(.*)", line.strip())
        if not m:
            continue
        for chunk in m.group(2).split("|"):
            name, notes = chunk.split(":")
            bar = []
            for n in notes.split(","):
                n = n.strip()
                if not n:
                    continue
                p, d = n.rsplit(" ", 1)
                ql = DUR[d.rstrip(".")] * (1.5 if d.endswith(".") else 1.0)
                bar.append((p.strip(), ql))
            voices[name.strip()].append(bar)
    return voices


def build_score(voices, title, composer, key_sig, bpm) -> stream.Score:
    sc = stream.Score()
    sc.insert(0, metadata.Metadata())
    sc.metadata.title = title
    sc.metadata.composer = composer
    for vid, pname in VOICE_NAMES.items():
        part = stream.Part(id=pname)
        part.partName = pname
        for mi, bar in enumerate(voices[vid]):
            meas = stream.Measure(number=mi + 1)
            if mi == 0:
                meas.append(key.Key(key_sig))
                meas.append(meter.TimeSignature("4/4"))
                meas.insert(0, tempo.MetronomeMark(number=bpm))
            for p, ql in bar:
                pitches = p.strip("[]").split()
                if len(pitches) > 1:
                    el = chord.Chord([x.replace("b", "-") for x in pitches])
                else:
                    el = note.Note(p.replace("b", "-") if len(p) > 1 and p[1] == "b" else p)
                el.quarterLength = ql
                meas.append(el)
            part.append(meas)
        sc.insert(0, part)
    return sc


def main() -> None:
    text = (Path(__file__).parent / "eventide_satb.txt").read_text(encoding="utf-8")
    voices = parse_voices(text)
    sc = build_score(voices, "Abide with Me (EVENTIDE)", "William Henry Monk, 1861", "E-", 72)
    out = ROOT / "abide-with-me" / "score.musicxml"
    out.parent.mkdir(parents=True, exist_ok=True)
    sc.write("musicxml", fp=str(out))
    print("wrote", out)


if __name__ == "__main__":
    main()
