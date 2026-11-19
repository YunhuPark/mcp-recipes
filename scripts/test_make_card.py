"""make_card.py 시험: 크기, 줄바꿈이 폭을 넘지 않는지, 사진 줄 넣기(한 번만)."""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_card  # noqa: E402


class MakeCardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        daily = self.root / "posts" / "daily"
        daily.mkdir(parents=True)
        self.post = daily / "D99-test.md"
        self.post.write_text("# D99\n\n- 상태: **초안**\n- 글자 수: 10자\n\n```\n본문\n```\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def run_main(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = make_card.main(["D99", "--big", "25/25", "--title", "지시 없이 맡긴 광고 CSV", "--line", "중복 행과 합계 행을 스스로 처리",
                                   "--note", "합성 CSV 1개, 한 번의 결과", *extra], root=self.root)
        return code, out.getvalue()

    def test_makes_a_square_png_in_the_images_folder(self):
        code, _ = self.run_main()
        p = self.root / "posts/images/D99/D99-card.png"
        self.assertEqual(code, 0)
        self.assertEqual(Image.open(p).size, (1080, 1080))

    def test_wrapped_lines_never_exceed_the_width(self):
        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        f = make_card.font(False, 44)
        long = "아주긴단어" * 30 + " 그리고 평범한 문장이 이어집니다 " * 3
        for line in make_card.wrap(d, long, f, 900):
            self.assertLessEqual(d.textlength(line, font=f), 900)

    def test_attach_adds_the_photo_line_once_without_touching_the_body(self):
        self.run_main("--attach")
        text = self.post.read_text(encoding="utf-8")
        self.assertIn("- 사진: posts/images/D99/D99-card.png", text)
        self.assertIn("```\n본문\n```", text)
        _, out = self.run_main("--attach")
        self.assertEqual(self.post.read_text(encoding="utf-8").count("- 사진:"), 1)
        self.assertIn("이미 사진 줄이 있어", out)

    def test_too_long_description_is_refused_instead_of_overflowing(self):
        with self.assertRaises(SystemExit):
            make_card.make_card(self.root / "x.png", "1", "t", ["가나다 " * 400], "n")


if __name__ == "__main__":
    unittest.main()
