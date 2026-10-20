"""get_token.py 시험. 실제 Threads를 부르지 않고 가짜 네트워크와 가짜 입력으로 확인한다.

실행: python -m unittest scripts/test_get_token.py -v   (저장소 루트에서)
모든 값은 시험용 가짜 문자열이며 실제 값이 아니다.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import get_token as gt  # noqa: E402
import post  # noqa: E402

APP_ID, REDIRECT = "TEST-APP-ID", "https://example.test/callback/"
SECRET, CODE = "TESTONLY-app-secret", "TESTONLY-auth-code"
SHORT, LONG = "TESTONLY-short-token", "TESTONLY-long-token"
NOW = datetime(2026, 10, 21, 9, 0)


class FakeTransport:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def request(self, method, url, data, timeout=30):
        self.calls.append((method, url, data))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def good_script(user_id="777", me_id="777", expires_in=5184000):
    return [(200, {"access_token": SHORT, "user_id": user_id}),
            (200, {"access_token": LONG, "token_type": "bearer", "expires_in": expires_in}),
            (200, {"id": me_id})]


class ParseTests(unittest.TestCase):
    def test_plain_code(self):
        self.assertEqual(gt.parse_code("abc123"), "abc123")

    def test_trailing_hash_underscore_is_removed(self):
        self.assertEqual(gt.parse_code("abc123#_"), "abc123")

    def test_full_redirect_url(self):
        self.assertEqual(gt.parse_code("https://example.test/callback/?code=abc123#_"), "abc123")

    def test_full_url_with_state(self):
        self.assertEqual(gt.parse_code("https://example.test/callback/?state=x&code=abc123%2Bz#_"), "abc123+z")

    def test_url_without_code_is_an_error(self):
        with self.assertRaises(gt.TokenError):
            gt.parse_code("https://example.test/callback/?error=access_denied&code=")

    def test_empty_is_an_error(self):
        with self.assertRaises(gt.TokenError):
            gt.parse_code("   ")

    def test_auth_url_scopes_can_be_overridden(self):
        url = gt.build_auth_url(APP_ID, REDIRECT, "threads_basic")
        self.assertIn("scope=threads_basic&", url + "&")
        self.assertNotIn("threads_content_publish", url)

    def test_default_scopes_cover_publish_insights_and_read_replies_only(self):
        self.assertEqual(set(gt.SCOPES.split(",")), {"threads_basic", "threads_content_publish", "threads_manage_insights", "threads_read_replies"})
        for dangerous in ("threads_delete", "threads_manage_replies"):
            self.assertNotIn(dangerous, gt.SCOPES)  # 지우기와 대신 답글 쓰기 권한은 기본으로 요청하지 않는다

    def test_auth_url_has_the_needed_parameters(self):
        url = gt.build_auth_url(APP_ID, REDIRECT)
        self.assertTrue(url.startswith("https://threads.com/oauth/authorize?"))
        for part in ("client_id=TEST-APP-ID", "response_type=code", "threads_basic", "threads_content_publish"):
            self.assertIn(part, url)


class ExchangeTests(unittest.TestCase):
    def run_exchange(self, script):
        t = FakeTransport(script)
        return gt.exchange(t, app_id=APP_ID, app_secret=SECRET, redirect_uri=REDIRECT, code=CODE, now=NOW), t

    def test_success_returns_token_user_and_expiry(self):
        res, t = self.run_exchange(good_script())
        self.assertEqual((res["token"], res["user_id"]), (LONG, "777"))
        self.assertEqual(res["expires"], "2026-12-20")  # 2026-10-21 + 60일

    def test_call_order_and_methods(self):
        _, t = self.run_exchange(good_script())
        self.assertEqual([c[0] for c in t.calls], ["POST", "GET", "GET"])
        self.assertIn("/oauth/access_token", t.calls[0][1])
        self.assertIn("th_exchange_token", t.calls[1][1])
        self.assertIn("/me?", t.calls[2][1])

    def test_app_secret_and_code_go_in_the_post_body_not_the_url(self):
        _, t = self.run_exchange(good_script())
        self.assertNotIn(SECRET, t.calls[0][1])
        self.assertNotIn(CODE, t.calls[0][1])
        self.assertEqual(t.calls[0][2]["client_secret"], SECRET)
        self.assertEqual(t.calls[0][2]["grant_type"], "authorization_code")

    def test_first_step_failure_hides_all_secrets(self):
        msg = f"code {CODE} used with {SECRET}"
        with self.assertRaises(gt.TokenError) as cm:
            self.run_exchange([(400, {"error": {"type": "OAuthException", "code": 400, "message": msg}})])
        for s in (SECRET, CODE):
            self.assertNotIn(s, str(cm.exception))

    def test_second_step_failure_hides_tokens(self):
        with self.assertRaises(gt.TokenError) as cm:
            self.run_exchange([(200, {"access_token": SHORT, "user_id": "777"}),
                               (400, {"error": {"message": f"bad {SHORT} {SECRET}"}})])
        for s in (SECRET, SHORT):
            self.assertNotIn(s, str(cm.exception))

    def test_account_mismatch_is_refused(self):
        with self.assertRaises(gt.TokenError):
            self.run_exchange(good_script(user_id="777", me_id="888"))

    def test_missing_expiry_is_refused(self):
        with self.assertRaises(gt.TokenError):
            self.run_exchange([(200, {"access_token": SHORT, "user_id": "777"}), (200, {"access_token": LONG})])

    def test_network_error_is_reported(self):
        with self.assertRaises(gt.TokenError):
            self.run_exchange([post.NetworkError("TimeoutError")])


class MainTests(unittest.TestCase):
    def run_main(self, answers, script, argv=()):
        lines, saved = [], []
        inputs = iter(answers)
        secrets = iter([CODE, SECRET])
        code = gt.main(list(argv), transport=FakeTransport(script), prompt=lambda _="": next(inputs),
                       secret_prompt=lambda _="": next(secrets), now=NOW,
                       env_setter=lambda n, v: saved.append((n, v)), out=lines.append)
        return code, "\n".join(lines), saved

    def test_saves_three_env_vars_after_confirmation_and_prints_no_secret(self):
        code, out, saved = self.run_main([APP_ID, REDIRECT, "y"], good_script())
        self.assertEqual(code, 0, out)
        self.assertEqual([n for n, _ in saved], [post.TOKEN_ENV, post.USER_ENV, post.EXPIRES_ENV])
        self.assertEqual(dict(saved)[post.TOKEN_ENV], LONG)
        for s in (LONG, SHORT, SECRET, CODE):
            self.assertNotIn(s, out)
        self.assertNotIn("THREADS_LIVE", [n for n, _ in saved])  # 두 번째 열쇠는 저장하지 않는다

    def test_declining_saves_nothing_and_discards_the_token(self):
        code, out, saved = self.run_main([APP_ID, REDIRECT, "n"], good_script())
        self.assertEqual(code, 0)
        self.assertEqual(saved, [])
        self.assertNotIn(LONG, out)

    def test_show_token_prints_it_only_when_asked_and_saves_nothing(self):
        code, out, saved = self.run_main([APP_ID, REDIRECT], good_script(), argv=["--show-token"])
        self.assertEqual(code, 0)
        self.assertIn(LONG, out)
        self.assertEqual(saved, [])
        self.assertNotIn(SECRET, out)

    def test_failure_prints_a_message_without_secrets(self):
        code, out, saved = self.run_main([APP_ID, REDIRECT], [(400, {"error": {"message": f"x {CODE} {SECRET}"}})])
        self.assertEqual(code, 1)
        self.assertEqual(saved, [])
        for s in (SECRET, CODE):
            self.assertNotIn(s, out)

    def test_save_failure_never_prints_the_value(self):
        def boom(name, value):
            raise PermissionError(value)  # 예외 메시지에 값이 들어 있어도 출력하면 안 된다
        lines, inputs, secrets = [], iter([APP_ID, REDIRECT, "y"]), iter([CODE, SECRET])
        code = gt.main([], transport=FakeTransport(good_script()), prompt=lambda _="": next(inputs),
                       secret_prompt=lambda _="": next(secrets), now=NOW, env_setter=boom, out=lines.append)
        self.assertEqual(code, 1)
        self.assertNotIn(LONG, "\n".join(lines))

    def test_missing_app_id_makes_no_network_call(self):
        t = FakeTransport([])
        code = gt.main([], transport=t, prompt=lambda _="": "", secret_prompt=lambda _="": "", now=NOW,
                       env_setter=lambda n, v: None, out=lambda s: None)
        self.assertEqual(code, 2)
        self.assertEqual(t.calls, [])


class FromTokenTests(unittest.TestCase):
    """대시보드 '사용자 토큰 생성기'로 만든 토큰을 붙여 넣는 경로 (리디렉션 URI와 앱 시크릿이 필요 없다)."""

    def run_main(self, answers, script, argv=("--from-token",), pasted=LONG):
        lines, saved = [], []
        inputs = iter(answers)
        t = FakeTransport(script)
        code = gt.main(list(argv), transport=t, prompt=lambda _="": next(inputs), secret_prompt=lambda _="": pasted,
                       now=NOW, env_setter=lambda n, v: saved.append((n, v)), out=lines.append)
        return code, chr(10).join(lines), saved, t

    def test_valid_token_is_verified_read_only_and_saved_after_confirmation(self):
        code, out, saved, t = self.run_main(["y"], [(200, {"id": "777"})])
        self.assertEqual(code, 0, out)
        self.assertEqual(dict(saved)[post.USER_ENV], "777")
        self.assertEqual(dict(saved)[post.TOKEN_ENV], LONG)
        self.assertEqual(dict(saved)[post.EXPIRES_ENV], "2026-12-20")  # 2026-10-21 + 60일(추정)
        self.assertEqual([c[0] for c in t.calls], ["GET"])  # 읽기 전용 호출 하나뿐
        self.assertNotIn(LONG, out)

    def test_expiry_is_labelled_as_an_estimate(self):
        _, out, _, _ = self.run_main(["y"], [(200, {"id": "777"})])
        self.assertIn("60일", out)
        self.assertIn("대시보드에 표시된 만료일이 다르면", out)

    def test_invalid_token_is_rejected_without_leaking_it(self):
        code, out, saved, _ = self.run_main(["y"], [(401, {"error": {"type": "OAuthException", "code": 190, "message": f"bad {LONG}"}})])
        self.assertEqual(code, 1)
        self.assertEqual(saved, [])
        self.assertNotIn(LONG, out)

    def test_network_error_saves_nothing(self):
        code, out, saved, _ = self.run_main(["y"], [post.NetworkError("TimeoutError")])
        self.assertEqual(code, 1)
        self.assertEqual(saved, [])

    def test_empty_paste_makes_no_call(self):
        code, out, saved, t = self.run_main([], [], pasted="   ")
        self.assertEqual(code, 2)
        self.assertEqual(t.calls, [])

    def test_declining_saves_nothing(self):
        code, out, saved, _ = self.run_main(["n"], [(200, {"id": "777"})])
        self.assertEqual(code, 0)
        self.assertEqual(saved, [])
        self.assertNotIn(LONG, out)

    def test_show_token_with_from_token_prints_it_only_when_asked(self):
        code, out, saved, _ = self.run_main([], [(200, {"id": "777"})], argv=["--from-token", "--show-token"])
        self.assertEqual(code, 0)
        self.assertIn(LONG, out)
        self.assertEqual(saved, [])

    def test_no_app_secret_or_redirect_is_asked(self):
        asked = []
        lines = []
        code = gt.main(["--from-token"], transport=FakeTransport([(200, {"id": "777"})]),
                       prompt=lambda q="": asked.append(q) or "n", secret_prompt=lambda q="": LONG, now=NOW,
                       env_setter=lambda n, v: None, out=lines.append)
        self.assertEqual(code, 0)
        self.assertFalse(any("앱 ID" in q or "리디렉션" in q for q in asked))


if __name__ == "__main__":
    unittest.main()
