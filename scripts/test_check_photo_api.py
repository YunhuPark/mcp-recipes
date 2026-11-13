"""check_photo_api.py 시험. 가짜 네트워크로 '발행을 부르지 않는다'와 실패 처리를 확인한다."""
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
import check_photo_api  # noqa: E402
import post  # noqa: E402
from test_post import FAKE, FakeTransport, make_root  # noqa: E402

BASE = "https://img.test/raw/main"


class CheckPhotoApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmp.name))
        env = {"THREADS_ACCESS_TOKEN": FAKE, "THREADS_USER_ID": "12345"}
        self._env = mock.patch.dict(os.environ, env, clear=False)
        self._env.start()
        self._base = mock.patch.object(post, "default_image_base", return_value=BASE)
        self._base.start()
        names, self.files = [], {}
        for i in range(3):
            rel = f"posts/images/D02/D02-{i + 1}.jpg"
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"\xff\xd8x" + str(i).encode())
            self.files[post.image_urls_for(BASE, [rel])[0]] = (200, f.read_bytes())
            names.append(rel)
        daily = next((self.root / "posts" / "daily").glob("D02-*.md"))
        daily.write_text(daily.read_text(encoding="utf-8").replace("- 글자 수: 10자\n", "- 글자 수: 10자\n- 사진: " + ", ".join(names) + "\n", 1), encoding="utf-8")

    def tearDown(self):
        self._base.stop()
        self._env.stop()
        self._tmp.cleanup()

    def run_main(self, t):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_photo_api.main(["D02"], transport=t, root=self.root, sleep=lambda s: None, wait=0)
        return code, out.getvalue()

    def test_creates_containers_and_never_publishes(self):
        t = FakeTransport([(200, {"id": "K1"}), (200, {"id": "K2"}), (200, {"id": "K3"}), (200, {"id": "P"}),
                           (200, {"status": "FINISHED"}), (200, {"status": "FINISHED"}), (200, {"status": "FINISHED"}),
                           (200, {"status": "FINISHED"})], files=self.files)
        code, out = self.run_main(t)
        self.assertEqual(code, 0, out)
        self.assertFalse(any("threads_publish" in c[1] for c in t.calls))
        self.assertEqual(t.calls[3][2]["media_type"], "CAROUSEL")
        self.assertEqual(t.calls[3][2]["children"], "K1,K2,K3")
        self.assertNotIn(FAKE, out)
        self.assertFalse((self.root / post.STATE_FILE).exists())

    def test_stops_when_a_child_is_rejected(self):
        t = FakeTransport([(200, {"id": "K1"}), (400, {"error": {"message": "bad image"}})], files=self.files)
        code, out = self.run_main(t)
        self.assertEqual(code, 1)
        self.assertEqual(len(t.calls), 2)
        self.assertIn("실패", out)

    def test_does_not_call_the_api_when_a_picture_is_not_public(self):
        self.files.pop(next(iter(self.files)))
        t = FakeTransport([], files=self.files)
        code, out = self.run_main(t)
        self.assertEqual((code, t.calls), (1, []))
        self.assertIn("API는 부르지 않았습니다", out)


if __name__ == "__main__":
    unittest.main()
