from __future__ import annotations

import unittest
from pathlib import Path

from src.pencilengine.parser import parse_pencilengine_bin


DATA_DIR = Path("data/unzipped/files")


class ParserStabilityTests(unittest.TestCase):
    def test_parse_bin_a(self) -> None:
        parsed = parse_pencilengine_bin(
            DATA_DIR / "53d1088bd634cba318c4d27cc9371070.bin"
        )
        self.assertEqual(parsed.header.magic, "PENCILENGINE")
        self.assertEqual(parsed.header.header_len_u32, 0x4C)
        self.assertEqual(parsed.first_stroke_offset, 0x88)
        self.assertEqual(len(parsed.strokes), 139)
        self.assertEqual(parsed.global_words["0x70"], 139)
        self.assertEqual(sum(s.point_count for s in parsed.strokes), 4016)
        self.assertEqual(len(bytes.fromhex(parsed.trailing_hex)), 72)

    def test_parse_bin_b(self) -> None:
        parsed = parse_pencilengine_bin(
            DATA_DIR / "9def0e3d381fa1c2e41f7f80d88503a3.bin"
        )
        self.assertEqual(parsed.header.magic, "PENCILENGINE")
        self.assertEqual(parsed.header.header_len_u32, 0x4C)
        self.assertEqual(parsed.first_stroke_offset, 0x88)
        self.assertEqual(len(parsed.strokes), 141)
        self.assertEqual(parsed.global_words["0x70"], 141)
        self.assertEqual(sum(s.point_count for s in parsed.strokes), 3374)
        self.assertEqual(len(bytes.fromhex(parsed.trailing_hex)), 72)

    def test_time_field_monotonic_per_stroke(self) -> None:
        parsed = parse_pencilengine_bin(
            DATA_DIR / "53d1088bd634cba318c4d27cc9371070.bin"
        )
        for stroke in parsed.strokes:
            prev = -1
            for pt in stroke.points:
                self.assertGreaterEqual(pt.t_u32, prev)
                prev = pt.t_u32


if __name__ == "__main__":
    unittest.main()
