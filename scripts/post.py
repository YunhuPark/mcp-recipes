#!/usr/bin/env python3
"""Threads 게시 도구 (단계적 자동 게시).

기본은 드라이런이다. 실제 발행은 `--publish` 와 환경 변수 THREADS_LIVE=yes 가 **둘 다** 있어야 한다.

  python scripts/post.py D02                 # 미리보기만 (네트워크 호출 없음)
  python scripts/post.py D02 --publish       # 실제 발행 (사람이 'yes'를 입력해 확인)
  python scripts/post.py --status            # 지금까지의 발행 기록
  python scripts/post.py --check-token       # 토큰이 유효한지 읽기 전용으로 확인 (아무것도 게시하지 않음)
  python scripts/post.py D02 --retry --publish    # 안전하게 실패한 글을 다시 시도
  python scripts/post.py D02 --resolve published|not_published   # 불확실한 시도를 사람이 확인한 뒤 해소
  python scripts/post.py --scheduled --publish    # 예약 실행용 (수동 발행 3회 성공 뒤에만 열림)

안전 설계 (알고 저장소의 교훈)
  1. 검수완료 상태이고 점검을 통과한 글만 올린다.
  2. 기본은 드라이런이다. 실제 발행에는 두 가지 열쇠가 필요하다.
  3. API를 부르기 **전에** 시도 기록을 파일에 남긴다.
  4. 결과가 불확실하면 **자동으로 다시 시도하지 않는다.** 사람이 Threads에서 확인한 뒤 --resolve 로 푼다.
  5. 다른 토큰으로 대체하지 않는다. THREADS_ACCESS_TOKEN 과 THREADS_USER_ID 만 쓴다.
  6. 토큰은 환경 변수에서만 읽고, 어떤 출력과 기록에도 남기지 않는다.
  7. 같은 글은 두 번 올리지 않고, 하루에 한 개만 올린다.
  8. 예약 실행은 수동 발행이 3회 성공해야 열린다.

기록 파일(.post-state.local.json)은 저장소에 올라가지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from threads_text import LIMIT, threads_len  # noqa: E402

API_BASE = "https://graph.threads.com/v1.0"  # 공식 문서(2026-10-20 확인)의 도메인. 예전 문서는 graph.threads.net
TOKEN_ENV, USER_ENV, LIVE_ENV, EXPIRES_ENV = (
    "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "THREADS_LIVE", "THREADS_TOKEN_EXPIRES")
TOPIC_ENV = "THREADS_TOPIC_TAG"  # 기본 주제 태그(비밀 아님). --topic 이 우선한다
STATE_FILE = ".post-state.local.json"
STALE_MINUTES = 10
GATE_MANUAL_SUCCESSES = 3
DEFAULT_WAIT_SECONDS = 30  # 문서: 컨테이너를 만든 뒤 발행 전에 약 30초 기다린다


# ---------------------------------------------------------------- 네트워크 (바꿔 끼울 수 있게 분리)
class NetworkError(Exception):
    """응답을 받지 못한 경우(시간 초과, 연결 실패 등)."""


class RealTransport:
    def request(self, method: str, url: str, data: dict | None, timeout: int = 30):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                return r.status, _json(raw)
        except urllib.error.HTTPError as e:
            return e.code, _json(e.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise NetworkError(type(e).__name__) from None


def _json(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return None


def redact(text: str, token: str | None) -> str:
    if token:
        text = text.replace(token, "[토큰 가림]")
    return re.sub(r"(?i)(access_token=)[^&\s\"']+", r"\1[토큰 가림]", text)


# ---------------------------------------------------------------- 글과 일정 읽기
@dataclass
class Post:
    id: str
    path: Path
    body: str
    file_status: str
    sched_status: str
    sched_date: tuple[int, int] | None


def load_post(root: Path, post_id: str) -> Post:
    daily = root / "posts" / "daily"
    files = sorted(daily.glob(f"{post_id}-*.md")) or sorted(daily.glob(f"{post_id}*.md"))
    if not files:
        raise SystemExit(f"글 파일을 찾지 못했습니다: {post_id}")
    path = files[0]
    text = path.read_text(encoding="utf-8")
    m = re.search(r"```[^\n]*\r?\n(.*?)\r?\n```", text, re.S)
    if not m:
        raise SystemExit(f"{path.name}: 게시 본문(코드 블록)을 찾지 못했습니다")
    ms = re.search(r"-\s*상태:\s*\*\*([^*]+)\*\*", text)
    file_status = ms.group(1).strip().split()[0] if ms else ""
    sched_status, sched_date = "", None
    sched = root / "posts" / "schedule.md"
    if sched.exists():
        for line in sched.read_text(encoding="utf-8").splitlines():
            r = re.match(rf"^\|\s*{post_id}\s*\|([^|]*)\|([^|]*)\|([^|]*)\|", line)
            if r:
                sched_status = r.group(3).strip()
                d = re.search(r"(\d{2})/(\d{2})", r.group(1))
                sched_date = (int(d.group(1)), int(d.group(2))) if d else None
                break
    return Post(post_id, path, m.group(1).replace("\r", ""), file_status, sched_status, sched_date)


# ---------------------------------------------------------------- 기록 (발행 전에 먼저 쓴다)
class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"version": 1, "posts": {}}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def get(self, post_id: str) -> dict | None:
        return self.data["posts"].get(post_id)

    def set(self, post_id: str, **fields) -> dict:
        rec = self.data["posts"].setdefault(post_id, {})
        rec.update(fields)
        rec["updated"] = datetime.now().isoformat(timespec="seconds")
        self.save()
        return rec

    def settle_stale(self, now: datetime) -> None:
        """중간에 끊긴 시도를 정리한다. 발행 호출 중이었다면 불확실, 그 전이었다면 게시되지 않은 것."""
        changed = False
        for pid, rec in self.data["posts"].items():
            if rec.get("state") not in ("STARTED", "CONTAINER_CREATED", "PUBLISHING"):
                continue
            try:
                age = now - datetime.fromisoformat(rec.get("updated", rec.get("started", "")))
            except ValueError:
                age = timedelta(days=1)
            if age > timedelta(minutes=STALE_MINUTES):
                rec["state"] = "UNCERTAIN" if rec["state"] == "PUBLISHING" else "FAILED"
                rec["reason"] = "중간에 끊긴 시도를 정리함 (발행 호출 중이었으면 불확실, 그 전이면 게시되지 않음)"
                changed = True
        if changed:
            self.save()

    def count(self, state: str, mode: str | None = None) -> int:
        return sum(1 for r in self.data["posts"].values()
                   if r.get("state") == state and (mode is None or r.get("mode") == mode))


def validate_topic(tag: str) -> str | None:
    """주제 태그 규칙(공식 문서): 1~50자, 마침표(.)와 앰퍼샌드(&)는 쓸 수 없다. 문제가 있으면 이유를, 없으면 None."""
    if not 1 <= len(tag) <= 50:
        return f"주제 태그는 1~50자여야 합니다 (현재 {len(tag)}자)"
    if "." in tag or "&" in tag:
        return "주제 태그에는 마침표(.)와 앰퍼샌드(&)를 쓸 수 없습니다"
    return None


# ---------------------------------------------------------------- 자격 조건 검사
def run_site_check(root: Path) -> tuple[bool, str]:
    script = Path(__file__).resolve().parent / "check.py"
    r = subprocess.run([sys.executable, str(script), "--root", str(root), "--no-commits"],
                       capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONUTF8": "1"})
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def eligibility(post: Post, state: State, root: Path, now: datetime, *, retry: bool,
                allow_extra: bool, check=run_site_check) -> list[str]:
    problems: list[str] = []
    if post.file_status != "검수완료":
        problems.append(f"글 파일의 상태가 '{post.file_status}'입니다 (검수완료여야 함)")
    if post.sched_status != "검수완료":
        problems.append(f"일정표의 상태가 '{post.sched_status}'입니다 (검수완료여야 함)")
    n = threads_len(post.body)
    if n > LIMIT:
        problems.append(f"Threads 기준 길이가 {n}로 {LIMIT}을 넘습니다")
    if not post.body.strip():
        problems.append("본문이 비어 있습니다")
    rec = state.get(post.id)
    if rec:
        s = rec.get("state")
        if s == "PUBLISHED":
            problems.append("이미 게시된 글입니다")
        elif s == "FAILED" and not retry:
            problems.append("이전 시도가 게시되지 않은 채 실패했습니다. 다시 하려면 --retry 를 쓰세요")
        elif s == "UNCERTAIN":
            problems.append("이전 시도의 결과가 불확실합니다. Threads에서 직접 확인한 뒤 --resolve 로 푸세요 (자동 재시도하지 않음)")
        elif s in ("STARTED", "CONTAINER_CREATED", "PUBLISHING"):
            problems.append(f"진행 중인 시도가 있습니다 ({s})")
    if not allow_extra:
        today = now.date().isoformat()
        for pid, r in state.data["posts"].items():
            if r.get("state") == "PUBLISHED" and str(r.get("published_at", "")).startswith(today) and pid != post.id:
                problems.append(f"오늘 이미 {pid}를 게시했습니다 (하루 1개 제한, 의도한 것이면 --allow-extra)")
    unresolved = [pid for pid, r in state.data["posts"].items() if r.get("state") == "UNCERTAIN" and pid != post.id]
    if unresolved:
        problems.append(f"불확실한 시도가 풀리지 않은 글이 있습니다: {', '.join(unresolved)}")
    ok, out = check(root)
    if not ok:
        problems.append("보안/개인 정보 점검(check.py)이 실패했습니다:\n    " + out.replace("\n", "\n    "))
    return problems


# ---------------------------------------------------------------- 발행
def _fail_text(status, body, token) -> str:
    msg = ""
    if isinstance(body, dict):
        e = body.get("error")
        if isinstance(e, dict):
            msg = f"{e.get('type', '')} {e.get('code', '')} {e.get('message', '')}".strip()
    return redact(f"HTTP {status} {msg}".strip(), token)


def publish_post(root: Path, post: Post, state: State, transport, token: str, user_id: str, *,
                 mode: str, wait_seconds: float, now: datetime, sleep=time.sleep,
                 topic: str | None = None) -> tuple[str, str]:
    """반환: (결과 상태, 설명). 어떤 경우에도 자동으로 다시 시도하지 않는다."""
    attempt = {
        "attempt_id": uuid.uuid4().hex, "mode": mode, "started": now.isoformat(timespec="seconds"),
        "text_sha256": hashlib.sha256(post.body.encode("utf-8")).hexdigest(), "state": "STARTED",
        "reason": "", "creation_id": None, "media_id": None,
    }
    state.set(post.id, **attempt)  # <- API를 부르기 전에 먼저 기록한다

    # 1단계: 컨테이너 만들기 (여기서 실패하면 게시된 것이 없다)
    try:
        container = {"media_type": "TEXT", "text": post.body, "access_token": token}
        if topic:
            container["topic_tag"] = topic
        status, body = transport.request("POST", f"{API_BASE}/{user_id}/threads", container)
    except NetworkError as e:
        state.set(post.id, state="FAILED", reason=f"컨테이너 생성 중 네트워크 오류({e}). 게시되지 않음")
        return "FAILED", "컨테이너 생성 중 네트워크 오류. 게시되지 않았습니다"
    creation_id = body.get("id") if isinstance(body, dict) else None
    if not (200 <= status < 300) or not creation_id:
        why = _fail_text(status, body, token)
        state.set(post.id, state="FAILED", reason=f"컨테이너 생성 실패: {why}. 게시되지 않음")
        return "FAILED", f"컨테이너 생성 실패 ({why}). 게시되지 않았습니다"
    state.set(post.id, state="CONTAINER_CREATED", creation_id=str(creation_id))

    sleep(wait_seconds)

    # 2단계: 발행. 호출 직전에 기록하고, 여기서 무슨 일이 생기든 '불확실'로 둔다.
    state.set(post.id, state="PUBLISHING")
    try:
        status, body = transport.request("POST", f"{API_BASE}/{user_id}/threads_publish",
                                         {"creation_id": str(creation_id), "access_token": token})
    except NetworkError as e:
        state.set(post.id, state="UNCERTAIN", reason=f"발행 중 네트워크 오류({e}). 게시됐는지 알 수 없음")
        return "UNCERTAIN", "발행 중 네트워크 오류. 게시됐는지 알 수 없습니다. Threads에서 직접 확인하세요"
    media_id = body.get("id") if isinstance(body, dict) else None
    if not (200 <= status < 300) or not media_id:
        why = _fail_text(status, body, token)
        state.set(post.id, state="UNCERTAIN", reason=f"발행 응답 이상: {why}. 게시됐는지 알 수 없음")
        return "UNCERTAIN", f"발행 응답이 이상합니다 ({why}). 게시됐는지 알 수 없습니다. Threads에서 직접 확인하세요"
    state.set(post.id, state="PUBLISHED", media_id=str(media_id), published_at=now.isoformat(timespec="seconds"))
    return "PUBLISHED", "게시되었습니다"


def mark_files_published(root: Path, post: Post, now: datetime) -> None:
    """게시 후 글 파일과 일정표의 상태를 '게시됨'으로 바꾼다. 커밋은 하지 않는다."""
    stamp = now.strftime("%Y-%m-%d %H:%M")
    text = post.path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^- 상태:.*$", f"- 상태: **게시됨** ({stamp}, post.py)", text, count=1)
    post.path.write_text(text, encoding="utf-8")
    sched = root / "posts" / "schedule.md"
    s = sched.read_text(encoding="utf-8")
    s = re.sub(rf"(?m)^(\|\s*{post.id}\s*\|[^|]*\|[^|]*\|)[^|]*\|", r"\1 게시됨 |", s, count=1)
    sched.write_text(s, encoding="utf-8")


def token_warnings(now: datetime) -> list[str]:
    exp = os.environ.get(EXPIRES_ENV, "").strip()
    if not exp:
        return [f"{EXPIRES_ENV}(토큰 만료일, YYYY-MM-DD)가 설정되지 않았습니다. 장기 토큰은 60일 뒤 만료됩니다"]
    try:
        d = datetime.strptime(exp, "%Y-%m-%d")
    except ValueError:
        return [f"{EXPIRES_ENV} 형식이 올바르지 않습니다 (YYYY-MM-DD)"]
    left = (d.date() - now.date()).days
    if left <= 0:
        return ["__EXPIRED__"]
    return [f"토큰 만료까지 {left}일 남았습니다. 14일 이하이면 갱신하세요"] if left <= 14 else []


# ---------------------------------------------------------------- 명령
def cmd_status(state: State) -> int:
    if not state.data["posts"]:
        print("발행 기록이 없습니다.")
        return 0
    print("글    | 상태        | 방식    | 갱신")
    for pid in sorted(state.data["posts"]):
        r = state.data["posts"][pid]
        print(f"{pid} | {r.get('state', ''):<11} | {r.get('mode', ''):<7} | {r.get('updated', '')}")
        if r.get("reason"):
            print(f"      사유: {r['reason']}")
    print(f"\n수동 발행 성공 {state.count('PUBLISHED', 'manual')}회 (예약 자동 발행은 {GATE_MANUAL_SUCCESSES}회 이상이어야 열림)")
    return 0


def cmd_check_token(transport, now: datetime) -> int:
    """읽기 전용 호출 하나(GET /me)로 토큰이 유효한지, THREADS_USER_ID 와 같은 계정인지 확인한다."""
    token, user_id = os.environ.get(TOKEN_ENV, ""), os.environ.get(USER_ENV, "")
    if not token or not user_id:
        print(f"{TOKEN_ENV}, {USER_ENV} 가 필요합니다. 다른 토큰으로 대체하지 않습니다.")
        return 1
    for w in token_warnings(now):
        print("[경고] 토큰이 만료되었습니다" if w == "__EXPIRED__" else f"[경고] {w}")
    transport = transport or RealTransport()
    try:
        status, body = transport.request("GET", f"{API_BASE}/me?fields=id&access_token={urllib.parse.quote(token)}", None)
    except NetworkError as e:
        print(f"네트워크 오류({e}). 토큰 상태를 확인하지 못했습니다")
        return 1
    if not (200 <= status < 300) or not isinstance(body, dict) or not body.get("id"):
        print(f"토큰을 확인하지 못했습니다 ({_fail_text(status, body, token)})")
        return 1
    if str(body["id"]) != user_id:
        print(f"토큰의 계정과 {USER_ENV} 가 다릅니다. 발행하지 말고 두 값을 다시 확인하세요")
        return 1
    print(f"토큰이 유효하고 {USER_ENV} 와 같은 계정입니다 (읽기 전용 확인, 게시하지 않았습니다)")
    return 0


def cmd_resolve(state: State, root: Path, post_id: str, outcome: str, now: datetime) -> int:
    rec = state.get(post_id)
    if not rec or rec.get("state") != "UNCERTAIN":
        print(f"{post_id}: 불확실 상태가 아닙니다. 풀 필요가 없습니다.")
        return 2
    if outcome == "published":
        state.set(post_id, state="PUBLISHED", published_at=now.isoformat(timespec="seconds"),
                  reason="사람이 Threads에서 게시를 확인함 (--resolve)")
        mark_files_published(root, load_post(root, post_id), now)
        print(f"{post_id}: 게시된 것으로 기록했습니다.")
    else:
        state.set(post_id, state="FAILED", reason="사람이 Threads에서 게시되지 않았음을 확인함 (--resolve)")
        print(f"{post_id}: 게시되지 않은 것으로 기록했습니다. 다시 하려면 --retry 를 쓰세요.")
    return 0


def pick_scheduled(root: Path, state: "State") -> tuple[str | None, str]:
    """일정표 순서대로 아직 안 올린 첫 글을 고른다. 날짜는 보지 않는다 (하루를 놓쳐도 순서가 이어지게).
    그 글이 '검수완료'가 아니면 뒤의 글로 건너뛰지 않고 멈춘다. (고른 글 번호 또는 None, 사유)"""
    sched = root / "posts" / "schedule.md"
    for line in sched.read_text(encoding="utf-8").splitlines():
        r = re.match(r"^\|\s*(D\d{2})\s*\|[^|]*\|[^|]*\|([^|]*)\|", line)
        if not r:
            continue
        pid, status = r.group(1), r.group(2).strip()
        if status == "게시됨" or (state.get(pid) or {}).get("state") == "PUBLISHED":
            continue
        if status == "검수완료":
            return pid, ""
        return None, f"다음 순서인 {pid}가 '{status}' 상태라 멈춥니다 (뒤의 글로 건너뛰지 않습니다)."
    return None, "올릴 글이 남아 있지 않습니다."


def main(argv=None, *, transport=None, now: datetime | None = None, root: Path | None = None,
         confirm=None, sleep=time.sleep, check=run_site_check) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Threads 게시 도구 (기본은 드라이런)")
    ap.add_argument("post_id", nargs="?", help="예: D02")
    ap.add_argument("--publish", action="store_true", help="실제 발행 (THREADS_LIVE=yes 도 필요)")
    ap.add_argument("--status", action="store_true", help="발행 기록 보기")
    ap.add_argument("--check-token", action="store_true", help="토큰이 유효한지 읽기 전용으로 확인")
    ap.add_argument("--retry", action="store_true", help="게시되지 않은 채 실패한 글을 다시 시도")
    ap.add_argument("--resolve", choices=["published", "not_published"], help="불확실한 시도를 사람이 확인한 뒤 해소")
    ap.add_argument("--scheduled", action="store_true", help="예약 실행(일정표 순서대로 아직 안 올린 첫 검수완료 글을 고름)")
    ap.add_argument("--topic", default=None, help=f"주제 태그(예: 'AI Threads'). 없으면 환경 변수 {TOPIC_ENV}, 그것도 없으면 태그 없이 올림")
    ap.add_argument("--allow-extra", action="store_true", help="하루 1개 제한을 풀기")
    ap.add_argument("--wait", type=float, default=DEFAULT_WAIT_SECONDS, help="컨테이너 생성 뒤 대기 초 (기본 30)")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    root = Path(root or args.root or Path(__file__).resolve().parent.parent).resolve()
    now = now or datetime.now()
    state = State(root / STATE_FILE)
    state.settle_stale(now)

    if args.status:
        return cmd_status(state)
    if args.check_token:
        return cmd_check_token(transport, now)
    if args.resolve:
        if not args.post_id:
            print("--resolve 에는 글 번호가 필요합니다 (예: D02)")
            return 2
        return cmd_resolve(state, root, args.post_id, args.resolve, now)

    mode = "manual"
    post_id = args.post_id
    if args.scheduled:
        mode = "scheduled"
        ok_count = state.count("PUBLISHED", "manual")
        if ok_count < GATE_MANUAL_SUCCESSES:
            print(f"예약 자동 발행은 수동 발행이 {GATE_MANUAL_SUCCESSES}회 성공한 뒤에 열립니다 (현재 {ok_count}회).")
            return 3
        post_id, why = pick_scheduled(root, state)
        if not post_id:
            print(f"{why} 아무것도 하지 않습니다.")
            return 0
    if not post_id:
        ap.print_help()
        return 2

    post = load_post(root, post_id)
    print(f"== {post.id} ({post.path.name}) ==")
    print(post.body)
    print(f"-- Threads 기준 길이 {threads_len(post.body)} / {LIMIT} --")
    topic = (args.topic if args.topic is not None else os.environ.get(TOPIC_ENV, "")).strip()
    print(f"-- 주제 태그: {topic or '(없음)'} --")

    problems = eligibility(post, state, root, now, retry=args.retry, allow_extra=args.allow_extra, check=check)
    if topic and validate_topic(topic):
        problems.append(validate_topic(topic))
    for w in token_warnings(now):
        if w == "__EXPIRED__":
            problems.append(f"토큰이 만료되었습니다 ({EXPIRES_ENV})")
        elif args.publish:
            print(f"[경고] {w}")

    if not args.publish:
        print("\n[드라이런] 아무것도 게시하지 않았습니다.")
        if problems:
            print("실제로 발행하려면 먼저 해결해야 할 문제:")
            for p in problems:
                print(f"  - {p}")
        else:
            print("지금 조건에서는 발행할 수 있습니다. 실제로 올리려면 --publish 를 붙이세요.")
        return 0

    if problems:
        print("\n발행하지 않습니다:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if os.environ.get(LIVE_ENV, "").strip().lower() != "yes":
        print(f"\n발행하지 않습니다: {LIVE_ENV}=yes 가 설정되어 있지 않습니다 (두 번째 열쇠).")
        return 1
    token, user_id = os.environ.get(TOKEN_ENV, ""), os.environ.get(USER_ENV, "")
    if not token or not user_id:
        print(f"\n발행하지 않습니다: {TOKEN_ENV}, {USER_ENV} 가 필요합니다. 다른 토큰으로 대체하지 않습니다.")
        return 1

    if mode == "manual":
        answer = confirm() if confirm else (input("\n위 내용을 지금 게시합니다. 정확히 'yes' 를 입력하세요: ") if sys.stdin.isatty() else "")
        if str(answer).strip() != "yes":
            print("확인되지 않아 발행하지 않았습니다.")
            return 1

    transport = transport or RealTransport()
    result, msg = publish_post(root, post, state, transport, token, user_id, mode=mode,
                               wait_seconds=args.wait, now=now, sleep=sleep, topic=topic or None)
    print(f"\n[{result}] {msg}")
    if result == "PUBLISHED":
        try:
            mark_files_published(root, post, now)
            print("글 파일과 일정표의 상태를 '게시됨'으로 바꿨습니다. (커밋은 하지 않았습니다)")
        except Exception as e:  # 게시는 이미 끝났다. 파일 갱신 실패가 상태를 되돌리면 안 된다.
            print(f"[경고] 게시는 됐지만 파일 갱신에 실패했습니다: {type(e).__name__}. 직접 '게시됨'으로 바꿔 주세요.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
