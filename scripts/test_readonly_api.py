"""post.py --check-token 와 insights.py 시험. 실제 Threads를 부르지 않고 가짜 네트워크로 확인한다.

실행: python -m unittest scripts/test_readonly_api.py -v   (저장소 루트에서)
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
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import insights  # noqa: E402
import post  # noqa: E402

FAKE = "TESTONLY-not-a-real-credential"
NOW = datetime(2026, 10, 21, 9, 0)


class FakeTransport:
    """호출을 기록하고, 준비한 응답을 순서대로 돌려준다. 응답이 예외이면 던진다."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def request(self, method, url, data, timeout=30):
        self.calls.append((method, url, data))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def run(func, *args, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = func(*args, **kw)
    return code, out.getvalue()


class CheckTokenTests(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("THREADS_") and k not in ("IG_ACCESS_TOKEN", "IG_USER_ID")}
        env.update({"THREADS_ACCESS_TOKEN": FAKE, "THREADS_USER_ID": "12345", "THREADS_TOKEN_EXPIRES": "2026-12-20"})
        self._env = mock.patch.dict(os.environ, env, clear=True)
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def check(self, script):
        t = FakeTransport(script)
        code, out = run(post.cmd_check_token, t, NOW)
        return code, out, t

    def test_valid_token_and_same_account(self):
        code, out, t = self.check([(200, {"id": "12345"})])
        self.assertEqual(code, 0, out)
        self.assertIn("유효", out)
        self.assertEqual(len(t.calls), 1)
        self.assertEqual(t.calls[0][0], "GET")  # 읽기 전용: 게시(POST)하지 않는다
        self.assertNotIn("threads_publish", t.calls[0][1])

    def test_a_different_account_is_refused(self):
        code, out, _ = self.check([(200, {"id": "99999"})])
        self.assertEqual(code, 1)
        self.assertIn("다릅니다", out)

    def test_http_error_is_reported_without_leaking_the_token(self):
        code, out, _ = self.check([(401, {"error": {"type": "OAuthException", "code": 190, "message": f"Invalid token {FAKE}"}})])
        self.assertEqual(code, 1)
        self.assertNotIn(FAKE, out)

    def test_network_error_is_reported(self):
        code, out, _ = self.check([post.NetworkError("TimeoutError")])
        self.assertEqual(code, 1)
        self.assertNotIn(FAKE, out)

    def test_odd_response_is_refused(self):
        code, out, _ = self.check([(200, {"nothing": 1})])
        self.assertEqual(code, 1)

    def test_missing_credentials_make_no_call(self):
        del os.environ["THREADS_ACCESS_TOKEN"]
        os.environ["IG_ACCESS_TOKEN"] = FAKE + "-instagram"  # 다른 토큰으로 대체하지 않는다
        code, out, t = self.check([])
        self.assertEqual(code, 1)
        self.assertEqual(t.calls, [])

    def test_expired_token_is_warned(self):
        os.environ["THREADS_TOKEN_EXPIRES"] = "2026-10-01"
        code, out, _ = self.check([(200, {"id": "12345"})])
        self.assertIn("만료", out)


def make_root(tmp: Path) -> Path:
    daily = tmp / "posts" / "daily"
    daily.mkdir(parents=True)
    rows = []
    for pid, body in (("D01", "첫 글입니다\n둘째 줄"), ("D02", "둘째 글입니다")):
        (daily / f"{pid}-test.md").write_text(
            f"# {pid}\n\n- 상태: **게시됨** (시험)\n- 글자 수: 10자\n\n```\n{body}\n```\n\n## 게시 후 기록\n| 조회 |\n|---|\n| |\n",
            encoding="utf-8")
        rows.append(f"| {pid} | 10/14 (수) | 시험 | 게시됨 | |")
    (tmp / "posts" / "schedule.md").write_text(
        "| 일차 | 날짜 | 글 | 상태 | 비고 |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return tmp


def insights_body(views, likes=0, replies=0, reposts=0, quotes=0):
    vals = dict(views=views, likes=likes, replies=replies, reposts=reposts, quotes=quotes)
    return {"data": [{"name": k, "period": "lifetime", "values": [{"value": v}], "title": k, "id": "x"} for k, v in vals.items()]}


class InsightsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def collect(self, script):
        t = FakeTransport(script)
        return insights.collect(self.root, t, FAKE), t

    def test_matches_posts_by_body_and_reads_metrics(self):
        listing = (200, {"data": [
            {"id": "m2", "text": "둘째 글입니다", "timestamp": "2026-10-15T01:51:00+0000"},
            {"id": "m1", "text": "첫 글입니다\n둘째 줄", "timestamp": "2026-10-14T02:53:00+0000"}]})
        rows, t = self.collect([listing, (200, insights_body(4)), (200, insights_body(130, likes=1))])
        self.assertEqual([r["id"] for r in rows], ["D01", "D02"])
        by = {r["id"]: r for r in rows}
        self.assertEqual((by["D01"]["views"], by["D01"]["likes"]), (130, 1))
        self.assertEqual(by["D02"]["views"], 4)

    def test_every_call_is_a_read(self):
        listing = (200, {"data": [{"id": "m1", "text": "첫 글입니다\n둘째 줄", "timestamp": "t"}]})
        _, t = self.collect([listing, (200, insights_body(1))])
        self.assertTrue(all(c[0] == "GET" for c in t.calls))
        self.assertFalse(any("publish" in c[1] or c[1].endswith("/threads") for c in t.calls))

    def test_threads_without_a_matching_local_post_are_skipped(self):
        listing = (200, {"data": [{"id": "mx", "text": "다른 글", "timestamp": "t"}]})
        rows, t = self.collect([listing])
        self.assertEqual(rows, [])
        self.assertEqual(len(t.calls), 1)  # 짝이 없으면 지표를 읽으러 가지 않는다

    def test_whitespace_differences_still_match(self):
        listing = (200, {"data": [{"id": "m1", "text": "첫  글입니다   둘째 줄 ", "timestamp": "t"}]})
        rows, _ = self.collect([listing, (200, insights_body(5))])
        self.assertEqual([r["id"] for r in rows], ["D01"])

    def test_a_failed_metric_call_leaves_blanks_instead_of_crashing(self):
        listing = (200, {"data": [{"id": "m1", "text": "첫 글입니다\n둘째 줄", "timestamp": "t"}]})
        rows, _ = self.collect([listing, (403, {"error": {"message": "permission"}})])
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["views"])

    def test_list_failure_raises_a_clear_error_without_the_token(self):
        t = FakeTransport([(401, {"error": {"type": "OAuthException", "code": 190, "message": f"bad {FAKE}"}})])
        with self.assertRaises(RuntimeError) as cm:
            insights.fetch_threads(t, FAKE)
        self.assertNotIn(FAKE, str(cm.exception))

    def test_main_prints_a_table_and_json(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("THREADS_")}
        env.update({"THREADS_ACCESS_TOKEN": FAKE, "THREADS_USER_ID": "12345"})
        listing = (200, {"data": [{"id": "m1", "text": "첫 글입니다\n둘째 줄", "timestamp": "2026-10-14T02:53:00+0000"}]})
        with mock.patch.dict(os.environ, env, clear=True):
            code, out = run(insights.main, [], transport=FakeTransport([listing, (200, insights_body(130))]), root=self.root)
            self.assertEqual(code, 0, out)
            self.assertIn("D01", out)
            self.assertIn("130", out)
            self.assertNotIn(FAKE, out)
            code, out = run(insights.main, ["--json"], transport=FakeTransport([listing, (200, insights_body(130))]), root=self.root)
            self.assertEqual(json.loads(out)[0]["views"], 130)

    def test_main_without_credentials_makes_no_call(self):
        t = FakeTransport([])
        env = {k: v for k, v in os.environ.items() if not k.startswith("THREADS_")}
        with mock.patch.dict(os.environ, env, clear=True):
            code, out = run(insights.main, [], transport=t, root=self.root)
        self.assertEqual(code, 1)
        self.assertEqual(t.calls, [])


if __name__ == "__main__":
    unittest.main()
