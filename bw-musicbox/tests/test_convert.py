"""실행: python tests/test_convert.py  (또는 pytest)"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from musicbox.arrange import arrange
from musicbox.layout import layout
from musicbox.score import NoteEvent, load_score
from musicbox.spec import STANDARD_30

ODE_BAR = "e4 e f g g f e d c c d e e4. d8 d2 "


def _events(midis, step=1.0):
    return [NoteEvent(i * step, m, 0, i // 4 + 1, str(m)) for i, m in enumerate(midis)]


def test_arrange_auto_transpose_prefers_octave():
    # C4 D4 E4 G3 : G3(55)는 트랙에 없음 → +12 또는 +7 이면 전부 수록. 동률이면 옥타브(+12) 우선
    r = arrange(_events([60, 62, 64, 55]))
    assert r.transpose == 12
    assert len(r.placed) == 4 and not r.dropped


def test_arrange_fold_drop_error():
    # C#4(61)는 아래 옥타브에 없음. +0 고정 시 fold 하면 C#2 트랙으로, drop 하면 탈락
    ev = _events([60, 61, 62])
    f = arrange(ev, transpose=0, out_of_range="fold")
    assert len(f.placed) == 3 and any(p.folded for p in f.placed)
    d = arrange(ev, transpose=0, out_of_range="drop")
    assert len(d.placed) == 2 and len(d.dropped) == 1
    try:
        arrange(ev, transpose=0, out_of_range="error")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_arrange_gap_detection_and_drop_close():
    # 같은 음을 0.5박(4 mm) 간격으로 → 위반 1건
    ev = [NoteEvent(0.0, 72, 0, 1, "C5"), NoteEvent(0.5, 72, 0, 1, "C5"), NoteEvent(2.0, 72, 0, 1, "C5")]
    r = arrange(ev, transpose=0)
    assert len(r.gap_violations) == 1 and len(r.placed) == 3
    r2 = arrange(ev, transpose=0, drop_close=True)
    assert len(r2.placed) == 2 and len(r2.removed_close) == 1


def test_layout_segments_cover_all_holes_and_respect_quiet_zone():
    spec = STANDARD_30
    # 4분음표 연속 600개 → 약 4.8 m → 여러 세그먼트
    ev = [NoteEvent(float(i), 72 + (i % 5), 0, i // 4 + 1, "") for i in range(600)]
    r = arrange(ev, transpose=0)
    lay = layout(r.placed, spec, title="T")
    assert len(lay.segments) >= 10
    assert sum(len(s.strip.holes) for s in lay.segments) == len(r.placed)
    for s in lay.segments:
        assert s.strip.length <= spec.max_segment_length + 1e-6
        for h in s.strip.holes:
            assert 0 <= h.t <= s.strip.length
        # 박 경계에서 잘렸는지
        if s.index > 1:
            k = (s.start - spec.lead_in) / spec.beat_mm
            assert abs(k - round(k)) < 1e-6
        if not s.forced_cut and s.index > 1:
            assert all(h.t >= spec.joint_quiet - 1e-9 for h in s.strip.holes)
    # 연속 4분음표는 모든 박 경계 ±4 mm 에 구멍이 있으므로 조용한 자리가 없어 강제 절단이 나와야 한다
    assert any(s.forced_cut for s in lay.segments[1:])


def test_layout_standalone_adds_leadin():
    ev = [NoteEvent(float(i) * 2, 72, 0, i + 1, "") for i in range(80)]  # 2박 간격 → 조용한 경계 많음
    r = arrange(ev, transpose=0)
    spec = STANDARD_30
    a = layout(r.placed, spec, title="T")
    b = layout(r.placed, spec, title="T", standalone_segments=True)
    assert len(a.segments) == len(b.segments) >= 2
    assert not any(s.forced_cut for s in a.segments)
    assert b.segments[1].strip.length == a.segments[1].strip.length + spec.lead_in + (spec.lead_out if len(a.segments) > 2 else 0)
    assert min(h.t for h in b.segments[1].strip.holes) >= spec.lead_in


def test_convert_end_to_end(tmp_path=None):
    from music21 import converter, metadata
    from musicbox.convert import convert
    tmp = Path(tmp_path or tempfile.mkdtemp())
    s = converter.parse("tinyNotation: 4/4 " + ODE_BAR * 6)
    s.insert(0, metadata.Metadata())
    s.metadata.title = "Ode Test"
    src = tmp / "ode.musicxml"
    s.write("musicxml", fp=str(src))

    r = convert(src, tmp / "out", svg=True, sheet=True, barlines=True)
    assert r["title"] == "Ode Test"
    assert r["placed"] == r["notes_in"] == 15 * 6
    assert r["transpose"] in (7, 12)
    assert len(r["segments"]) >= 2 and r["sheets"]
    assert all(Path(f).exists() for f in r["files"])
    assert (tmp / "out" / "report.txt").exists()
    # 세그먼트 길이 합 = 총 길이
    assert abs(sum(sg["length_mm"] for sg in r["segments"]) - r["total_length_mm"]) < 1e-6


def test_ensemble_register_split():
    from musicbox.ensemble import allocate
    # 4성부 화음(S A T B) 3개 → 3대: B1=S, B2=A+T, B3=B
    ev = []
    for i, (s_, a_, t_, b_) in enumerate([(84, 79, 76, 67), (83, 77, 72, 62), (81, 77, 74, 60)]):
        for m in (s_, a_, t_, b_):
            ev.append(NoteEvent(float(i), m, 0, 1, str(m)))
    r = arrange(ev, transpose=0)
    ens = allocate(r.placed, 3)
    assert [len(b) for b in ens.boxes] == [3, 6, 3]
    tops = sorted(p.track for p in ens.boxes[0])
    assert tops == sorted(max(p.track for p in r.placed if abs(p.beat - i) < 1e-9) for i in range(3))
    assert not ens.unresolved


def test_ensemble_hocket_moves_close_repeats():
    from musicbox.ensemble import allocate
    # 멜로디가 같은 음을 0.5박 간격으로 반복 → 1번 박스에서 못 넣는 뒤 음을 다른 박스로
    ev = [NoteEvent(0.0, 84, 0, 1, "C6"), NoteEvent(0.5, 84, 0, 1, "C6"), NoteEvent(0.0, 72, 0, 1, "C5")]
    r = arrange(ev, transpose=0)
    ens = allocate(r.placed, 2)
    assert len(ens.moved) == 1 and not ens.unresolved
    assert sum(len(b) for b in ens.boxes) == 3


def test_convert_ensemble_shared_cuts(tmp_path=None):
    from music21 import converter, metadata
    from musicbox.convert import convert
    tmp = Path(tmp_path or tempfile.mkdtemp())
    root = Path(__file__).resolve().parents[1] / "songs"
    r = convert(root / "abide-with-me" / "score.musicxml", tmp / "out", boxes=3, sheet=True)
    assert len(r["boxes"]) == 3
    segs = [len(b["holes_per_segment"]) for b in r["boxes"]]
    assert len(set(segs)) == 1                       # 모든 박스가 같은 세그먼트 수
    assert sum(b["notes"] for b in r["boxes"]) == r["placed"]
    assert all(Path(f).exists() for f in r["files"])
    assert (tmp / "out" / "box3" / "seg01.dxf").exists()


def test_preview_midi_and_wav(tmp_path=None):
    import wave
    from musicbox.convert import convert
    tmp = Path(tmp_path or tempfile.mkdtemp())
    root = Path(__file__).resolve().parents[1] / "songs"
    r = convert(root / "ode-to-joy" / "melody.musicxml", tmp / "out", preview=True)
    mid, wav = (Path(f) for f in r["preview"])
    data = mid.read_bytes()
    assert data[:4] == b"MThd" and data.count(b"MTrk") == 2          # 템포 트랙 + 박스 1
    # note-on(0x90, velocity 90) 개수 = 배치된 음 수
    assert data.count(bytes([90])) >= r["placed"]
    with wave.open(str(wav)) as w:
        secs = w.getnframes() / w.getframerate()
    assert w.getnchannels() == 2 and secs > r["est_duration_s_at_bpm"]["seconds"] * 0.9


def test_load_sample_scores():
    root = Path(__file__).resolve().parents[1] / "songs"
    sd = load_score(root / "ode-to-joy" / "melody.musicxml")
    assert sd.title == "Ode to Joy" and sd.tempo_bpm == 100 and len(sd.events) == 62
    assert sd.measure_starts and sd.measure_starts[0] == 0.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
