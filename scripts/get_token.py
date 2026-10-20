#!/usr/bin/env python3
"""Threads 장기 토큰 발급 도우미. **사용자가 직접 자기 터미널에서 실행한다.**

하는 일: 승인 코드 -> 단기 토큰 -> 장기 토큰(60일) 교환 -> 계정 확인 -> (확인 후) 이 PC의 사용자 환경 변수에 저장.
토큰, 앱 시크릿, 승인 코드는 화면에 출력하지 않고 숨김 입력으로 받는다. 파일에도 쓰지 않는다.
Claude는 이 스크립트를 실행하지 않는다 (비밀값을 보지 않기 위해).

사용:
  python scripts/get_token.py
  python scripts/get_token.py --from-token   # 대시보드 '사용자 토큰 생성기'로 만든 토큰을 붙여 넣어 확인하고 저장 (리디렉션 URI 불필요)
  python scripts/get_token.py --show-token   # 저장하지 않고 토큰을 화면에 보여 달라는 명시적 요청 (직접 복사해 쓸 때)

**실제 Threads와는 아직 한 번도 연결해 보지 않았다.** 엔드포인트와 매개변수는 공식 문서(2026-10-20 확인)를 근거로 했다.
"""
from __future__ import annotations

import argparse
import getpass
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import post as post_mod  # noqa: E402

AUTH_URL = "https://threads.com/oauth/authorize"
GRAPH = "https://graph.threads.com"
SCOPES = "threads_basic,threads_content_publish,threads_manage_insights,threads_read_replies"  # 대시보드에 추가한 권한과 같아야 한다
ENV_NAMES = (post_mod.TOKEN_ENV, post_mod.USER_ENV, post_mod.EXPIRES_ENV)


class TokenError(Exception):
    pass


def build_auth_url(app_id: str, redirect_uri: str, scopes: str = SCOPES) -> str:
    q = urllib.parse.urlencode({"client_id": app_id, "redirect_uri": redirect_uri, "scope": scopes, "response_type": "code"})
    return f"{AUTH_URL}?{q}"


def parse_code(text: str) -> str:
    """붙여 넣은 주소 전체 또는 code 값에서 승인 코드를 꺼낸다. 끝의 '#_'는 코드가 아니다."""
    text = text.strip()
    if "code=" in text:
        query = urllib.parse.urlsplit(text.replace("#_", "")).query or text.split("?", 1)[-1]
        vals = urllib.parse.parse_qs(query).get("code")
        if not vals:
            raise TokenError("주소에서 code 값을 찾지 못했습니다")
        text = vals[0]
    code = text.replace("#_", "").strip()
    if not code:
        raise TokenError("승인 코드가 비어 있습니다")
    return code


def _scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "[가림]")
    return text


def _error_text(status, body, secrets) -> str:
    msg = ""
    if isinstance(body, dict):
        e = body.get("error")
        if isinstance(e, dict):
            msg = f"{e.get('type', '')} {e.get('code', '')} {e.get('message', '')}".strip()
        elif isinstance(e, str):
            msg = e
    return _scrub(f"HTTP {status} {msg}".strip(), secrets)


def exchange(transport, *, app_id: str, app_secret: str, redirect_uri: str, code: str, now: datetime) -> dict:
    """코드 -> 단기 토큰 -> 장기 토큰. 반환: {token, user_id, expires}. 실패하면 TokenError."""
    secrets = [app_secret, code]
    try:
        status, body = transport.request("POST", f"{GRAPH}/oauth/access_token", {
            "client_id": app_id, "client_secret": app_secret, "grant_type": "authorization_code",
            "redirect_uri": redirect_uri, "code": code})
    except post_mod.NetworkError as e:
        raise TokenError(f"코드 교환 중 네트워크 오류({e})") from None
    short = body.get("access_token") if isinstance(body, dict) else None
    user_id = body.get("user_id") if isinstance(body, dict) else None
    if not (200 <= status < 300) or not short or not user_id:
        raise TokenError(f"코드를 단기 토큰으로 바꾸지 못했습니다 ({_error_text(status, body, secrets)}). "
                         "코드는 1시간 안에 한 번만 쓸 수 있고, 리디렉션 URI가 승인할 때와 정확히 같아야 합니다")
    secrets.append(short)

    qs = urllib.parse.urlencode({"grant_type": "th_exchange_token", "client_secret": app_secret, "access_token": short})
    try:
        status, body = transport.request("GET", f"{GRAPH}/access_token?{qs}", None)
    except post_mod.NetworkError as e:
        raise TokenError(f"장기 토큰 교환 중 네트워크 오류({e})") from None
    long_token = body.get("access_token") if isinstance(body, dict) else None
    expires_in = body.get("expires_in") if isinstance(body, dict) else None
    if not (200 <= status < 300) or not long_token or not isinstance(expires_in, (int, float)):
        raise TokenError(f"장기 토큰으로 바꾸지 못했습니다 ({_error_text(status, body, secrets)})")
    secrets.append(long_token)

    q2 = urllib.parse.urlencode({"fields": "id", "access_token": long_token})
    try:
        status, body = transport.request("GET", f"{post_mod.API_BASE}/me?{q2}", None)
    except post_mod.NetworkError as e:
        raise TokenError(f"계정 확인 중 네트워크 오류({e})") from None
    if not (200 <= status < 300) or not isinstance(body, dict) or str(body.get("id")) != str(user_id):
        raise TokenError(f"발급된 토큰으로 계정을 확인하지 못했습니다 ({_error_text(status, body, secrets)})")
    expires = (now + timedelta(seconds=int(expires_in))).date().isoformat()
    return {"token": long_token, "user_id": str(user_id), "expires": expires}


def set_user_env(name: str, value: str) -> None:
    """Windows 사용자 환경 변수에 저장한다 (명령줄에 값이 남지 않도록 레지스트리에 직접 쓴다)."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def broadcast_env_change() -> None:
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
    except Exception:
        pass  # 새 터미널을 열면 어차피 반영된다


def verify_token(transport, token: str, now: datetime) -> dict:
    """이미 만든 장기 토큰을 읽기 전용 호출(GET /me)로 확인한다. 발급 시각을 모르므로 만료일은 오늘부터 60일로 **추정**한다."""
    q = urllib.parse.urlencode({"fields": "id", "access_token": token})
    try:
        status, body = transport.request("GET", f"{post_mod.API_BASE}/me?{q}", None)
    except post_mod.NetworkError as e:
        raise TokenError(f"토큰 확인 중 네트워크 오류({e})") from None
    if not (200 <= status < 300) or not isinstance(body, dict) or not body.get("id"):
        raise TokenError(f"토큰을 확인하지 못했습니다 ({_error_text(status, body, [token])})")
    return {"token": token, "user_id": str(body["id"]), "expires": (now + timedelta(days=60)).date().isoformat()}


def finish(result: dict, show_token: bool, prompt, env_setter, out) -> int:
    """토큰을 보여 주거나(--show-token) 확인을 받아 환경 변수에 저장한다. 값은 --show-token 일 때만 출력한다."""
    if show_token:
        out("--show-token: 아래 값을 직접 환경 변수에 넣으세요. 화면 기록에 남을 수 있으니 주의하세요.")
        out(f"{post_mod.TOKEN_ENV}={result['token']}")
        out(f"{post_mod.USER_ENV}={result['user_id']}")
        out(f"{post_mod.EXPIRES_ENV}={result['expires']}")
        return 0
    answer = prompt("이 PC의 사용자 환경 변수에 저장할까요? 'y' 를 입력하면 저장합니다 (그 외는 저장하지 않고 토큰을 버립니다): ")
    if answer.strip().lower() != "y":
        out("저장하지 않았습니다. 토큰은 어디에도 남지 않았고, 다시 하려면 처음부터 다시 실행하세요.")
        return 0
    try:
        env_setter(post_mod.TOKEN_ENV, result["token"])
        env_setter(post_mod.USER_ENV, result["user_id"])
        env_setter(post_mod.EXPIRES_ENV, result["expires"])
    except Exception as e:  # 값은 출력하지 않는다
        out(f"저장하지 못했습니다 ({type(e).__name__}). --show-token 으로 다시 해서 직접 넣으세요.")
        return 1
    if env_setter is set_user_env:
        broadcast_env_change()
    out(f"저장했습니다: {', '.join(ENV_NAMES)}. 새 터미널을 열고 'python scripts/post.py --check-token' 으로 확인하세요.")
    out("THREADS_LIVE 는 일부러 저장하지 않았습니다 (실제로 올릴 때만 yes 로 설정).")
    return 0


def main(argv=None, *, transport=None, prompt=input, secret_prompt=getpass.getpass, now=None,
         env_setter=set_user_env, out=print) -> int:
    ap = argparse.ArgumentParser(description="Threads 장기 토큰 발급 도우미 (사용자가 직접 실행)")
    ap.add_argument("--show-token", action="store_true", help="저장하지 않고 토큰을 화면에 보여 준다")
    ap.add_argument("--from-token", action="store_true",
                    help="대시보드 '사용자 토큰 생성기'로 만든 장기 토큰을 붙여 넣어 확인하고 저장한다 (리디렉션 URI, 앱 시크릿 불필요)")
    ap.add_argument("--scopes", default=SCOPES, help="요청할 권한(쉼표로 구분). 앱 대시보드에 추가한 권한과 같아야 한다")
    args = ap.parse_args(argv)
    now = now or datetime.now()

    if args.from_token:
        token = secret_prompt("대시보드 '사용자 토큰 생성기'에서 만든 토큰을 붙여 넣으세요 (화면에 보이지 않습니다): ").strip()
        if not token:
            out("토큰이 필요합니다")
            return 2
        try:
            result = verify_token(transport or post_mod.RealTransport(), token, now)
        except TokenError as e:
            out(f"\n실패: {e}")
            return 1
        out(f"\n토큰이 유효합니다. 사용자 ID {result['user_id']}. 발급 시각을 몰라 만료일은 오늘부터 60일({result['expires']})로 잡았습니다. "
            "대시보드에 표시된 만료일이 다르면 THREADS_TOKEN_EXPIRES 를 직접 고치세요.")
        return finish(result, args.show_token, prompt, env_setter, out)

    out("Threads 앱 대시보드 > 설정에서 'Threads 앱 ID'를 확인하세요 (Meta 앱 ID가 아니라 Threads 앱 ID입니다).")
    app_id = prompt("Threads 앱 ID: ").strip()
    redirect_uri = prompt("대시보드에 등록한 리디렉션 URI (정확히 같게): ").strip()
    if not app_id or not redirect_uri:
        out("앱 ID와 리디렉션 URI가 필요합니다")
        return 2
    out("\n1) 아래 주소를 브라우저에서 열고, 본인 Threads 계정으로 승인하세요.")
    out("   (승인 뒤 브라우저가 등록한 주소로 이동하며 주소창에 code=... 가 붙습니다. 페이지가 열리지 않아도 괜찮습니다)\n")
    out(build_auth_url(app_id, redirect_uri, args.scopes))
    try:
        code = parse_code(secret_prompt("\n2) 이동한 뒤의 주소 전체(또는 code 값)를 붙여 넣으세요 (화면에 보이지 않습니다): "))
    except TokenError as e:
        out(str(e))
        return 1
    app_secret = secret_prompt("3) Threads 앱 시크릿 (화면에 보이지 않습니다): ").strip()
    if not app_secret:
        out("앱 시크릿이 필요합니다")
        return 2

    transport = transport or post_mod.RealTransport()
    try:
        result = exchange(transport, app_id=app_id, app_secret=app_secret, redirect_uri=redirect_uri, code=code, now=now)
    except TokenError as e:
        out(f"\n실패: {e}")
        return 1
    out(f"\n토큰을 발급했고 계정이 확인되었습니다. 사용자 ID {result['user_id']}, 만료 예정일 {result['expires']} (60일).")
    return finish(result, args.show_token, prompt, env_setter, out)


if __name__ == "__main__":
    sys.exit(main())
