"""4성부 데이터(텍스트) → MusicXML (파트 4개: S, A, T, B).

곡 목록(SONGS):
  abide-with-me  : EVENTIDE(W. H. Monk, 1861). Hymnary.org MusicXML 의 음표를 성부별로 옮긴 것. 저작권 만료.
  happy-birthday : 선율은 Hill 자매(PD, 미국 2016 판결). 4성부 화성은 이 프로젝트에서 새로 붙임(CC0).
가사는 포함하지 않는다.

데이터 형식: 한 줄에 한 마디. "m<번호> P1v1: 음 길이, ... | P1v2: ... | P2v1: ... | P2v2: ..."
  길이: w h q e s (온·2분·4분·8분·16분), 점은 뒤에 '.'.  m0 은 못갖춘마디.

실행: python tools/make_hymn_scores.py            # 전부
      python tools/make_hymn_scores.py happy-birthday
"""

import re
from pathlib import Path

from music21 import chord, key, metadata, meter, note, stream, tempo

ROOT = Path(__file__).resolve().parents[1] / "songs"
DUR = {"w": 4.0, "h": 2.0, "q": 1.0, "e": 0.5, "s": 0.25}
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


def build_score(voices, title, composer, key_sig, bpm, time_sig="4/4", pickup=False) -> stream.Score:
    sc = stream.Score()
    sc.insert(0, metadata.Metadata())
    sc.metadata.title = title
    sc.metadata.composer = composer
    for vid, pname in VOICE_NAMES.items():
        part = stream.Part(id=pname)
        part.partName = pname
        bar_ql = meter.TimeSignature(time_sig).barDuration.quarterLength
        for mi, bar in enumerate(voices[vid]):
            meas = stream.Measure(number=mi if pickup else mi + 1)
            if mi == 0:
                meas.append(key.Key(key_sig))
                meas.append(meter.TimeSignature(time_sig))
                meas.insert(0, tempo.MetronomeMark(number=bpm))
            filled = sum(ql for _, ql in bar)
            if pickup and mi == 0:
                meas.paddingLeft = bar_ql - filled          # 못갖춘마디
            elif mi == len(voices[vid]) - 1 and filled < bar_ql:
                meas.paddingRight = bar_ql - filled         # 못갖춘마디와 짝을 맞춘 끝마디
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


SONGS = {
    "abide-with-me": dict(data="eventide_satb.txt", title="Abide with Me (EVENTIDE)",
                          composer="William Henry Monk, 1861", key="E-", bpm=72),
    "happy-birthday": dict(data="happy_birthday_satb.txt", title="Happy Birthday to You (SATB)",
                           composer="Mildred J. Hill & Patty S. Hill (melody, PD); SATB arr. bw-musicbox (CC0)",
                           key="F", bpm=100, time="3/4", pickup=True),
}


def main(argv=None) -> None:
    import sys
    names = (argv if argv is not None else sys.argv[1:]) or list(SONGS)
    for slug in names:
        cfg = SONGS[slug]
        text = (Path(__file__).parent / cfg["data"]).read_text(encoding="utf-8")
        voices = parse_voices(text)
        sc = build_score(voices, cfg["title"], cfg["composer"], cfg["key"], cfg["bpm"],
                         cfg.get("time", "4/4"), cfg.get("pickup", False))
        out = ROOT / slug / "score.musicxml"
        out.parent.mkdir(parents=True, exist_ok=True)
        sc.write("musicxml", fp=str(out))
        print("wrote", out)


if __name__ == "__main__":
    main()
