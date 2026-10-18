"""배치된 음 → 세그먼트(Strip) 목록.

전역 좌표 T (mm, 곡 선단 기준): T = lead_in + beat * beat_mm
세그먼트는 박 경계에서 자르고, 절단선 앞뒤 joint_quiet 안에 구멍이 없는 자리를 고른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from .arrange import Placed
from .spec import StripSpec, STANDARD_30
from .strip import Strip


@dataclass
class Segment:
    index: int          # 1부터
    start: float        # 전역 T
    end: float
    strip: Strip
    forced_cut: bool = False   # 무음 구간을 못 지켜 강제로 자른 경우


@dataclass
class LayoutResult:
    segments: list[Segment]
    total_length: float
    warnings: list[str] = field(default_factory=list)


def _choose_cut(start: float, holes_T: list[float], spec: StripSpec, max_len: float) -> tuple[float, bool]:
    """start 이후 max_len 안에서 가장 뒤쪽의 '조용한' 박 경계를 고른다."""
    limit = start + max_len
    k_max = math.floor((limit - spec.lead_in) / spec.beat_mm + 1e-9)
    k_min = math.ceil((start + spec.beat_mm - spec.lead_in) / spec.beat_mm - 1e-9)
    q = spec.joint_quiet
    best_forced = None
    for k in range(k_max, k_min - 1, -1):
        Tc = spec.lead_in + k * spec.beat_mm
        if Tc <= start + 2 * q:
            break
        if all(abs(h - Tc) >= q - 1e-9 for h in holes_T):
            return Tc, False
        if best_forced is None:
            best_forced = Tc
    if best_forced is None:
        best_forced = start + max_len
    return best_forced, True


def holes_T_of(placed: list[Placed], spec: StripSpec, count_in_track: int | None = None) -> list[tuple[float, int]]:
    holes = sorted(((spec.lead_in + p.beat * spec.beat_mm, p.track) for p in placed))
    if count_in_track is not None:
        holes.insert(0, (spec.lead_in, count_in_track))
    return holes


def compute_bounds(holes_T: list[float], spec: StripSpec) -> tuple[list[float], list[bool], list[str]]:
    """전역 구멍 위치 목록 → 세그먼트 경계 [0, c1, c2, ..., total], 강제절단 플래그, 경고."""
    warnings: list[str] = []
    holes_T = sorted(holes_T)
    total = holes_T[-1] + spec.lead_out
    cuts: list[tuple[float, bool]] = []
    start = 0.0
    max_len = spec.max_segment_length
    while total - start > max_len + 1e-9:
        Tc, forced = _choose_cut(start, holes_T, spec, max_len)
        if forced:
            warnings.append(f"segment cut at {Tc:.1f} mm has holes inside the {spec.joint_quiet} mm quiet zone")
        cuts.append((Tc, forced))
        start = Tc
    bounds = [0.0] + [c[0] for c in cuts] + [total]
    forced_flags = [False] + [c[1] for c in cuts]
    return bounds, forced_flags, warnings


def layout(placed: list[Placed], spec: StripSpec = STANDARD_30, title: str = "",
           standalone_segments: bool = False, measure_starts: list[float] | None = None,
           barlines: bool = False, ruler: bool = False, count_in_track: int | None = None,
           bounds: list[float] | None = None, forced_flags: list[bool] | None = None,
           box_label: str = "") -> LayoutResult:
    """bounds 를 주면(합주) 그 경계를 그대로 쓴다. 모든 파트 스트립이 같은 자리에서 잘린다."""
    warnings: list[str] = []
    if not placed:
        raise ValueError("no notes to lay out")

    holes = holes_T_of(placed, spec, count_in_track)
    if bounds is None:
        bounds, forced_flags, warnings = compute_bounds([h[0] for h in holes], spec)
    total = bounds[-1]
    forced_flags = forced_flags or [False] * (len(bounds) - 1)

    segments: list[Segment] = []
    n = len(bounds) - 1
    for i in range(n):
        a, b = bounds[i], bounds[i + 1]
        pre = spec.lead_in if (standalone_segments and i > 0) else 0.0
        post = spec.lead_out if (standalone_segments and i < n - 1) else 0.0
        strip = Strip(length=round(b - a + pre + post, 3), spec=spec, title=title)
        for T, track in holes:
            if a - 1e-9 <= T < b - 1e-9 or (i == n - 1 and abs(T - b) < 1e-9):
                strip.add_hole(track, T - a + pre)
        _decorate(strip, spec, title, i + 1, n, a, b, pre, post, i == 0, i == n - 1,
                  measure_starts if barlines else None, ruler, box_label)
        segments.append(Segment(i + 1, a, b, strip, forced_flags[i] if i < len(forced_flags) else False))

    return LayoutResult(segments, total, warnings)


def _decorate(strip: Strip, spec: StripSpec, title: str, idx: int, n: int, a: float, b: float,
              pre: float, post: float, first: bool, last: bool,
              measure_starts: list[float] | None, ruler: bool, box_label: str = "") -> None:
    label_x = spec.width - 5.3
    seg_txt = f"{idx}/{n}" + (f" {box_label}" if box_label else "")
    # 선단 영역: 첫 세그먼트(또는 standalone)는 리드인 안에 제목
    if first or pre > 0:
        t = title[:40]
        h = min(3.0, (spec.width - 10.0) / (0.62 * max(1, len(t))))   # 폭에 맞춰 글자 크기 자동
        strip.add_text(spec.width / 2, 6.0, t, height=round(h, 2), align="center")
        strip.add_text(spec.width / 2, 11.5, f"seg {seg_txt}", height=2.2, align="center")
        strip.add_direction_arrow(t=14.0)
    else:
        strip.add_direction_arrow(t=22.0)
        strip.add_text(label_x, 26.0, f"{title[:12]} {seg_txt}", height=1.8, rotation=-90)

    # 이음 정합 표시: 절단선에서 3 mm 안쪽, 양 여백에 짧은 선 + 이음 번호
    if not first and pre == 0:
        for x0, d in ((0.0, 1), (spec.width, -1)):
            strip.add_line(x0, 3.0, x0 + d * 4.0, 3.0)
        strip.add_text(label_x, 4.0, f"J{idx - 1}{box_label}", height=1.6, rotation=-90)
    if not last and post == 0:
        L = strip.length
        for x0, d in ((0.0, 1), (spec.width, -1)):
            strip.add_line(x0, L - 3.0, x0 + d * 4.0, L - 3.0)
        strip.add_text(label_x, L - 9.0, f"J{idx}{box_label}", height=1.6, rotation=-90)

    if measure_starts:
        x1 = spec.first_track_x - 1.0
        x2 = spec.last_track_x + 1.0
        for mb in measure_starts:
            T = spec.lead_in + mb * spec.beat_mm
            if a <= T < b:
                strip.add_line(x1, T - a + pre, x2, T - a + pre)
    if ruler:
        strip.add_margin_ruler(every=8.0, label_every=40.0, side="left")
