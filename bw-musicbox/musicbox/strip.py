"""스트립 모델과 DXF/SVG 렌더링, 용지 배치.

DXF 레이어:
  CUT_HOLE     구멍 (원)              - 가장 먼저 자른다
  ENGRAVE      각인 (선, 글자)         - 종이를 뚫지 않는 낮은 출력
  CUT_OUTLINE  스트립 외곽선           - 마지막에 자른다

DXF 좌표: 단위 mm, y축 위쪽. 스트립의 선단(먼저 들어가는 끝)이 위(y 큰 쪽)에 오도록 놓는다.
  dxf_x = origin_x + x
  dxf_y = origin_y + (length - t)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .spec import StripSpec, STANDARD_30

LAYER_HOLE = "CUT_HOLE"
LAYER_OUTLINE = "CUT_OUTLINE"
LAYER_ENGRAVE = "ENGRAVE"

# AutoCAD color index: 1 red, 5 blue, 7 white/black
LAYERS = {
    LAYER_HOLE: {"color": 1},
    LAYER_ENGRAVE: {"color": 7},
    LAYER_OUTLINE: {"color": 5},
}


@dataclass(frozen=True)
class Hole:
    track: int
    t: float                      # 진행 방향 위치 (mm, 선단 기준)
    diameter: float | None = None  # None이면 spec.hole_diameter


@dataclass(frozen=True)
class Engraving:
    """각인 요소. kind: 'line' | 'text'."""

    kind: str
    # line: (x1, t1, x2, t2)
    # text: (x, t) + text + height + rotation(도, 0 = 트랙 방향으로 읽음)
    coords: tuple[float, ...]
    text: str = ""
    height: float = 2.5
    rotation: float = 0.0
    align: str = "left"   # left | center | right (text 전용)


@dataclass
class Strip:
    length: float
    spec: StripSpec = STANDARD_30
    title: str = ""
    holes: list[Hole] = field(default_factory=list)
    engravings: list[Engraving] = field(default_factory=list)

    # ---- 구성 도우미 -------------------------------------------------
    def add_hole(self, track: int, t: float, diameter: float | None = None) -> None:
        self.spec.track_x(track)  # 범위 검사
        if not 0 <= t <= self.length:
            raise ValueError(f"hole t={t} outside strip length {self.length}")
        self.holes.append(Hole(track, t, diameter))

    def add_line(self, x1: float, t1: float, x2: float, t2: float) -> None:
        self.engravings.append(Engraving("line", (x1, t1, x2, t2)))

    def add_text(self, x: float, t: float, text: str, height: float = 2.5,
                 rotation: float = 0.0, align: str = "left") -> None:
        self.engravings.append(Engraving("text", (x, t), text, height, rotation, align))

    def add_margin_ruler(self, every: float = 5.0, label_every: float = 10.0,
                         side: str = "left") -> None:
        """여백에 진행 방향 눈금을 각인. 숫자는 선단에서의 거리(mm)."""
        s = self.spec
        if side == "left":
            x_edge, direction = 0.0, +1
        else:
            x_edge, direction = s.width, -1
        t = 0.0
        while t <= self.length + 1e-9:
            is_label = abs((t / label_every) - round(t / label_every)) < 1e-6
            tick = 2.5 if is_label else 1.5
            self.add_line(x_edge, t, x_edge + direction * tick, t)
            if is_label and t > 0:
                # 글자는 가장자리와 트랙 사이(폭 6 mm)에 세로로 눕혀 넣는다
                tx = x_edge + direction * 3.2 if side == "left" else x_edge + direction * 5.6
                self.add_text(tx, t - 0.9 if side == "left" else t + 0.9, f"{int(round(t))}",
                              height=1.6, rotation=-90 if side == "left" else 90,
                              align="left")
            t += every

    def add_direction_arrow(self, t: float | None = None) -> None:
        """진행 방향 화살표(선단을 가리킴)를 오른쪽 여백에 각인."""
        s = self.spec
        x = s.width - 3.0
        t0 = self.length - 12.0 if t is None else t
        self.add_line(x, t0, x, t0 - 8.0)
        self.add_line(x, t0 - 8.0, x - 1.5, t0 - 6.0)
        self.add_line(x, t0 - 8.0, x + 1.5, t0 - 6.0)

    # ---- 검사 --------------------------------------------------------
    def same_track_gap_violations(self, min_gap: float | None = None) -> list[tuple[int, float, float]]:
        """같은 트랙에서 중심 거리가 min_gap 미만인 (track, t1, t2) 목록."""
        g = self.spec.min_same_track_gap if min_gap is None else min_gap
        out = []
        by_track: dict[int, list[float]] = {}
        for h in self.holes:
            by_track.setdefault(h.track, []).append(h.t)
        for track, ts in by_track.items():
            ts.sort()
            for a, b in zip(ts, ts[1:]):
                if b - a < g - 1e-9:
                    out.append((track, a, b))
        return out


# ---- 용지 배치 --------------------------------------------------------
@dataclass
class Placement:
    strip: Strip
    origin_x: float
    origin_y: float


@dataclass
class Sheet:
    """레이저 용지 한 장. 기본 315 × 467 mm, 세로 방향 열 배치."""

    width: float = 315.0
    height: float = 467.0
    margin: float = 5.0
    gap: float = 5.0
    placements: list[Placement] = field(default_factory=list)

    def place_columns(self, strips: Iterable[Strip]) -> list[Strip]:
        """열마다 위에서 아래로 채운다. 들어가지 못한 스트립을 반환."""
        strips = list(strips)
        if not strips:
            return []
        col_w = max(s.spec.width for s in strips)
        n_cols = int((self.width - 2 * self.margin + self.gap) // (col_w + self.gap))
        cols = [self.height - self.margin] * n_cols  # 각 열의 다음 빈 y(위에서 아래로)
        leftover = []
        for s in strips:
            if s.length > self.height - 2 * self.margin:
                leftover.append(s)
                continue
            for c in range(n_cols):
                if cols[c] - s.length >= self.margin - 1e-9:
                    ox = self.margin + c * (col_w + self.gap)
                    oy = cols[c] - s.length
                    self.placements.append(Placement(s, ox, oy))
                    cols[c] = oy - self.gap
                    break
            else:
                leftover.append(s)
        return leftover


# ---- DXF -------------------------------------------------------------
def _outline_segments(w: float, L: float, bridges: int, bridge_len: float):
    """직사각형 외곽을 브릿지(미절단 구간)만큼 끊어 선분 목록으로. 좌표는 스트립 로컬 (x, y_up)."""
    # 긴 변 두 개에만 브릿지를 둔다 (짧은 변은 이음용 직각면이라 끊지 않는다)
    segs = []
    segs.append(((0, 0), (w, 0)))
    segs.append(((0, L), (w, L)))
    for x in (0.0, w):
        if bridges <= 0:
            segs.append(((x, 0), (x, L)))
            continue
        cuts = []
        step = L / (bridges + 1)
        y = 0.0
        for i in range(1, bridges + 1):
            yb = step * i
            cuts.append(((x, y), (x, yb - bridge_len / 2)))
            y = yb + bridge_len / 2
        cuts.append(((x, y), (x, L)))
        segs.extend(cuts)
    return segs


def _draw_strip(msp, strip: Strip, ox: float, oy: float, bridges: int, bridge_len: float) -> None:
    s = strip.spec
    L = strip.length

    def P(x: float, t: float) -> tuple[float, float]:
        return (ox + x, oy + (L - t))

    for h in strip.holes:
        d = h.diameter if h.diameter is not None else s.hole_diameter
        msp.add_circle(P(s.track_x(h.track), h.t), d / 2, dxfattribs={"layer": LAYER_HOLE})

    for e in strip.engravings:
        if e.kind == "line":
            x1, t1, x2, t2 = e.coords
            msp.add_line(P(x1, t1), P(x2, t2), dxfattribs={"layer": LAYER_ENGRAVE})
        elif e.kind == "text":
            x, t = e.coords
            txt = msp.add_text(e.text, dxfattribs={"layer": LAYER_ENGRAVE,
                                                   "height": e.height,
                                                   "rotation": e.rotation})
            from ezdxf.enums import TextEntityAlignment as TA
            al = {"left": TA.LEFT, "center": TA.CENTER, "right": TA.RIGHT}[e.align]
            txt.set_placement(P(x, t), align=al)

    for (a, b) in _outline_segments(s.width, L, bridges, bridge_len):
        msp.add_line((ox + a[0], oy + a[1]), (ox + b[0], oy + b[1]),
                     dxfattribs={"layer": LAYER_OUTLINE})


def _new_doc():
    import ezdxf
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4  # mm
    doc.header["$MEASUREMENT"] = 1
    for name, attrs in LAYERS.items():
        doc.layers.add(name, color=attrs["color"])
    return doc


def write_strip_dxf(strip: Strip, path: str | Path, bridges: int = 0, bridge_len: float = 0.4) -> Path:
    doc = _new_doc()
    _draw_strip(doc.modelspace(), strip, 0.0, 0.0, bridges, bridge_len)
    path = Path(path)
    doc.saveas(path)
    return path


def write_sheet_dxf(sheet: Sheet, path: str | Path, bridges: int = 4, bridge_len: float = 0.4,
                    draw_sheet_border: bool = True) -> Path:
    doc = _new_doc()
    msp = doc.modelspace()
    if draw_sheet_border:
        doc.layers.add("SHEET", color=8)
        msp.add_lwpolyline([(0, 0), (sheet.width, 0), (sheet.width, sheet.height), (0, sheet.height)],
                           close=True, dxfattribs={"layer": "SHEET"})
    for p in sheet.placements:
        _draw_strip(msp, p.strip, p.origin_x, p.origin_y, bridges, bridge_len)
    path = Path(path)
    doc.saveas(path)
    return path


# ---- SVG 미리보기 ------------------------------------------------------
def strip_svg(strip: Strip, scale: float = 4.0) -> str:
    """브라우저 확인용 SVG(단위 px = mm × scale). SVG는 y가 아래로 커지므로 t를 그대로 쓰면 선단이 위."""
    s = strip.spec
    L = strip.length
    W, H = s.width * scale, L * scale

    def P(x: float, t: float) -> tuple[float, float]:
        return (x * scale, t * scale)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.1f}" height="{H:.1f}" '
           f'viewBox="0 0 {W:.1f} {H:.1f}" font-family="sans-serif">',
           f'<rect x="0" y="0" width="{W:.1f}" height="{H:.1f}" fill="white" stroke="#1f6feb" stroke-width="1"/>']
    # 트랙 격자(참고용, DXF에는 없음)
    for i in range(s.n_tracks):
        x = s.track_x(i) * scale
        out.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{H:.1f}" stroke="#ddd" stroke-width="0.5"/>')
    for e in strip.engravings:
        if e.kind == "line":
            x1, t1, x2, t2 = e.coords
            (a, b), (c, d) = P(x1, t1), P(x2, t2)
            out.append(f'<line x1="{a:.1f}" y1="{b:.1f}" x2="{c:.1f}" y2="{d:.1f}" stroke="#222" stroke-width="0.8"/>')
        else:
            x, t = e.coords
            px, py = P(x, t)
            anchor = {"left": "start", "center": "middle", "right": "end"}[e.align]
            out.append(f'<text x="{px:.1f}" y="{py:.1f}" font-size="{e.height * scale:.1f}" '
                       f'text-anchor="{anchor}" transform="rotate({-e.rotation:.1f} {px:.1f} {py:.1f})">'
                       f'{_esc(e.text)}</text>')
    for h in strip.holes:
        d = h.diameter if h.diameter is not None else s.hole_diameter
        cx, cy = P(s.track_x(h.track), h.t)
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{d / 2 * scale:.2f}" fill="#d1242f"/>')
    out.append("</svg>")
    return "\n".join(out)


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
