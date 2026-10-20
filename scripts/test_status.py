"""status.py 의 읽기 규칙 시험 (실제로 겪은 오류의 재발 방지).

실행: python -m unittest scripts/test_status.py  (저장소 루트에서)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status  # noqa: E402

RECORD = """## 게시 후 기록
| 조회 | 저장 | 공유 | 요청한 사람(서로 다른) | 확인일 |
|---|---|---|---|---|
| 98 | - | - | 0 | 2026-10-20 인사이트: 조회 98 (이전 값 88) |
"""


class MetricsTests(unittest.TestCase):
    def test_header_row_is_skipped_and_data_row_is_read(self):
        cells = status.parse_metrics(RECORD)
        self.assertEqual(cells[:4], ["98", "-", "-", "0"])

    def test_a_data_row_mentioning_views_in_the_note_is_still_read(self):
        # 확인일 칸의 설명에 '조회'가 들어 있어도 데이터 줄로 읽어야 한다 (예전에는 머리글로 오인해 건너뜀)
        cells = status.parse_metrics(RECORD)
        self.assertIsNotNone(cells)
        self.assertIn("조회", cells[4])

    def test_empty_row_gives_empty_cells(self):
        cells = status.parse_metrics("## 게시 후 기록\n| 조회 | 저장 | 공유 | 요청 | 확인일 |\n|---|---|---|---|---|\n| | | | | |\n")
        self.assertEqual(cells, ["", "", "", "", ""])


class BacklogTests(unittest.TestCase):
    def test_numbers_beyond_35_are_counted(self):
        # ㊱ 이후의 원문자 번호도 글감으로 센다 (예전에는 ㉟까지만 세어 하나가 빠졌음)
        text = ("### 남은 단독 글감 (시험)\n| 번호 | 글감 | 근거 |\n|---|---|---|\n"
                "| ② | a | x |\n| ㉟ | b | x |\n| ㊱ | c | x |\n| ㊲ | d | x |\n\n### 다음\n")
        self.assertEqual(status.count_backlog(text), 4)


if __name__ == "__main__":
    unittest.main()
