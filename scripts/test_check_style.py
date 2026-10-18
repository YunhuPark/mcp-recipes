"""check.py 의 지시형 문장 경고 시험.

실행: python -m unittest scripts/test_check_style.py  (저장소 루트에서)
경고는 점검을 실패시키지 않는다. 아직 올리지 않은 글에만 경고하고, 댓글 요청("알려주세요")은 허용한다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(__file__).resolve().parent / "check.py"


def post_text(status: str, body: str) -> str:
    return "\n".join([
        "# D01 · 시험", "", f"- 상태: **{status}** (시험)", "- 글자 수: 10자", "",
        "```", body, "```", "",
        "## 게시 후 기록", "| 조회 |", "|---|", "| |", ""])


class StyleWarningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "posts" / "daily").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def run_check(self, status: str, body: str):
        (self.root / "posts" / "schedule.md").write_text(
            f"| 일차 | 날짜 | 글 | 상태 | 비고 |\n|---|---|---|---|---|\n| D01 | 10/14 | 시험 | {status} | |\n",
            encoding="utf-8")
        (self.root / "posts" / "daily" / "D01-test.md").write_text(post_text(status, body), encoding="utf-8")
        r = subprocess.run([sys.executable, str(CHECK), "--root", str(self.root), "--no-commits"],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr

    def test_imperative_in_a_draft_is_warned_but_does_not_fail(self):
        code, out = self.run_check("초안", "등록하고 나면 날짜를 다시 조회해보세요")
        self.assertEqual(code, 0, out)
        self.assertIn("독자에게 지시하는 문장", out)

    def test_various_imperative_endings_are_warned(self):
        for line in ("미리보기는 꼭 확인해주세요", "이렇게 하세요", "절대 하지 마세요", "한번 써보십시오"):
            with self.subTest(line=line):
                code, out = self.run_check("초안", line)
                self.assertEqual(code, 0, out)
                self.assertIn("독자에게 지시하는 문장", out)

    def test_a_comment_request_is_allowed(self):
        for line in ("다뤄줬으면 하는 조합 있으면 댓글로 알려주세요", "댓글로 알려 주세요"):
            with self.subTest(line=line):
                code, out = self.run_check("초안", line)
                self.assertEqual(code, 0, out)
                self.assertNotIn("독자에게 지시하는 문장", out)

    def test_plain_statements_are_not_warned(self):
        code, out = self.run_check("초안", "11/11로 요청했지만 11/10으로 저장됐습니다\n정상이었어요")
        self.assertEqual(code, 0, out)
        self.assertNotIn("독자에게 지시하는 문장", out)

    def test_published_posts_are_not_warned(self):
        code, out = self.run_check("게시됨", "미리보기는 꼭 확인해주세요")
        self.assertNotIn("독자에게 지시하는 문장", out)

    def test_reviewed_posts_are_warned_too(self):
        # 검수완료 글은 근거표가 없어 실패하지만, 지시형 경고는 함께 나와야 한다
        code, out = self.run_check("검수완료", "꼭 확인해주세요")
        self.assertIn("독자에게 지시하는 문장", out)


if __name__ == "__main__":
    unittest.main()
