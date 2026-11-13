#!/usr/bin/env python3
"""사진 글이 Threads API에서 받아들여지는지, 발행하지 않고 확인한다.

  python scripts/check_photo_api.py D24

하는 일: post.py 와 같은 요청으로 사진 컨테이너(캐러셀이면 자식과 부모)를 만들고 각 컨테이너의 상태를 읽는다.
**threads_publish 는 부르지 않는다.** 컨테이너는 발행하기 전에는 프로필에 보이지 않고 약 24시간 뒤 사라진다.
기록 파일(.post-state.local.json)은 건드리지 않는다. 토큰은 출력하지 않는다.
사진이 공개 저장소에 푸시되어 있어야 한다(post.py 와 같은 확인을 한다).
"""
from __future__ import annotations

import os
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import post  # noqa: E402


def main(argv=None, *, transport=None, root: Path | None = None, sleep=time.sleep, wait: float = 20) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("사용: python scripts/check_photo_api.py D24")
        return 2
    root = (root or Path(__file__).resolve().parent.parent).resolve()
    token, user_id = os.environ.get(post.TOKEN_ENV, ""), os.environ.get(post.USER_ENV, "")
    if not token or not user_id:
        print(f"{post.TOKEN_ENV}, {post.USER_ENV} 가 필요합니다.")
        return 1
    p = post.load_post(root, argv[0])
    if not p.images:
        print(f"{p.id} 글 파일에 `- 사진:` 줄이 없습니다.")
        return 2
    transport = transport or post.RealTransport()
    problems = post.image_problems(root, p)
    base = post.default_image_base(root)
    more, urls = post.verify_public_images(root, p, base, transport)
    problems += more
    if problems:
        print("사진 점검에서 막혔습니다 (API는 부르지 않았습니다):")
        for x in problems:
            print(f"  - {x}")
        return 1
    print(f"{p.id}: 사진 {len(urls)}장, 공개 주소에서 로컬 파일과 같음을 확인했습니다. 발행은 하지 않습니다.")

    def create(data, label):
        data = dict(data, access_token=token)
        status, body = transport.request("POST", f"{post.API_BASE}/{user_id}/threads", data)
        cid = body.get("id") if isinstance(body, dict) else None
        if not (200 <= status < 300) or not cid:
            print(f"  {label}: 실패 ({post._fail_text(status, body, token)})")
            return None
        print(f"  {label}: 컨테이너 생성됨 (HTTP {status})")
        return str(cid)

    def container_status(cid, label):
        url = f"{post.API_BASE}/{cid}?fields=status,error_message&access_token={urllib.parse.quote(token)}"
        status, body = transport.request("GET", url, None)
        b = body if isinstance(body, dict) else {}
        print(f"  {label}: 상태 {b.get('status', '?')}" + (f" ({b['error_message']})" if b.get("error_message") else ""))
        return b.get("status")

    ids = []
    if len(urls) == 1:
        cid = create({"media_type": "IMAGE", "image_url": urls[0], "text": p.body}, "이미지 글")
        ids = [cid] if cid else []
        ok = bool(cid)
    else:
        kids = []
        for i, u in enumerate(urls, 1):
            kid = create({"media_type": "IMAGE", "image_url": u, "is_carousel_item": "true"}, f"사진 {i}")
            if not kid:
                return 1
            kids.append(kid)
        sleep(wait)
        parent = create({"media_type": "CAROUSEL", "children": ",".join(kids), "text": p.body}, "캐러셀(부모)")
        ids = kids + ([parent] if parent else [])
        ok = bool(parent)
    if not ok:
        return 1
    sleep(wait)
    states = [container_status(c, f"컨테이너 {i + 1}/{len(ids)}") for i, c in enumerate(ids)]
    if all(s == "FINISHED" for s in states):
        print("\n성공: 요청 형식이 받아들여졌고 컨테이너가 준비됐습니다. (아무것도 게시하지 않았습니다. 컨테이너는 약 24시간 뒤 사라집니다)")
        return 0
    print("\n컨테이너를 만들었지만 아직 FINISHED가 아닙니다. 잠시 뒤 다시 확인하거나 오류 문구를 확인하세요. (아무것도 게시하지 않았습니다)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
