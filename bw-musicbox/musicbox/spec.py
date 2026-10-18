"""종이 악보 규격.

좌표계 (스트립 로컬):
  x : 트랙 방향, 0 = 종이 왼쪽 가장자리 (악보를 진행 방향이 위로 오게 놓았을 때 왼쪽), 단위 mm
  t : 진행 방향, 0 = 먼저 오르골에 들어가는 끝(선단), 단위 mm
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


# 30음 표준 배열. 왼쪽(트랙 0) → 오른쪽(트랙 29). 사진의 두 줄 표기를 교대로 합친 것.
NOTES_30: tuple[str, ...] = (
    "C", "D", "G", "A", "B", "C1", "D1", "E1", "F1", "F#1",
    "G1", "G#1", "A1", "A#1", "B1", "C2", "C#2", "D2", "D#2", "E2",
    "F2", "F#2", "G2", "G#2", "A2", "A#2", "B2", "C3", "D3", "E3",
)

_NAME_TO_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_name_to_midi(name: str, base_midi: int = 60) -> int:
    """'C' → base_midi, 'F#1' → base_midi+17 ... 악보 표기 'C'를 base_midi로 둔다."""
    letter = name[0]
    rest = name[1:]
    sharp = rest.startswith("#")
    if sharp:
        rest = rest[1:]
    octave = int(rest) if rest else 0
    return base_midi + 12 * octave + _NAME_TO_SEMITONE[letter] + (1 if sharp else 0)


@dataclass(frozen=True)
class StripSpec:
    """한 스트립의 기하 규격 (mm)."""

    name: str = "30-note-standard"
    width: float = 70.0            # 종이 폭
    track_pitch: float = 2.0       # 트랙 간격
    first_track_x: float = 6.0     # 왼쪽 가장자리 → 트랙 0 중심
    beat_mm: float = 8.0           # 1박(4분음표) 길이
    hole_diameter: float = 2.4     # 레이저 구멍 외경 (커프 포함 목표값)
    min_same_track_gap: float = 8.0  # 같은 트랙 연속 구멍 중심 간 최소 거리
    lead_in: float = 60.0          # 곡 첫 세그먼트 선단 여백
    lead_out: float = 25.0         # 곡 마지막 세그먼트 후단 여백
    joint_quiet: float = 4.0       # 이음부(절단선) 앞뒤 무음 구간
    max_segment_length: float = 455.0  # 467 용지 기준 세그먼트 최대 길이
    notes: Sequence[str] = field(default=NOTES_30)

    @property
    def n_tracks(self) -> int:
        return len(self.notes)

    @property
    def last_track_x(self) -> float:
        return self.first_track_x + self.track_pitch * (self.n_tracks - 1)

    @property
    def margin_right_x(self) -> float:
        """오른쪽 여백이 시작하는 x (마지막 트랙 중심 + 피치/2 보다 여유 있게 가장자리-여백폭)."""
        return self.width - self.first_track_x

    def track_x(self, track: int) -> float:
        if not 0 <= track < self.n_tracks:
            raise ValueError(f"track {track} out of range 0..{self.n_tracks - 1}")
        return self.first_track_x + self.track_pitch * track

    def track_of(self, note: str) -> int:
        try:
            return self.notes.index(note)
        except ValueError:
            raise KeyError(f"note {note!r} is not on this strip") from None

    def midi_table(self, base_midi: int = 60) -> dict[int, int]:
        """MIDI 번호 → 트랙 번호."""
        return {note_name_to_midi(n, base_midi): i for i, n in enumerate(self.notes)}


STANDARD_30 = StripSpec()
