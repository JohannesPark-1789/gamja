"""악보 → 세그먼트 DXF + 시트 DXF + 보고서.

사용:
  python -m musicbox.convert songs/ode-to-joy/melody.musicxml --out out/ode --svg --sheet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .arrange import arrange
from .ensemble import allocate
from .layout import compute_bounds, holes_T_of, layout
from .score import load_score
from .spec import StripSpec, STANDARD_30
from .strip import Sheet, strip_svg, write_sheet_dxf, write_strip_dxf


def convert(path: str | Path, out_dir: str | Path, spec: StripSpec = STANDARD_30,
            transpose: int | None = None, out_of_range: str = "fold", drop_close: bool = False,
            part: int | None = None, title: str | None = None, standalone_segments: bool = False,
            barlines: bool = False, ruler: bool = False, svg: bool = False, sheet: bool = False,
            bridges: int = 4, base_midi: int = 60, count_in: bool = False,
            boxes: int = 1, box_mode: str = "register", box_parts: list[list[int]] | None = None,
            preview: bool = False) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sd = load_score(path)
    events = sd.events if part is None else [e for e in sd.events if e.part == part]
    if not events:
        raise SystemExit("no notes found")
    title = title or sd.title

    ar = arrange(events, spec, transpose, out_of_range, base_midi, drop_close)
    if not ar.placed:
        raise SystemExit("no playable notes after arrangement")
    count_track = spec.track_of("C2") if count_in else None

    ens = None
    box_lists = [ar.placed]
    if boxes > 1:
        ens = allocate(ar.placed, boxes, spec, box_mode, box_parts)
        box_lists = ens.boxes
        if any(not b for b in box_lists):
            raise SystemExit("a box received no notes; use fewer boxes or mode=parts with explicit groups")

    # 모든 박스가 같은 자리에서 잘리도록 전체 구멍으로 경계를 정한다
    all_T = [h[0] for h in holes_T_of(ar.placed, spec, count_track)]
    bounds, forced, lay_warnings = compute_bounds(all_T, spec)

    layouts = []
    files = []
    all_strips = []
    for bi, bl in enumerate(box_lists):
        label = f"B{bi + 1}" if boxes > 1 else ""
        lay = layout(bl, spec, title, standalone_segments, sd.measure_starts, barlines, ruler,
                     count_in_track=count_track, bounds=bounds, forced_flags=forced, box_label=label)
        layouts.append(lay)
        sub = out_dir / f"box{bi + 1}" if boxes > 1 else out_dir
        sub.mkdir(parents=True, exist_ok=True)
        for seg in lay.segments:
            p = sub / f"seg{seg.index:02d}.dxf"
            write_strip_dxf(seg.strip, p)
            files.append(str(p))
            all_strips.append(seg.strip)
            if svg:
                p.with_suffix(".svg").write_text(strip_svg(seg.strip), encoding="utf-8")
    lay = layouts[0]

    sheets = []
    if sheet:
        pending = list(all_strips)
        k = 1
        while pending:
            sh = Sheet()
            left = sh.place_columns(pending)
            if len(left) == len(pending):
                raise SystemExit("a segment does not fit on the sheet")
            p = out_dir / f"sheet{k:02d}.dxf"
            write_sheet_dxf(sh, p, bridges=bridges)
            sheets.append({"file": str(p), "segments": len(sh.placements)})
            pending = left
            k += 1

    bpm = sd.tempo_bpm or 80.0
    previews = []
    if preview:
        from .preview import render_wav, write_midi
        previews.append(str(write_midi(box_lists, spec, bpm, out_dir / "preview.mid", base_midi)))
        previews.append(str(render_wav(box_lists, spec, bpm, out_dir / "preview.wav", base_midi)))
    music_mm = lay.total_length - spec.lead_in - spec.lead_out
    report = {
        "title": title,
        "source": str(path),
        "parts_in_score": sd.n_parts,
        "notes_in": len(events),
        "transpose": ar.transpose,
        "transpose_candidates": [
            {"semitones": c.semitones, "direct": c.direct, "folded": c.folded, "dropped": c.dropped}
            for c in ar.candidates[:6]
        ],
        "placed": len(ar.placed),
        "folded": sum(1 for p in ar.placed if p.folded),
        "dropped": [{"measure": e.measure, "note": e.name, "beat": e.beat} for e in ar.dropped],
        "gap_violations": [
            {"track": a.track, "note": spec.notes[a.track], "orig": b.name, "measure": b.measure,
             "beat": b.beat, "gap_mm": round((b.beat - a.beat) * spec.beat_mm, 2)}
            for a, b in ar.gap_violations
        ],
        "removed_close": len(ar.removed_close),
        "total_length_mm": round(lay.total_length, 1),
        "music_length_mm": round(music_mm, 1),
        "est_duration_s_at_bpm": {"bpm": bpm, "seconds": round(music_mm / spec.beat_mm / bpm * 60, 1)},
        "segments": [
            {"index": s.index, "start_mm": round(s.start, 1), "end_mm": round(s.end, 1),
             "length_mm": s.strip.length, "holes": len(s.strip.holes), "forced_cut": s.forced_cut}
            for s in lay.segments
        ],
        "boxes": [
            {"box": i + 1, "notes": len(bl),
             "holes_per_segment": [len(sg.strip.holes) for sg in layouts[i].segments]}
            for i, bl in enumerate(box_lists)
        ],
        "ensemble": None if ens is None else {
            "mode": box_mode,
            "moved_for_spacing": [
                {"measure": p.measure, "note": p.name, "from": a + 1, "to": b + 1} for p, a, b in ens.moved
            ],
            "unresolved_spacing": [
                {"box": b + 1, "measure": p.measure, "note": p.name,
                 "gap_mm": round((p.beat - q.beat) * spec.beat_mm, 2)} for b, q, p in ens.unresolved
            ],
        },
        "files": files,
        "preview": previews,
        "sheets": sheets,
        "warnings": sd.warnings + lay_warnings,
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "report.txt").write_text(format_report(report, spec), encoding="utf-8")
    return report


def format_report(r: dict, spec: StripSpec) -> str:
    L = []
    L.append(f"{r['title']}  ({r['source']})")
    L.append(f"notes {r['notes_in']} → placed {r['placed']} (folded {r['folded']}), dropped {len(r['dropped'])}, "
             f"removed-close {r['removed_close']}")
    L.append(f"transpose {r['transpose']:+d} semitones; candidates: " +
             ", ".join(f"{c['semitones']:+d}:{c['direct']}/{c['folded']}/{c['dropped']}" for c in r['transpose_candidates'])
             + "  (direct/folded/dropped)")
    L.append(f"length {r['total_length_mm']} mm total, music {r['music_length_mm']} mm, "
             f"~{r['est_duration_s_at_bpm']['seconds']} s at {r['est_duration_s_at_bpm']['bpm']:.0f} bpm")
    L.append(f"segments {len(r['segments'])}: " +
             ", ".join(f"#{s['index']} {s['length_mm']} mm/{s['holes']} holes{' FORCED' if s['forced_cut'] else ''}"
                       for s in r['segments']))
    if r["gap_violations"]:
        L.append(f"same-track gaps < {spec.min_same_track_gap} mm: {len(r['gap_violations'])}")
        for g in r["gap_violations"][:30]:
            L.append(f"  m.{g['measure']} {g['orig']} (track {g['note']}) gap {g['gap_mm']} mm")
    if r["dropped"]:
        L.append("dropped notes:")
        for d in r["dropped"][:30]:
            L.append(f"  m.{d['measure']} {d['note']}")
    for w in r["warnings"]:
        L.append(f"warning: {w}")
    if len(r.get("boxes", [])) > 1:
        L.append("boxes: " + ", ".join(f"B{b['box']} {b['notes']} notes {b['holes_per_segment']}" for b in r["boxes"]))
        e = r["ensemble"]
        if e["moved_for_spacing"]:
            L.append(f"moved to another box for spacing: {len(e['moved_for_spacing'])}: " +
                     ", ".join(f"m.{m['measure']} {m['note']} B{m['from']}→B{m['to']}" for m in e["moved_for_spacing"][:20]))
        if e["unresolved_spacing"]:
            L.append(f"unresolved spacing in ensemble: {len(e['unresolved_spacing'])}: " +
                     ", ".join(f"B{u['box']} m.{u['measure']} {u['note']} {u['gap_mm']} mm" for u in e["unresolved_spacing"][:20]))
    if r["sheets"]:
        L.append("sheets: " + ", ".join(f"{s['file']} ({s['segments']} seg)" for s in r["sheets"]))
    if r.get("preview"):
        L.append("preview: " + ", ".join(r["preview"]))
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="악보(MusicXML/MIDI/ABC) → 30음 오르골 천공악보 DXF")
    ap.add_argument("score")
    ap.add_argument("--out", required=True, help="출력 폴더")
    ap.add_argument("--transpose", type=int, default=None, help="반음 단위 이조. 생략하면 자동")
    ap.add_argument("--out-of-range", choices=["fold", "drop", "error"], default="fold")
    ap.add_argument("--drop-close", action="store_true", help="같은 트랙 최소 간격 안의 뒤 음을 버림")
    ap.add_argument("--part", type=int, default=None, help="특정 파트만 (0부터). 생략하면 전 파트 합침")
    ap.add_argument("--title", default=None)
    ap.add_argument("--standalone-segments", action="store_true", help="세그먼트마다 리드인/리드아웃")
    ap.add_argument("--barlines", action="store_true", help="마디선 각인")
    ap.add_argument("--ruler", action="store_true", help="왼쪽 여백 눈금 각인")
    ap.add_argument("--count-in", action="store_true", help="리드인 끝(0박)에 C2 한 음을 넣음(합주 정렬 확인용)")
    ap.add_argument("--svg", action="store_true")
    ap.add_argument("--sheet", action="store_true", help="315x467 시트 DXF도 생성")
    ap.add_argument("--bridges", type=int, default=4)
    ap.add_argument("--base-midi", type=int, default=60, help="악보 표기 'C' 에 대응하는 MIDI 번호")
    ap.add_argument("--boxes", type=int, default=1, help="합주 오르골 대수")
    ap.add_argument("--box-mode", choices=["register", "parts"], default="register",
                    help="register: 음높이로 나눔(맨 위 음=1번). parts: --box-parts 로 파트 지정")
    ap.add_argument("--box-parts", default=None, help="예: '0;1;2,3' (박스별 파트 번호, 0부터)")
    ap.add_argument("--preview", action="store_true", help="preview.mid / preview.wav 미리듣기 생성")
    a = ap.parse_args(argv)
    groups = None
    if a.box_parts:
        groups = [[int(x) for x in g.split(",") if x.strip()] for g in a.box_parts.split(";")]
    r = convert(a.score, a.out, STANDARD_30, a.transpose, a.out_of_range, a.drop_close, a.part, a.title,
                a.standalone_segments, a.barlines, a.ruler, a.svg, a.sheet, a.bridges, a.base_midi, a.count_in,
                a.boxes, a.box_mode, groups, a.preview)
    print(format_report(r, STANDARD_30), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
