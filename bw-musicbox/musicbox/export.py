"""레이저 소프트웨어용 내보내기: DXF(글자→선) / SVG / PLT(HPGL).

레이저 프로그램마다 잘 읽는 형식이 달라서 같은 도면을 세 가지로 낸다.
  - *_laser.dxf : TEXT 를 선(폴리라인)으로 바꾼 DXF. 글꼴이 없어 글자가 빠지는 문제를 막는다.
  - *.svg       : mm 단위, 레이어별 색(구멍 빨강, 각인 검정, 외곽 파랑), 선 굵기 0.01 mm, 채움 없음.
  - *.plt       : HPGL. 40 단위 = 1 mm, 펜 번호 = 레이어(SP1 구멍, SP2 각인, SP3 외곽). 원은 다각형으로.
  - *_r12.dxf   : 가장 오래된 호환 형식(AutoCAD R12). LINE/CIRCLE/POLYLINE 만, 가공 순서대로 기록.
                  골든레이저 등 레이저 전용 CAD 가 최신 DXF 를 잘 못 읽을 때 쓴다.

공통 규칙
  - 좌표는 1:1 mm, 원점(0,0) = 용지 왼쪽 아래 모서리, y 는 위쪽.
  - 출력 순서 = 가공 순서: 구멍 → 각인 → 외곽선. 외곽을 먼저 자르면 조각이 움직여 구멍이 틀어진다.
  - 구멍은 스트립(열)별로 위→아래 순서로 정렬해 헤드 이동을 줄인다.
  - 용지 테두리(SHEET 레이어)는 내보내지 않는다(잘리면 안 되는 선).
"""

from __future__ import annotations

import math
from pathlib import Path

from .strip import LAYER_ENGRAVE, LAYER_HOLE, LAYER_OUTLINE

ORDER = [LAYER_HOLE, LAYER_ENGRAVE, LAYER_OUTLINE]
SVG_COLOR = {LAYER_HOLE: "#ff0000", LAYER_ENGRAVE: "#000000", LAYER_OUTLINE: "#0000ff"}
PEN = {LAYER_HOLE: 1, LAYER_ENGRAVE: 2, LAYER_OUTLINE: 3}
HPGL_UNITS_PER_MM = 40


def explode_text(doc) -> int:
    """모델 공간의 TEXT 를 같은 레이어의 LWPOLYLINE 들로 바꾼다. 바꾼 개수를 돌려준다."""
    from ezdxf.addons import text2path
    Kind = text2path.Kind

    msp = doc.modelspace()
    texts = list(msp.query("TEXT MTEXT"))
    for t in texts:
        layer = t.dxf.layer
        for e in text2path.virtual_entities(t, kind=Kind.LWPOLYLINES):
            e.dxf.layer = layer
            msp.add_entity(e)
        msp.delete_entity(t)
    return len(texts)


def _shapes(doc, circle_segments: int = 48):
    """레이어 → [('circle', cx, cy, r) | ('poly', [(x, y), ...], closed)] (가공 순서대로 정렬)."""
    from ezdxf import path as dxfpath

    out: dict[str, list] = {k: [] for k in ORDER}
    for e in doc.modelspace():
        layer = e.dxf.layer
        if layer not in out:
            continue
        t = e.dxftype()
        if t == "CIRCLE":
            c = e.dxf.center
            out[layer].append(("circle", c.x, c.y, e.dxf.radius))
        elif t == "LINE":
            out[layer].append(("poly", [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)], False))
        else:
            try:
                p = dxfpath.make_path(e)
            except TypeError:
                continue
            for sub in p.sub_paths():
                pts = [(v.x, v.y) for v in sub.flattening(0.02)]
                if len(pts) >= 2:
                    closed = math.dist(pts[0], pts[-1]) < 1e-6
                    out[layer].append(("poly", pts, closed))
    # 구멍: 열(x 를 75 mm 간격으로 묶음) → 위에서 아래로
    out[LAYER_HOLE].sort(key=lambda s: (round(s[1] // 75), -s[2], s[1]))
    return out


def write_svg(doc, path: str | Path, width: float, height: float) -> Path:
    shapes = _shapes(doc)
    L = [f'<?xml version="1.0" encoding="UTF-8"?>',
         f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" '
         f'viewBox="0 0 {width} {height}">',
         f'<!-- 1:1 mm, 원점 = 용지 왼쪽 아래. 순서: 구멍(빨강) → 각인(검정) → 외곽(파랑) -->']

    def Y(y):  # SVG 는 y 가 아래로
        return height - y

    for layer in ORDER:
        col = SVG_COLOR[layer]
        L.append(f'<g id="{layer}" fill="none" stroke="{col}" stroke-width="0.01">')
        for s in shapes[layer]:
            if s[0] == "circle":
                _, cx, cy, r = s
                L.append(f'<circle cx="{cx:.3f}" cy="{Y(cy):.3f}" r="{r:.3f}"/>')
            else:
                _, pts, closed = s
                d = "M" + " L".join(f"{x:.3f},{Y(y):.3f}" for x, y in pts) + (" Z" if closed else "")
                L.append(f'<path d="{d}"/>')
        L.append("</g>")
    L.append("</svg>")
    path = Path(path)
    path.write_text("\n".join(L), encoding="utf-8")
    return path


def write_plt(doc, path: str | Path, circle_segments: int = 48) -> Path:
    shapes = _shapes(doc)
    k = HPGL_UNITS_PER_MM

    def u(v):
        return int(round(v * k))

    cmds = ["IN;", "PA;"]
    for layer in ORDER:
        cmds.append(f"SP{PEN[layer]};")
        for s in shapes[layer]:
            if s[0] == "circle":
                _, cx, cy, r = s
                pts = [(cx + r * math.cos(2 * math.pi * i / circle_segments),
                        cy + r * math.sin(2 * math.pi * i / circle_segments)) for i in range(circle_segments + 1)]
            else:
                pts = s[1]
            cmds.append(f"PU{u(pts[0][0])},{u(pts[0][1])};")
            cmds.append("PD" + ",".join(f"{u(x)},{u(y)}" for x, y in pts[1:]) + ";")
    cmds += ["PU;", "SP0;"]
    path = Path(path)
    path.write_text("\n".join(cmds) + "\n", encoding="ascii")
    return path


R12_COLOR = {LAYER_HOLE: 1, LAYER_ENGRAVE: 7, LAYER_OUTLINE: 5}   # 빨강, 검정(흰색), 파랑


def write_dxf_r12(doc, path: str | Path) -> Path:
    import logging

    import ezdxf

    shapes = _shapes(doc)
    log = logging.getLogger("ezdxf")
    old = log.level
    log.setLevel(logging.ERROR)          # "R12 에는 단위 정보가 없다" 경고 숨김(단위는 mm)
    try:
        r12 = ezdxf.new("R12")
    finally:
        log.setLevel(old)
    for layer in ORDER:
        r12.layers.add(layer, color=R12_COLOR[layer])
    msp = r12.modelspace()
    for layer in ORDER:
        att = {"layer": layer, "color": R12_COLOR[layer]}
        for sh in shapes[layer]:
            if sh[0] == "circle":
                _, cx, cy, r = sh
                msp.add_circle((cx, cy), r, dxfattribs=att)
            else:
                _, pts, closed = sh
                if len(pts) == 2 and not closed:
                    msp.add_line(pts[0], pts[1], dxfattribs=att)
                else:
                    msp.add_polyline2d(pts[:-1] if closed else pts, close=closed, dxfattribs=att)
    path = Path(path)
    r12.saveas(path)
    return path


def export_laser(dxf_path: str | Path, width: float, height: float) -> list[str]:
    """시트 DXF 하나 → *_laser.dxf, *.svg, *.plt, *_r12.dxf. 만든 파일 경로 목록을 돌려준다."""
    import ezdxf

    dxf_path = Path(dxf_path)
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    for e in list(msp.query('*[layer=="SHEET"]')):
        msp.delete_entity(e)
    explode_text(doc)
    base = dxf_path.with_suffix("")
    laser_dxf = Path(f"{base}_laser.dxf")
    doc.saveas(laser_dxf)
    svg = write_svg(doc, f"{base}.svg", width, height)
    plt = write_plt(doc, f"{base}.plt")
    r12 = write_dxf_r12(doc, f"{base}_r12.dxf")
    return [str(laser_dxf), str(svg), str(plt), str(r12)]
