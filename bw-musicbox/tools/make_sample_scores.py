"""저작권 만료 시험곡을 tinyNotation 으로 만들어 MusicXML 로 저장한다.

실행: python tools/make_sample_scores.py
"""

from pathlib import Path

from music21 import converter, metadata, tempo

ROOT = Path(__file__).resolve().parents[1] / "songs"

ODE = ("tinyNotation: 4/4 "
       "e4 e f g g f e d c c d e e4. d8 d2 "
       "e4 e f g g f e d c c d e d4. c8 c2 "
       "d4 d e c d e8 f8 e4 c d e8 f8 e4 d c d G2 "
       "e4 e f g g f e d c c d e d4. c8 c2")

TWINKLE = ("tinyNotation: 4/4 "
           "c4 c g g a a g2 f4 f e e d d c2 "
           "g4 g f f e e d2 g4 g f f e e d2 "
           "c4 c g g a a g2 f4 f e e d d c2")

SAMPLES = {
    "ode-to-joy": ("Ode to Joy", ODE, 100),
    "twinkle": ("Twinkle Twinkle Little Star", TWINKLE, 90),
}


def main() -> None:
    for slug, (title, tn, bpm) in SAMPLES.items():
        s = converter.parse(tn)
        s.insert(0, metadata.Metadata())
        s.metadata.title = title
        s.metadata.composer = "traditional / public domain"
        s.getElementsByClass("Measure")[0].insert(0, tempo.MetronomeMark(number=bpm))
        out = ROOT / slug / "melody.musicxml"
        out.parent.mkdir(parents=True, exist_ok=True)
        s.write("musicxml", fp=str(out))
        print("wrote", out)


if __name__ == "__main__":
    main()
