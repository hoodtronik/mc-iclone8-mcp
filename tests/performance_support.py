"""Small deterministic SDK stand-ins; never claims native RLPy verification."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch


class Time:
    def __init__(self, tick=0):
        self.tick = tick

    @staticmethod
    def FromValue(tick):
        return Time(tick)

    def ToInt(self):
        return self.tick


class FloatControl:
    def __init__(self, sdk, initial=0):
        self.sdk, self.initial, self.values = sdk, initial, {}
        self.fail = False
        self.reject = False

    def GetValue(self, t, default):
        return 1, self.values.get(t.tick, self.initial)

    def SetValue(self, t, value):
        self.sdk.edits.append(("channel", t.tick, value))
        if self.fail:
            return 0
        if not self.reject:
            self.values[t.tick] = value
        return 1


class Bone:
    def __init__(self, name, sdk):
        self.name, self.sdk = name, sdk
        self.world = lambda: ([0, 0, 0], [0, 0, 0, 1])

    def GetName(self):
        return self.name

    def Update(self):
        pass

    def WorldTransform(self):
        pos, rot = self.world()
        return types.SimpleNamespace(
            T=lambda: types.SimpleNamespace(**dict(zip("xyz", pos))),
            R=lambda: types.SimpleNamespace(**dict(zip("xyzw", rot))),
        )


class Clip:
    def __init__(self, sdk, start=2, length=8, speed=2):
        self.sdk, self.start, self.length, self.speed = sdk, start, length, speed
        self.channels = {}
        self.transition, self.curve, self.strength = 0, "linear", 50
        self.loops = 0

    def ClipTimeToSceneTime(self, t):
        return Time(round(self.start * 6000 + t.tick / self.speed))

    def SceneTimeToClipTime(self, t):
        return Time(round((t.tick - self.start * 6000) * self.speed))

    def GetClipLength(self):
        return Time(round(self.length * 6000 / self.speed))

    def GetLength(self):
        return Time(round(self.length * 6000))

    def GetSpeed(self):
        return self.speed

    def GetControl(self, key, bone):
        def get(path):
            identity = (bone.name, path)
            if identity not in self.channels:
                self.channels[identity] = FloatControl(
                    self.sdk, 0.2 if path.startswith("Rotation") else 1
                )
            return self.channels[identity]

        return types.SimpleNamespace(
            GetDataBlock=lambda: types.SimpleNamespace(GetControl=get)
        )

    def SetSpeed(self, speed):
        self.sdk.edits.append(("speed", speed))
        self.speed = speed
        return 1

    def SetLength(self, t):
        self.sdk.edits.append(("length", t.tick))
        self.length = t.tick / 6000
        return 1

    def SetLoopCount(self, n):
        self.loops = n
        return 1

    def SetTransitionRange(self, t):
        self.transition = t.tick / 6000
        return 1

    def GetTransitionRange(self):
        return Time(round(self.transition * 6000))

    def SetTransitionType(self, fade_in, curve, strength):
        self.curve, self.strength = curve, strength
        return 1

    def GetTransitionType(self, fade_in):
        return self.curve

    def GetTransitionStrength(self, fade_in):
        return self.strength


class Skeleton:
    def __init__(self, sdk):
        self.sdk = sdk
        self.clips = [Clip(sdk)]
        self.bones = [
            Bone(n, sdk)
            for n in ("Arm_R", "Arm_L", "Finger_R", "Head", "Eye_R", "Eye_L")
        ]

    def GetSkinBones(self):
        return self.bones

    def GetClipCount(self):
        return len(self.clips)

    def GetClip(self, i):
        return self.clips[i]

    def BreakClip(self, t):
        s = t.tick / 6000
        for i, clip in enumerate(self.clips):
            end = clip.start + clip.length / clip.speed
            if clip.start < s < end:
                self.clips[i : i + 1] = [
                    Clip(self.sdk, clip.start, s - clip.start, 1),
                    Clip(self.sdk, s, end - s, 1),
                ]
                self.sdk.edits.append(("split", s))
                return 1
        return 0

    def MergeClips(self, a, b):
        a.length = (a.length / a.speed + b.length / b.speed) * a.speed
        self.clips.remove(b)
        return 1


class SDK:
    def __init__(self):
        self.edits = []
        self.tick = 0
        self.saved = []
        self.sk = Skeleton(self)
        self.face = Face(self)
        self.reach_keys = []
        self.hik = types.SimpleNamespace(
            GetReachKeys=lambda e: self.reach_keys, AddReachKey=lambda *a: 1
        )
        self.avatar = types.SimpleNamespace(
            GetName=lambda: "Actor",
            GetSkeletonComponent=lambda: self.sk,
            GetFaceComponent=lambda: self.face,
            GetHikEffectorComponent=lambda: self.hik,
            Update=lambda: None,
        )
        self.camera = types.SimpleNamespace(GetName=lambda: "Cam")
        self.active_camera = self.camera
        self.fps = types.SimpleNamespace(
            ToFloat=lambda: 24.0,
            IndexedFrameTime=lambda n: Time(n * 250),
            GetFrameIndex=lambda t: t.tick // 250,
        )
        self.config = {"fps": "24", "width": 32, "height": 32}
        self.RTime = Time
        self.RStatus = types.SimpleNamespace(Success=1)
        self.RGlobal = types.SimpleNamespace(
            IsPlaying=lambda: False,
            GetTime=lambda: Time(self.tick),
            SetTime=self.set_time,
            GetEndTime=lambda: Time(60000),
            GetFps=lambda: self.fps,
            GetRenderExportImageSequenceParameter=lambda: types.SimpleNamespace(
                kCommon=types.SimpleNamespace(
                    kFps=self.config["fps"],
                    nOutputSizeWidth=self.config["width"],
                    nOutputSizeHeight=self.config["height"],
                )
            ),
            RenderImageSequence=lambda *a: 1,
            RenderImageSequenceOpenPoseKeyPoint=lambda *a: 1,
        )
        self.RScene = types.SimpleNamespace(
            GetAvatars=lambda: [self.avatar],
            GetCameras=lambda: [self.camera],
            GetCurrentCamera=lambda: self.active_camera,
            SetCurrentCamera=self.set_camera,
        )
        self.RFileIO = types.SimpleNamespace(
            SaveProject=self.save,
            ExportGlbFile=lambda *a: 1,
            ExportFbxFile=lambda *a: 1,
        )
        self.RExportGlbSetting = object
        self.ETransitionType_Linear = "linear"
        self.ETransitionType_Step = "step"
        self.ETransitionType_Ease_In = "ease_in"
        self.ETransitionType_Ease_Out = "ease_out"
        self.ETransitionType_Ease_In_Out = "ease_in_out"
        self.EHikEffector_RightHand = "right_hand"
        self.Qt = types.SimpleNamespace(
            QtWidgets=types.SimpleNamespace(
                QApplication=types.SimpleNamespace(processEvents=lambda: None)
            )
        )
        self.fight = types.SimpleNamespace(
            _EFFECTORS={"right_hand": "EHikEffector_RightHand"},
            _find_any=lambda name: types.SimpleNamespace(GetName=lambda: name),
            reach_key=self.write_reach,
        )

    def write_reach(self, args):
        self.edits.append(("reach", args))
        return {"status": "ok"}

    def set_time(self, t):
        self.tick = t.tick
        return 1

    def set_camera(self, cam):
        self.active_camera = cam
        return 1

    def save(self, path):
        Path(path).write_bytes(b"project backup")
        self.saved.append(path)
        return 1


class Face:
    def __init__(self, sdk):
        self.sdk = sdk
        self.editing = False
        self.fail = False

    def GetExpressionGroups(self):
        return ["group"]

    def GetExpressionNames(self, group):
        return ["Smile", "Frown"]

    def GetClipByTime(self, t):
        return object()

    def BeginKeyEditing(self):
        self.editing = True

    def EndKeyEditing(self):
        self.editing = False

    def AddExpressionKeys(self, t, names, values, interval):
        self.sdk.edits.append(("face", t.tick, names, values))
        return 0 if self.fail else 1


def load(name, sdk, p=None):
    import tools

    namespace = {"RLPy": sdk, "PySide2": sdk.Qt}
    overrides = {"fight_tools": sdk.fight}
    if p is None:
        previz = types.SimpleNamespace(_avatar=lambda name: avatar_named(sdk, name))
        namespace["tools.previz"] = previz
        overrides["previz"] = previz
    else:
        namespace["tools.performance"] = p
        overrides["performance"] = p
    with context(overrides, namespace, tools):
        spec = importlib.util.spec_from_file_location(
            name + "_test_instance",
            Path(__file__).parents[1] / "tools" / (name + ".py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def avatar_named(sdk, name):
    if name != "Actor":
        raise ValueError("Avatar not found")
    return sdk.avatar


class context:
    def __init__(self, overrides, namespace, tools):
        self.overrides, self.namespace, self.tools = overrides, namespace, tools

    def __enter__(self):
        import contextlib

        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.dict(sys.modules, self.namespace))
        for key, value in self.overrides.items():
            self.stack.enter_context(patch.object(self.tools, key, value, create=True))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)
