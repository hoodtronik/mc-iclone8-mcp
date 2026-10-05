import math
import queue
import threading

import RLPy


_queue = queue.Queue()
_timer = None
_callback = None
_owner_thread = None


class _Job:
    def __init__(self, function):
        self.function = function
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.state = "queued"
        self.result = {}

    def execute(self):
        with self.lock:
            if self.state != "queued":
                return
            self.state = "running"
        try:
            self.result["value"] = self.function()
        except Exception as error:
            self.result["error"] = error
        finally:
            with self.lock:
                self.state = "finished"
                self.done.set()

    def wait(self, timeout):
        if not self.done.wait(timeout):
            with self.lock:
                if self.state == "queued":
                    self.state = "cancelled"
                    raise TimeoutError("iClone operation timed out before execution; cancelled, no changes made")
                if self.state == "running":
                    raise TimeoutError("iClone operation timed out after execution started; it may still complete. "
                                       "Inspect the scene before retrying; do not repeat an edit blindly")
                # Completion raced with the wait deadline: return the actual result.
        if "error" in self.result:
            raise self.result["error"]
        return self.result.get("value")


class _Callback(RLPy.RPyTimerCallback):
    def __init__(self):
        RLPy.RPyTimerCallback.__init__(self)
        self.busy = False

    def Timeout(self):
        # Tools may pump Qt events. Do not let a nested timer callback interleave
        # another HTTP edit with an operation that is still sampling or rendering.
        if self.busy:
            return
        self.busy = True
        try:
            # Discard cancelled jobs without costing one timer tick each.
            while True:
                try:
                    job = _queue.get_nowait()
                except queue.Empty:
                    return
                job.execute()
                if job.state != "cancelled":
                    return
        finally:
            self.busy = False


def start():
    global _timer, _callback, _owner_thread
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Start the iClone dispatcher from the application main thread")
    if _timer is not None:
        return
    timer = RLPy.RPyTimer()
    timer.SetInterval(50)
    timer.SetSingleShot(False)
    callback = _Callback()
    timer.RegisterPyTimerCallback(callback)
    timer.Start()
    _callback = callback
    _owner_thread = threading.get_ident()
    _timer = timer


def run(function, timeout=120):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("timeout must be a finite, nonnegative number of seconds")
    if threading.get_ident() == _owner_thread:
        return function()
    if _timer is None:
        if threading.current_thread() is threading.main_thread():
            return function()
        raise RuntimeError("iClone dispatcher is not started; refusing to run RLPy on a worker thread")
    job = _Job(function)
    _queue.put(job)
    return job.wait(timeout)
