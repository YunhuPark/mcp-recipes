#!/usr/bin/env python3
"""결과 카드 이미지(1080x1080)를 만든다. 큰 숫자 하나와 짧은 설명 몇 줄만 담는다.

  python scripts/make_card.py D29 --big "25/25" --title "지시 없이 맡긴 광고 CSV" \\
      --line "중복 행과 합계 행을 스스로 처리" --note "합성 CSV 1개, 한 번의 결과" [--attach]

결과는 posts/images/D29/D29-card.png. --attach 는 글 파일 머리(본문 밖)에 `- 사진:` 줄을 넣는다.
카드에는 시험의 한계를 한 줄(--note)로 꼭 적는다. 숫자만 크게 보이고 "한 번의 결과"가 빠지는 것을 막으려는 것이다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W = H = 1080
MARGIN = 90
BG, ACCENT, TITLE, BODY, NOTE = "#0f172a", "#22c55e", "#cbd5e1", "#e2e8f0", "#94a3b8"
FONT_DIR = Path(os.environ.get("CARD_FONT_DIR", r"C:\Windows\Fonts"))  # shortcut: Windows 글꼴만 찾는다, 다른 OS는 CARD_FONT_DIR 로 맑은 고딕 호환 글꼴 폴더를 준다


def font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    p = FONT_DIR / ("malgunbd.ttf" if bold else "malgun.ttf")
    if not p.exists():
        raise SystemExit(f"한글 글꼴을 찾지 못했습니다: {p} (CARD_FONT_DIR 환경 변수로 글꼴 폴더를 지정하세요)")
    return ImageFont.truetype(str(p), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, f, max_w: int) -> list[str]:
    """공백 단위로 줄을 나누고, 한 단어가 너무 길면 글자 단위로 자른다."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=f) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            if draw.textlength(cur + ch, font=f) > max_w and cur:
                lines.append(cur)
                cur = ""
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def make_card(out: Path, big: str, title: str, lines: list[str], note: str) -> Path:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    max_w = W - 2 * MARGIN
    y = 110
    for t in wrap(d, title, font(True, 46), max_w)[:2]:
        d.text((MARGIN, y), t, font=font(True, 46), fill=TITLE)
        y += 64
    size = 360  # 큰 숫자는 폭에 맞춰 글자 크기를 줄인다
    while size > 80 and d.textlength(big, font=font(True, size)) > max_w:
        size -= 10
    f_big = font(True, size)
    d.text((W / 2, 390), big, font=f_big, fill=ACCENT, anchor="mm")
    y = 610
    for line in lines:
        for t in wrap(d, line, font(False, 42), max_w):
            d.text((MARGIN, y), t, font=font(False, 42), fill=BODY)
            y += 58
        y += 10
    if y > H - 200:
        raise SystemExit(f"설명이 너무 깁니다 (카드 아래 여백을 넘음). 줄 수나 길이를 줄이세요")
    d.line([(MARGIN, H - 150), (W - MARGIN, H - 150)], fill="#334155", width=2)
    ny = H - 125
    for t in wrap(d, note, font(False, 32), max_w)[:2]:
        d.text((MARGIN, ny), t, font=font(False, 32), fill=NOTE)
        ny += 44
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def attach(post_file: Path, rel: str) -> bool:
    raw = post_file.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    t = raw.replace("\r\n", "\n")
    if re.search(r"(?m)^-\s*사진:", t):
        return False
    t = re.sub(r"(?m)^(- 글자 수:[^\n]*)$", lambda m: m.group(1) + f"\n- 사진: {rel}", t, count=1)
    post_file.write_bytes(t.replace("\n", nl).encode("utf-8"))
    return True


def main(argv=None, root: Path | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="결과 카드 이미지 만들기")
    ap.add_argument("post_id", help="예: D29")
    ap.add_argument("--big", required=True, help="큰 숫자, 예: 25/25")
    ap.add_argument("--title", required=True)
    ap.add_argument("--line", action="append", default=[], help="설명 줄 (여러 번 가능)")
    ap.add_argument("--note", required=True, help="한계를 밝히는 한 줄, 예: 합성 CSV 1개, 한 번의 결과")
    ap.add_argument("--attach", action="store_true", help="글 파일에 `- 사진:` 줄을 넣는다")
    a = ap.parse_args(argv)
    root = (root or Path(__file__).resolve().parent.parent).resolve()
    rel = f"posts/images/{a.post_id}/{a.post_id}-card.png"
    make_card(root / rel, a.big, a.title, a.line, a.note)
    print(f"카드를 만들었습니다: {rel}")
    if a.attach:
        files = sorted((root / "posts" / "daily").glob(f"{a.post_id}-*.md"))
        if not files:
            print("글 파일을 찾지 못해 사진 줄은 넣지 않았습니다")
        elif attach(files[0], rel):
            print(f"{files[0].name} 에 사진 줄을 넣었습니다")
        else:
            print(f"{files[0].name} 에는 이미 사진 줄이 있어 넣지 않았습니다 (직접 고치세요)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
