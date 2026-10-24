"""approve.py, new_post.py, insights.py --write 시험. 실제 Threads를 부르지 않는다.

실행: python -m unittest scripts/test_workflow_tools.py -v   (저장소 루트에서)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import approve  # noqa: E402
import check as check_mod  # noqa: E402
import insights  # noqa: E402
import new_post  # noqa: E402

NOW = datetime(2026, 10, 22, 14, 30)
NL = chr(10)
CHECK = Path(__file__).resolve().parent / "check.py"
SOURCE = "검증 기록\n종일 일정은 하루 앞당겨져 저장됨\n"
BODY = "종일 일정을 넣었더니\n하루가 밀렸습니다"


def real_check(root: Path):
    r = subprocess.run([sys.executable, str(CHECK), "--root", str(root), "--no-commits"],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def post_text(status="초안", body=BODY, rows=None, stamp="auto", note=""):
    rows = rows if rows is not None else ["| 하루가 밀렸다 | `validation-log.md` | 하루 앞당겨져 저장됨 | 일치 |"]
    lines = ["# D01 · 시험", "", f"- 상태: **{status}** (시험)", "- 글자 수: 10자", "", "```", body, "```", "",
             "## 근거표"]
    if stamp == "auto":
        lines.append(f"- 대조일: 2026-10-22 / 본문 해시: {check_mod.body_hash(BODY)}")
    elif stamp:
        lines.append(stamp)
    lines += ["| 본문 주장 | 근거 파일 | 근거 인용 | 결과 |", "|---|---|---|---|", *rows, "",
              "## 게시 후 기록", "| 조회 | 저장 | 공유 | 요청한 사람(서로 다른) | 확인일 |", "|---|---|---|---|---|",
              f"| | | | | {note} |"]
    return "\n".join(lines) + "\n"


def schedule_text(status="초안", pid="D01", title="시험", date="10/14 (수)"):
    return f"| 일차 | 날짜 | 글 | 상태 | 비고 |\n|---|---|---|---|---|\n| {pid} | {date} | {title} | {status} | |\n"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "posts" / "daily").mkdir(parents=True)
        (self.root / "validation-log.md").write_text(SOURCE, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, status="초안", sched_status=None, **kw):
        (self.root / "posts" / "schedule.md").write_text(schedule_text(sched_status or status), encoding="utf-8")
        self.path = self.root / "posts" / "daily" / "D01-test.md"
        self.path.write_text(post_text(status, **kw), encoding="utf-8")

    def read(self):
        return self.path.read_text(encoding="utf-8"), (self.root / "posts" / "schedule.md").read_text(encoding="utf-8")


class ApproveTests(Base):
    def run_approve(self, answer="yes", check=real_check):
        lines = []
        code = approve.approve(self.root, "D01", now=NOW, confirm=lambda: answer, check=check, out=lines.append)
        return code, "\n".join(lines)

    def test_approves_a_valid_draft_after_yes_and_changes_both_files(self):
        self.write()
        code, out = self.run_approve()
        self.assertEqual(code, 0, out)
        text, sched = self.read()
        self.assertIn("**검수완료**", text)
        self.assertIn("| 검수완료 |", sched)
        self.assertIn("하루가 밀렸습니다", out)  # 본문을 보여 준다
        self.assertIn("근거표", out)

    def test_anything_but_exactly_yes_changes_nothing(self):
        for answer in ("", "y", "Yes", "네", "yes please"):
            with self.subTest(answer=answer):
                self.write()
                before = self.read()
                code, out = self.run_approve(answer)
                self.assertEqual(code, 1)
                self.assertEqual(self.read(), before)

    def test_a_failing_check_blocks_and_restores_the_files(self):
        self.write(stamp=None)  # 대조 기록(해시)이 없음
        before = self.read()
        code, out = self.run_approve()
        self.assertEqual(code, 1)
        self.assertIn("확정할 수 없습니다", out)
        self.assertEqual(self.read(), before)

    def test_body_changed_after_the_stamp_blocks(self):
        self.write(body=BODY + "\n한 줄 추가")
        before = self.read()
        code, out = self.run_approve()
        self.assertEqual(code, 1)
        self.assertIn("바뀌었습니다", out)
        self.assertEqual(self.read(), before)

    def test_a_quote_missing_from_the_source_blocks(self):
        self.write(rows=["| 하루가 밀렸다 | `validation-log.md` | 이틀 앞당겨져 저장됨 | 일치 |"])
        code, out = self.run_approve()
        self.assertEqual(code, 1)

    def test_already_reviewed_or_published_is_not_changed(self):
        self.write(status="검수완료")
        self.assertEqual(self.run_approve()[0], 0)
        self.write(status="게시됨")
        before = self.read()
        code, out = self.run_approve()
        self.assertEqual(code, 1)
        self.assertIn("초안만 확정할 수 있습니다", out)
        self.assertEqual(self.read(), before)

    def test_schedule_must_also_be_a_draft(self):
        self.write(status="초안", sched_status="미정")
        before = self.read()
        code, out = self.run_approve()
        self.assertEqual(code, 1)
        self.assertIn("일정표의 상태가 '미정'", out)
        self.assertEqual(self.read(), before)

    def test_missing_post_is_an_error(self):
        (self.root / "posts" / "schedule.md").write_text(schedule_text(), encoding="utf-8")
        code, _ = self.run_approve()
        self.assertEqual(code, 2)

    def test_no_commit_is_made_and_crlf_is_preserved(self):
        self.write()
        self.path.write_bytes(post_text().replace("\n", "\r\n").encode("utf-8"))
        code, out = self.run_approve()
        self.assertEqual(code, 0, out)
        self.assertIn(b"\r\n", self.path.read_bytes())
        self.assertNotIn(b"\r\r\n", self.path.read_bytes())


class BatchTests(Base):
    """approve.py --batch: 초안 전부를 한 번에 확정."""

    def setUp(self):
        super().setUp()
        daily = self.root / "posts" / "daily"
        rows = []
        for pid in ("D01", "D02", "D03"):
            (daily / f"{pid}-test.md").write_text(post_text("초안").replace("# D01", f"# {pid}"), encoding="utf-8")
            rows.append(f"| {pid} | 10/14 (수) | 시험 | 초안 | |")
        (self.root / "posts" / "schedule.md").write_text(
            NL.join(["| 일차 | 날짜 | 글 | 상태 | 비고 |", "|---|---|---|---|---|", *rows]) + NL, encoding="utf-8")

    def snapshot(self):
        return {p.name: p.read_text(encoding="utf-8") for p in sorted((self.root / "posts").rglob("*.md"))}

    def run_batch(self, answer="yes", dry_run=False, check=real_check):
        lines = []
        self.asked = []
        code = approve.approve_batch(self.root, now=NOW, confirm=lambda: (self.asked.append(1), answer)[1], check=check, out=lines.append, dry_run=dry_run)
        return code, NL.join(lines)

    def test_one_yes_approves_every_draft(self):
        code, out = self.run_batch()
        self.assertEqual(code, 0, out)
        snap = self.snapshot()
        for pid in ("D01", "D02", "D03"):
            self.assertIn("**검수완료**", snap[f"{pid}-test.md"])
        self.assertEqual(snap["schedule.md"].count("| 검수완료 |"), 3)
        self.assertIn("3개를 검수완료로 확정", out)

    def test_anything_but_yes_changes_nothing(self):
        before = self.snapshot()
        code, _ = self.run_batch("y")
        self.assertEqual(code, 1)
        self.assertEqual(self.snapshot(), before)

    def test_one_failing_post_stops_the_whole_batch_and_changes_nothing(self):
        bad = self.root / "posts" / "daily" / "D02-test.md"
        bad.write_text(post_text("초안", rows=["| 틀림 | `validation-log.md` | 이 문구는 기록에 없음 | 일치 |"]).replace("# D01", "# D02"), encoding="utf-8")
        before = self.snapshot()
        code, out = self.run_batch()
        self.assertEqual(code, 1)
        self.assertIn("D02: 실패", out)
        self.assertIn("D01: 통과", out)
        self.assertEqual(self.asked, [])  # 실패가 있으면 확정 여부를 묻지도 않는다
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_checks_but_never_changes_anything(self):
        before = self.snapshot()
        code, out = self.run_batch(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("확정은 하지 않았습니다", out)
        self.assertEqual(self.snapshot(), before)

    def test_only_drafts_are_included(self):
        (self.root / "posts" / "daily" / "D02-test.md").write_text(post_text("게시됨").replace("# D01", "# D02"), encoding="utf-8")
        sched = (self.root / "posts" / "schedule.md").read_text(encoding="utf-8").replace("| D02 | 10/14 (수) | 시험 | 초안 |", "| D02 | 10/14 (수) | 시험 | 게시됨 |")
        (self.root / "posts" / "schedule.md").write_text(sched, encoding="utf-8")
        code, out = self.run_batch()
        self.assertEqual(code, 0, out)
        snap = self.snapshot()
        self.assertIn("**게시됨**", snap["D02-test.md"])
        self.assertIn("2개를 검수완료로 확정", out)

    def test_final_check_failure_reverts_everything(self):
        calls = {"n": 0}

        def flaky(root):
            calls["n"] += 1
            return (calls["n"] <= 3, "마지막 점검 실패")  # 글마다 3번은 통과, 확정 뒤 마지막 점검에서 실패

        before = self.snapshot()
        code, out = self.run_batch(check=flaky)
        self.assertEqual(code, 1)
        self.assertIn("모두 되돌렸습니다", out)
        self.assertEqual(self.snapshot(), before)

    def test_no_drafts_is_a_noop(self):
        for p in (self.root / "posts" / "daily").glob("*.md"):
            p.write_text(post_text("게시됨"), encoding="utf-8")
        code, out = self.run_batch()
        self.assertEqual(code, 0)
        self.assertIn("확정할 초안이 없습니다", out)


class NewPostTests(Base):
    def make(self, status="미정", title="미정"):
        (self.root / "posts" / "schedule.md").write_text(
            f"| 일차 | 날짜 | 글 | 상태 | 비고 |\n|---|---|---|---|---|\n| D10 | 10/24 (토) | {title} | {status} | |\n| D11 | 10/25 (일) | 미정 | 미정 | |\n",
            encoding="utf-8")

    def create(self, **kw):
        lines = []
        args = dict(post_id="D10", slug="my-post", title="새 글 제목")
        args.update(kw)
        code = new_post.create(self.root, args["post_id"], args["slug"], args["title"], now=NOW, out=lines.append)
        return code, "\n".join(lines)

    def test_creates_the_file_and_updates_the_schedule_row(self):
        self.make()
        code, out = self.create()
        self.assertEqual(code, 0, out)
        f = self.root / "posts" / "daily" / "D10-2026-10-24-my-post.md"
        self.assertTrue(f.exists())
        text = f.read_text(encoding="utf-8")
        self.assertIn("**초안**", text)
        self.assertIn("## 근거표", text)
        sched = (self.root / "posts" / "schedule.md").read_text(encoding="utf-8")
        self.assertIn("| D10 | 10/24 (토) | 새 글 제목 | 초안 |", sched)
        self.assertIn("| D11 | 10/25 (일) | 미정 | 미정 |", sched)  # 다른 행은 그대로

    def test_the_skeleton_cannot_be_approved_until_it_is_filled_in(self):
        self.make()
        self.create()
        lines = []
        code = approve.approve(self.root, "D10", now=NOW, confirm=lambda: "yes", check=real_check, out=lines.append)
        self.assertEqual(code, 1)  # 대조 기록과 인용이 없어서 점검이 막는다
        self.assertIn("**초안**", (self.root / "posts" / "daily" / "D10-2026-10-24-my-post.md").read_text(encoding="utf-8"))

    def test_refuses_when_the_row_is_not_undecided(self):
        self.make(status="초안", title="이미 있음")
        code, _ = self.create()
        self.assertEqual(code, 1)
        self.assertEqual(list((self.root / "posts" / "daily").glob("D10-*.md")), [])

    def test_refuses_to_overwrite_an_existing_file(self):
        self.make()
        self.create()
        (self.root / "posts" / "schedule.md").write_text(
            "| 일차 | 날짜 | 글 | 상태 | 비고 |\n|---|---|---|---|---|\n| D10 | 10/24 (토) | 미정 | 미정 | |\n", encoding="utf-8")
        code, _ = self.create(slug="other")
        self.assertEqual(code, 1)
        self.assertEqual(len(list((self.root / "posts" / "daily").glob("D10-*.md"))), 1)

    def test_bad_slug_or_empty_title_or_unknown_row(self):
        self.make()
        self.assertEqual(self.create(slug="한글")[0], 2)
        self.assertEqual(self.create(slug="Has Space")[0], 2)
        self.assertEqual(self.create(title="  ")[0], 2)
        self.assertEqual(self.create(post_id="D99")[0], 2)


class InsightsWriteTests(Base):
    def row(self, **kw):
        r = {"id": "D01", "media_id": "m1", "timestamp": "t", "views": 98, "likes": 1, "replies": 1, "reposts": 0, "quotes": 0}
        r.update(kw)
        return r

    def test_writes_views_and_an_api_note_without_touching_the_request_cell(self):
        self.write(note="2026-10-18 수동 기록")
        text = self.path.read_text(encoding="utf-8").replace("| | | | | 2026-10-18 수동 기록 |", "| | - | - | 3 | 2026-10-18 수동 기록 |", 1)
        self.path.write_text(text, encoding="utf-8")
        done = insights.write_records(self.root, [self.row()], NOW)
        self.assertEqual(done, ["D01"])
        out = self.path.read_text(encoding="utf-8")
        self.assertIn("| 98 | - | - | 3 |", out)  # 조회만 바뀌고 저장, 공유, 요청 칸은 그대로
        self.assertIn("2026-10-18 수동 기록 / 2026-10-22 14:30 인사이트(API): 조회 98, 좋아요 1, 답글 1, 리포스트 0", out)

    def test_running_twice_replaces_the_previous_api_note(self):
        self.write()
        insights.write_records(self.root, [self.row(views=10)], NOW)
        insights.write_records(self.root, [self.row(views=20)], datetime(2026, 10, 23, 9, 0))
        out = self.path.read_text(encoding="utf-8")
        self.assertEqual(out.count("인사이트(API)"), 1)
        self.assertIn("| 20 |", out)
        self.assertIn("2026-10-23 09:00 인사이트(API): 조회 20", out)
        self.assertNotIn("조회 10,", out)

    def test_a_missing_metric_keeps_the_old_views_value(self):
        self.write()
        insights.write_records(self.root, [self.row(views=55)], NOW)
        insights.write_records(self.root, [self.row(views=None)], NOW)
        out = self.path.read_text(encoding="utf-8")
        self.assertIn("| 55 |", out)
        self.assertIn("조회 -", out)

    def test_posts_without_a_local_file_or_table_are_skipped(self):
        self.write()
        self.assertEqual(insights.write_records(self.root, [self.row(id="D77")], NOW), [])
        self.path.write_text("# D01\n\n내용만 있음\n", encoding="utf-8")
        self.assertEqual(insights.write_records(self.root, [self.row()], NOW), [])

    def test_the_updated_record_is_read_back_by_status(self):
        import status
        self.write()
        insights.write_records(self.root, [self.row(views=130)], NOW)
        cells = status.parse_metrics(self.path.read_text(encoding="utf-8"))
        self.assertEqual(cells[0], "130")


if __name__ == "__main__":
    unittest.main()
