# bw-musicbox

30음 종이 오르골용 천공악보를 레이저 절단 도면(DXF)으로 만드는 도구. 설계 배경은 [DESIGN.md](DESIGN.md).

## 설치

```bash
cd bw-musicbox
pip install -r requirements.txt     # ezdxf
```

## 악보 변환 (변환기 코어)

MusicXML(.musicxml/.mxl)·MIDI·ABC 악보를 읽어 세그먼트별 DXF, 315×467 시트 DXF, 보고서를 만든다.

```bash
python -m musicbox.convert songs/ode-to-joy/melody.musicxml --out out/ode --svg --sheet --barlines
python -m musicbox.convert song.mxl --out out/song --transpose 5 --out-of-range drop --drop-close
python -m musicbox.convert song.musicxml --out out/song --standalone-segments   # 장마다 단독 재생 가능
```

처리 순서와 옵션:

1. **악보 읽기** (`score.py`): 도돌이표를 펼치고, 꾸밈음과 타이 뒷음은 버리고, 화음은 음마다 이벤트로.
2. **이조·트랙 매핑** (`arrange.py`): `--transpose` 를 생략하면 −12~+12 반음을 전부 시험해 수록 음표가 가장 많은 조를 고른다(동률이면 원조 유지인 옥타브 이동 우선). 범위 밖 음은 `--out-of-range fold|drop|error`. 같은 트랙 최소 간격(기본 8 mm) 위반은 보고하고, `--drop-close` 를 주면 뒤 음을 버린다.
3. **분할** (`layout.py`): 455 mm 이하가 되도록 박 경계에서 자르되 절단선 앞뒤 4 mm 가 비는 자리를 고른다. 못 찾으면 강제로 자르고 `FORCED` 로 표시한다. 첫 세그먼트에만 리드인 60 mm, 마지막에만 리드아웃 25 mm. 이음부 양 여백에 정합 눈금과 `J1`, `J2` 번호를 각인한다.
4. **출력** (`convert.py`): `seg01.dxf …`, `--sheet` 시 `sheet01.dxf …`(4열 배치, 브릿지), `report.txt/json`.

보고서 예:

```
Ode to Joy  (songs/ode-to-joy/melody.musicxml)
notes 62 → placed 62 (folded 0), dropped 0, removed-close 0
transpose +12 semitones; candidates: +12:62/0/0, +7:62/0/0, ...  (direct/folded/dropped)
length 581.0 mm total, music 496.0 mm, ~37.2 s at 100 bpm
segments 2: #1 436.0 mm/47 holes, #2 145.0 mm/15 holes
same-track gaps < 8.0 mm: 3
  m.4 D4 (track D1) gap 4.0 mm
```

시험곡은 `python tools/make_sample_scores.py` 로 다시 만들 수 있다(환희의 송가, 작은별).

### 합주 (오르골 여러 대)

```bash
python -m musicbox.convert songs/abide-with-me/score.musicxml --out out/abide --boxes 4 --box-mode parts --box-parts "0;1;2;3" --svg --sheet --barlines
```

- 모든 박스는 같은 30음 콤이다. 박스를 늘려도 음역은 늘지 않고, 동시에 독립적으로 울리는 성부 수가 는다.
- `--boxes N`, `--box-mode register`(기본): 같은 박의 음을 높은 순으로 정렬해 맨 위 음은 1번, 맨 아래 음은 마지막 박스, 남는 음은 가운데로. `--box-mode parts --box-parts "0;1;2,3"`: 악보 파트로 직접 지정.
- 한 박스에서 같은 트랙 최소 간격을 어기는 음은 다른 박스로 옮긴다(호켓). 못 옮기면 보고서에 `unresolved`.
- 모든 박스의 스트립은 같은 자리에서 잘리고 같은 리드인을 가진다. 각 스트립에 `B1`…과 이음 번호(`J1B2`)가 각인된다. `--count-in` 으로 0박에 정렬 확인용 C2 한 음을 넣을 수 있다.
- 출력은 `box1/seg01.dxf …`, 시트는 모든 박스의 세그먼트를 함께 배치한다.

`songs/abide-with-me/` 는 찬송가 EVENTIDE(때 저물어서 날이 어두니, W. H. Monk 1861) 4성부 악보로, 합주 예제다.

## 캘리브레이션 스트립

실제 오르골과 레이저에 맞는 값을 실측하기 위한 첫 번째 출력물. 70 × 403 mm 스트립 하나에 네 가지 시험이 들어 있다.

```bash
python -m musicbox.calib --out out/calib.dxf --svg          # 스트립 1장 + SVG 미리보기
python -m musicbox.calib --out out/calib_sheet.dxf --copies 4   # 315×467 시트에 4장 배치(브릿지 포함)
python -m musicbox.calib --diameters 2.2 2.4 2.6 --gaps 6 7 8 --out out/calib2.dxf
```

DXF 레이어와 가공 순서: `CUT_HOLE`(빨강, 구멍) → `ENGRAVE`(각인, 종이를 뚫지 않는 출력) → `CUT_OUTLINE`(파랑, 외곽선, 마지막).

### 읽는 법

스트립은 제목 `CAL 30`이 있는 쪽이 선단(먼저 들어가는 끝)이다. 왼쪽 여백의 눈금은 선단에서의 거리(mm).

| 구간 | 내용 | 결과 → 반영할 값 |
|---|---|---|
| L15~L55 | 선단 15/25/35/45/55 mm 에 C, D, G, A, B 한 음씩 | 종이를 롤러에 물리고 돌렸을 때 **처음 들리는 음의 위치**가 최소 리드인. 그 값 + 10 mm 를 `StripSpec.lead_in` 으로 |
| A SWEEP | 트랙 0→29 를 4 mm 간격으로 한 번씩 (C 부터 E3 까지 음계) | 양끝 음(C, E3)이 또렷하면 좌우 정렬 OK. 한쪽 끝이 약하거나 안 나면 `first_track_x` 를 0.2 mm 단위로 조정 |
| B DIA | 지름 2.0 / 2.2 / 2.4 / 2.6 / 2.8 mm 를 저·중·고음 트랙(D, C2, C3)에 한 줄씩 | 셋 다 또렷하고 종이가 걸리지 않는 **가장 작은 값**을 `hole_diameter` 로 |
| C GAP | 같은 트랙(G, C2, A2)에 구멍 두 개를 4/5/6/7/8/10 mm 간격으로 | 두 번째 음이 **셋 다** 나는 가장 작은 간격을 `min_same_track_gap` 으로 |

### 테스트

```bash
python tests/test_calib.py && python tests/test_convert.py     # pytest 가 있으면 python -m pytest
```

## 구조

```
musicbox/spec.py    종이 규격(StripSpec), 30음 배열, MIDI 매핑
musicbox/strip.py   Strip 모델, DXF/SVG 렌더링, 315×467 시트 배치
musicbox/calib.py   캘리브레이션 스트립 생성 CLI
musicbox/score.py   악보 파일 → 노트 이벤트 (music21)
musicbox/arrange.py 이조 선택, 트랙 매핑, 간격 검사
musicbox/layout.py  세그먼트 분할과 각인
musicbox/ensemble.py 합주용 박스 배정(음역 분할·파트 지정, 호켓)
musicbox/convert.py 변환 CLI와 보고서
tools/              시험곡 생성 스크립트
songs/              곡 데이터(meta.yaml + melody.musicxml), 후보 목록
```
