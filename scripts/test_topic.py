"""post.py 의 주제 태그(topic_tag) 시험. 실제 Threads를 부르지 않고 가짜 네트워크로 확인한다.

실행: python -m unittest scripts/test_topic.py -v   (저장소 루트에서)
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import post  # noqa: E402
import test_post as tp  # noqa: E402  (가짜 통신, 시험용 글 만들기를 재사용)


class ValidateTests(unittest.TestCase):
    def test_valid_tags(self):
        for tag in ("AI Threads", "a", "가" * 50, "AI 도구"):
            with self.subTest(tag=tag):
                self.assertIsNone(post.validate_topic(tag))

    def test_invalid_tags(self):
        for tag in ("", "가" * 51, "AI.Threads", "AI & Threads", "끝에 마침표."):
            with self.subTest(tag=tag):
                self.assertIsNotNone(post.validate_topic(tag))


class TopicPublishTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = tp.make_root(Path(self._tmp.name))
        env = {k: v for k, v in os.environ.items() if not k.startswith("THREADS_") and k not in ("IG_ACCESS_TOKEN", "IG_USER_ID")}
        env.update({"THREADS_LIVE": "yes", "THREADS_ACCESS_TOKEN": tp.FAKE, "THREADS_USER_ID": "12345",
                    "THREADS_TOKEN_EXPIRES": "2026-12-01"})
        self._env = mock.patch.dict(os.environ, env, clear=True)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def run_main(self, argv, transport):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = post.main(argv + ["--root", str(self.root), "--wait", "0"], transport=transport, now=tp.NOW, root=self.root,
                             confirm=lambda: "yes", sleep=lambda s: None, check=tp.OK_CHECK)
        return code, out.getvalue()

    def container_data(self, t):
        return t.calls[0][2]

    def test_topic_tag_is_sent_in_the_container_when_given(self):
        t = tp.FakeTransport(tp.good_script())
        code, out = self.run_main(["D02", "--publish", "--topic", "AI Threads"], t)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.container_data(t)["topic_tag"], "AI Threads")
        self.assertIn("AI Threads", out)

    def test_no_topic_tag_is_sent_when_none_is_given(self):
        t = tp.FakeTransport(tp.good_script())
        code, out = self.run_main(["D02", "--publish"], t)
        self.assertEqual(code, 0, out)
        self.assertNotIn("topic_tag", self.container_data(t))
        self.assertIn("(없음)", out)

    def test_env_default_is_used_and_the_flag_overrides_it(self):
        os.environ["THREADS_TOPIC_TAG"] = "환경 기본"
        t = tp.FakeTransport(tp.good_script())
        self.run_main(["D02", "--publish"], t)
        self.assertEqual(self.container_data(t)["topic_tag"], "환경 기본")
        self.root = tp.make_root(Path(tempfile.mkdtemp()))  # 첫 게시가 글 상태를 '게시됨'으로 바꾸므로 새로 만든다
        t2 = tp.FakeTransport(tp.good_script())
        self.run_main(["D02", "--publish", "--topic", "직접 지정"], t2)
        self.assertEqual(self.container_data(t2)["topic_tag"], "직접 지정")

    def test_empty_flag_turns_the_env_default_off(self):
        os.environ["THREADS_TOPIC_TAG"] = "환경 기본"
        t = tp.FakeTransport(tp.good_script())
        self.run_main(["D02", "--publish", "--topic", ""], t)
        self.assertNotIn("topic_tag", self.container_data(t))

    def test_an_invalid_tag_stops_before_any_call(self):
        for tag in ("AI.Threads", "AI & Threads", "가" * 51):
            with self.subTest(tag=tag):
                t = tp.FakeTransport([])
                code, out = self.run_main(["D02", "--publish", "--topic", tag], t)
                self.assertEqual(code, 1)
                self.assertEqual(t.calls, [])
                self.assertIn("주제 태그", out)

    def test_dry_run_shows_the_tag_and_makes_no_call(self):
        t = tp.FakeTransport([])
        code, out = self.run_main(["D02", "--topic", "AI Threads"], t)
        self.assertEqual(code, 0)
        self.assertEqual(t.calls, [])
        self.assertIn("주제 태그: AI Threads", out)

    def test_the_posted_text_is_unchanged_by_the_tag(self):
        t = tp.FakeTransport(tp.good_script())
        self.run_main(["D02", "--publish", "--topic", "AI Threads"], t)
        self.assertEqual(self.container_data(t)["text"], "D02 본문입니다\n두 번째 줄")


if __name__ == "__main__":
    unittest.main()
