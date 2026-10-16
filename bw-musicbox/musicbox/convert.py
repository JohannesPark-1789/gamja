"""악보 → 세그먼트 DXF + 시트 DXF + 보고서.

사용:
  python -m musicbox.convert songs/ode-to-joy/melody.musicxml --out out/ode --svg --sheet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .arrange import arrange
from .layout import layout
from .score import load_score
from .spec import StripSpec, STANDARD_30
from .strip import Sheet, strip_svg, write_sheet_dxf, write_strip_dxf


def convert(path: str | Path, out_dir: str | Path, spec: StripSpec = STANDARD_30,
            transpose: int | None = None, out_of_range: str = "fold", drop_close: bool = False,
            part: int | None = None, title: str | None = None, standalone_segments: bool = False,
            barlines: bool = False, ruler: bool = False, svg: bool = False, sheet: bool = False,
            bridges: int = 4, base_midi: int = 60, count_in: bool = False) -> dict:
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
    lay = layout(ar.placed, spec, title, standalone_segments, sd.measure_starts, barlines, ruler,
                 count_in_track=spec.track_of("C2") if count_in else None)

    files = []
    for seg in lay.segments:
        p = out_dir / f"seg{seg.index:02d}.dxf"
        write_strip_dxf(seg.strip, p)
        files.append(str(p))
        if svg:
            p.with_suffix(".svg").write_text(strip_svg(seg.strip), encoding="utf-8")

    sheets = []
    if sheet:
        pending = [s.strip for s in lay.segments]
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
        "files": files,
        "sheets": sheets,
        "warnings": sd.warnings + lay.warnings,
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
    if r["sheets"]:
        L.append("sheets: " + ", ".join(f"{s['file']} ({s['segments']} seg)" for s in r["sheets"]))
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
    a = ap.parse_args(argv)
    r = convert(a.score, a.out, STANDARD_30, a.transpose, a.out_of_range, a.drop_close, a.part, a.title,
                a.standalone_segments, a.barlines, a.ruler, a.svg, a.sheet, a.bridges, a.base_midi, a.count_in)
    print(format_report(r, STANDARD_30), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
