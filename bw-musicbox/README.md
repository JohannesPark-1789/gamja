# bw-musicbox

30음 종이 오르골용 천공악보를 레이저 절단 도면(DXF)으로 만드는 도구. 설계 배경은 [DESIGN.md](DESIGN.md).

## 설치

```bash
cd bw-musicbox
pip install -r requirements.txt     # ezdxf
```

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
python tests/test_calib.py      # pytest 가 있으면 python -m pytest
```

## 구조

```
musicbox/spec.py    종이 규격(StripSpec), 30음 배열, MIDI 매핑
musicbox/strip.py   Strip 모델, DXF/SVG 렌더링, 315×467 시트 배치
musicbox/calib.py   캘리브레이션 스트립 생성 CLI
songs/              곡 데이터(메타데이터 스키마, 후보 목록)
```
