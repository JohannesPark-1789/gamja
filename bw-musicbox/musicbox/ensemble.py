"""합주: 배치된 음을 N 대의 오르골(박스)에 나눈다.

mode = "register": 같은 박에 울리는 음을 높은 순으로 정렬해 맨 위 음은 1번 박스(멜로디),
                   맨 아래부터 마지막 박스로 채우고 남는 음은 가운데 박스로.
                   SATB 4성부 + 3대 → 1: S, 2: A+T, 3: B.
mode = "parts"   : 악보 파트 번호로 묶는다. groups=[[0],[1],[2,3]] 처럼.

배정 뒤 같은 트랙 최소 간격을 어기는 음은 다른 박스로 옮겨 본다(호켓). 옮길 곳이 없으면 그대로 두고 보고.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .arrange import Placed, dedupe_unison
from .spec import StripSpec, STANDARD_30


@dataclass
class EnsembleResult:
    boxes: list[list[Placed]]
    moved: list[tuple[Placed, int, int]] = field(default_factory=list)      # (note, from, to)
    unresolved: list[tuple[int, Placed, Placed]] = field(default_factory=list)  # (box, prev, note)


def _split_register(notes_desc: list[Placed], n: int) -> list[list[Placed]]:
    out: list[list[Placed]] = [[] for _ in range(n)]
    if not notes_desc:
        return out
    out[0].append(notes_desc[0])
    rest = notes_desc[1:]
    if n == 1:
        out[0].extend(rest)
        return out
    # 아래쪽부터 마지막 박스에 하나씩, 남는 것은 가운데(2번)부터
    slots = n - 1
    k = len(rest)
    if k <= slots:
        # 낮은 음일수록 뒤 박스로
        for j, note in enumerate(reversed(rest)):
            out[n - 1 - j].append(note)
    else:
        base, extra = divmod(k, slots)
        sizes = [base + (1 if j < extra else 0) for j in range(slots)]  # 앞(2번 박스)부터 넉넉히
        i = 0
        for j, sz in enumerate(sizes):
            out[1 + j].extend(rest[i:i + sz])
            i += sz
    return out


def allocate(placed: list[Placed], n_boxes: int, spec: StripSpec = STANDARD_30, mode: str = "register",
             groups: list[list[int]] | None = None) -> EnsembleResult:
    if n_boxes < 1:
        raise ValueError("n_boxes must be >= 1")
    boxes: list[list[Placed]] = [[] for _ in range(n_boxes)]

    if mode == "parts":
        if not groups or len(groups) != n_boxes:
            raise ValueError("mode='parts' needs groups with one part list per box")
        lookup = {p: b for b, ps in enumerate(groups) for p in ps}
        for note in placed:
            boxes[lookup.get(note.part, n_boxes - 1)].append(note)
    elif mode == "register":
        by_onset: dict[float, list[Placed]] = {}
        for note in placed:
            by_onset.setdefault(round(note.beat, 6), []).append(note)
        for beat in sorted(by_onset):
            notes = sorted(by_onset[beat], key=lambda p: -p.track)
            for b, chunk in enumerate(_split_register(notes, n_boxes)):
                boxes[b].extend(chunk)
    else:
        raise ValueError(f"unknown mode {mode}")

    boxes = [dedupe_unison(b) for b in boxes]

    res = EnsembleResult(boxes)
    _repair_gaps(res, spec)
    return res


def _track_ok(box: list[Placed], note: Placed, min_gap_beats: float) -> bool:
    for q in box:
        if q.track == note.track and q is not note and abs(q.beat - note.beat) < min_gap_beats - 1e-9:
            return False
    return True


def _repair_gaps(res: EnsembleResult, spec: StripSpec) -> None:
    g = spec.min_same_track_gap / spec.beat_mm
    n = len(res.boxes)
    for b in range(n):
        box = res.boxes[b]
        by_track: dict[int, list[Placed]] = {}
        for p in box:
            by_track.setdefault(p.track, []).append(p)
        for track, ps in by_track.items():
            ps.sort(key=lambda p: p.beat)
            last = None
            for p in ps:
                if last is not None and p.beat - last.beat < g - 1e-9 and p in box:
                    # 가까운 박스부터 시도
                    order = sorted((j for j in range(n) if j != b), key=lambda j: abs(j - b))
                    for j in order:
                        if _track_ok(res.boxes[j], p, g):
                            box.remove(p)
                            res.boxes[j].append(p)
                            res.boxes[j].sort(key=lambda q: (q.beat, q.track))
                            res.moved.append((p, b, j))
                            break
                    else:
                        res.unresolved.append((b, last, p))
                        last = p
                    continue
                last = p
