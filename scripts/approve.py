#!/usr/bin/env python3
"""글을 '검수완료'로 확정하는 도우미. **확정은 사람이 직접 한다** (마지막에 'yes' 입력).

사용:
  python scripts/approve.py D10
  python scripts/approve.py --batch            # 초안인 글 전부를 한 번에 보고 'yes' 한 번으로 확정 (하나라도 점검에 실패하면 전체 중단)
  python scripts/approve.py --batch --dry-run  # 확정하지 않고 각 글이 점검을 통과하는지만 보여 줌

하는 일 (Claude 없이):
  1. 글이 초안인지, 일정표에도 초안으로 되어 있는지 확인한다.
  2. 확정했다고 가정하고 `check.py` 를 돌린다 (근거표, 대조 뒤 본문이 바뀌지 않았는지, 개인 정보, 글자 수 ...).
     통과하지 못하면 이유를 보여 주고 아무것도 바꾸지 않는다.
  3. 본문, 글자 수, 근거표를 보여 주고 정확히 'yes' 를 입력받는다.
  4. 글 파일과 일정표의 상태를 '검수완료'로 바꾼다. (커밋은 하지 않는다)

이 도구는 근거표가 **사실에 맞는지**는 판단하지 못한다. 인용이 근거 파일에 있는지와 본문이 대조 뒤 바뀌지 않았는지만 본다.
대조 자체는 사람이 하고, 끝낸 뒤 `python scripts/check.py --stamp D10` 으로 기록해야 확정할 수 있다.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check as check_mod  # noqa: E402
import post as post_mod  # noqa: E402
from threads_text import LIMIT, threads_len  # noqa: E402

STATUS_RE = re.compile(r"- 상태: \*\*[^*]+\*\*[^\n]*")


def find_file(root: Path, post_id: str) -> Path | None:
    found = sorted((root / "posts" / "daily").glob(f"{post_id}-*.md"))
    return found[0] if len(found) == 1 else None


def _read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def _with_status(text: str, nl: str, line: str) -> str:
    return STATUS_RE.sub(lambda m: line, text.replace("\r\n", "\n"), count=1).replace("\n", nl)


def _row_status(schedule_text: str, post_id: str) -> str | None:
    m = re.search(rf"^\| {post_id} \| [^|]*\| [^|]*\| ([^|]*)\|", schedule_text, re.M)
    return m.group(1).strip() if m else None


def _set_row_status(schedule_text: str, post_id: str, old: str, new: str) -> str:
    return re.sub(rf"(^\| {post_id} \| [^|]*\| [^|]*\| ){old}( \|)", rf"\g<1>{new}\g<2>", schedule_text, count=1, flags=re.M)


def approve(root: Path, post_id: str, *, now: datetime, confirm, check=post_mod.run_site_check, out=print) -> int:
    path = find_file(root, post_id)
    sched_path = root / "posts" / "schedule.md"
    if path is None or not sched_path.exists():
        out(f"{post_id} 글 파일이나 일정표를 찾지 못했습니다")
        return 2
    text, nl = _read(path)
    status = check_mod.file_status(text)
    if status == "검수완료":
        out("이미 검수완료입니다")
        return 0
    if status != "초안":
        out(f"글 파일의 상태가 '{status}'입니다. 초안만 확정할 수 있습니다")
        return 1
    sched_raw, sched_nl = _read(sched_path)
    sched = sched_raw.replace("\r\n", "\n")
    row = _row_status(sched, post_id)
    if row != "초안":
        out(f"일정표의 상태가 '{row}'입니다. 일정표도 초안이어야 합니다")
        return 1

    new_line = f"- 상태: **검수완료** ({now:%Y-%m-%d}, 사용자 확인. approve.py로 확정)"
    approved_text = _with_status(text, nl, new_line)
    approved_sched = _set_row_status(sched, post_id, "초안", "검수완료").replace("\n", sched_nl)

    # 시험 삼아 확정한 상태로 점검한다. 실패하면 되돌리고 아무것도 바꾸지 않는다.
    path.write_bytes(approved_text.encode("utf-8"))
    sched_path.write_bytes(approved_sched.encode("utf-8"))
    try:
        ok, report = check(root)
    finally:
        path.write_bytes(text.encode("utf-8"))
        sched_path.write_bytes(sched_raw.encode("utf-8"))
    if not ok:
        out("확정할 수 없습니다. 점검이 통과하지 못했습니다 (아무것도 바꾸지 않았습니다):")
        out(report)
        return 1

    body = check_mod.first_code_block(text.replace("\r\n", "\n")) or ""
    out(f"== {post_id} ({path.name}) ==")
    out(body)
    out(f"-- Threads 기준 길이 {threads_len(body)} / {LIMIT} --\n")
    section = check_mod.evidence_section(text)
    if section:
        out("[근거표]")
        out(section.strip())
    answer = confirm() if confirm else (input("\n위 내용으로 검수완료로 확정합니다. 정확히 'yes' 를 입력하세요: ") if sys.stdin.isatty() else "")
    if str(answer).strip() != "yes":
        out("확인되지 않아 확정하지 않았습니다.")
        return 1
    path.write_bytes(approved_text.encode("utf-8"))
    sched_path.write_bytes(approved_sched.encode("utf-8"))
    out(f"{post_id} 를 검수완료로 확정했습니다. (커밋은 하지 않았습니다)")
    return 0


def _draft_ids(root: Path) -> list[str]:
    """글 파일과 일정표가 모두 초안인 글 번호."""
    sched_path = root / "posts" / "schedule.md"
    sched = sched_path.read_bytes().decode("utf-8").replace("\r\n", "\n") if sched_path.exists() else ""
    ids = []
    for path in sorted((root / "posts" / "daily").glob("D*-*.md")):
        pid = path.name[:3]
        text = path.read_bytes().decode("utf-8")
        if check_mod.file_status(text) == "초안" and _row_status(sched, pid) == "초안":
            ids.append(pid)
    return ids


def approve_batch(root: Path, *, now: datetime, confirm, check=post_mod.run_site_check, out=print, dry_run: bool = False) -> int:
    ids = _draft_ids(root)
    if not ids:
        out("확정할 초안이 없습니다")
        return 0
    sched_path = root / "posts" / "schedule.md"
    sched_raw, sched_nl = _read(sched_path)
    plans = {}
    for pid in ids:
        path = find_file(root, pid)
        text, nl = _read(path)
        plans[pid] = (path, text, _with_status(text, nl, f"- 상태: **검수완료** ({now:%Y-%m-%d}, 사용자 확인. approve.py --batch로 확정)"))

    # 1) 글마다 '그 글만 확정했다고 가정하고' 점검한다. 끝나면 항상 원래대로 돌려 놓는다.
    failed = []
    for pid in ids:
        path, text, approved = plans[pid]
        approved_sched = _set_row_status(sched_raw.replace("\r\n", "\n"), pid, "초안", "검수완료").replace("\n", sched_nl)
        path.write_bytes(approved.encode("utf-8"))
        sched_path.write_bytes(approved_sched.encode("utf-8"))
        try:
            ok, report = check(root)
        finally:
            path.write_bytes(text.encode("utf-8"))
            sched_path.write_bytes(sched_raw.encode("utf-8"))
        out(f"{pid}: {'통과' if ok else '실패'}")
        if not ok:
            failed.append((pid, report))
    if failed:
        out("\n점검에 실패한 글이 있어 확정하지 않았습니다 (아무것도 바꾸지 않았습니다):")
        for pid, report in failed:
            out(f"\n[{pid}]\n{report}")
        return 1
    if dry_run:
        out(f"\n--dry-run: {len(ids)}개 모두 점검을 통과했습니다. 확정은 하지 않았습니다.")
        return 0

    # 2) 전부 통과했으면 모두 보여 주고 한 번만 묻는다.
    for pid in ids:
        path, text, _ = plans[pid]
        body = check_mod.first_code_block(text.replace("\r\n", "\n")) or ""
        out(f"\n===== {pid} ({path.name}) =====")
        out(body)
        out(f"-- Threads 기준 길이 {threads_len(body)} / {LIMIT} --")
        section = check_mod.evidence_section(text)
        if section:
            out("[근거표]")
            out(section.strip())
    answer = confirm() if confirm else (input(f"\n위 {len(ids)}개를 모두 검수완료로 확정합니다. 정확히 'yes' 를 입력하세요: ") if sys.stdin.isatty() else "")
    if str(answer).strip() != "yes":
        out("확인되지 않아 확정하지 않았습니다.")
        return 1
    new_sched = sched_raw.replace("\r\n", "\n")
    for pid in ids:
        path, text, approved = plans[pid]
        path.write_bytes(approved.encode("utf-8"))
        new_sched = _set_row_status(new_sched, pid, "초안", "검수완료")
    sched_path.write_bytes(new_sched.replace("\n", sched_nl).encode("utf-8"))
    ok, report = check(root)
    if not ok:  # 마지막 점검에 실패하면 전부 되돌린다
        for pid in ids:
            plans[pid][0].write_bytes(plans[pid][1].encode("utf-8"))
        sched_path.write_bytes(sched_raw.encode("utf-8"))
        out("최종 점검에 실패해 모두 되돌렸습니다:")
        out(report)
        return 1
    out(f"\n{len(ids)}개를 검수완료로 확정했습니다: {', '.join(ids)} (커밋은 하지 않았습니다)")
    return 0


def main(argv=None, *, root: Path | None = None, now: datetime | None = None, confirm=None,
         check=post_mod.run_site_check, out=print) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="글을 검수완료로 확정 (사람이 직접 yes 를 입력)")
    ap.add_argument("post_id", nargs="?", help="예: D10")
    ap.add_argument("--batch", action="store_true", help="초안인 글 전부를 한 번에 확정")
    ap.add_argument("--dry-run", action="store_true", help="--batch 와 함께: 점검만 하고 확정하지 않음")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(root or args.root or Path(__file__).resolve().parent.parent).resolve()
    if args.batch:
        return approve_batch(root, now=now or datetime.now(), confirm=confirm, check=check, out=out, dry_run=args.dry_run)
    if not args.post_id:
        ap.print_help()
        return 2
    return approve(root, args.post_id, now=now or datetime.now(), confirm=confirm, check=check, out=out)


if __name__ == "__main__":
    sys.exit(main())
