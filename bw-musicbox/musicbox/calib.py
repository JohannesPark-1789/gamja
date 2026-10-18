"""캘리브레이션 스트립 생성기.

한 장으로 네 가지를 실측한다.
  0. 리드인   : 선단 15/25/35/45/55 mm 에 C D G A B 를 하나씩. 처음 들리는 음의 위치가 최소 리드인.
  A. 트랙 정렬: 트랙 0→29 를 4 mm 간격으로 한 번씩(음계 훑기). 양끝 트랙이 제대로 나면 좌우 정렬이 맞는 것.
  B. 구멍 지름: 지름 후보를 한 줄씩, 저음·중음·고음 트랙에 동시에. 가장 또렷하고 걸리지 않는 값을 고른다.
  C. 동일 트랙 간격: 같은 트랙에 구멍 두 개를 g mm 떨어뜨려 둘 다 나는지 듣는다. 둘 다 나는 최소 g.

사용: python -m musicbox.calib --out out/calib.dxf --svg
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .spec import StripSpec, STANDARD_30
from .strip import Sheet, Strip, strip_svg, write_sheet_dxf, write_strip_dxf

DEFAULT_DIAMETERS = (2.0, 2.2, 2.4, 2.6, 2.8)
DEFAULT_GAPS = (4.0, 5.0, 6.0, 7.0, 8.0, 10.0)
LEADIN_PROBES = (15.0, 25.0, 35.0, 45.0, 55.0)   # 트랙 0..4 (C D G A B)


def build_calibration_strip(
    spec: StripSpec = STANDARD_30,
    diameters=DEFAULT_DIAMETERS,
    gaps=DEFAULT_GAPS,
    sweep_step: float = 4.0,
    row_step: float = 12.0,
    pair_rest: float = 16.0,
    lead_out: float = 20.0,
    dia_tracks=(1, 15, 27),
    gap_tracks=(2, 15, 24),
    title: str = "CAL 30",
) -> Strip:
    # 길이를 먼저 계산
    t = 70.0
    sweep_len = sweep_step * (spec.n_tracks - 1)
    t_sweep = t
    t = t_sweep + sweep_len + 14.0
    t_dia = t
    t = t_dia + row_step * (len(diameters) - 1) + 15.0
    t_gap = t
    gap_len = sum(gaps) + pair_rest * (len(gaps) - 1)
    t = t_gap + gap_len + lead_out
    length = round(t, 1)
    if length > spec.max_segment_length:
        raise ValueError(f"calibration strip {length} mm exceeds max {spec.max_segment_length} mm")

    s = Strip(length=length, spec=spec, title=title)
    label_x = spec.width - 5.3   # 오른쪽 여백 글자 기준선

    # 제목, 방향, 눈금
    s.add_text(spec.width / 2, 4.5, title, height=3.0, align="center")
    s.add_direction_arrow(t=10.0)
    s.add_margin_ruler(every=5.0, label_every=10.0, side="left")

    # 0. 리드인 프로브
    for track, tp in enumerate(LEADIN_PROBES):
        s.add_hole(track, tp)
        s.add_text(label_x, tp - 1.0, f"L{int(tp)}", height=1.6, rotation=-90)

    # A. 트랙 훑기
    s.add_text(label_x, t_sweep - 6.0, "A SWEEP", height=1.8, rotation=-90)
    for i in range(spec.n_tracks):
        s.add_hole(i, t_sweep + sweep_step * i)

    # B. 구멍 지름
    s.add_text(label_x, t_dia - 8.0, "B DIA", height=1.8, rotation=-90)
    for k, d in enumerate(diameters):
        tt = t_dia + row_step * k
        for tr in dia_tracks:
            s.add_hole(tr, tt, diameter=d)
        s.add_text(label_x, tt - 1.2, f"{d:.1f}", height=1.6, rotation=-90)
        s.add_line(spec.width - 1.0, tt, spec.width, tt)

    # C. 동일 트랙 간격
    s.add_text(label_x, t_gap - 8.0, "C GAP", height=1.8, rotation=-90)
    tt = t_gap
    for g in gaps:
        for tr in gap_tracks:
            s.add_hole(tr, tt)
            s.add_hole(tr, tt + g)
        s.add_text(label_x, tt - 1.2, f"g{g:g}", height=1.6, rotation=-90)
        s.add_line(spec.width - 1.0, tt, spec.width, tt)
        tt += g + pair_rest

    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="30음 오르골 캘리브레이션 스트립 DXF 생성")
    ap.add_argument("--out", default="out/calib.dxf", help="출력 DXF 경로")
    ap.add_argument("--svg", action="store_true", help="같은 이름의 .svg 미리보기도 저장")
    ap.add_argument("--diameters", type=float, nargs="+", default=list(DEFAULT_DIAMETERS))
    ap.add_argument("--gaps", type=float, nargs="+", default=list(DEFAULT_GAPS))
    ap.add_argument("--copies", type=int, default=1,
                    help="2 이상이면 315x467 시트에 복수 배치한 DXF를 만든다")
    ap.add_argument("--bridges", type=int, default=0, help="외곽선 긴 변당 브릿지 수(시트 배치 시 기본 4)")
    args = ap.parse_args(argv)

    strip = build_calibration_strip(diameters=args.diameters, gaps=args.gaps)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.copies > 1:
        sheet = Sheet()
        left = sheet.place_columns([strip] * args.copies)
        bridges = args.bridges or 4
        write_sheet_dxf(sheet, out, bridges=bridges)
        print(f"sheet {sheet.width}x{sheet.height}: placed {len(sheet.placements)}, leftover {len(left)}")
    else:
        write_strip_dxf(strip, out, bridges=args.bridges)

    if args.svg:
        out.with_suffix(".svg").write_text(strip_svg(strip), encoding="utf-8")

    print(f"strip length {strip.length} mm, holes {len(strip.holes)}, wrote {out}")
    v = strip.same_track_gap_violations()
    print(f"same-track gaps below {strip.spec.min_same_track_gap} mm (intended in section C): {len(v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
