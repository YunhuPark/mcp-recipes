#!/usr/bin/env python3
"""진행 현황 요약.

저장소의 파일(README, posts/schedule.md, posts/daily, posts/0*.md)을 읽어
지금 상태를 한 화면으로 보여 준다. 파일을 수정하지 않는다.

  python scripts/status.py                  # 오늘 기준
  python scripts/status.py --today 2026-10-20   # 날짜를 바꿔 보기(시험용)
  python scripts/status.py --root DIR       # 다른 폴더를 읽기(시험용)

주의
  - 판단 기준(계속/조정/접기)은 README의 표에서 읽는다. 스크립트에 따로 적지 않았다.
  - '요청한 서로 다른 사람'의 공식 값은 posts/schedule.md 의 주간 집계 표다.
    글별 기록을 합치면 같은 사람이 여러 글에 요청한 경우 중복되므로 참고용으로만 보여 준다.
  - 중간에는 계속/접기를 판정하지 않는다. 최종 판단은 README의 판단일에 4주 누적으로 한다.
  - 집계 숫자만 다룬다. 댓글 아이디나 본문은 이 저장소에 두지 않는다.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

WEEKDAY = "월화수목금토일"
BUFFER_MIN = 3  # README 운영 규칙: 버퍼가 3개 아래로 내려가면 새 글 작성과 검증을 우선


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def parse_date(s: str) -> date | None:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def fmt(d: date) -> str:
    return f"{d.month:02d}/{d.day:02d} ({WEEKDAY[d.weekday()]})"


def parse_readme(text: str) -> dict:
    info: dict = {"start": None, "end": None, "decision": None, "go": None, "adj": None}
    for line in text.splitlines():
        if line.startswith("| 첫 게시"):
            info["start"] = parse_date(line)
        elif line.startswith("| 기간"):
            ds = re.findall(r"\d{4}-\d{2}-\d{2}", line)
            if len(ds) >= 2:
                info["end"] = parse_date(ds[1])
            m = re.search(r"글\s*(\d+)개", line)
            info["total"] = int(m[1]) if m else None
        elif line.startswith("| 최종 판단일"):
            info["decision"] = parse_date(line)
        elif "**계속**" in line:
            m = re.search(r"\*\*(\d+)건 이상\*\*", line)
            info["go"] = int(m[1]) if m else None
        elif "**조정**" in line:
            m = re.search(r"(\d+)~(\d+)건", line)
            info["adj"] = int(m[1]) if m else None
    return info


def parse_schedule(text: str, year: int) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\|\s*(D\d{2})\s*\|([^|]*)\|([^|]*)\|([^|]*)\|(.*)\|\s*$", line)
        if not m:
            continue
        dm = re.search(r"(\d{2})/(\d{2})", m[2])
        d = date(year, int(dm[1]), int(dm[2])) if dm else None
        rows.append({"id": m[1], "date": d, "title": m[3].strip(), "status": m[4].strip(), "note": m[5].strip()})
    return rows


def parse_weekly(text: str, year: int) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\|\s*([1-9])\s*\|\s*(\d{2})/(\d{2})\s*\|([^|]*)\|", line)
        if not m:
            continue
        val = m[4].strip()
        rows.append({
            "week": int(m[1]),
            "date": date(year, int(m[2]), int(m[3])),
            "count": int(val) if re.fullmatch(r"\d+", val) else None,
        })
    return rows


def count_backlog(text: str) -> int:
    m = re.search(r"### 남은 단독 글감.*?\n(.*?)(?=\n### |\n## |\Z)", text, re.S)
    if not m:
        return 0
    return len(re.findall(r"^\|\s*[①-⑳㉑-㉟]\s*\|", m[1], re.M))


def parse_metrics(text: str) -> list[str] | None:
    # 제목 뒤에 설명이 붙어도(예: "## 게시 후 기록 (주간 집계에 사용)") 읽는다
    m = re.search(r"## 게시 후 기록[^\n]*\n(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        return None
    for line in m[1].splitlines():
        s = line.strip()
        if s.startswith("|") and not s.startswith("|---") and "조회" not in s:
            cells = [c.strip() for c in s.strip("|").split("|")]
            return cells + [""] * (5 - len(cells))
    return None


def bar(n: int, total: int, width: int = 15) -> str:
    n = max(0, min(n, total))
    filled = round(width * n / total) if total else 0
    return "█" * filled + "░" * (width - filled)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="진행 현황 요약")
    ap.add_argument("--today", default=None, help="기준 날짜 YYYY-MM-DD (시험용)")
    ap.add_argument("--root", default=None, help="읽을 폴더 (시험용)")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    today = parse_date(args.today) if args.today else date.today()
    if today is None:
        print("--today 는 YYYY-MM-DD 형식이어야 합니다.")
        return 2

    readme = parse_readme(read(root / "README.md"))
    year = (readme["start"] or today).year
    sched_text = read(root / "posts" / "schedule.md")
    rows = parse_schedule(sched_text, year)
    weekly = parse_weekly(sched_text, year)
    warnings: list[str] = []

    for key, label in (("start", "첫 게시일"), ("end", "기간 끝"), ("decision", "최종 판단일"), ("go", "계속 기준"), ("adj", "조정 기준")):
        if readme.get(key) is None:
            warnings.append(f"README에서 '{label}'을 읽지 못했습니다. 표 형식이 바뀌었는지 확인하세요.")

    start, end, decision = readme["start"], readme["end"], readme["decision"]
    total = readme.get("total") or len(rows) or 28
    go, adj = readme["go"], readme["adj"]

    print(f"=== MCP 레시피 진행 현황 ({today.isoformat()}) ===")
    if start and end:
        print(f"기간: {start.isoformat()} ~ {end.isoformat()} ({total}일)"
              + (f" | 최종 판단 {decision.isoformat()}" if decision else ""))
        if today < start:
            print(f"오늘: 시작 {(start - today).days}일 전")
        elif today <= end:
            print(f"오늘: {(today - start).days + 1}일차 / {total}일, 끝까지 {(end - today).days}일")
        else:
            print(f"오늘: 기간 종료 후 {(today - end).days}일"
                  + (f" (최종 판단일까지 {(decision - today).days}일)" if decision and today <= decision else ""))

    # ---- 게시 현황 ----
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    posted = by_status.get("게시됨", 0)
    parts = [f"{k} {v}" for k, v in by_status.items() if k != "게시됨"]
    print("\n[게시 현황]")
    print(f"게시됨 {posted} / {total}" + ("  |  " + "  |  ".join(parts) if parts else ""))
    upcoming = [r for r in rows if r["status"] != "게시됨"]
    if upcoming:
        n = upcoming[0]
        print(f"다음 게시: {n['id']} {fmt(n['date']) if n['date'] else ''} {n['title']} [{n['status']}]")
    overdue = [r for r in rows if r["date"] and r["date"] < today and r["status"] != "게시됨"]
    if overdue:
        ids = ", ".join(r["id"] for r in overdue)
        warnings.append(f"날짜가 지났는데 '게시됨'이 아닌 글: {ids} (올리지 않았거나 상태 갱신을 놓쳤을 수 있음)")
    buffer = sum(1 for r in rows if r["status"] == "검수완료")
    mark = "✔" if buffer >= BUFFER_MIN else "✖ 새 글 작성과 검증을 우선하세요"
    print(f"버퍼(검수완료, 미게시): {buffer}개 (최소 {BUFFER_MIN}개) {mark}")

    # ---- 성공 기준 진행도 ----
    print("\n[성공 기준 진행도]")
    filled = [w for w in weekly if w["count"] is not None]
    official = filled[-1]["count"] if filled else None
    for a, b in zip(filled, filled[1:]):
        if b["count"] < a["count"]:
            warnings.append(f"주간 집계가 줄었습니다({a['week']}주차 {a['count']} → {b['week']}주차 {b['count']}). 누적 값이 줄 수 없으니 확인하세요.")
    if go:
        if official is None:
            print(f"요청한 서로 다른 사람(누적): 아직 집계 없음  [{bar(0, go)}] 0/{go}")
        else:
            print(f"요청한 서로 다른 사람(누적, {filled[-1]['week']}주차 집계 기준): {official}명  [{bar(official, go)}] {official}/{go}")
        print(f"기준: 계속 {go}건 이상 | 조정 {adj}~{go - 1}건 | 접기 검토 {adj}건 미만 (4주 누적, 최종 판단 "
              f"{decision.isoformat() if decision else '?'})")
    metric_sum = 0
    metric_filled = 0
    per_post = []
    for path in sorted((root / "posts" / "daily").glob("D*.md")):
        cells = parse_metrics(read(path))
        if cells and any(cells[:4]):
            metric_filled += 1
            req = cells[3]
            if re.fullmatch(r"\d+", req):
                metric_sum += int(req)
            per_post.append(f"{path.name[:3]}: 조회 {cells[0] or '-'} / 저장 {cells[1] or '-'} / 공유 {cells[2] or '-'} / 요청 {cells[3] or '-'}")
    print(f"참고: 글별 기록의 요청 합계 {metric_sum} (같은 사람이 여러 글에 요청하면 중복되므로 공식 값이 아님, 기록한 글 {metric_filled}개)")
    for line in per_post:
        print("  " + line)
    if official is not None and metric_sum and official > metric_sum:
        warnings.append("누적 집계가 글별 요청 합계보다 큽니다. 글별 기록을 놓쳤거나 집계가 잘못됐을 수 있습니다.")

    # ---- 주간 집계 ----
    print("\n[주간 집계]")
    nxt = next((w for w in weekly if w["date"] >= today and w["count"] is None), None)
    if nxt:
        d = (nxt["date"] - today).days
        print(f"다음 집계일: {nxt['week']}주차 {fmt(nxt['date'])} ({'오늘' if d == 0 else f'{d}일 뒤'})")
    missed = [w for w in weekly if w["date"] < today and w["count"] is None]
    if missed:
        print("집계를 입력하지 않은 지난 주차: " + ", ".join(f"{w['week']}주차({fmt(w['date'])})" for w in missed))
    if not weekly:
        print("주간 집계 표를 읽지 못했습니다.")

    # ---- 글감 ----
    print("\n[글감]")
    undecided = sum(1 for r in rows if r["status"] == "미정")
    backlog = count_backlog(sched_text)
    threads = 0
    for p in sorted((root / "posts").glob("0*.md")):
        if re.search(r"-\s*상태:\s*\*\*미게시\*\*", read(p)):
            threads += 1
    supply = backlog + threads
    gap = supply - undecided
    print(f"글이 정해지지 않은 날 {undecided}일 | 남은 단독 글감 {backlog}개 + 미게시 스레드 {threads}개 = {supply}개")
    print(("여유 +" + str(gap)) if gap >= 0 else f"부족 {-gap}개 → 새 레시피 검증이 필요합니다")
    print("(일정표의 '남은 단독 글감' 표를 기준으로 셉니다. 글을 일정에 배정하면 그 글감을 표에서 빼야 정확합니다.)")

    # ---- 경고 ----
    if warnings:
        print("\n[경고]")
        for w in warnings:
            print("- " + w)
    print("\n보안/개인 정보 점검은 `python scripts/check.py` 로 따로 실행하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
