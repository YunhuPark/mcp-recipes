"""Two OS processes must not independently publish the same post."""
import contextlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
from threading import BrokenBarrierError
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import post
from test_post import make_root, NOW, FAKE, FakeTransport, good_script, OK_CHECK


def attempt(root, start, results, home=None):
    class Transport:
        calls = 0
        def request(self, method, url, data, timeout=30):
            self.calls += 1
            time.sleep(0.3)
            return 200, {"id": "synthetic"}
    transport = Transport()
    with patch.object(post.Path, "home", return_value=Path(home) if home else Path(root) / "test-home"), patch.dict(os.environ, {
        "THREADS_LIVE": "yes", "THREADS_ACCESS_TOKEN": FAKE,
        "THREADS_USER_ID": "lock-regression", "THREADS_TOKEN_EXPIRES": "2026-12-01",
    }):
        def check(root):
            # Both old processes have read eligibility state before either reserves.
            try:
                start.wait(2)
            except BrokenBarrierError:
                pass  # Fixed implementation rejects the other process at its lock.
            return True, ""
        start.wait(10)
        code = post.main(["D02", "--publish", "--wait", "0"], root=Path(root),
                         now=NOW, transport=transport, confirm=lambda: "yes",
                         check=check, sleep=lambda _: None)
        results.put((code, transport.calls))


class PublishOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.one = make_root(self.base / "one")
        self.two = make_root(self.base / "two")
        self.env = patch.dict(os.environ, {
            "THREADS_LIVE": "yes", "THREADS_ACCESS_TOKEN": FAKE,
            "THREADS_USER_ID": "canonical-regression-" + self.base.name,
            "THREADS_TOKEN_EXPIRES": "2026-12-01",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        # Force any new persistent account store to this synthetic test home.
        self.home = patch.object(post.Path, "home", return_value=self.base / "home")
        self.home.start()
        self.addCleanup(self.home.stop)

    def run_at(self, root, pid, transport, *extra):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = post.main([pid, "--publish", "--wait", "0", *extra], root=root,
                             transport=transport, now=NOW, confirm=lambda: "yes",
                             check=OK_CHECK, sleep=lambda _: None)
        return code, output.getvalue()

    def test_successful_attempt_rejects_second_checkout_after_release(self):
        first, second = FakeTransport(good_script()), FakeTransport(good_script())
        self.assertEqual(self.run_at(self.one, "D02", first)[0], 0)
        code, output = self.run_at(self.two, "D02", second, "--allow-extra")
        self.assertEqual(code, 1, output)
        self.assertEqual(second.calls, [])
        self.assertIn("canonical publishing checkout", output)

    def test_uncertain_attempt_rejects_second_checkout_even_for_other_post(self):
        first = FakeTransport([(200, {"id": "C1"}), post.NetworkError("synthetic timeout")])
        self.assertEqual(self.run_at(self.one, "D02", first)[0], 1)
        state = json.loads((self.one / post.STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(state["posts"]["D02"]["state"], "UNCERTAIN")
        second = FakeTransport(good_script())
        code, output = self.run_at(self.two, "D03", second, "--allow-extra")
        self.assertEqual(code, 1, output)
        self.assertEqual(second.calls, [])
        self.assertIn("canonical publishing checkout", output)

    def test_daily_budget_cannot_be_bypassed_with_other_checkout_and_post(self):
        self.assertEqual(self.run_at(self.one, "D02", FakeTransport(good_script()))[0], 0)
        second = FakeTransport(good_script())
        code, output = self.run_at(self.two, "D03", second)
        self.assertEqual(code, 1, output)
        self.assertEqual(second.calls, [])
        same = FakeTransport(good_script())
        code, output = self.run_at(self.one, "D03", same)
        self.assertEqual(code, 1, output)
        self.assertEqual(same.calls, [])
        self.assertIn("하루 1개", output)

    def test_invalid_ownership_record_fails_closed_without_transport(self):
        self.assertEqual(self.run_at(self.one, "D02", FakeTransport(good_script()))[0], 0)
        owner = next((self.base / "home" / ".mcp-recipes" / "publishing").glob("*.owner.json"))
        owner.write_text("{interrupted first claim", encoding="utf-8")
        transport = FakeTransport(good_script())
        code, output = self.run_at(self.one, "D03", transport, "--allow-extra")
        self.assertEqual(code, 1, output)
        self.assertEqual(transport.calls, [])
        self.assertIn("Cannot verify the canonical", output)

    def test_dry_run_does_not_claim_publishing_ownership(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = post.main(["D02"], root=self.two, now=NOW, check=OK_CHECK)
        self.assertEqual(code, 0)
        self.assertFalse(list((self.base / "home").rglob("*.owner.json")))
        self.assertEqual(self.run_at(self.one, "D02", FakeTransport(good_script()))[0], 0)


class PublishConcurrencyTests(unittest.TestCase):
    def test_account_lock_applies_across_checkouts_and_releases_after_failure(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            with patch.object(post.Path, "home", return_value=Path(one) / "test-home"), patch.dict(os.environ, {"THREADS_USER_ID": "synthetic-shared-account"}):
                with self.assertRaisesRegex(ValueError, "synthetic"):
                    with post.publishing_locks(Path(one)):
                        with self.assertRaises(post.PublishBusy):
                            with post.publishing_locks(Path(two)):
                                self.fail("same account entered twice")
                        raise ValueError("synthetic failure")
                with post.publishing_locks(Path(two)):
                    pass

    def test_two_checkouts_first_claim_is_exclusive_and_owner_can_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            roots = [make_root(base / name) for name in ("one", "two")]
            home = base / "test-home"
            ctx = multiprocessing.get_context("spawn")
            start, results = ctx.Barrier(2), ctx.Queue()
            workers = [ctx.Process(target=attempt, args=(str(root), start, results, str(home))) for root in roots]
            for worker in workers:
                worker.start()
            try:
                outcomes = [results.get(timeout=20) for _ in workers]
            finally:
                for worker in workers:
                    worker.join(5)
                    if worker.is_alive():
                        worker.terminate()
                        worker.join()
            self.assertTrue(all(worker.exitcode == 0 for worker in workers))
            self.assertEqual(sum(calls for _, calls in outcomes), 2)
            self.assertEqual(sum(code == 0 for code, _ in outcomes), 1)
            owner = next(root for root in roots if (root / post.STATE_FILE).exists())
            other = next(root for root in roots if root != owner)
            with patch.object(post.Path, "home", return_value=home), patch.dict(os.environ, {
                "THREADS_LIVE": "yes", "THREADS_ACCESS_TOKEN": FAKE,
                "THREADS_USER_ID": "lock-regression", "THREADS_TOKEN_EXPIRES": "2026-12-01",
            }), contextlib.redirect_stdout(io.StringIO()):
                # Both OS processes exited: the rejected checkout remains rejected
                # while canonical owner can take both locks and explicitly post extra.
                blocked, allowed = FakeTransport(good_script()), FakeTransport(good_script())
                kwargs = dict(now=NOW, confirm=lambda: "yes", check=OK_CHECK, sleep=lambda _: None)
                self.assertEqual(post.main(["D03", "--publish", "--allow-extra", "--wait", "0"],
                                           root=other, transport=blocked, **kwargs), 1)
                self.assertEqual(blocked.calls, [])
                self.assertEqual(post.main(["D03", "--publish", "--allow-extra", "--wait", "0"],
                                           root=owner, transport=allowed, **kwargs), 0)
                self.assertEqual(len(allowed.calls), 2)

    def test_two_processes_only_one_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            ctx = multiprocessing.get_context("spawn")
            start, results = ctx.Barrier(2), ctx.Queue()
            workers = [ctx.Process(target=attempt, args=(str(root), start, results)) for _ in range(2)]
            for worker in workers:
                worker.start()
            try:
                outcomes = [results.get(timeout=20) for _ in workers]
            finally:
                for worker in workers:
                    worker.join(5)
                    if worker.is_alive():
                        worker.terminate()
                        worker.join()
            self.assertEqual(sum(calls for _, calls in outcomes), 2)
            self.assertEqual(sum(code == 0 for code, _ in outcomes), 1)


if __name__ == "__main__":
    unittest.main()
