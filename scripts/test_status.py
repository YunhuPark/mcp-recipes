import unittest
from datetime import date

from scripts.status import parse_date


class ParseDateTests(unittest.TestCase):
    def test_invalid_calendar_date_returns_none(self):
        self.assertIsNone(parse_date("2026-02-30"))

    def test_valid_leap_day_is_preserved(self):
        self.assertEqual(parse_date("2024-02-29"), date(2024, 2, 29))

    def test_empty_and_unicode_text_without_date_return_none(self):
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date("일정 없음"))


if __name__ == "__main__":
    unittest.main()
