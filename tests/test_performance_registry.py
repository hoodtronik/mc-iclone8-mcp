import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from performance_support import SDK

from mcp_handler import MCPHandler


class RegistrySDK(SDK):
    def __getattr__(self, name):
        if name.startswith("E"):
            return name  # Constants for metadata registration only.
        raise AttributeError(name)


class PerformanceRegistryTests(unittest.TestCase):
    def test_full_registry_reload_schema_and_mcp_adapter(self):
        sdk = RegistrySDK()
        spec = importlib.util.spec_from_file_location(
            "iclone_main_registry_test", Path(__file__).parents[1] / "main.py"
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"RLPy": sdk, "PySide2": sdk.Qt}):
            spec.loader.exec_module(module)
            registry = module._tool_registry()
            new = [
                "capture_pose",
                "set_pose_keys",
                "apply_hand_pose",
                "split_motion_clip",
                "trim_motion_clip",
                "merge_motion_clips",
                "hold_motion_pose",
                "apply_contact_interval",
                "check_contact_pose",
                "plan_actor_gaze",
                "validate_shot_list",
                "build_shot_list_verified",
                "schedule_face_performance",
                "export_previz_bundle",
                "inspect_glb",
                "export_animation_package",
            ]
            for name in new:
                self.assertIn(name, registry)
                self.assertTrue(registry[name]["main_thread"])
                json.dumps(registry[name]["inputSchema"])
            registry["capture_pose"]["main_thread"] = False
            result = MCPHandler(registry)(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "capture_pose",
                            "arguments": {
                                "avatar": "Actor",
                                "seconds": 3,
                                "bones": ["Head"],
                            },
                        },
                    }
                )
            )
            response = json.loads(result)
            self.assertNotIn("isError", response["result"])
            self.assertIn(
                "Head", json.loads(response["result"]["content"][0]["text"])["bones"]
            )


if __name__ == "__main__":
    unittest.main()
