"""check.py 의 근거표 규칙 시험.

실행: python -m unittest scripts/test_check_evidence.py  (저장소 루트에서)
근거표의 내용이 사실인지는 이 규칙이 판단하지 못한다. 여기서는 '대조를 건너뛰거나 대조 뒤에 글이 바뀐 경우'를
막는지, 인용이 근거 파일에 실제로 있는지만 시험한다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(__file__).resolve().parent / "check.py"
sys.path.insert(0, str(CHECK.parent))
from check import body_hash  # noqa: E402

SOURCE = "검증 기록\n종일 일정은 하루 앞당겨져 저장됨\n시간 지정 일정은 정상\n"
BODY = "종일 일정을 넣었더니\n하루가 밀렸습니다"


def post_text(status="검수완료", body=BODY, rows=None, stamp="auto", heading="## 근거표"):
    rows = rows if rows is not None else [
        "| 하루가 밀렸다 | `validation-log.md` | 하루 앞당겨져 저장됨 | 일치 |"]
    lines = [f"# D01 · 시험", "", f"- 상태: **{status}** (시험)", "- 글자 수: 10자", "", "```", body, "```", ""]
    if heading:
        lines += [heading]
        if stamp == "auto":
            lines += [f"- 대조일: 2026-10-15 / 본문 해시: {body_hash(BODY)}"]
        elif stamp:
            lines += [stamp]
        lines += ["| 본문 주장 | 근거 파일 | 근거 인용 | 결과 |", "|---|---|---|---|", *rows, ""]
    lines += ["## 게시 후 기록", "| 조회 |", "|---|", "| |"]
    return "\n".join(lines) + "\n"


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "posts" / "daily").mkdir(parents=True)
        (self.root / "validation-log.md").write_text(SOURCE, encoding="utf-8")
        (self.root / "posts" / "schedule.md").write_text(
            "| 일차 | 날짜 | 글 | 상태 | 비고 |\n|---|---|---|---|---|\n| D01 | 10/14 | 시험 | 검수완료 | |\n",
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, **kw):
        status = kw.get("status", "검수완료")
        (self.root / "posts" / "schedule.md").write_text(
            f"| 일차 | 날짜 | 글 | 상태 | 비고 |\n|---|---|---|---|---|\n| D01 | 10/14 | 시험 | {status} | |\n",
            encoding="utf-8")
        self.post = self.root / "posts" / "daily" / "D01-test.md"
        self.post.write_text(post_text(**kw), encoding="utf-8")

    def run_check(self, *extra):
        r = subprocess.run([sys.executable, str(CHECK), "--root", str(self.root), "--no-commits", *extra],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr

    def test_valid_table_passes(self):
        self.write()
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_draft_does_not_need_a_table(self):
        self.write(status="초안", heading=None)
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_reviewed_without_a_table_fails(self):
        self.write(heading=None)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("'## 근거표'가 없습니다", out)

    def test_published_also_needs_a_table(self):
        self.write(status="게시됨", heading=None)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("근거표", out)

    def test_missing_stamp_fails(self):
        self.write(stamp=None)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("본문 해시", out)

    def test_body_changed_after_the_check_fails(self):
        self.write(body=BODY + "\n그리고 한 줄 추가")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("대조한 뒤에 바뀌었습니다", out)

    def test_quote_must_exist_in_the_source(self):
        self.write(rows=["| 하루가 밀렸다 | `validation-log.md` | 이틀 앞당겨져 저장됨 | 일치 |"])
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("그대로 있지 않습니다", out)

    def test_quote_ignores_line_breaks_and_extra_spaces(self):
        self.write(rows=["| 정상이었다 | `validation-log.md` | 시간   지정 일정은 정상 | 일치 |"])
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_source_file_must_exist(self):
        self.write(rows=["| 주장 | `없는-파일.md` | 아무 말 | 일치 |"])
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("찾지 못했습니다", out)

    def test_source_outside_the_repo_is_refused(self):
        outside = self.root.parent / "outside-source.md"
        outside.write_text("바깥 파일의 문구", encoding="utf-8")
        try:
            self.write(rows=["| 주장 | `../outside-source.md` | 바깥 파일의 문구 | 일치 |"])
            code, out = self.run_check()
            self.assertEqual(code, 1)
            self.assertIn("찾지 못했습니다", out)
        finally:
            outside.unlink()

    def test_every_cell_must_be_filled(self):
        self.write(rows=["| 주장 | `validation-log.md` | | 일치 |"])
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("네 칸이 모두", out)

    def test_result_must_be_a_known_word(self):
        self.write(rows=["| 주장 | `validation-log.md` | 하루 앞당겨져 저장됨 | 아마 맞음 |"])
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("결과는", out)

    def test_external_source_needs_a_check_date(self):
        self.write(rows=["| 주장 | 외부: 다른 저장소 main.py | if args.threads: | 일치 |"])
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("확인한 날짜", out)
        self.write(rows=["| 주장 | 외부: 다른 저장소 main.py | 2026-10-15 직접 확인 if args.threads: | 일치 |"])
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_table_without_rows_fails(self):
        self.write(rows=[])
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("행이 없습니다", out)

    def test_stamp_records_the_hash_and_a_later_edit_invalidates_it(self):
        self.write(stamp=None)
        self.assertEqual(self.run_check()[0], 1)
        code, out = self.run_check("--stamp", "D01")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_check()[0], 0)
        text = self.post.read_text(encoding="utf-8")
        self.post.write_text(text.replace("하루가 밀렸습니다", "하루가 밀렸어요"), encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("대조한 뒤에 바뀌었습니다", out)
        self.assertEqual(self.run_check("--stamp", "D01")[0], 0)
        self.assertEqual(self.run_check()[0], 0)

    def test_stamp_needs_a_table_section(self):
        self.write(heading=None)
        code, out = self.run_check("--stamp", "D01")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
