import importlib.util
import math
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch


class Timer:
    def SetInterval(self, value):
        pass

    def SetSingleShot(self, value):
        pass

    def RegisterPyTimerCallback(self, callback):
        self.callback = callback

    def Start(self):
        pass


class DispatchTests(unittest.TestCase):
    def setUp(self):
        fake = types.SimpleNamespace(RPyTimerCallback=object, RPyTimer=Timer)
        spec = importlib.util.spec_from_file_location("dispatch_under_test", Path(__file__).parents[1] / "dispatch.py")
        self.dispatch = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"RLPy": fake}):
            spec.loader.exec_module(self.dispatch)

    def worker(self, function):
        results = {}
        def run():
            try:
                results["value"] = function()
            except Exception as error:
                results["error"] = error
        thread = threading.Thread(target=run)
        thread.start()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        return results

    def test_unstarted_worker_refuses_rlpy(self):
        called = []
        result = self.worker(lambda: self.dispatch.run(lambda: called.append(1)))
        self.assertIsInstance(result["error"], RuntimeError)
        self.assertEqual(called, [])

    def test_main_thread_can_run_before_start(self):
        self.assertEqual(self.dispatch.run(lambda: 7), 7)

    def test_owner_thread_executes_without_waiting(self):
        self.dispatch.start()
        self.assertEqual(self.dispatch.run(lambda: 9, timeout=0), 9)
        self.assertTrue(self.dispatch._queue.empty())

    def test_start_from_worker_refused(self):
        self.assertIsInstance(self.worker(self.dispatch.start)["error"], RuntimeError)
        self.assertIsNone(self.dispatch._timer)

    def test_queued_timeout_never_edits_on_later_tick(self):
        self.dispatch.start()
        called = []
        result = self.worker(lambda: self.dispatch.run(lambda: called.append(1), timeout=0))
        self.assertIn("cancelled", str(result["error"]))
        self.dispatch._callback.Timeout()
        self.assertEqual(called, [])

    def test_cancelled_jobs_do_not_delay_next_job(self):
        self.dispatch.start()
        cancelled = self.dispatch._Job(lambda: self.fail("cancelled job executed"))
        with self.assertRaises(TimeoutError):
            cancelled.wait(0)
        good = self.dispatch._Job(lambda: 42)
        self.dispatch._queue.put(cancelled)
        self.dispatch._queue.put(good)
        self.dispatch._callback.Timeout()
        self.assertEqual(good.wait(0), 42)

    def test_started_timeout_warns_and_completion_survives(self):
        entered, finish = threading.Event(), threading.Event()
        def slow():
            entered.set()
            finish.wait(1)
            return 23
        job = self.dispatch._Job(slow)
        thread = threading.Thread(target=job.execute)
        thread.start()
        self.assertTrue(entered.wait(1))
        try:
            with self.assertRaisesRegex(TimeoutError, "may still complete"):
                job.wait(0)
        finally:
            finish.set()
            thread.join(1)
        self.assertEqual(job.wait(0), 23)

    def test_callback_returns_exception_to_worker(self):
        def fail():
            raise ValueError("bad scene")
        job = self.dispatch._Job(fail)
        job.execute()
        with self.assertRaisesRegex(ValueError, "bad scene"):
            job.wait(0)

    def test_real_worker_job_runs_on_owner(self):
        self.dispatch.start()
        result = {}
        queued = threading.Event()
        original_put = self.dispatch._queue.put
        def put(job):
            original_put(job)
            queued.set()
        self.dispatch._queue.put = put
        thread = threading.Thread(target=lambda: result.update(value=self.dispatch.run(threading.get_ident)))
        thread.start()
        self.assertTrue(queued.wait(1))
        self.dispatch._callback.Timeout()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["value"], threading.get_ident())

    def test_event_pump_cannot_interleave_another_job(self):
        self.dispatch.start()
        order = []
        second = self.dispatch._Job(lambda: order.append("second"))
        def first():
            order.append("first-start")
            self.dispatch._queue.put(second)
            self.dispatch._callback.Timeout()  # Simulate a Qt event pump.
            order.append("first-end")
        self.dispatch._queue.put(self.dispatch._Job(first))
        self.dispatch._callback.Timeout()
        self.assertEqual(order, ["first-start", "first-end"])
        self.dispatch._callback.Timeout()
        self.assertEqual(order, ["first-start", "first-end", "second"])

    def test_invalid_timeouts(self):
        for value in (-1, math.nan, math.inf, True, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.dispatch.run(lambda: None, value)


if __name__ == "__main__":
    unittest.main()
