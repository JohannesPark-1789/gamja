"""오디오(mp3/wav) → 보컬 멜로디 MusicXML.

처리 순서
  1. Demucs 로 보컬과 반주를 분리한다 (--stems 로 이미 분리된 폴더를 넘기면 건너뜀).
  2. 반주에서 박을 찾고, 등간격 격자(t0 + k·P)로 맞춘다. 저음 에너지가 큰 박을 마디 첫 박으로.
  3. 보컬에서 pYIN 으로 음높이를 추적하고, 곡 전체의 튜닝 오차를 보정한다.
  4. 16분음표 칸마다 대표 음높이를 정하고, 같은 음이 이어지면 합친다.
     보컬 onset 이 칸 시작에 있으면 같은 음이라도 새 음표로 끊는다(반복음 보존).
  5. 한 칸짜리 경과음(글리산도 잔재)은 이웃 음에 흡수한다.
  6. music21 로 4/4 MusicXML 을 쓴다. 앞뒤 무음은 마디 단위로 잘라낸다.
     --compact 를 주면 2마디 넘는 간주(쉼)를 1마디로 줄인 판도 쓴다(오르골 종이 절약).

필요 패키지(무거움, 변환기 본체와 별도):  pip install -r requirements-audio.txt

예:
  python tools/audio_to_musicxml.py song.mp3 --out out/song --title "My Song" --compact
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 22050
HOP = 256


# ---------------------------------------------------------------- 1. 분리
def separate(audio: Path, work: Path) -> tuple[Path, Path]:
    out = work / "sep"
    stem_dir = out / "htdemucs" / audio.stem
    voc, acc = stem_dir / "vocals.wav", stem_dir / "no_vocals.wav"
    if voc.exists() and acc.exists():
        return voc, acc
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
                    "-o", str(out), str(audio)], check=True)
    return voc, acc


# ---------------------------------------------------------------- 2. 박 격자
def beat_grid(acc: np.ndarray, bpm: float | None = None) -> tuple[float, float, int]:
    """(t0, period, downbeat_phase). t0 는 첫 박 시각, 박 k 의 시각 = t0 + k*period."""
    import librosa

    oenv = librosa.onset.onset_strength(y=acc, sr=SR, hop_length=HOP)
    kw = {"start_bpm": bpm} if bpm else {}
    _, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=SR, hop_length=HOP,
                                       units="time", tightness=200, **kw)
    bt = np.asarray(beats, dtype=float)
    if len(bt) < 8:
        raise SystemExit("beat tracking failed")
    P0 = float(np.median(np.diff(bt))) if bpm is None else 60.0 / bpm
    k = np.round((bt - bt[0]) / P0)
    A = np.vstack([np.ones_like(k), k]).T
    t0, P = np.linalg.lstsq(A, bt, rcond=None)[0]
    if bpm is not None:
        P = 60.0 / bpm
        t0 = float(np.median(bt - k * P))
    # 마디 첫 박: 저음(<150 Hz) 에너지가 가장 큰 위상
    S = np.abs(librosa.stft(acc, n_fft=2048, hop_length=HOP))
    low = S[librosa.fft_frequencies(sr=SR, n_fft=2048) < 150].sum(axis=0)
    n_beats = int((len(acc) / SR - t0) / P)
    frames = librosa.time_to_frames(t0 + np.arange(n_beats) * P, sr=SR, hop_length=HOP)
    lowb = low[np.clip(frames, 0, len(low) - 1)]
    phase = int(np.argmax([lowb[p::4].mean() for p in range(4)]))
    return float(t0), float(P), phase


# ---------------------------------------------------------------- 3. 음높이
def _crepe(voc_path: Path, cache: Path):
    """torchcrepe(full, viterbi) 로 10 ms 간격 f0/주기성. 느리므로(5분 곡에 CPU 약 10분) 캐시한다."""
    if cache.exists():
        c = np.load(cache)
        return c["f0"], c["per"], 0.01
    import librosa
    import torch
    import torchcrepe

    y, _ = librosa.load(str(voc_path), sr=16000, mono=True)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    f0, per = torchcrepe.predict(torch.tensor(y)[None], 16000, hop_length=160, fmin=80, fmax=1000,
                                 model="full", decoder=torchcrepe.decode.viterbi,
                                 return_periodicity=True, batch_size=1024, device="cpu")
    f0, per = f0[0].numpy(), per[0].numpy()
    np.savez(cache, f0=f0, per=per)
    return f0, per, 0.01


def track_pitch(voc: np.ndarray, voc_path: Path, method: str, cache_dir: Path, min_conf: float = 0.3):
    """반환: (frame_t, midi(튜닝 보정·평활, 무성은 nan), gate, onset_times, tuning)."""
    import librosa
    from scipy.ndimage import median_filter

    if method == "crepe":
        f0, conf, dt = _crepe(voc_path, cache_dir / "crepe_f0.npz")
        voiced = conf > min_conf
        y16, _ = librosa.load(str(voc_path), sr=16000, mono=True)
        rms = librosa.feature.rms(y=y16, frame_length=1024, hop_length=160)[0]
    else:
        f0, voiced, conf = librosa.pyin(voc, fmin=librosa.note_to_hz("E2"), fmax=librosa.note_to_hz("C6"),
                                        sr=SR, frame_length=2048, hop_length=HOP)
        voiced = voiced & (conf > min_conf)
        dt = HOP / SR
        rms = librosa.feature.rms(y=voc, frame_length=2048, hop_length=HOP)[0]
    n = min(len(f0), len(rms))
    f0, voiced, rms = f0[:n], voiced[:n], rms[:n]
    frame_t = np.arange(n) * dt
    rms_thr = max(0.005, 0.15 * float(np.percentile(rms, 90)))
    gate = voiced & (rms > rms_thr) & np.isfinite(f0) & (f0 > 0)
    midi = librosa.hz_to_midi(np.where(gate, f0, np.nan))
    frac = midi[gate] - np.round(midi[gate])
    tuning = float(np.angle(np.mean(np.exp(2j * np.pi * frac))) / (2 * np.pi)) if gate.any() else 0.0
    midi = midi - tuning
    sm = median_filter(np.where(gate, midi, 0.0), size=max(3, int(round(0.06 / dt)) | 1))
    sm = np.where(gate, sm, np.nan)
    # 음절 시작(onset) 시각: 22.05 kHz 보컬에서 피크 검출
    onset_times = librosa.onset.onset_detect(y=voc, sr=SR, hop_length=HOP, units="time", backtrack=False)
    return frame_t, sm, gate, np.asarray(onset_times, dtype=float), tuning


# ---------------------------------------------------------------- 4~5. 음표
def cells_to_notes(frame_t, midi, gate, onset_times, t0, P, sub=4, min_voiced=0.4):
    """16분음표(sub=4) 칸 단위로 음높이를 정하고 음표 목록 [(start_cell, len_cells, midi)] 을 만든다.

    onset_times: 음절 시작 시각(초). 칸 시작 근처에 onset 이 있으면 같은 음이라도 새 음표로 끊는다.
    """
    cell = P / sub
    n_cells = int((frame_t[-1] - t0) / cell)
    pitch = np.full(n_cells, -1, dtype=int)
    new_syllable = np.zeros(n_cells, dtype=bool)
    on = np.sort(np.asarray(onset_times, dtype=float))
    # onset 을 가장 가까운 칸 경계에 붙인다
    if len(on):
        k = np.round((on - t0) / cell).astype(int)
        k = k[(k >= 0) & (k < n_cells)]
        new_syllable[k] = True
    for c in range(n_cells):
        a, b = t0 + c * cell, t0 + (c + 1) * cell
        sel = (frame_t >= a) & (frame_t < b)
        if not sel.any():
            continue
        g = gate[sel]
        if g.mean() >= min_voiced:
            vals = np.round(midi[sel][g]).astype(int)
            pitch[c] = int(np.bincount(vals - vals.min()).argmax() + vals.min())

    # 옥타브 튐 보정: 앞뒤 2 박 중앙값과 9 반음 넘게 다르면 옥타브 이동
    for c in np.where(pitch >= 0)[0]:
        lo, hi = max(0, c - 2 * sub), min(n_cells, c + 2 * sub + 1)
        ctx = pitch[lo:hi][pitch[lo:hi] >= 0]
        if len(ctx) >= 3:
            med = np.median(ctx)
            while pitch[c] - med > 9:
                pitch[c] -= 12
            while med - pitch[c] > 9:
                pitch[c] += 12

    # 같은 음 사이의 한 칸 무성 구간(자음, 숨)은 메운다
    for c in range(1, n_cells - 1):
        if pitch[c] < 0 and pitch[c - 1] >= 0 and pitch[c - 1] == pitch[c + 1]:
            pitch[c] = pitch[c - 1]

    notes = []
    c = 0
    while c < n_cells:
        if pitch[c] < 0:
            c += 1
            continue
        s, p = c, pitch[c]
        c += 1
        while c < n_cells and pitch[c] == p and not new_syllable[c]:
            c += 1
        notes.append([s, c - s, p])

    # 한 칸짜리 경과음 흡수: 바로 이어지는 이웃과 붙어 있고 이웃이 2칸 이상이면
    cleaned = []
    for i, (s, L, p) in enumerate(notes):
        if L == 1:
            prev = cleaned[-1] if cleaned else None
            nxt = notes[i + 1] if i + 1 < len(notes) else None
            prev_adj = prev is not None and prev[0] + prev[1] == s
            next_adj = nxt is not None and s + 1 == nxt[0]
            if prev_adj and next_adj and abs(prev[2] - p) <= 2 and abs(nxt[2] - p) <= 2 and prev[1] >= 2:
                prev[1] += 1
                continue
            if prev_adj and not next_adj and prev[1] >= 2 and abs(prev[2] - p) <= 2:
                prev[1] += 1
                continue
            if next_adj and not prev_adj and nxt[1] >= 2 and abs(nxt[2] - p) <= 2:
                nxt[0] -= 1
                nxt[1] += 1
                continue
        cleaned.append([s, L, p])

    # 앞뒤 1칸 안에 다른 음이 없는 고립된 한 칸짜리 음은 잡음으로 보고 버린다
    out = []
    for i, (s, L, p) in enumerate(cleaned):
        if L == 1:
            prev_end = cleaned[i - 1][0] + cleaned[i - 1][1] if i > 0 else -10
            next_start = cleaned[i + 1][0] if i + 1 < len(cleaned) else 10 ** 9
            if s - prev_end > 1 and next_start - (s + 1) > 1:
                continue
        out.append([s, L, p])

    # 레가토 채우기: 다음 음까지 1박 이하로 비면 앞 음을 늘린다(시작 위치는 그대로, 악보 가독성용)
    for i in range(len(out) - 1):
        gap = out[i + 1][0] - (out[i][0] + out[i][1])
        if 0 < gap <= sub:
            out[i][1] += gap
    return out, sub


def _scale_pcs(key_name: str | None) -> set[int] | None:
    if not key_name:
        return None
    from music21 import key as m21key
    return {p.pitchClass for p in m21key.Key(key_name).getScale().getPitches()}


def syllables_to_notes(frame_t, midi, gate, onset_times, t0, P, sub=4, key_name=None,
                       min_syll=0.07, min_stable=0.12, snap_tol=0.75):
    """음절 단위 분할 → 음표 목록 [(start_cell, len_cells, midi)].

    1. 유성 구간을 잇고(40 ms 이하 끊김은 붙임) 음절 onset 에서 나눈다.
    2. 음절 안에서 120 ms 이상 머문 음높이 영역만 음표로 인정한다(멜리스마는 여러 음).
       그런 영역이 없으면 음절 가운데 부분(앞 15%, 뒤 20% 제외)의 최빈 음높이 하나.
       → 꺾기, 글리산도, 비브라토가 반음계 경과음으로 바뀌지 않는다.
    3. 조성 밖 음인데 실제로 부른 음높이가 조성 안 음과 snap_tol 반음 이내면 조성 안 음으로.
    4. 시작을 16분음표 격자에 맞추고, 다음 음까지 1박 이내면 이어 붙인다.
    """
    dt = float(np.median(np.diff(frame_t)))
    cell = P / sub
    scale = _scale_pcs(key_name)

    # 1. 유성 구간
    idx = np.where(gate)[0]
    if len(idx) == 0:
        return [], sub
    runs, s = [], idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if (b - a) * dt > 0.04:
            runs.append((s, a + 1))
            s = b
    runs.append((s, idx[-1] + 1))
    on = np.sort(np.asarray(onset_times, dtype=float))
    segs = []
    for a, b in runs:
        cuts = [a]
        for t in on[(on > frame_t[a] + 0.08) & (on < frame_t[b - 1] - 0.05)]:
            cuts.append(int(np.searchsorted(frame_t, t)))
        cuts.append(b)
        segs += [(x, y) for x, y in zip(cuts[:-1], cuts[1:]) if (y - x) * dt >= min_syll]

    def choose(vals: np.ndarray) -> int:
        vals = vals[np.isfinite(vals)]
        r = np.round(vals).astype(int)
        p = int(np.bincount(r - r.min()).argmax() + r.min())
        if scale is not None and p % 12 not in scale:
            med = float(np.median(vals))
            cands = [q for q in (p - 1, p + 1) if q % 12 in scale and abs(q - med) <= snap_tol]
            if cands:
                p = min(cands, key=lambda q: abs(q - med))
        return p

    # 2. 음절 → 음표(초 단위)
    from scipy.ndimage import median_filter
    raw = []  # (start_s, end_s, pitch)
    k = max(3, int(round(0.09 / dt)) | 1)
    for a, b in segs:
        seg = midi[a:b]
        sm = median_filter(np.nan_to_num(seg, nan=0.0), size=min(k, max(1, (b - a) | 1)))
        r = np.round(sm).astype(int)
        regions, rs = [], 0
        for i in range(1, len(r) + 1):
            if i == len(r) or r[i] != r[rs]:
                if (i - rs) * dt >= min_stable:
                    regions.append((rs, i, r[rs]))
                rs = i
        merged = []
        for reg in regions:  # 같은 음이 이어지는 영역은 하나로
            if merged and merged[-1][2] == reg[2]:
                merged[-1] = (merged[-1][0], reg[1], reg[2])
            else:
                merged.append(reg)
        if len(merged) >= 2:
            for j, (x, y, _) in enumerate(merged):
                st = a if j == 0 else a + x
                en = b if j == len(merged) - 1 else a + merged[j + 1][0]
                raw.append((frame_t[st], frame_t[en - 1] + dt, choose(seg[x:y])))
        else:
            n = b - a
            core = seg[int(n * 0.15): max(int(n * 0.15) + 1, int(n * 0.8))]
            raw.append((frame_t[a], frame_t[b - 1] + dt, choose(core)))

    # 옥타브 튐 보정(앞뒤 6음 중앙값과 9반음 넘게 차이)
    ps = np.array([p for _, _, p in raw], dtype=float)
    for i in range(len(raw)):
        ctx = np.delete(ps[max(0, i - 6): i + 7], min(i, 6))
        if len(ctx) >= 4:
            med = np.median(ctx)
            p = raw[i][2]
            while p - med > 9:
                p -= 12
            while med - p > 9:
                p += 12
            raw[i] = (raw[i][0], raw[i][1], p)

    # 4. 격자 맞춤
    notes: list[list[int]] = []
    for st, en, p in raw:
        c0 = int(round((st - t0) / cell))
        c1 = max(c0 + 1, int(round((en - t0) / cell)))
        if c0 < 0:
            continue
        if notes and c0 <= notes[-1][0]:
            # 같은 칸에 두 음 → 앞 음이 더 짧으면 바꿔치기, 아니면 한 칸 뒤로
            if notes[-1][1] <= 1 and notes[-1][2] != p:
                notes[-1] = [notes[-1][0], c1 - notes[-1][0], p]
                continue
            c0 = notes[-1][0] + 1
            c1 = max(c1, c0 + 1)
        if notes and notes[-1][0] + notes[-1][1] > c0:
            notes[-1][1] = c0 - notes[-1][0]
        notes.append([c0, c1 - c0, p])
    for i in range(len(notes) - 1):
        gap = notes[i + 1][0] - (notes[i][0] + notes[i][1])
        if 0 < gap <= sub:
            notes[i][1] += gap
    return notes, sub


def render_check_audio(notes, sub, t0, P, acc_path: Path, out_path: Path) -> None:
    """추출한 음표를 오르골 비슷한 감쇠음으로 합성해 반주와 섞는다(귀로 검증용)."""
    import librosa
    import soundfile as sf

    acc, _ = librosa.load(str(acc_path), sr=SR, mono=True)
    mel = np.zeros_like(acc)
    cell = P / sub
    for s, L, p in notes:
        st = int((t0 + s * cell) * SR)
        dur = min(int(L * cell * SR) + int(0.25 * SR), len(acc) - st)
        if dur <= 0 or st < 0:
            continue
        t = np.arange(dur) / SR
        f = librosa.midi_to_hz(p)
        tone = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)) * np.exp(-t * 3.0)
        mel[st:st + dur] += tone
    mel /= max(1e-9, np.abs(mel).max())
    mix = 0.45 * acc / max(1e-9, np.abs(acc).max()) + 0.55 * mel
    sf.write(str(out_path), np.vstack([mix, mel]).T * 0.9, SR)


# ---------------------------------------------------------------- 6. MusicXML
def write_musicxml(notes, sub, phase, path: Path, title: str, bpm: float, key_name: str | None,
                   compact: bool = False) -> dict:
    from music21 import key as m21key, metadata, meter, note, stream, tempo

    cells_per_bar = 4 * sub
    off = phase * sub  # 마디 첫 칸
    if not notes:
        raise SystemExit("no notes")
    # 앞뒤 마디 자르기
    first_bar = (notes[0][0] - off) // cells_per_bar
    start = off + first_bar * cells_per_bar
    evs = [(s - start, L, p) for s, L, p in notes]

    removed_bars = 0
    if compact:
        out, shift = [], 0
        prev_end = 0
        for s, L, p in evs:
            s2 = s - shift
            gap = s2 - prev_end
            if gap > 2 * cells_per_bar:
                # 쉼을 마디 경계를 지키며 1마디+나머지로
                cut = (gap // cells_per_bar - 1) * cells_per_bar
                shift += cut
                removed_bars += cut // cells_per_bar
                s2 -= cut
            out.append((s2, L, p))
            prev_end = s2 + L
        evs = out

    sc = stream.Score()
    sc.insert(0, metadata.Metadata())
    sc.metadata.title = title
    sc.metadata.composer = "transcribed from audio (bw-musicbox)"
    part = stream.Part(id="Melody")
    part.partName = "Melody"
    part.insert(0, meter.TimeSignature("4/4"))
    part.insert(0, tempo.MetronomeMark(number=round(bpm)))
    if key_name:
        part.insert(0, m21key.Key(key_name))
    q = 1.0 / sub
    for s, L, p in evs:
        n = note.Note(int(p))
        n.quarterLength = L * q
        part.insert(s * q, n)
    total_cells = evs[-1][0] + evs[-1][1]
    end_ql = -(-total_cells // cells_per_bar) * 4
    filled = part.makeRests(fillGaps=True, inPlace=False, timeRangeFromBarDuration=False)
    filled.makeMeasures(inPlace=True)
    filled.makeTies(inPlace=True)
    sc.insert(0, filled)
    if key_name:
        # 조표에 맞춰 철자: 플랫 조면 A# → Bb 처럼
        flats = m21key.Key(key_name).sharps < 0
        for n in sc.recurse().notes:
            acc = n.pitch.accidental
            if acc is not None and ((flats and acc.name == "sharp") or (not flats and acc.name == "flat")):
                n.pitch = n.pitch.getEnharmonic()
    sc.write("musicxml", fp=str(path))
    return {"bars": int(end_ql // 4), "removed_rest_bars": int(removed_bars), "notes": len(evs),
            "first_bar_index": int(first_bar)}


def estimate_key(acc: np.ndarray) -> str:
    import librosa

    ch = librosa.feature.chroma_cqt(y=acc, sr=SR).mean(axis=1)
    names = ["C", "C#", "D", "E-", "E", "F", "F#", "G", "A-", "A", "B-", "B"]
    maj = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    mnr = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    best = max(((np.corrcoef(np.roll(maj, i), ch)[0, 1], names[i]) for i in range(12)),
               key=lambda x: x[0])
    bestm = max(((np.corrcoef(np.roll(mnr, i), ch)[0, 1], names[i].lower()) for i in range(12)),
                key=lambda x: x[0])
    return best[1] if best[0] >= bestm[0] else bestm[1]


def main(argv=None) -> int:
    import librosa

    ap = argparse.ArgumentParser(description="오디오 → 보컬 멜로디 MusicXML")
    ap.add_argument("audio")
    ap.add_argument("--out", required=True, help="출력 폴더")
    ap.add_argument("--title", default=None)
    ap.add_argument("--bpm", type=float, default=None, help="템포를 알면 지정(박 추적 보정)")
    ap.add_argument("--key", default=None, help="조성 지정 예: B- (Bb장조), g (g단조). 생략하면 추정")
    ap.add_argument("--grid", type=int, default=16, choices=[8, 16], help="최소 음표 단위(8분/16분)")
    ap.add_argument("--compact", action="store_true", help="2마디 넘는 쉼을 1마디로 줄인 판도 저장")
    ap.add_argument("--stems", default=None, help="이미 분리된 vocals.wav/no_vocals.wav 가 있는 폴더")
    ap.add_argument("--pitch", choices=["crepe", "pyin"], default=None,
                    help="음높이 추적기. 기본: torchcrepe 가 있으면 crepe(정확, 느림), 없으면 pyin")
    ap.add_argument("--segment", choices=["syllable", "cell"], default="syllable",
                    help="syllable: 음절 단위(꺾기·비브라토에 강함, 기본). cell: 16분음표 칸 단위")
    ap.add_argument("--min-conf", type=float, default=None,
                    help="유성 판정 신뢰도 하한 (기본 crepe 0.3, pyin 0.2)")
    a = ap.parse_args(argv)

    audio = Path(a.audio)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.stems:
        voc_p, acc_p = Path(a.stems) / "vocals.wav", Path(a.stems) / "no_vocals.wav"
    else:
        voc_p, acc_p = separate(audio, out)

    voc, _ = librosa.load(str(voc_p), sr=SR, mono=True)
    acc, _ = librosa.load(str(acc_p), sr=SR, mono=True)
    t0, P, phase = beat_grid(acc, a.bpm)
    bpm = 60.0 / P
    key_name = a.key or estimate_key(acc)
    method = a.pitch
    if method is None:
        try:
            import torchcrepe  # noqa: F401
            method = "crepe"
        except ImportError:
            method = "pyin"
    min_conf = a.min_conf if a.min_conf is not None else (0.3 if method == "crepe" else 0.2)
    frame_t, midi, gate, onsets, tuning = track_pitch(voc, voc_p, method, out, min_conf)
    sub = 4 if a.grid == 16 else 2
    if a.segment == "syllable":
        notes, sub = syllables_to_notes(frame_t, midi, gate, onsets, t0, P, sub=sub, key_name=key_name)
    else:
        notes, sub = cells_to_notes(frame_t, midi, gate, onsets, t0, P, sub=sub)

    render_check_audio(notes, sub, t0, P, acc_p, out / "check_melody_over_accomp.wav")
    title = a.title or audio.stem
    info = write_musicxml(notes, sub, phase, out / "melody.musicxml", title, bpm, key_name)
    report = {"source": audio.name, "bpm": round(bpm, 2), "first_beat_s": round(t0, 3),
              "downbeat_phase": phase, "key": key_name, "tuning_offset_semitones": round(tuning, 3),
              "grid": a.grid, "segment": a.segment, "pitch_tracker": method, "min_conf": min_conf, "melody": info,
              "pitch_range": [int(min(n[2] for n in notes)), int(max(n[2] for n in notes))]}
    if a.compact:
        report["compact"] = write_musicxml(notes, sub, phase, out / "melody_compact.musicxml",
                                           title + " (compact)", bpm, key_name, compact=True)
    (out / "transcribe_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
