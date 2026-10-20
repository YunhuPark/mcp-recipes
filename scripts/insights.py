#!/usr/bin/env python3
"""게시한 글의 조회, 반응 수를 Threads API로 읽는다 (읽기 전용, 아무것도 게시하지 않음).

사용:
  python scripts/insights.py            # 표로 보기
  python scripts/insights.py --json     # JSON 으로 보기

필요: THREADS_ACCESS_TOKEN, THREADS_USER_ID (post.py 와 같은 값). 토큰에 threads_manage_insights 권한이 있어야 한다.

동작: 내 최근 글 목록(GET /me/threads)을 읽어, 글 본문이 posts/daily 의 글과 같은 것끼리 짝지은 뒤
글마다 지표(GET /{글 id}/insights)를 읽는다. 짝이 없는 글은 건너뛴다.
**실제 Threads API로는 아직 확인하지 않았다.** 응답 형식은 공식 문서를 근거로 한 것이고, 첫 실행에서 틀릴 수 있다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import post as post_mod  # noqa: E402  (토큰 환경 변수 이름, 통신 계층, 글 읽기를 같이 쓴다)

METRICS = ("views", "likes", "replies", "reposts", "quotes")
LIST_LIMIT = 50


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def local_posts(root: Path) -> dict[str, str]:
    """글 번호 -> 정리한 본문."""
    out = {}
    for path in sorted((root / "posts" / "daily").glob("D*.md")):
        try:
            p = post_mod.load_post(root, path.name[:3])
        except Exception:
            continue
        out[p.id] = norm(p.body)
    return out


def fetch_threads(transport, token: str) -> list[dict]:
    url = (f"{post_mod.API_BASE}/me/threads?fields=id,text,timestamp&limit={LIST_LIMIT}"
           f"&access_token={urllib.parse.quote(token)}")
    status, body = transport.request("GET", url, None)
    if not (200 <= status < 300) or not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise RuntimeError(f"글 목록을 읽지 못했습니다 ({post_mod._fail_text(status, body, token)})")
    return body["data"]


def fetch_metrics(transport, token: str, media_id: str) -> dict[str, int | None]:
    url = (f"{post_mod.API_BASE}/{media_id}/insights?metric={','.join(METRICS)}"
           f"&access_token={urllib.parse.quote(token)}")
    status, body = transport.request("GET", url, None)
    out: dict[str, int | None] = {m: None for m in METRICS}
    if not (200 <= status < 300) or not isinstance(body, dict):
        return out  # 이 글의 지표만 비워 두고 계속한다 (이유는 호출한 쪽이 표시)
    for item in body.get("data", []):
        name = item.get("name")
        values = item.get("values") or []
        if name in out and values and isinstance(values[0], dict):
            out[name] = values[0].get("value")
    return out


def collect(root: Path, transport, token: str) -> list[dict]:
    mine = local_posts(root)
    rows = []
    for th in fetch_threads(transport, token):
        text = norm(th.get("text") or "")
        match = [pid for pid, body in mine.items() if body == text]
        if len(match) != 1:
            continue  # 우리 글이 아니거나 본문이 달라 짝을 못 찾은 글
        m = fetch_metrics(transport, token, str(th["id"]))
        rows.append({"id": match[0], "media_id": str(th["id"]), "timestamp": th.get("timestamp"), **m})
    return sorted(rows, key=lambda r: r["id"])


def main(argv=None, *, transport=None, root: Path | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="게시한 글의 조회와 반응 (읽기 전용)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(root or args.root or Path(__file__).resolve().parent.parent).resolve()

    token, user_id = os.environ.get(post_mod.TOKEN_ENV, ""), os.environ.get(post_mod.USER_ENV, "")
    if not token or not user_id:
        print(f"{post_mod.TOKEN_ENV}, {post_mod.USER_ENV} 가 필요합니다. 다른 토큰으로 대체하지 않습니다.")
        return 1
    transport = transport or post_mod.RealTransport()
    try:
        rows = collect(root, transport, token)
    except post_mod.NetworkError as e:
        print(f"네트워크 오류({e}). 읽지 못했습니다")
        return 1
    except RuntimeError as e:
        print(str(e))
        return 1

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("짝이 맞는 글이 없습니다. (게시한 글의 본문이 posts/daily 의 글과 같아야 합니다)")
        return 0
    print("글  | 게시 시각           | 조회  | 좋아요 | 답글 | 리포스트 | 인용")
    show = lambda v: "-" if v is None else str(v)  # noqa: E731
    for r in rows:
        print(f"{r['id']} | {str(r['timestamp'] or '')[:19]:<19} | {show(r['views']):>5} | {show(r['likes']):>6} | "
              f"{show(r['replies']):>4} | {show(r['reposts']):>8} | {show(r['quotes'])}")
    print("\n'-' 는 읽지 못한 값입니다 (권한이 없거나 아직 제공되지 않는 지표일 수 있음).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
