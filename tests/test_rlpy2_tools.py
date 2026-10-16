"""Offline tests for tools.rlpy2_tools with fake RLPy / RLPy2 modules (logic only; live proof is in the docstrings)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _Result:
    def __init__(self, s):
        self.s = s

    def __str__(self):
        return self.s


def _install_fakes(undo_steps=0):
    calls = []
    rl = types.ModuleType("RLPy")
    state = {"silent": False}

    class RGlobal:
        @staticmethod
        def BeginAction(label):
            calls.append(("begin", label))

        @staticmethod
        def EndAction():
            calls.append(("end",))

        @staticmethod
        def GetSilentMode():
            return state["silent"]
    rl.RGlobal = RGlobal
    sys.modules["RLPy"] = rl

    r2 = types.ModuleType("RLPy2")
    hist = {"undo": undo_steps, "redo": 0}

    class Query:
        @staticmethod
        def GetInterface():
            return Query()

        def CanUndo(self):
            return hist["undo"] > 0

        def CanRedo(self):
            return hist["redo"] > 0

    class System:
        @staticmethod
        def GetInterface():
            return System()

        def Undo(self):
            hist["undo"] -= 1; hist["redo"] += 1
            return _Result("RL_OK")

        def Redo(self):
            hist["redo"] -= 1; hist["undo"] += 1
            return _Result("RL_OK")

        def RecordUndoStep(self, immediate=False):
            calls.append(("record", immediate))
            return _Result("RL_OK")

        def SetSilentMode(self, v):
            calls.append(("silent", v)); state["silent"] = v
    r2.Query, r2.System = Query, System
    sys.modules["RLPy2"] = r2
    import importlib
    from tools import rlpy2_tools
    rlpy2_tools = importlib.reload(rlpy2_tools)  # rebind its module-level RLPy to this test's fake
    return rlpy2_tools, calls, hist


class TestRlpy2Tools(unittest.TestCase):
    def test_undo_stops_when_history_empty(self):
        mod, _, hist = _install_fakes(undo_steps=2)
        r = mod.undo({"steps": 5})
        self.assertEqual((r["done"], r["can_undo"], r["can_redo"]), (2, False, True))
        self.assertTrue(r["ok"])
        r = mod.redo({})
        self.assertEqual(r["done"], 1)

    def test_undo_nothing_explains_why(self):
        mod, _, _ = _install_fakes(undo_steps=0)
        r = mod.undo({})
        self.assertFalse(r["ok"])
        self.assertIn("undo_label", r["note"])

    def test_undo_step_brackets_even_on_error(self):
        mod, calls, _ = _install_fakes()
        with self.assertRaises(ValueError):
            with mod.undo_step("x"):
                raise ValueError
        self.assertEqual(calls, [("begin", "x"), ("end",)])

    def test_silent_mode_restores_previous(self):
        mod, calls, _ = _install_fakes()
        with mod.silent_mode(True):
            pass
        self.assertEqual(calls, [("silent", True), ("silent", False)])
        calls.clear()
        with mod.silent_mode(False):
            pass
        self.assertEqual(calls, [])

    def test_crowd_scatter_validates_actor_paths(self):
        mod, _, _ = _install_fakes()
        with self.assertRaises(ValueError):
            mod.crowd_scatter({"actors": []})
        with self.assertRaises(FileNotFoundError):
            mod.crowd_scatter({"actors": [r"C:\nope\missing.iAvatar"]})

    def test_ok_raises_on_non_ok(self):
        mod, _, _ = _install_fakes()
        mod._ok(_Result("RL_OK"), "x")
        with self.assertRaisesRegex(RuntimeError, "GeneratePlacement returned RL_FAIL"):
            mod._ok(_Result("RL_FAIL"), "GeneratePlacement")


if __name__ == "__main__":
    unittest.main()
