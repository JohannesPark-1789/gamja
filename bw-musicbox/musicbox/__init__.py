"""bw-musicbox: 30음 종이 오르골용 천공악보를 레이저 절단 도면(DXF)으로 만드는 도구."""

from .spec import StripSpec, STANDARD_30
from .strip import Strip, Hole, Engraving, Sheet

__all__ = ["StripSpec", "STANDARD_30", "Strip", "Hole", "Engraving", "Sheet"]
