#!/usr/bin/env python3
"""새 글 파일의 뼈대를 만든다 (Claude 없이 직접 쓰기 위한 도구).

사용:
  python scripts/new_post.py D10 --slug char-limit --title "글자 수 제한을 세지 않고 쓰면"

하는 일:
  - 일정표의 해당 행(날짜가 정해져 있고 상태가 '미정')을 읽어 `posts/daily/D10-2026-MM-DD-<slug>.md` 를 만든다.
  - 일정표의 글 제목을 채우고 상태를 '초안'으로 바꾼다.
  - 파일에는 본문 자리, **근거표 틀**, 과장 주의 칸, 체크리스트, 게시 후 기록 표가 들어 있다.

다음 순서:
  1. 본문(코드 블록)을 쓴다. 사실 주장마다 근거표에 한 행을 적는다 (근거 파일, 그 파일에 **그대로 있는 문구**, 결과).
  2. `python scripts/check.py --stamp D10` 으로 대조한 날짜와 본문 해시를 기록한다.
  3. `python scripts/approve.py D10` 으로 확정한다 (사람이 yes 입력).
이 도구는 글이 근거와 **맞는지**는 판단하지 못한다. 대조는 사람이 한다.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


def build_text(post_id: str, label: str, title: str, today: str) -> str:
    fence = "`" * 3
    lines = [
        f"# {post_id} · {label} · {title}",
        "",
        f"- 상태: **초안** ({today} 작성. 근거표 대조 전)",
        "- 글자 수: 0자",
        "- 근거: (근거 파일과 위치를 적는다)",
        "",
        fence,
        "(여기에 본문을 쓴다. 독자에게 지시하는 문장(~하세요)은 피하고 해본 것을 기록한다)",
        fence,
        "",
        "## 근거표 (본문의 사실 주장마다 한 행. 요청이나 다짐 문장은 사실 주장이 아니라 제외)",
        "| 본문 주장 | 근거 파일 | 근거 인용 | 결과 |",
        "|---|---|---|---|",
        "| (본문의 사실 주장) | `validation-log.md` | (그 파일에 그대로 있는 문구) | 일치 |",
        "",
        "## 과장하면 안 되는 점",
        "- (일반화하지 말아야 할 것, 한 번의 결과라는 점 등)",
        "",
        "## 올리기 전 체크",
        "- [ ] 근거표를 대조하고 `check.py --stamp` 로 기록했는가",
        "- [ ] 독자에게 하라고 지시하는 문장이 없는가",
        "- [ ] 오타 없음",
        "",
        "## 게시 후 기록",
        "| 조회 | 저장 | 공유 | 요청한 사람(서로 다른) | 확인일 |",
        "|---|---|---|---|---|",
        "| | | | | |",
        "",
    ]
    return "\n".join(lines)


def create(root: Path, post_id: str, slug: str, title: str, *, now: datetime, out=print) -> int:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        out("--slug 는 영문 소문자, 숫자, 하이픈만 쓸 수 있습니다 (예: char-limit)")
        return 2
    if not title.strip():
        out("--title 이 필요합니다")
        return 2
    sched_path = root / "posts" / "schedule.md"
    if not sched_path.exists():
        out("posts/schedule.md 를 찾지 못했습니다")
        return 2
    raw = sched_path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    sched = raw.replace("\r\n", "\n")
    m = re.search(rf"^\| {post_id} \| (\d\d)/(\d\d) \((.)\) \| ([^|]*)\| ([^|]*)\| ([^|]*)\|$", sched, re.M)
    if not m:
        out(f"일정표에서 {post_id} 행을 찾지 못했습니다")
        return 2
    month, day, weekday, _old_title, status, _note = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5).strip(), m.group(6)
    if status != "미정":
        out(f"{post_id} 의 일정표 상태가 '{status}'입니다. 상태가 '미정'인 칸에만 새 글을 만듭니다")
        return 1
    daily = root / "posts" / "daily"
    if list(daily.glob(f"{post_id}-*.md")):
        out(f"{post_id} 글 파일이 이미 있습니다")
        return 1
    name = f"{post_id}-{now.year}-{month}-{day}-{slug}.md"
    daily.mkdir(parents=True, exist_ok=True)
    (daily / name).write_bytes(build_text(post_id, f"{now.year}-{month}-{day} ({weekday})", title.strip(), f"{now:%Y-%m-%d}").replace("\n", nl).encode("utf-8"))
    new_row = f"| {post_id} | {month}/{day} ({weekday}) | {title.strip()} | 초안 | `daily/{post_id}-...` |"
    sched = sched.replace(m.group(0), new_row, 1)
    sched_path.write_bytes(sched.replace("\n", nl).encode("utf-8"))
    out(f"만들었습니다: posts/daily/{name}")
    out("다음: 본문과 근거표를 쓰고 -> python scripts/check.py --stamp " + post_id + " -> python scripts/approve.py " + post_id)
    return 0


def main(argv=None, *, root: Path | None = None, now: datetime | None = None, out=print) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="새 글 파일의 뼈대 만들기")
    ap.add_argument("post_id", help="예: D10")
    ap.add_argument("--slug", required=True, help="파일 이름에 쓸 영문 이름 (예: char-limit)")
    ap.add_argument("--title", required=True, help="일정표와 글 제목")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(root or args.root or Path(__file__).resolve().parent.parent).resolve()
    return create(root, args.post_id, args.slug, args.title, now=now or datetime.now(), out=out)


if __name__ == "__main__":
    sys.exit(main())
