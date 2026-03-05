from __future__ import annotations

import unittest
from pathlib import Path

from src.pencilengine.alignment import build_dark_mask, collect_sample_points, score_transform
from src.pencilengine.export import extract_strokes_to_document
from src.pencilengine.png import read_png_rgba


class AlignmentHypothesisTests(unittest.TestCase):
    def test_known_scale_beats_identity_on_page6(self) -> None:
        doc = extract_strokes_to_document(
            Path("data/unzipped/files/53d1088bd634cba318c4d27cc9371070.bin")
        )
        width, height, rgba = read_png_rgba(
            Path("data/unzipped/files/71e46e4aad83a6f0f8e10169ea3fc4d1.png")
        )
        dark = build_dark_mask(rgba, threshold=80)
        points = collect_sample_points(doc, step=3)

        identity = score_transform(
            points,
            dark,
            width,
            height,
            scale=1.0,
            dx=0.0,
            dy=0.0,
        )
        tuned = score_transform(
            points,
            dark,
            width,
            height,
            scale=0.902,
            dx=-0.5,
            dy=-0.5,
        )

        self.assertLess(identity, 0.2)
        self.assertGreater(tuned, 0.85)
        self.assertGreater(tuned - identity, 0.5)


if __name__ == "__main__":
    unittest.main()
