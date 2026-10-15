"""post.py 시험. 실제 Threads를 부르지 않고 가짜 네트워크로 안전장치를 확인한다.

실행: python -m unittest scripts/test_post.py -v   (저장소 루트에서)
토큰은 시험용 가짜 문자열이며 실제 값이 아니다.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import post  # noqa: E402

FAKE = "TESTONLY-not-a-real-credential"
NOW = datetime(2026, 10, 15, 9, 0)
OK_CHECK = lambda root: (True, "")  # noqa: E731


class FakeTransport:
    def __init__(self, script, on_call=None):
        self.script, self.calls, self.on_call = list(script), [], on_call

    def request(self, method, url, data, timeout=30):
        self.calls.append((method, url, dict(data or {})))
        if self.on_call:
            self.on_call(len(self.calls), self)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_root(tmp: Path, *, d2_status="검수완료", d2_body=None, d2_date="10/15 (목)") -> Path:
    daily = tmp / "posts" / "daily"
    daily.mkdir(parents=True)
    rows = []
    for pid, date, title in (("D01", "10/14 (수)", "첫 글"), ("D02", d2_date, "둘째 글"), ("D03", "10/16 (금)", "셋째 글")):
        status = d2_status if pid == "D02" else "검수완료"
        body = (d2_body if (pid == "D02" and d2_body is not None) else f"{pid} 본문입니다\n두 번째 줄")
        (daily / f"{pid}-test.md").write_text(
            f"# {pid} · 시험\n\n- 상태: **{status}** (시험)\n- 글자 수: 10자\n\n```\n{body}\n```\n\n## 게시 후 기록\n| 조회 | 저장 | 공유 | 요청한 사람(서로 다른) | 확인일 |\n|---|---|---|---|---|\n| | | | | |\n",
            encoding="utf-8")
        rows.append(f"| {pid} | {date} | {title} | {status} | 비고 |")
    (tmp / "posts" / "schedule.md").write_text(
        "| 일차 | 날짜 | 글 | 상태 | 비고 |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return tmp


def good_script():
    return [(200, {"id": "CONTAINER1"}), (200, {"id": "MEDIA1"})]


class PostTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmp.name))
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("THREADS_") and k not in ("IG_ACCESS_TOKEN", "IG_USER_ID")}
        env.update({"THREADS_LIVE": "yes", "THREADS_ACCESS_TOKEN": FAKE, "THREADS_USER_ID": "12345",
                    "THREADS_TOKEN_EXPIRES": "2026-12-01"})
        self._env = mock.patch.dict(os.environ, env, clear=True)
        self._env.start()
        self.sleeps = []

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def run_main(self, argv, transport=None, now=NOW, confirm=lambda: "yes", check=OK_CHECK):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = post.main(argv + ["--root", str(self.root), "--wait", "0"], transport=transport, now=now,
                             root=self.root, confirm=confirm, sleep=self.sleeps.append, check=check)
        return code, out.getvalue()

    def state(self):
        p = self.root / post.STATE_FILE
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"posts": {}}

    # 1
    def test_dry_run_makes_no_calls_and_no_state(self):
        t = FakeTransport([])
        code, out = self.run_main(["D02"], t)
        self.assertEqual(code, 0)
        self.assertEqual(t.calls, [])
        self.assertFalse((self.root / post.STATE_FILE).exists())
        self.assertIn("드라이런", out)

    # 2
    def test_publish_needs_the_second_key(self):
        del os.environ["THREADS_LIVE"]
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 1)
        self.assertEqual(t.calls, [])
        self.assertIn("THREADS_LIVE", out)

    # 3
    def test_no_token_fallback(self):
        del os.environ["THREADS_ACCESS_TOKEN"]
        os.environ["IG_ACCESS_TOKEN"] = FAKE + "-instagram"
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 1)
        self.assertEqual(t.calls, [])
        self.assertIn("대체하지 않습니다", out)

    # 4
    def test_only_reviewed_posts(self):
        self.tearDown(); self.setUp()
        self.root = make_root(Path(tempfile.mkdtemp()), d2_status="초안")
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 1)
        self.assertEqual(t.calls, [])
        self.assertIn("검수완료여야 함", out)

    def test_each_status_source_blocks_on_its_own(self):
        # 글 파일과 일정표 중 한쪽만 '검수완료'가 아니어도 막아야 한다 (검사가 서로 가려주지 않게)
        daily_file = next((self.root / "posts" / "daily").glob("D02-*.md"))
        schedule = self.root / "posts" / "schedule.md"
        file_text, sched_text = daily_file.read_text(encoding="utf-8"), schedule.read_text(encoding="utf-8")

        daily_file.write_text(file_text.replace("**검수완료**", "**초안**"), encoding="utf-8")
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("글 파일의 상태", out)

        daily_file.write_text(file_text, encoding="utf-8")
        schedule.write_text(sched_text.replace("| D02 | 10/15 (목) | 둘째 글 | 검수완료 |", "| D02 | 10/15 (목) | 둘째 글 | 초안 |"),
                            encoding="utf-8")
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("일정표의 상태", out)

    # 5
    def test_over_the_limit_is_refused(self):
        self.root = make_root(Path(tempfile.mkdtemp()), d2_body="가" * 501)
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 1)
        self.assertEqual(t.calls, [])
        self.assertIn("500을 넘습니다", out)

    def test_emoji_bytes_count_toward_the_limit(self):
        self.root = make_root(Path(tempfile.mkdtemp()), d2_body="🙏" * 126)  # 126 * 4 = 504 바이트
        code, out = self.run_main(["D02", "--publish"], FakeTransport([]))
        self.assertEqual(code, 1)
        self.assertIn("넘습니다", out)

    # 6
    def test_success_records_before_the_first_call_and_never_leaks_the_token(self):
        seen = {}

        def on_call(n, t):
            if n == 1:  # 첫 API 호출 시점에 이미 시도 기록이 있어야 한다
                seen["state"] = self.state()["posts"].get("D02")
                seen["raw"] = (self.root / post.STATE_FILE).read_text(encoding="utf-8")

        t = FakeTransport(good_script(), on_call)
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 0)
        self.assertEqual(seen["state"]["state"], "STARTED")
        self.assertNotIn(FAKE, seen["raw"])
        final = self.state()["posts"]["D02"]
        self.assertEqual((final["state"], final["media_id"], final["mode"]), ("PUBLISHED", "MEDIA1", "manual"))
        self.assertEqual(len(t.calls), 2)
        self.assertIn("/12345/threads", t.calls[0][1])
        self.assertTrue(t.calls[1][1].endswith("/12345/threads_publish"))
        self.assertEqual(t.calls[0][2]["media_type"], "TEXT")
        self.assertEqual(t.calls[1][2]["creation_id"], "CONTAINER1")
        self.assertEqual(self.sleeps, [0.0])
        self.assertNotIn(FAKE, out)
        self.assertNotIn(FAKE, (self.root / post.STATE_FILE).read_text(encoding="utf-8"))
        # 글 파일과 일정표가 '게시됨'으로 바뀐다
        self.assertIn("**게시됨**", next((self.root / "posts" / "daily").glob("D02*.md")).read_text(encoding="utf-8"))
        self.assertRegex((self.root / "posts" / "schedule.md").read_text(encoding="utf-8"), r"\| D02 \|[^|]*\|[^|]*\| 게시됨 \|")

    # 7
    def test_the_posted_text_is_exactly_the_reviewed_body(self):
        t = FakeTransport(good_script())
        self.run_main(["D02", "--publish"], t)
        self.assertEqual(t.calls[0][2]["text"], "D02 본문입니다\n두 번째 줄")

    # 8
    def test_a_published_post_is_never_posted_twice(self):
        self.run_main(["D02", "--publish"], FakeTransport(good_script()))
        t2 = FakeTransport(good_script())
        code, out = self.run_main(["D02", "--publish", "--allow-extra"], t2)
        self.assertEqual(code, 1)
        self.assertEqual(t2.calls, [])
        self.assertIn("이미 게시된 글", out)

    # 9
    def test_clear_failure_at_creation_is_safe_and_redacted(self):
        t = FakeTransport([(400, {"error": {"type": "OAuthException", "code": 190,
                                             "message": f"invalid token access_token={FAKE}"}})])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 1)
        rec = self.state()["posts"]["D02"]
        self.assertEqual(rec["state"], "FAILED")
        self.assertNotIn(FAKE, out)
        self.assertNotIn(FAKE, json.dumps(rec, ensure_ascii=False))
        self.assertEqual(len(t.calls), 1)
        # --retry 없이는 다시 못 한다, 있으면 된다
        t2 = FakeTransport([])
        code2, out2 = self.run_main(["D02", "--publish"], t2)
        self.assertEqual((code2, t2.calls), (1, []))
        self.assertIn("--retry", out2)
        t3 = FakeTransport(good_script())
        self.assertEqual(self.run_main(["D02", "--publish", "--retry"], t3)[0], 0)

    # 10
    def test_network_error_at_creation_means_not_posted(self):
        t = FakeTransport([post.NetworkError("TimeoutError")])
        code, _ = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 1)
        self.assertEqual(self.state()["posts"]["D02"]["state"], "FAILED")
        self.assertEqual(len(t.calls), 1)

    # 11
    def test_uncertain_publish_is_never_retried_automatically(self):
        t = FakeTransport([(200, {"id": "C1"}), post.NetworkError("TimeoutError")])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 1)
        self.assertEqual(self.state()["posts"]["D02"]["state"], "UNCERTAIN")
        self.assertEqual(len(t.calls), 2)  # 발행 호출은 한 번뿐
        t2 = FakeTransport(good_script())
        code2, out2 = self.run_main(["D02", "--publish", "--retry"], t2)
        self.assertEqual((code2, t2.calls), (1, []))  # --retry 로도 못 푼다
        self.assertIn("--resolve", out2)
        # 사람이 확인한 뒤에만 풀린다
        self.assertEqual(self.run_main(["D02", "--resolve", "not_published"])[0], 0)
        self.assertEqual(self.state()["posts"]["D02"]["state"], "FAILED")
        self.assertEqual(self.run_main(["D02", "--publish", "--retry"], FakeTransport(good_script()))[0], 0)

    # 12
    def test_odd_publish_responses_are_uncertain(self):
        for resp in ((200, {}), (500, None), (200, None), (400, {"error": {"message": "x"}})):
            with self.subTest(resp=resp):
                self.tearDown(); self.setUp()
                code, _ = self.run_main(["D02", "--publish"], FakeTransport([(200, {"id": "C1"}), resp]))
                self.assertEqual(code, 1)
                self.assertEqual(self.state()["posts"]["D02"]["state"], "UNCERTAIN")

    # 13
    def test_interrupted_attempts_are_settled_safely(self):
        old = (NOW - timedelta(minutes=30)).isoformat(timespec="seconds")
        (self.root / post.STATE_FILE).write_text(json.dumps({"version": 1, "posts": {
            "D01": {"state": "PUBLISHING", "updated": old, "mode": "manual"},
            "D03": {"state": "CONTAINER_CREATED", "updated": old, "mode": "manual"}}}), encoding="utf-8")
        self.run_main(["--status"])
        s = self.state()["posts"]
        self.assertEqual(s["D01"]["state"], "UNCERTAIN")  # 발행 호출 중이었다 -> 불확실
        self.assertEqual(s["D03"]["state"], "FAILED")      # 발행 전이었다 -> 게시되지 않음

    # 14
    def test_one_post_per_day(self):
        self.run_main(["D01", "--publish"], FakeTransport(good_script()))
        t = FakeTransport(good_script())
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("하루 1개", out)
        self.assertEqual(self.run_main(["D02", "--publish", "--allow-extra"], FakeTransport(good_script()))[0], 0)

    # 15
    def test_an_unresolved_uncertain_post_blocks_everything_else(self):
        self.run_main(["D01", "--publish"], FakeTransport([(200, {"id": "C"}), post.NetworkError("x")]))
        t = FakeTransport(good_script())
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("불확실한 시도가 풀리지 않은 글", out)

    # 16
    def test_scheduled_mode_is_gated_on_three_manual_successes(self):
        t = FakeTransport(good_script())
        code, out = self.run_main(["--scheduled", "--publish"], t)
        self.assertEqual((code, t.calls), (3, []))
        self.assertIn("3회", out)

    # 17
    def test_scheduled_mode_posts_only_todays_reviewed_post_without_a_prompt(self):
        (self.root / post.STATE_FILE).write_text(json.dumps({"version": 1, "posts": {
            f"X{i}": {"state": "PUBLISHED", "mode": "manual", "published_at": "2026-10-10T09:00:00"} for i in range(3)}}),
            encoding="utf-8")
        t = FakeTransport(good_script())
        code, out = self.run_main(["--scheduled", "--publish"], t, confirm=lambda: self.fail("예약 실행은 확인을 묻지 않는다"))
        self.assertEqual(code, 0)
        self.assertEqual(self.state()["posts"]["D02"]["mode"], "scheduled")
        self.assertEqual(t.calls[0][2]["text"], "D02 본문입니다\n두 번째 줄")

    def test_scheduled_mode_does_nothing_when_no_post_is_due(self):
        (self.root / post.STATE_FILE).write_text(json.dumps({"version": 1, "posts": {
            f"X{i}": {"state": "PUBLISHED", "mode": "manual", "published_at": "2026-10-10T09:00:00"} for i in range(3)}}),
            encoding="utf-8")
        t = FakeTransport(good_script())
        code, out = self.run_main(["--scheduled", "--publish"], t, now=datetime(2026, 11, 20, 9, 0))
        self.assertEqual((code, t.calls), (0, []))
        self.assertIn("아무것도 하지 않습니다", out)

    # 18
    def test_expired_token_is_refused(self):
        os.environ["THREADS_TOKEN_EXPIRES"] = "2026-10-14"
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("만료", out)

    # 19
    def test_a_failing_safety_check_blocks_publishing(self):
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t, check=lambda r: (False, "[오류] 시험용 실패"))
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("check.py", out)

    def test_the_real_check_catches_a_leak_before_publishing(self):
        (self.root / "posts" / "leak.md").write_text("연락처 someone" + "@" + "gmail.com\n", encoding="utf-8")  # 소스에 주소 형태가 남지 않게 나눠 적음
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t, check=post.run_site_check)
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("이메일", out)

    def test_the_real_check_refuses_a_reviewed_post_without_an_evidence_table(self):
        t = FakeTransport([])
        code, out = self.run_main(["D02", "--publish"], t, check=post.run_site_check)
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("근거표", out)

    # 20
    def test_manual_publish_needs_a_human_yes(self):
        for answer in ("", "y", "no", "Yes "):
            with self.subTest(answer=answer):
                self.tearDown(); self.setUp()
                t = FakeTransport(good_script())
                code, _ = self.run_main(["D02", "--publish"], t, confirm=lambda a=answer: a)
                if answer.strip() == "yes":
                    self.assertEqual(code, 0)
                else:
                    self.assertEqual((code, t.calls), (1, []))

    # 21
    def test_status_and_unresolved_resolve(self):
        code, out = self.run_main(["--status"])
        self.assertEqual(code, 0)
        self.assertEqual(self.run_main(["D02", "--resolve", "published"])[0], 2)  # 불확실이 아니면 풀 수 없다


if __name__ == "__main__":
    unittest.main(verbosity=2)
