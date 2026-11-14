"""Two OS processes must not independently publish the same post."""
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
from test_post import make_root, NOW, FAKE


def attempt(root, start, results):
    class Transport:
        calls = 0
        def request(self, method, url, data, timeout=30):
            self.calls += 1
            time.sleep(0.3)
            return 200, {"id": "synthetic"}
    transport = Transport()
    with patch.dict(os.environ, {
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


class PublishConcurrencyTests(unittest.TestCase):
    def test_account_lock_applies_across_checkouts_and_releases_after_failure(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            with patch.dict(os.environ, {"THREADS_USER_ID": "synthetic-shared-account"}):
                with self.assertRaisesRegex(ValueError, "synthetic"):
                    with post.publishing_locks(Path(one)):
                        with self.assertRaises(post.PublishBusy):
                            with post.publishing_locks(Path(two)):
                                self.fail("same account entered twice")
                        raise ValueError("synthetic failure")
                with post.publishing_locks(Path(two)):
                    pass

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
