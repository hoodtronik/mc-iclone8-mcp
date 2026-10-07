# iClone 8 — Agent Reference for Previz Automation (RLPy)

Compiled 2026-09-26 for driving iClone 8 through its embedded Python (RLPy): character blocking,
motions, cameras, and control-pass renders. Nothing was installed and iClone was not run.

## Evidence tags (read these first)

| Tag | Meaning |
|---|---|
| **VERIFIED-WIKI** | Stated on an official Reallusion wiki page (URL given). |
| **VERIFIED-SAMPLE** | Used in Reallusion's official GitHub samples (`github.com/reallusion/iClone`, file given). |
| **VERIFIED-MANUAL** | Stated in the iClone 8 online manual (URL given). |
| **LOCAL-STUB** | Present in the SWIG stub `C:\Program Files\Reallusion\iClone 8\Bin64\RLPy.py` on this machine (iClone.exe FileVersion **8.75.5630.1**). This proves the symbol and its C++ prototype exist. It does **not** prove the call behaves as expected. Nothing was executed. |
| **UNVERIFIED** | No official page or sample found. Probe it at runtime before relying on it. |

Wiki pages come in two families: `IC_Python_API:` (older, often iClone 7-era examples) and
`IC8_Python_API:` / `IC_8_Python_API:` (iClone 8). **Where they conflict, iClone 8 and LOCAL-STUB win.**
The biggest conflict is time (§1.3): the old pages use `RLPy.RTime(1000)`, but in the 8.75 stub `RTime`
has **no int constructor**.

Key sources:
- Index: https://wiki.reallusion.com/IC_8_Python_API · modules: https://wiki.reallusion.com/IC8_Python_API:Modules
- Custom FPS: https://wiki.reallusion.com/IC_8_Python_API:Dealing_With_Custom_FPS
- End effectors: https://wiki.reallusion.com/IC_8_Python_API:End_Effector_Animation
- Samples: https://github.com/reallusion/iClone (SmoothCameraFollow, Camera_Dolly_Zoom, Pose_Manager, BatchRenderFolder, SampleRequests)

---

## 0. Conventions

- **Axes:** Z is up, **−Y is forward**, right-handed. **VERIFIED-WIKI** (IC_8_Python_API).
- **Rotation:** quaternion, Matrix3, or Euler, always in **radians**. Convert with `RLPy.RMath.CONST_DEG_TO_RAD` / `CONST_RAD_TO_DEG`. **VERIFIED-WIKI** (IC_8_Python_API, IC_Python_API:RLPy_RMatrix3).
- **Scale:** `1` = 100 %. **VERIFIED-WIKI**.
- **Units:** distances are **centimetres**. **UNVERIFIED on the wiki**: the API index does not state a unit. This is iClone's UI unit, and the Camera_Dolly_Zoom sample moves the camera in the same units as UI distances.
- **Avatar default facing:** the wiki gives "−Y forward" as a scene convention. That a freshly loaded avatar faces −Y (toward a default front camera) is **UNVERIFIED**. Probe it: load an avatar, read `WorldTransform().R()`, and render a frame.
- **Python / Qt:** Python 3.8, Qt 5.15.2, PySide2. **VERIFIED-WIKI**.

---

## 1. Transforms

### 1.1 Constructors

`RTransform` overloads (**LOCAL-STUB**):
```
RTransform()
RTransform(RTransform)
RTransform(float d, RVector3 s, RQuaternion u, RQuaternion r, RVector3 t)   # wiki form; u = stretch
RTransform(RVector3 s, RQuaternion r, RVector3 t)                          # 3-arg form: scale, rot, pos
RTransform(RMatrix4)
```
- The 3-arg `(scale, rotation, translation)` form is **VERIFIED-WIKI** (IC_Python_API:RLPy_RTransformControl example) and **VERIFIED-SAMPLE** (SmoothCameraFollow/main.py).
- Accessors `S()`, `R()`, `T()`, `U()`, `D()`, `Matrix()`, `Inverse()` are **VERIFIED-WIKI** (IC_Python_API:RLPy_RTransform).

`RQuaternion` (**VERIFIED-WIKI**, IC_Python_API:RLPy_RQuaternion):
- Constructors: `()`, `(RVector4)`, `(RQuaternion)`, `(RVector3 axis, float angle)`, `(RMatrix3)`.
- Methods: `FromRotationMatrix(RMatrix3)`, `FromAxisAngle(axis, angle)`, `ToRotationMatrix()` (**LOCAL-STUB**, also used in Pose_Manager), `Multiply`, `Inverse`, `Normalize`.

`RMatrix3` (**VERIFIED-WIKI**, IC_Python_API:RLPy_RMatrix3):
- `FromEulerAngle(order, rx, ry, rz)`, `ToEulerAngle(order, rx, ry, rz)`, `RotationX/Y/Z(angle)`, `FromAxisAngle(axis, angle)`.
- Euler-order enums: `RLPy.EEulerOrder_XYZ | _ZYX | _XZY | _YZX | _YXZ | _ZXY` (**LOCAL-STUB**; XYZ is shown on the wiki).
- The stub marks `FromEulerAngle` **static** and returning `RMatrix3`. `ToEulerAngle(order)` also has a single-argument overload that returns an `RVector3`. The wiki uses the 4-argument form, which returns a list whose `[0]`, `[1]` and `[2]` are x, y and z.

### 1.2 Pattern A: build a transform from Euler degrees (official building blocks)

Every step below is **VERIFIED-WIKI** or **VERIFIED-SAMPLE**. The wiki does not show one sample that goes all the way from Euler degrees to `SetValue`, so this is an assembly of official steps.
```python
import RLPy
D2R = RLPy.RMath.CONST_DEG_TO_RAD

def make_transform(pos_cm, rot_deg, scale=(1, 1, 1)):
    # RMatrix3.FromEulerAngle: wiki RLPy_RMatrix3 example (called on an instance there; the stub marks it static)
    m = RLPy.RMatrix3().FromEulerAngle(RLPy.EEulerOrder_XYZ,
                                       rot_deg[0] * D2R, rot_deg[1] * D2R, rot_deg[2] * D2R)
    # RQuaternion().FromRotationMatrix(m): SmoothCameraFollow/main.py line 143
    q = RLPy.RQuaternion().FromRotationMatrix(m)
    # RTransform(scale, rot, pos): SmoothCameraFollow/main.py line 145
    return RLPy.RTransform(RLPy.RVector3(*scale), q, RLPy.RVector3(*pos_cm))

obj = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, "Box")        # or an avatar or camera
t = RLPy.RTime.FromValue(0)                                         # iClone 8 time (see 1.3)
obj.GetControl("Transform").SetValue(t, make_transform((0, -200, 0), (0, 0, 180)))
```
- `GetControl("Transform").SetValue(time, RTransform)` writes a key at `time`. **VERIFIED-SAMPLE** (SmoothCameraFollow `camera.GetControl("Transform").SetValue(current_time, new_transform)`) and **VERIFIED-WIKI** (RLPy_RTransformControl).
- The avatar yaw sign that turns a character around is **UNVERIFIED** (see §0). Check it once with a render.

### 1.3 Pattern B: per-channel float keys

Set per channel to rotate only yaw, or to move only X. **VERIFIED-SAMPLE** (Camera_Dolly_Zoom/main.py lines 211–224):
```python
ctrl = cam.GetControl("Transform")
db = ctrl.GetDataBlock()
db.SetData("Position/PositionX", t, RLPy.RVariant(x_cm))
db.SetData("Position/PositionY", t, RLPy.RVariant(y_cm))
db.SetData("Position/PositionZ", t, RLPy.RVariant(z_cm))
ctrl.SetKeyTransition(t, RLPy.ETransitionType_Linear, 1.0)   # interpolation of this key
```
The float-control form is **VERIFIED-SAMPLE** (Pose_Manager, SpringJoints) for bone layers. The wiki shows it on bone layer controls:
```python
db.GetControl("Rotation/RotationZ").SetValue(t, yaw_radians)
```
Channel keys used in official code: `Position/PositionX|Y|Z` and `Rotation/RotationX|Y|Z`. Scale keys (`Scale/ScaleX`?) are **UNVERIFIED**.
`ETransitionType_*` values (**LOCAL-STUB**): `Linear, Step, Ease_In, Ease_Out, Ease_In_Out, … _Sine/_Quad/_Cubic/_Back/_Bounce/_Elastic`.

### 1.4 Time: the iClone 8 gotcha

- 6000 ticks per second; `RTime.FromValue(ticks)`; `RTick.FromSecond(s)` and `RTick.FromMilliSecond(ms)`. **VERIFIED-WIKI** (Dealing_With_Custom_FPS).
- Frame and time conversion (**VERIFIED-WIKI**):
  ```python
  fps = RLPy.RGlobal.GetFps()                   # returns an RFps object in iC8 (older wiki page says int 60, which is wrong for iC8)
  t   = RLPy.IndexedFrameTime(frame, fps)        # module-level function
  n   = RLPy.GetFrameIndex(t, fps)
  ```
  **LOCAL-STUB** also shows `fps.IndexedFrameTime(n)`, `fps.GetFrameIndex(t)` and `fps.FrameTimeFromSecond(s)` on `RFps`.
- 🔴 **`RLPy.RTime(1000)`, used in older wiki examples, does not exist in 8.75.** The stub has only `RTime()` (**LOCAL-STUB**).
- 🔴 The samples call `RLPy.RTime.IndexedFrameTime(n, fps)`. The 8.75 stub has **no** such static on `RTime`; only the module-level `RLPy.IndexedFrameTime` exists. Use the module-level function.
- `Control.AddKey(key)` dropped its FPS argument in iC8 (**VERIFIED-WIKI**). The sample `SampleRequests/add_clear_remove_removekeyat.py` still passes `(key, fps)`: that is iC7 code.
- `RTransformKey` path (**VERIFIED-SAMPLE**, add_clear_remove_removekeyat.py): `key = RLPy.RTransformKey(); key.SetTransform(tr); key.SetTime(t); control.AddKey(key)`. Prefer `SetValue`.
- Readback: `obj.WorldTransform().T()` returns an `RVector3`. `.x` works as an attribute in the samples, and `.X()` works as a method on this machine.

---

## 2. Motions

### 2.1 Loading

- `RLPy.RFileIO.LoadMotion(strFilePath, kTime, spObject) -> RStatus` **VERIFIED-WIKI** (https://wiki.reallusion.com/IC8_Python_API:RLPy_RFileIO; the stub confirms `RTime kTime`). It places the clip starting at `kTime` on the avatar's body-motion track.
- `RFileIO.PreLoadMotion(path, obj, kMotionLength)` **VERIFIED-WIKI** (purpose not described).
- Accepted animation types: `imotion, imotionplus, rlmotion, ihand, italk, rltalk, ipath` **VERIFIED-WIKI** (IC_Python_API:RLPy_RFileIO list).
- The wiki does not document an options argument for motion loading.
  - `RGlobal.SetMotionSettingOptions(EMotionSettingOption)` exists (**LOCAL-STUB**) with the flags `ResetMotionRoot`, `ResetMotionRootRotate`, `AlignActorMotion` and `AlignToActorOrientation`. These likely control whether the clip starts where the actor stands. Behaviour is **UNVERIFIED**.
- 🔴 **A success status is not proof (measured on this machine, iclone-rlpy skill §38).** `LoadMotion` has returned `IsError()==False` while nothing moved. Verify by sampling `GetSkinBones()[i].WorldTransform().T()` at two frames.

### 2.2 Clips, transitions, and blending

`avatar.GetSkeletonComponent()` returns an `RISkeletonComponent`. **VERIFIED-WIKI** (https://wiki.reallusion.com/IC8_Python_API:RLPy_RISkeletonComponent):
- `GetClipCount()`, `GetClip(i)`, `GetClipByTime(t)`.
- Experimental: `AddClip(t)`, `BreakClip(t)`, `MergeClips(c1, c2)`, `FlattenMotionClip(c)`, `SampleMotionClip(c, bOptimize)`, `BakeFkToIk(t, bAllClip)`.

`RIClip` (**VERIFIED-WIKI**, https://wiki.reallusion.com/IC8_Python_API:RLPy_RIClip):
- `GetLength/SetLength`, `GetSpeed/SetSpeed`, `GetLoopCount`.
- `SetTransitionRange(kLength)`: blend duration into the clip.
- `SetTransitionType(bFadeIn, eTransitionType, fStrength)`.
- `SetTransitionData`.
- `SceneTimeToClipTime` and `ClipTimeToSceneTime`.

How to blend clips (assembled from the documented calls):
1. Load clip B so it starts where clip A ends.
2. `clipB = sc.GetClipByTime(tB)`.
3. `clipB.SetTransitionRange(RLPy.RTick.FromSecond(0.5))`.
4. `clipB.SetTransitionType(True, RLPy.ETransitionType_Ease_In_Out, 1.0)`.

Whether an overlapping `LoadMotion` inserts, overwrites, or pushes later clips is **UNVERIFIED**.

Moving a clip on the timeline: there is no documented "move clip" call. **UNVERIFIED**.

### 2.3 Motion layer (edit on top of a clip)

**VERIFIED-WIKI** (End_Effector_Animation; RIObject IC8 page):
```python
clip = sc.GetClip(0)
ctl  = clip.GetControl("Layer", bone)                     # FK layer on a bone
ctl.GetDataBlock().GetControl("Rotation/RotationX").SetValue(t_clip, math.radians(10))
bone.Update()
```
IK layer on an end effector (**VERIFIED-WIKI**, End_Effector_Animation):
```python
eff = sc.GetEffector(RLPy.EHikEffector_LeftFoot)
blk = clip.GetDataBlock("Layer", eff)
pz  = blk.GetControl("Position/PositionZ")
z   = pz.GetValue(RLPy.RTime.FromValue(0), 0.0)[1]
pz.SetValue(RLPy.IndexedFrameTime(10, RLPy.RGlobal.GetFps()), z + 30)
```
- The time passed to layer controls is **clip time**. Convert with `ClipTimeToSceneTime` / `SceneTimeToClipTime`.
- Effector enum values (**LOCAL-STUB**): `EHikEffector_Hip, LeftFoot, RightFoot, LeftHand, RightHand, LeftKnee, RightKnee, LeftElbow, RightElbow, ChestOrigin, Neck, LeftToe, RightToe, LeftShoulder, …`.

### 2.4 Reach Target: making a hand reach an object from script

Manual (**VERIFIED-MANUAL**):
- Reach Target panel: https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Reach_Target/Introducing_the_Reach_Target_Panel.htm
- Contact with targets: https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Reach_Target/Character_Contacting_with_Targets.htm

In the UI you pick an effector, pick a target object, and set key types Reach, Lock, or Release. The Position and Rotation checkboxes snap the hand to the target's pivot. Dummy props act as offset targets.

API:
- **VERIFIED-WIKI:** `RReachKey` exists (https://wiki.reallusion.com/IC8_Python_API:RLPy_RReachKey), with `SetTargetObject(RIObject)`, `SetTime`, `SetTransitionRange`, `SetRotationActive`, `SetForceReach`, and `SetKeyType`. The page has **no example** and does not say what adds the key.
- **VERIFIED-WIKI:** `RISkeletonComponent.GetReach(eEffector) -> RIReach`.
- **LOCAL-STUB:**
  - `RIHikEffectorComponent.AddReachKey(EHikEffector, RReachKey) -> RStatus`
  - `RemoveReachKey`
  - `GetReachKeys(eEffector) -> RReachKeyVector`
  - `SetReachOffsetKey(eEffector, RTime, RMatrix4) -> RStatus`
  - `RIReach.GetReachOffsetControl(strKey, nClipIndex=-1)`
  - Key types `ReachKeyType_Target | _Lock | _Release`

Scripted reach — **VERIFIED LIVE 2026-09-26** (see §8; fork tools `reach_key`, `link_to_bone`). ⚠️ NEVER call methods on `RReachKey.GetTargetObject()` — hard crash. Original inferred sequence (it works):
```python
hik = avatar.GetHikEffectorComponent()            # VERIFIED-WIKI (RIAvatar)
k = RLPy.RReachKey()
k.SetTime(RLPy.IndexedFrameTime(48, RLPy.RGlobal.GetFps()))
k.SetTargetObject(cup_prop)                       # the prop or dummy to grab
k.SetKeyType(RLPy.ReachKeyType_Target)
k.SetTransitionRange(RLPy.RTick.FromSecond(0.5))  # ease-in length
k.SetRotationActive(False)                        # position only, like "Position" in the panel
st = hik.AddReachKey(RLPy.EHikEffector_RightHand, k)
# later: another key with ReachKeyType_Release to let go
```
Verify by reading the right-hand bone's world position at frame 48 and checking it is within a few cm of `cup_prop.WorldTransform().T()`.

Fallback that is documented: keyframe the hand effector position on the motion layer (§2.3) toward the target's world position.

Other IK tools:
- `RIHikEffectorComponent.SetActive(eff, EHikEffectorType_Translate|_Rotate, bool)`, `SetPosition(eff, RMatrix4, bRot, bTrans)` and `SetBodyWeight(0..1)`. **VERIFIED-WIKI** (https://wiki.reallusion.com/IC_Python_API:RLPy_RIHikEffectorComponent). These are live, un-keyed effector puppeting; making them persist in the timeline is **UNVERIFIED**.

### 2.5 Look At and foot contact

- **Look At:** the manual covers look-at through dummy props (https://manual.reallusion.com/iClone-8/Content/ENU/8.0/30-Set/Prop/Using_Dummy_Props.htm).
  - The only look-at API found is `RICamera.IsLookAtMode(t)`, which is read-only (**VERIFIED-WIKI**, IC8 RLPy_RICamera).
  - **Avatar look-at IS scriptable** (**PROVEN-RUNTIME** 8.75.5630.1, 2026-10-07, superseding the line below):
    `avatar.GetSkeletonComponent().GetLookAtComponent().AddLookAtKey(...)` — details in §8 *Look At*; MCP tool `set_look_at`.
  - Setting a *camera* look-at target from script is still **UNVERIFIED**; no setter was found in the wiki or the stub.
  - For cameras, the official workaround is to compute the rotation (SmoothCameraFollow's `look_at_right_handed`, §3.3).
  - For heads, key the neck/head bone on the motion layer.
- **Foot and hand contact:** the Edit Motion Layer panel has Foot Contact and Hand Contact toggles (**VERIFIED-MANUAL**, https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Motion-Layer/Using_Body_Key_Editor.htm).
  - Script: `RIAvatar.GetFloorContactValue(eType)` / `SetFloorContactValue(eType, fValue)` and `AutoAdjustFootHeight()` are listed (**VERIFIED-WIKI**, https://wiki.reallusion.com/IC8_Python_API:RLPy_RIAvatar). The enum values and semantics are **UNVERIFIED**.

### 2.6 Motion Director and Motion Puppet

- `RGlobal.GetMotionDirector() -> RIMotionDirectorManager` is **LOCAL-STUB** only, with no wiki page. **UNVERIFIED** as usable.
- Motion Puppet is a UI mode (`EModeType_MotionPuppet` for `RGlobal.SetDialogMode`, **LOCAL-STUB**). Driving puppet recording from script is **UNVERIFIED**; treat it as not scriptable.

---

## 3. Cameras

### 3.1 Creating a camera

- **The wiki and samples document no camera-creation API.** `RScene` (**VERIFIED-WIKI**) has Find, Select, Show, Hide and Remove only.
  - The 8.75 stub has no `CreateCamera` or `CreateObject` either.
  - The Camera_Dolly_Zoom sample tells the user to "create a new camera" by hand.
- Routes that are documented and scriptable:
  - `RFileIO.LoadObject(path)` "loads an object (Avatar, **Camera**, Light, Particle, or Prop)". **VERIFIED-WIKI** (Experimental in iC8). Save one camera as an `.iCam`/template once, then load it per shot. The file extension is **UNVERIFIED**.
  - Keep a template `.iProject` that already contains named cameras (`Cam_A`, `Cam_B`, …) and `LoadFile` it.
  - `RIObject.Clone()` (**VERIFIED-WIKI**, IC8 RLPy_RIObject) on an existing camera. Whether it returns an `RICamera` is **UNVERIFIED**.
- Find cameras (**VERIFIED-WIKI / SAMPLE**):
  - `RScene.FindObject(RLPy.EObjectType_Camera, "Camera")`
  - `RScene.FindObjects(RLPy.EObjectType_Camera)`
  - Skip `"Preview Camera"`; the samples treat it as not animatable.

### 3.2 Setting the active camera

- `RLPy.RScene.GetCurrentCamera()` is **VERIFIED-SAMPLE** (Camera_Auto_Focus, Camera_Dolly_Zoom).
- `RScene.SetCurrentCamera(RICamera) -> RStatus` is **LOCAL-STUB** only, with no wiki or sample.
- Camera switching: `RScene.AddSwitchCameraKey(RTime, RICamera) -> RStatus`, `ClearSwitchCameraKeys()`, `GetSwitchCameraFrameIndexs(fps)`, and `GetCameras()`. All **LOCAL-STUB**.
- Renders use the current or switcher camera (see the render caveat in §4).

### 3.3 Camera animation

**VERIFIED-WIKI** (https://wiki.reallusion.com/IC8_Python_API:RLPy_RICamera) and **VERIFIED-SAMPLE** (Camera_Dolly_Zoom):
```python
cam.SetFocalLength(t, 35.0)             # mm, range 2.5–3500; each call writes a key at t
cam.GetFocalLength(t); cam.RemoveFocalLengthKey(t); cam.GetFocalLengthKeyCount()
cam.GetAngleOfView(t)                   # "AOV" means angle of view, not a render pass
dof = cam.GetDOFData(); dof.SetEnable(True); dof.SetFocus(cm)
k = RLPy.RKey(); k.SetTime(t); cam.AddDofKey(k, dof)
cam.SetNearClippingPlane(n); cam.SetFarClippingPlane(n)
```
- The focal-length transition curve is not accessible; the sample keys focal length every frame for smooth zooms (**VERIFIED-SAMPLE** comment).
- Camera transform: use the same `GetControl("Transform").SetValue(...)` as §1.2.
- Official look-at matrix, from SmoothCameraFollow (**VERIFIED-SAMPLE**). The camera looks down its local −Z, so `forward` = pos − target:
```python
def look_at(pos, target, up=RLPy.RVector3(0, 0, 1)):
    f = pos - target; f.Normalize()
    r = up.Cross(f);  r.Normalize()
    u = f.Cross(r)
    m = RLPy.RMatrix3(r.x, r.y, r.z,  u.x, u.y, u.z,  f.x, f.y, f.z)
    return RLPy.RTransform(RLPy.RVector3(1, 1, 1), RLPy.RQuaternion().FromRotationMatrix(m), pos)
```

---

## 4. Rendering

### 4.1 Official surface

- Wiki: `RGlobal.RenderVideo()` "uses the current render settings" and returns an `RStatus` (**VERIFIED-WIKI**, IC_Python_API:RLPy_RGlobal).
- `GetScreenSize()` returns `[status, w, h]` (**VERIFIED-WIKI**).
- Sample BatchRenderFolder: `LoadFile(project)` then `RenderVideo()` (**VERIFIED-SAMPLE**).
- Everything else below is **LOCAL-STUB** (8.75). There are no wiki pages for these; signatures are from the SWIG docstrings.

### 4.2 Direct render calls (LOCAL-STUB)

```
RGlobal.RenderVideo(strFileName="")                          # uses settings range
RGlobal.RenderVideo(RTime start, RTime end, strFileName="")
RGlobal.RenderImage(strOutputFileName)                       # current frame
RGlobal.RenderImageSequence(RTime start, RTime end, strFileName="")
RGlobal.RenderImageSequenceNormal(start, end, strFileName="")
RGlobal.RenderImageSequenceDepth(start, end, RDepthParam, strFileName="")
RGlobal.RenderImageSequenceCanny(start, end, REdgeDetectionCannyParam, strFileName="")
RGlobal.RenderImageSequenceOpenPoseKeyPoint(start, end, ROpenPoseKeyPointParam, strFileName="")
RGlobal.RenderVideoNormal / RenderVideoDepth / RenderVideoCanny / RenderVideoOpenPoseKeyPoint   # same args, video out
RGlobal.RenderPreview[Normal|Depth|Canny|OpenPoseKeyPoint](strFileName="")                     # viewport-quality variants
RGlobal.RenderAudio(start, end, strFileName="")
```

Pass parameter fields (**LOCAL-STUB**):
- `RDepthParam`: `bEnhanced, fClipLimit, nTilesGridSize`
- `REdgeDetectionCannyParam`: `fThreshold1, fThreshold2, nApertureSize, bL2gradient`
- `ROpenPoseKeyPointParam`: `strPoseFormat, bFace, bHand, bWholeHand, bWholeFace, bEnableEars, fOpacity, fBone/Hand/Face(Nub)GizmoScale, bCheckBody/Finger/FaceBlocking, fBlockingThreshold, fVisibleFacialGizmoPercentage, bEnableHikIndexMapping, bUseNoseVertexAsNosePos`
- None of them has a resolution field.
- The OpenPose image-sequence call was confirmed at runtime on 8.74 in an earlier session (iclone-rlpy skill §17). The others are UNVERIFIED at runtime.

Known issue: a forum bug report says Canny/Depth export fails on 8.7 (https://discussions.reallusion.com/t/bug-report-oct-2-release-ver-fails-to-export-canny-depth-videos-json-in-iclone-8-7/17176). Always check the output file exists and is larger than 0 bytes.

### 4.3 Render settings: output size, render FPS, range (LOCAL-STUB)

```
RGlobal.SetRenderExportType(RExportType) / GetRenderExportType()     # Image / ImageSequence / Video; enum names UNVERIFIED
RGlobal.GetRenderExportVideoParameter() -> RExportVideoParameter     # get, mutate, set back
RGlobal.SetRenderExportParameter(RExportImageParameter | RExportImageSequenceParameter | RExportVideoParameter | RExportAudioParameter)
```
Field names:
- `kCommon` (`RExportCommonParameter`):
  - `kFps` (a **wstring**, e.g. "24"?; format UNVERIFIED)
  - `nOutputSizeWidth`, `nOutputSizeHeight`, `bLockRatio`, `nPixelAspect`
  - `bFinalRender`, `nAntiAliasType`, `bHighQualityDof`, `bStereoOutput`, `bPanoramaOutput`, `bBurnMetadata`
- `kOutputRange` (`RExportOutputRangeParameter`): `nOutputRangeStart`, `nOutputRangeEnd` (frames), `bDiscardSimulatingFrames`, `nDiscardSimulatingFrame`
- Video only: `strFormat`, `nVideoQuality`, `nAudioQuality`, `bAlphaOnly`, `bHardwareVideoEncode`
- Image and sequence: `strFormat`, `nImageQuality`

Manual (**VERIFIED-MANUAL**, https://manual.reallusion.com/iClone-8/Content/ENU/8.0/80-Export/Exporting.htm and General_Export_Settings.htm):
- Output types: Video (AVI/WMV/MP4 H.264/WAV), Image (BMP/JPG/TGA/PNG/EXR), Image Sequence.
- **Export frame rate: 12/24/25/30/60.**
- Size is a preset or custom with a Lock Ratio option.
- Quality is Preview or Final.
- Range is All, or a Range set by Mark In/Out.

Other: `RGlobal.SetRealtimeRenderOptions(RRealtimeRenderOptions)` toggles viewport features (`bShadowMap, bHdr, bGlow, bReflection, bDisplacementMap, bLod, bViewportLessUpdate…`). **LOCAL-STUB**.

---

## 5. Timeline and project

### 5.1 FPS

- Project FPS is set in the UI under Project Settings > Time Unit (drop-down) (**VERIFIED-MANUAL**, https://manual.reallusion.com/iClone-8/Content/ENU/8.0/03-Introducing-the-User-Interface/Project_Settings_Time_Unit.htm).
- **Reading** it is scriptable: `RGlobal.GetFps() -> RFps` (**VERIFIED-WIKI**).
- **Setting project FPS from Python is not documented**, and there is **no `SetFps` in the 8.75 stub**. Treat it as **NOT SCRIPTABLE**.
- Workarounds:
  1. A template `.iProject` saved at 24 fps and loaded with `RFileIO.LoadFile`.
  2. Set the render output FPS through `RExportCommonParameter.kFps` (LOCAL-STUB, UNVERIFIED).
- `RFps` constants include `Fps24, Fps25, Fps30, Fps60, …` (**LOCAL-STUB**; wiki mentions Fps24/60/120).

### 5.2 Length and range

- Default project length is 1800 frames, maximum 54,000 (**VERIFIED-MANUAL**, Time Unit page).
- **VERIFIED-WIKI**: `GetProjectLength()`, `GetStartTime()`, `GetEndTime()`, `GetTime()`, `SetTime(t)`, `Play(start, end)`, `Pause()`, `Stop()`.
- **LOCAL-STUB**: `SetProjectLength(RTime) -> RStatus`, `SetStartTime(t)`, `SetEndTime(t)` (Mark In/Out), and `SetPreviewStartTime/EndTime`.

### 5.3 Save and undo

- `RFileIO.SaveProject(path)` (Experimental) and `LoadFile(path)` for `.iProject` (**VERIFIED-WIKI**).
- `RGlobal.BeginAction(name)` / `EndAction()` for undo grouping (**VERIFIED-WIKI**; the old page calls it incomplete).

### 5.4 Modal blockers

- Symptoms seen elsewhere: load-reminder and version dialogs, license or login popups, "Preview Camera" errors.
- **LOCAL-STUB** calls:
  - `RGlobal.SetSilentMode(bool)` / `GetSilentMode()`: likely suppresses message boxes. **UNVERIFIED** behaviour.
  - `RGlobal.SetDialogMode(EModeType)` selects a UI edit mode (`EModeType_ReachTarget`, `_MotionPuppet`, `_IkEditing`, …). It does **not** suppress dialogs.
- `LoadFile` and `LoadObject` take `bRecordStep=True`; pass `False` to skip undo recording (**VERIFIED-WIKI**).
- Measured on this machine (iclone-rlpy skill §36):
  - The `iClone.exe -RunPython` switch never runs the script.
  - Headless `iClonepy.exe` crashes on the first singleton call.
  - Code must run **in-process**, through a `Bin64\OpenPlugin\<name>\main.py` with `initialize_plugin()` or a Script > Load Python menu call (**VERIFIED-WIKI**, IC_Python_API:Your_First_iClone_Python_Plugin).

---

## 6. Content and file types

`LoadObject` / `LoadFile` accept (**VERIFIED-WIKI**, RLPy_RFileIO):
- Avatar: `iAvatar` and parts (`iacc, ihair, icloth, …`)
- Props: `iProp, iTree, iParticle, ipkfx`
- Motion: `iMotion, iMotionPlus, rlMotion, iHand, iTalk, rlTalk, iPath`
- Models: `fbx, obj, abc`
- Project: `.iProject`

`LoadObject` returns a typed object (`RIAvatar`, `RIProp`, …), or a failure.

Content location:
- Stock location is `C:\Users\Public\Documents\Reallusion\...`, but on this machine that folder is empty. The library is on `F:\iCLONE` (4,466 `.iAvatar`, ~37,651 motions; iclone-rlpy skill §37).
- `RGlobal.GetDefaultContentFileAbsolutePath(EContentRootFolder, bCustom)` and `RGlobal.GetPath(ePath, …)` resolve paths (**LOCAL-STUB** / **VERIFIED-WIKI** respectively).
- Prefer standard ActorCore avatars over ActorCore *Crowd* avatars.

Which features are scriptable:

| Feature | Status |
|---|---|
| Transform keys | ✅ VERIFIED |
| Motion load and clip transition data | ✅ VERIFIED (Experimental for add/break/merge) |
| Motion Layer (FK/IK layer keys) | ✅ VERIFIED (End_Effector_Animation) |
| Reach Target keys | ⚠️ symbols verified (RReachKey on the wiki; `AddReachKey` LOCAL-STUB); sequence UNVERIFIED |
| Look At (set) | ✅ avatars: `RILookAtComponent.AddLookAtKey` (LOCAL-STUB, runtime-proven 8.75 → `set_look_at`); cameras: ❌ compute rotation |
| Motion Director | ⚠️ LOCAL-STUB getter only |
| Motion Puppet recording | ❌ UI only |
| Camera create | ❌ no API; use LoadObject, a template project, or Clone |
| Active camera and switcher | ⚠️ LOCAL-STUB (`SetCurrentCamera`, `AddSwitchCameraKey`) |
| Project FPS set | ❌ UI only |
| Render + OpenPose/Depth/Normal/Canny | ⚠️ LOCAL-STUB (OpenPose runtime-confirmed on 8.74) |

---

## 7. Minimal previz recipe (agent checklist)

1. `LoadFile(template_24fps.iProject)`. It already contains the named cameras, the set, and 24 fps.
2. `a = RFileIO.LoadObject(avatar_path)`, then place it with `a.GetControl("Transform").SetValue(RTime.FromValue(0), make_transform(...))`.
3. `RFileIO.LoadMotion(motion_path, IndexedFrameTime(f, fps), a)`. Verify by checking that bones moved.
4. Blend: `GetClipByTime(t).SetTransitionRange(...)` and `SetTransitionType(True, ETransitionType_Ease_In_Out, 1.0)`.
5. Camera: `cam = FindObject(EObjectType_Camera, "Cam_A")`. Key `look_at(pos, target)` transforms and `SetFocalLength`, then `SetCurrentCamera(cam)`.
6. `SetEndTime(...)`. Set the render parameter size and range. Call `RenderImageSequence[Depth|Canny|OpenPoseKeyPoint](t0, t1, param, out)`.
7. Check that each output exists and is larger than 0 bytes. Inspect one frame.


---

## 8. MEASURED LIVE 2026-09-26 (iClone 8.74, hoodtronik fork) — overrides anything above

**Reach / contact (VERIFIED)**
- `RIHikEffectorComponent.AddReachKey(EHikEffector_*, RReachKey)` works; `RReachKey.SetTargetObject` takes an OBJECT, not a bone.
  To grab a bone: small prop → `RIObject.LinkTo(RINode_bone, ELinkObjectAlignType_Position, RTime)` (LinkTo accepts a bone
  node) → reach for the prop. Grab measured 11.7 cm wrist-to-wrist, palm strike 4 cm (fork: `link_to_bone` + `reach_key`).
- 🔴 **CRASH:** any method (`IsValid`, `GetName`) on the object returned by `RReachKey.GetTargetObject()` kills iClone. Read back
  only time / key type / transition. Iterating `RReachKeyVector` yields raw SwigPyObject — index it (`keys[i]`).
- Key types: Target=0, Lock=1, Release=2. Default transition = 1.0 s; the transition ramps IN BEFORE the key time.
- `SetRotationActive(True)` + target linked with Position_And_Rotation aligns the hand to the bone's orientation.
- Reach IK is limited by arm length (~55–60 cm shoulder→hand bone): place the actor from MEASURED bone positions
  (`iclone_stot_fight_build.grab_spot`) — hard-coded spots broke every time the other actor's motion changed.

**Motion clips**
- Outside any clip an avatar shows the FIRST frame of its first clip (before) and the bind/base pose (after) — no hold.
- Hold a pose: `BreakClip(t)` then set the remainder's speed very low. `RIClip.SetLength` is in **clip time** (scene × speed)
  and a clip shorter than 1 frame (100 ticks @60) is **silently rejected** → speed ≥ ~0.01 for multi-second holds.
- After `BreakClip`, both halves report speed 1.0 (speed baked into length).
- `DeleteClip(clip)` works; replacing clips also deletes an avatar's original 1-frame pose clip → give it a new idle.
- Root-motion-free idles + transform keys + reach IK was the controllable combo; mixamo "scared"/"disbelief" read wrong on camera.

**Transforms**
- iClone collapses identical transform keys on save. Heading 0 = facing −Y; +h rotates CCW (h=90 faces +X).
- Seated slump toward +X at heading −90 = `tilt x −30` (euler XYZ; measured, not derived).
- A bare "hold" key at t re-reads whatever key already sits at t → always write holds with explicit values.

**Evaluation / sampling**
- Right after a clip/reach edit, the first `SetTime` sample returns STALE bones; nudge the playhead + `processEvents()` first.

**Project / server**
- `RFileIO.SaveProject()` needs a path (TypeError without); RLPy has no current-project getter → fork tracks it (last save, else
  the .iProject on iClone's command line). Crash-prone fork tools checkpoint-save first.
- Killing iClone / a crash → next launch shows TWO modals in sequence, each blocking the command-line project load:
  1. "Unsaved project data found. Would you like to update your project with the unsaved changes?" (OK/Cancel) → **Cancel**
     when the saved .iProject is the truth (OK restores iClone's autosave of the crashed session).
  2. "The current project will be discarded. Would you like to save?" (Yes/No/Cancel) → **No** (the "current project" at
     launch is the empty startup scene). The project then loads in ~10 s.
  `launch_iclone.py` answers both automatically (2026-10-07; `--recover-autosave` presses OK on the first). `dialog_watch`
  itself never auto-answers data prompts.
- Reloading the main server module inside a hot-reload kills the server (only restartable by relaunch).
- JSON-RPC errors with id=null are rejected by Claude Code — tool failures must be `isError` results.
- `RTime(int)` raises in iClone 8 — `RTime.FromValue(ms*6)`.
- Viewport shows camera gizmos; check a real render before judging clutter.

**Look At (measured 2026-10-07, iClone 8.75.5630.1 — the 09-26 notes above were 8.74; everything re-exercised behaved the same)**
- `sc.GetLookAtComponent().AddLookAtKey` has two SWIG overloads with EMPTY docstrings (recovered by mis-calling it):
  `(RTime, RIObjectPtr)` and `(RTime, RTime transition, RINodePtr, head_w, body_w)`. Props/cameras only fit the 2-arg form
  (a RIProp is rejected as RINode); skin bones fit the 5-arg form.
- Target = an avatar *object* → it looks at that avatar's PIVOT (feet). For eye contact target the other avatar's
  `CC_Base_Head` bone (5-arg form).
- `AddLookAtKey(t, None)` = release key; the head eases back over ~1 s AFTER the key. The 5-arg transition ramps IN BEFORE the
  key (0° at key−30f, full at the key) — same convention as reach keys.
- `GetLookAtWeightDataBlock(False/True)` → one RFloatControl each (defaults 0.7 head / 0.3 body); they did NOT change after a
  1.0/0.0 call → not a readback. Proof = CC_Base_Head world-rotation delta (27–61° measured) + `RenderImage`.
- `RIProp` also has `GetSkeletonComponent` → detect avatars with `isinstance(obj, RLPy.RIAvatar)`, not `hasattr`.
- On an unattended launch `viewport_capture` returned STALE pixels (window visible, not minimized, not active) while
  `render_snapshot` was correct → use a real render as proof when nobody has focused iClone.
- `aim_camera` raised "camera not found" right after creating it on this launch; `menu_action "Create > Camera > Linear Camera"`
  itself worked (added "Camera"). Not yet diagnosed.
- `hot_reload.py` does NOT reload `main.py` → a new entry in the checkpoint tuple only takes effect after an iClone relaunch.

**Project session (measured 2026-10-07, iClone 8.75.5630.1)**
- `RFileIO.LoadProject(path)` works in-session: returned Success in 2.2 s, every old `RIObject` handle → `IsValid()` False,
  saved transforms restored. It asked NOTHING about unsaved changes on a dirty scene → `load_project` saves the tracked
  project first and makes the loaded path the tracked project.
- No `NewProject` symbol; `menu_action "File > New Project"` empties the scene in 0.7 s, again with no save prompt →
  `new_project` saves first, then CLEARS the tracked path (incl. the command-line fallback) so no checkpoint overwrites the
  old project with an empty scene.
- `RGlobal.Undo()` / `Redo()` and `Edit > Undo` all returned without reverting an API `SetValue` transform write, with or
  without `BeginAction("x")`/`EndAction()`. Earlier, `SaveProject` + `BeginAction` + move + `EndAction` + `Undo` + `Redo` +
  `Undo` in ONE call on an API-built untitled scene crashed iClone (the output was lost with it). Not exposed as a tool.
- **Stale tracked path incident:** a raw `menu_action "File > New Project"` left the tracked project path pointing at the
  previous file; the next automatic save-first wrote the EMPTY scene over it (35 MB → 7.6 MB, scratch project lost). A human
  doing File > New Project puts the fork in the same state → every automatic save (session tools AND the checkpoint in
  `mcp_handler`) now skips when `tools.common.scene_is_empty()`. Use `new_project` (clears the path) instead of the raw menu.
- `RGlobal.GetDialogMode()` = 0, `GetSilentMode()` = False by default; `SetSilentMode(bool)` exists (effect untested).
- A big `.iProject` passed on the command line: the MCP is healthy ~45 s in, avatars appear ~60 s later; the launcher now
  ignores the default `Shadow Catcher` prop when deciding "project loaded".
- Crash-safe probing recipe: write each risky call's name to a log file (flush) BEFORE calling it; `python_exec` stdout dies
  with the process.

**Timeline range (measured 2026-10-07, iClone 8.75.5630.1 → `set_timeline_range`)**
- `RGlobal.SetProjectLength(RTime)`, `SetStartTime/SetEndTime` (play range) and `SetPreviewStartTime/SetPreviewEndTime` all
  return Success and read back exactly through their getters. A fresh project reads length 1799 / end 1799.
- Setting the length clamps `end` and `preview_end` down to it and pulls the playhead inside; `end` may exceed the length
  (600 with length 240 was accepted, not clamped). Start/end and the preview range are independent of each other.
- GROWING the length does not grow `end`/`preview_end` back (after a shrink to 60 and a grow to 600, `end` stayed 60) →
  always pass `end` with a longer `project_length`, or playback/renders stop early.
- Shrinking the length does NOT delete keys past the new end (a transform key at frame 500 survived length 60 and evaluated
  correctly after restoring 1800).
- Which UI control each pair drives (timeline play-range bar vs Render panel "preview range") is **UNVERIFIED** visually.

**Clip surgery (measured 2026-10-07, iClone 8.75.5630.1 → `edit_clip`)**
- `BreakClip(t)` on a 760-frame clip at 60 → `[0,60]` + `[60,760]`; `MergeClips(clip0, clip1)` → one `[0,760]` again;
  `DeleteClip(clip)` → empty track. All returned Success and no crash (each call in its own request, scratch project saved first).
- `MirrorClip(clip)` mirrors in **WORLD X**: hip x −149.3 → +149.3, L_Hand lands where R_Hand was (x sign flipped). An actor
  blocked off-centre jumps to the other side → re-place after mirroring. Pose mirrored correctly otherwise.
- Clip rows (`ClipTimeToSceneTime(0)`, `GetClipLength`) are a reliable before/after proof for break/merge/delete; mirror needs
  bone positions.

**Audio (measured 2026-10-07, iClone 8.75.5630.1 → `load_audio`, `render_audio`)**
- `RAudio.LoadAudioToObject(obj, path, RTime start, int loops=1, RTime fadeIn, RTime fadeOut, RTime cutLength) -> float`
  (prototypes via the TypeError trick). It put `Alarm01.wav` on a prop's sound track at frame 0.
- The float return is NOT a success flag: a MISSING path returned the same 5.572 as the real file (the real clip is 5.57 s long,
  so it reads like "track content length"). Check the file yourself and prove the load with a render.
- `RGlobal.RenderAudio(RTime start, RTime end, path)` → stereo 48 kHz PCM wav, 120 frames in ~0.2 s, no dialog, Success.
  A 1 s window before/after the load (peak 0 → 7970) is the proof `load_audio` uses.
- 🔴 **`LoadAudioToObject` on a CAMERA crashes iClone** (process gone, reproduced twice, 3-arg form, crash log shows the call
  as the last line). Props accept the 3-arg and the 6-arg (loops, fadeIn, fadeOut) forms. `load_audio` refuses non-avatar,
  non-prop targets.
- `RIObject` has no audio getter (`dir()` shows none); `RAudio.CreateAudioObject()` + the RIAudioObject overload exist, untested.
