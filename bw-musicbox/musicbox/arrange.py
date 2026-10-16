"""이조 선택, 트랙 매핑, 간격 검사."""

from __future__ import annotations

from dataclasses import dataclass, field

from .score import NoteEvent
from .spec import StripSpec, STANDARD_30


@dataclass(frozen=True)
class Placed:
    beat: float
    track: int
    part: int
    measure: int | None
    name: str
    folded: int = 0     # 옥타브 접기 양(반음)


@dataclass
class TransposeCandidate:
    semitones: int
    direct: int     # 그대로 들어가는 음표 수
    folded: int     # 옥타브를 옮겨야 들어가는 수
    dropped: int    # 어떻게 해도 안 들어가는 수

    @property
    def score(self) -> tuple:
        # 수록 가능 수 → 그대로 들어가는 수 → 원조 유지(옥타브 배수) → 작은 이동량
        return (self.direct + self.folded, self.direct, self.semitones % 12 == 0, -abs(self.semitones))


@dataclass
class ArrangeResult:
    transpose: int
    placed: list[Placed]
    dropped: list[NoteEvent]
    candidates: list[TransposeCandidate]
    gap_violations: list[tuple[Placed, Placed]] = field(default_factory=list)
    removed_close: list[Placed] = field(default_factory=list)


def _classify(midi: int, table: dict[int, int]) -> tuple[int | None, int]:
    """(track, fold) — fold 는 적용한 옥타브 이동(반음). 못 넣으면 (None, 0)."""
    if midi in table:
        return table[midi], 0
    for shift in (12, -12, 24, -24, 36, -36):
        if midi + shift in table:
            return table[midi + shift], shift
    return None, 0


def evaluate_transposes(events: list[NoteEvent], spec: StripSpec, base_midi: int,
                        rng: range = range(-24, 25)) -> list[TransposeCandidate]:
    table = spec.midi_table(base_midi)
    out = []
    for semi in rng:
        d = f = x = 0
        for e in events:
            tr, fold = _classify(e.midi + semi, table)
            if tr is None:
                x += 1
            elif fold == 0:
                d += 1
            else:
                f += 1
        out.append(TransposeCandidate(semi, d, f, x))
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def arrange(events: list[NoteEvent], spec: StripSpec = STANDARD_30, transpose: int | None = None,
            out_of_range: str = "fold", base_midi: int = 60, drop_close: bool = False) -> ArrangeResult:
    """events 를 트랙에 배치한다.

    transpose   : None 이면 자동 선택.
    out_of_range: 'fold'(옥타브 이동) | 'drop' | 'error'
    drop_close  : 같은 트랙 최소 간격 안의 뒤 음을 버린다(기본은 보고만).
    """
    cands = evaluate_transposes(events, spec, base_midi)
    semi = cands[0].semitones if transpose is None else transpose
    table = spec.midi_table(base_midi)

    placed: list[Placed] = []
    dropped: list[NoteEvent] = []
    for e in events:
        tr, fold = _classify(e.midi + semi, table)
        if tr is None or (fold != 0 and out_of_range == "drop"):
            dropped.append(e)
            continue
        if fold != 0 and out_of_range == "error":
            raise ValueError(f"note {e.name} (m.{e.measure}) out of range after transpose {semi:+d}")
        placed.append(Placed(e.beat, tr, e.part, e.measure, e.name, fold))

    # 같은 시각·같은 트랙 중복(유니즌) 제거
    seen = set()
    uniq = []
    for p in placed:
        key = (round(p.beat, 6), p.track)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    placed = uniq

    # 같은 트랙 최소 간격 검사
    min_gap_beats = spec.min_same_track_gap / spec.beat_mm
    by_track: dict[int, list[Placed]] = {}
    for p in placed:
        by_track.setdefault(p.track, []).append(p)
    violations = []
    removed = []
    keep = set(id(p) for p in placed)
    for track, ps in by_track.items():
        ps.sort(key=lambda p: p.beat)
        last = None
        for p in ps:
            if last is not None and p.beat - last.beat < min_gap_beats - 1e-9:
                violations.append((last, p))
                if drop_close:
                    keep.discard(id(p))
                    removed.append(p)
                    continue  # last 유지
            last = p
    if drop_close:
        placed = [p for p in placed if id(p) in keep]

    return ArrangeResult(semi, placed, dropped, cands, violations, removed)
