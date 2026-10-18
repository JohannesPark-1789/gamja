"""오디오 추출의 음표 분할 로직 시험(합성 음높이 곡선, 무거운 의존성 불필요).

실행: python tests/test_audio.py
"""

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_to_musicxml import cells_to_notes, syllables_to_notes, write_musicxml  # noqa: E402


def _synth(seq, t0=0.5, P=0.5, dt=0.01, wobble=0.15):
    """seq: [(start_beat, len_beats, midi or None)] → frame_t, midi, gate, onset."""
    T = t0 + P * (max(s + l for s, l, _ in seq) + 2)
    ft = np.arange(0, T, dt)
    midi = np.full(len(ft), np.nan)
    onset = []
    rng = np.random.default_rng(0)
    for s, l, p in seq:
        a, b = t0 + s * P, t0 + (s + l) * P - 0.03
        sel = (ft >= a) & (ft < b)
        if p is not None:
            midi[sel] = p + rng.uniform(-wobble, wobble, sel.sum())
            onset.append(a + 0.01)
    gate = np.isfinite(midi)
    return ft, midi, gate, np.array(onset), t0, P


def test_basic_segmentation():
    seq = [(0, 1, 60), (1, 1, 62), (2, 2, 64), (5, 0.5, 65), (5.5, 0.5, 67), (6, 1, 65)]
    ft, midi, gate, onset, t0, P = _synth(seq)
    notes, sub = cells_to_notes(ft, midi, gate, onset, t0, P, sub=4)
    got = [(s / sub, L / sub, p) for s, L, p in notes]
    assert [p for _, _, p in got] == [60, 62, 64, 65, 67, 65], got
    assert got[2][0] == 2 and got[2][1] >= 2          # 시작 위치 유지, 레가토로 길이는 늘 수 있음


def test_repeated_note_split_by_onset():
    seq = [(0, 1, 62), (1, 1, 62), (2, 1, 62)]
    ft, midi, gate, onset, t0, P = _synth(seq)
    notes, _ = cells_to_notes(ft, midi, gate, onset, t0, P, sub=4)
    assert len(notes) == 3 and all(p == 62 for _, _, p in notes)


def test_octave_jump_corrected_and_blip_dropped():
    seq = [(0, 1, 60), (1, 1, 72 + 2), (2, 1, 64), (6, 0.25, 70)]
    ft, midi, gate, onset, t0, P = _synth(seq)
    notes, _ = cells_to_notes(ft, midi, gate, onset, t0, P, sub=4)
    ps = [p for _, _, p in notes]
    assert 62 in ps and 74 not in ps        # 옥타브 튐 → 62 로
    assert 70 not in ps                      # 고립된 16분음표 잡음 제거


def test_syllable_glide_absorbed():
    # D4 를 길게 부르다 Bb3 로 미끄러져 내려가는 꺾기: 중간의 C#4, C4 가 음표가 되면 안 된다
    t0, P, dt = 0.5, 0.6, 0.01
    ft = np.arange(0, 4.0, dt)
    midi = np.full(len(ft), np.nan)
    a1, a2 = t0, t0 + 1.0 * P           # D4 1박
    g1 = a2 + 0.10                        # 0.10 s 글리산도
    a3 = g1                               # Bb3 1박
    sel = (ft >= a1) & (ft < a2)
    midi[sel] = 62 + 0.2 * np.sin(2 * np.pi * 5.5 * ft[sel])      # 비브라토
    sel = (ft >= a2) & (ft < g1)
    midi[sel] = np.linspace(62, 58, sel.sum())
    sel = (ft >= a3) & (ft < a3 + P)
    midi[sel] = 58 + 0.1 * np.sin(2 * np.pi * 5 * ft[sel])
    gate = np.isfinite(midi)
    notes, sub = syllables_to_notes(ft, midi, gate, np.array([a1 + 0.01]), t0, P, key_name="B-")
    assert [p for _, _, p in notes] == [62, 58], notes
    assert notes[0][0] == 0


def test_write_musicxml_compact(tmp=None):
    from music21 import converter
    tmp = Path(tmp or tempfile.mkdtemp())
    # 2마디 음, 6마디 쉼, 1마디 음 (16분 칸 단위)
    notes = [[0, 16, 60], [16, 16, 62], [16 * 8, 16, 64]]
    full = write_musicxml(notes, 4, 0, tmp / "a.musicxml", "t", 96, "B-")
    comp = write_musicxml(notes, 4, 0, tmp / "b.musicxml", "t", 96, "B-", compact=True)
    assert full["bars"] == 9 and comp["bars"] == 4 and comp["removed_rest_bars"] == 5
    s = converter.parse(str(tmp / "b.musicxml"))
    assert len(s.parts[0].getElementsByClass("Measure")) == 4


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
