"""악보 파일 → 노트 이벤트 목록.

music21로 MusicXML(.musicxml/.mxl), MIDI, ABC, kern 을 읽는다. 오르골에는 음의 시작(onset)만 의미가
있으므로 이벤트는 (박 위치, MIDI 음높이, 파트, 마디) 만 가진다.
  - 도돌이표·D.C. 는 펼친다(실패하면 펼치지 않고 경고).
  - 꾸밈음(grace)은 버린다.
  - 타이로 이어진 음은 첫 음만 남긴다.
  - 화음은 음마다 이벤트 하나.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class NoteEvent:
    beat: float        # 곡 시작부터의 4분음표 단위 위치
    midi: int
    part: int = 0
    measure: int | None = None
    name: str = ""     # 원래 음이름 (보고서용)


@dataclass
class ScoreData:
    title: str
    events: list[NoteEvent]
    n_parts: int
    warnings: list[str]
    tempo_bpm: float | None = None
    end_beat: float = 0.0       # 마지막 음의 끝(길이 포함)
    measure_starts: list[float] | None = None  # 마디 시작 박 (마디선 각인용)


def load_score(path: str | Path, expand_repeats: bool = True) -> ScoreData:
    from music21 import converter, note, chord, stream, tempo

    path = Path(path)
    s = converter.parse(str(path))
    warnings: list[str] = []

    if expand_repeats:
        try:
            s = s.expandRepeats()
        except Exception as e:  # 도돌이가 비정형이면 그대로 진행
            warnings.append(f"repeat expansion failed, using written order: {e}")

    title = ""
    if s.metadata is not None:
        title = str(s.metadata.bestTitle or s.metadata.title or "")
    if not title:
        title = _title_from_meta(path) or (path.parent.name if path.stem.lower() == "melody" else path.stem)

    parts = list(s.parts) if isinstance(s, stream.Score) and len(s.parts) else [s]
    events: list[NoteEvent] = []
    end_beat = 0.0
    for pi, part in enumerate(parts):
        flat = part.flatten()
        for n in flat.notes:
            if n.duration.isGrace:
                continue
            if n.tie is not None and n.tie.type in ("continue", "stop"):
                continue
            off = float(Fraction(n.offset).limit_denominator(96))
            end_beat = max(end_beat, off + float(n.duration.quarterLength))
            meas = getattr(n, "measureNumber", None)
            if isinstance(n, chord.Chord):
                pitches = n.pitches
            else:
                pitches = (n.pitch,)
            for p in pitches:
                events.append(NoteEvent(off, int(p.midi), pi, meas, p.nameWithOctave))

    events.sort(key=lambda e: (e.beat, e.part, e.midi))

    bpm = None
    try:
        mms = list(s.recurse().getElementsByClass(tempo.MetronomeMark))
        if mms:
            bpm = float(mms[0].getQuarterBPM())
    except Exception:
        pass

    measure_starts = None
    try:
        p0 = parts[0]
        ms = p0.getElementsByClass(stream.Measure)
        if ms:
            measure_starts = sorted({float(m.offset) for m in ms})
    except Exception:
        pass

    return ScoreData(title, events, len(parts), warnings, bpm, end_beat, measure_starts)


def _title_from_meta(path: Path) -> str:
    """같은 폴더의 meta.yaml 에서 title: 한 줄을 읽는다 (yaml 라이브러리 없이)."""
    meta = path.parent / "meta.yaml"
    if not meta.exists():
        return ""
    for line in meta.read_text(encoding="utf-8").splitlines():
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""
