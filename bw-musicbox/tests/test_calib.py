"""실행: python -m pytest  또는  python tests/test_calib.py"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from musicbox.calib import build_calibration_strip, DEFAULT_DIAMETERS, DEFAULT_GAPS, LEADIN_PROBES
from musicbox.spec import STANDARD_30, note_name_to_midi
from musicbox.strip import LAYER_HOLE, LAYER_OUTLINE, LAYER_ENGRAVE, Sheet, write_strip_dxf, write_sheet_dxf


def test_spec_geometry():
    s = STANDARD_30
    assert s.n_tracks == 30
    assert s.track_x(0) == 6.0
    assert s.track_x(29) == 64.0
    assert s.width - s.track_x(29) == s.track_x(0)      # 좌우 여백 대칭
    assert s.track_of("C") == 0 and s.track_of("E3") == 29
    assert note_name_to_midi("C") == 60 and note_name_to_midi("F#1") == 78 and note_name_to_midi("E3") == 100
    assert len(set(s.midi_table())) == 30


def test_calibration_strip_contents():
    st = build_calibration_strip()
    assert st.length <= STANDARD_30.max_segment_length
    n_expected = len(LEADIN_PROBES) + 30 + 3 * len(DEFAULT_DIAMETERS) + 3 * 2 * len(DEFAULT_GAPS)
    assert len(st.holes) == n_expected
    assert all(0 <= h.t <= st.length for h in st.holes)
    # 간격 위반은 C 구간에서 의도한 것만: 8 mm 미만 간격 4,5,6,7 × 3트랙
    v = st.same_track_gap_violations()
    assert len(v) == 3 * sum(1 for g in DEFAULT_GAPS if g < 8.0)


def test_dxf_roundtrip(tmp_path=None):
    import ezdxf
    tmp = Path(tmp_path or tempfile.mkdtemp())
    st = build_calibration_strip()
    p = write_strip_dxf(st, tmp / "calib.dxf")
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    circles = [e for e in msp.query("CIRCLE") if e.dxf.layer == LAYER_HOLE]
    assert len(circles) == len(st.holes)
    assert doc.header["$INSUNITS"] == 4
    outline = [e for e in msp.query("LINE") if e.dxf.layer == LAYER_OUTLINE]
    assert len(outline) == 4                       # 브릿지 없음 → 변 4개
    assert any(e.dxf.layer == LAYER_ENGRAVE for e in msp)
    # 모든 구멍이 외곽 안쪽, 트랙 영역 안에 있는지
    xs = [c.dxf.center.x for c in circles]
    assert min(xs) >= 6.0 - 1e-6 and max(xs) <= 64.0 + 1e-6


def test_sheet_layout(tmp_path=None):
    import ezdxf
    tmp = Path(tmp_path or tempfile.mkdtemp())
    st = build_calibration_strip()
    sheet = Sheet()
    left = sheet.place_columns([st] * 5)
    assert len(sheet.placements) == 4 and len(left) == 1   # 315 폭에 70 mm 4열
    xs = sorted(p.origin_x for p in sheet.placements)
    assert xs[0] == 5.0 and xs[-1] + 70 <= 315 - 5
    p = write_sheet_dxf(sheet, tmp / "sheet.dxf", bridges=4)
    doc = ezdxf.readfile(p)
    circles = doc.modelspace().query("CIRCLE")
    assert len(circles) == 4 * len(st.holes)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
