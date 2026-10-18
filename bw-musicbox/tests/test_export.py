"""레이저 내보내기(DXF 글자→선, SVG, PLT) 시험. 실행: python tests/test_export.py"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from musicbox.convert import convert  # noqa: E402


def test_laser_export_happy_birthday(tmp_path=None):
    import ezdxf
    tmp = Path(tmp_path or tempfile.mkdtemp())
    root = Path(__file__).resolve().parents[1] / "songs"
    r = convert(root / "happy-birthday" / "score.musicxml", tmp / "out", sheet=True, laser=True,
                boxes=4, box_mode="parts", box_parts=[[0], [1], [2], [3]])
    holes = sum(sum(b["holes_per_segment"]) for b in r["boxes"])
    sheet = r["sheets"][0]
    ldxf, svg, plt = (Path(p) for p in sheet["laser"])

    doc = ezdxf.readfile(ldxf)
    msp = doc.modelspace()
    assert len(msp.query("TEXT MTEXT")) == 0                       # 글자는 모두 선으로
    assert len(msp.query('*[layer=="SHEET"]')) == 0                # 용지 테두리는 자르지 않음
    assert len(msp.query('CIRCLE[layer=="CUT_HOLE"]')) == holes

    s = svg.read_text(encoding="utf-8")
    assert 'width="315.0mm"' in s and s.count("<circle") == holes
    assert s.index('id="CUT_HOLE"') < s.index('id="ENGRAVE"') < s.index('id="CUT_OUTLINE"')

    p = plt.read_text(encoding="ascii")
    assert p.index("SP1;") < p.index("SP2;") < p.index("SP3;")
    # 구멍 한 개의 지름 = 2.4 mm = 96 HPGL 단위
    first = p.split("SP1;")[1].split("SP2;")[0].split(";")
    pd = [int(v) for v in first[1].strip()[2:].split(",")]
    xs = pd[0::2]
    assert abs((max(xs) - min(xs)) - 96) <= 2


if __name__ == "__main__":
    test_laser_export_happy_birthday()
    print("ok test_laser_export_happy_birthday")
