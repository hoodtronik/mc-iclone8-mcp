# iCloneMCP — Handoff for the next agent

Last updated: 2026-06-30. Read this first, then `README.md` and `AGENTS.md`.

## Goal

Drive **iClone 8** from an AI agent via its `RLPy` Python API to assemble scenes, block
animation/cameras, and **render control-video passes** (OpenPose, depth, canny, normal) for
conditioning AI video generation. End state = an **MCP server** bridged to an embedded socket
server running inside iClone.

## Current status

| Thing | State |
|---|---|
| Feasibility analysis (all categories) | ✅ Done — see `README.md` table. Verdict: viable. Rendering is the standout (native OpenPose/Depth/Canny/Normal AOV passes). |
| `iclone_api_probe.py` (read-only API dump) | ✅ Written. **Not yet run by user** → no `iclone_api_dump.json` captured yet. Optional but would lock every signature in one pass. |
| `poc_openpose_slice.py` (vertical slice) | ⚠️ **Latest revision NOT yet run.** See below. |
| Git / GitHub | ✅ `hoodtronik/iCloneMCP` (private). `main` tracks origin. |

### Vertical-slice POC — exact state
Three runs of history, each fixing the prior:
1. Run 1 crashed: `RLPy.RTime(0)` → `TypeError` (RTime has **no int constructor**). Fixed.
2. Run 2 (log: `docs/runs/icmcp_log_run2.txt`): avatar loaded ✅; motion returned `IsError()=False`
   but clip count 1→1 (heuristic inconclusive); **render failed** because the guessed arg shapes
   were wrong. The failure leaked the real C++ prototypes (see below).
3. **Current revision (uncommitted-run): not executed yet.** It uses the confirmed render signature,
   replaces the clip-count heuristic with a **bone-world-position delta** motion check, and lists
   written files to confirm frames on disk.

**NEXT ACTION:** have the user run the current `poc_openpose_slice.py` in iClone
(Script → Load Python), then read `<user Desktop>\icmcp_openpose\icmcp_log.txt`.
Look for `MOTION CONFIRMED` and `SUCCESS: N image(s) written`. If motion still doesn't take,
suspect an ActorCore **Crowd** avatar ↔ "1.Human Male" motion skeleton mismatch — try a standard
CC/ActorCore avatar or a motion known-compatible with the crowd rig.

## 🖥️ Machine profiles + where the content actually lives (added 2026-08-29)

This project was authored on the **work PC** (`C:\Users\Animation`), where the Reallusion library is at
the default `C:\Users\Public\Documents\Reallusion`. On the **home PC** (`C:\Users\hoodt`, RTX 4090) that
default folder is **EMPTY** — the library is on **`F:\iCLONE`**. Found via
`HKCU:\Software\Reallusion\...\OpenFolderPath`; check there first on any new box.

`poc_openpose_slice.py` no longer hardcodes one machine: `AVATAR_CANDIDATES` / `MOTION_CANDIDATES` are
tried in order and the first existing path wins, so the same file runs on both. Home-PC inventory
(verified 2026-08-29): **4,466 `.iAvatar`**, **37,651 motions**.

**Assets the slice now uses on the home PC:**
- Avatar `F:\iCLONE\Reallusion Templates\Actor\Character\ActorCore\Party_M_0001.iavatar`
  (standard ActorCore, **not** Crowd — dodges the run-2 skeleton mismatch). Siblings in that folder:
  `Party_M_0005`, `Party_F_0001`, `Kid_M_0001`.
- Motion `F:\iCLONE\Custom\iClone 7 Custom\MographMotion\01_Male\SitC01.iMotion` — swapped in for
  "Talk Serious" deliberately: **seated** is the pose the downstream job needs, so a green run is
  directly reusable instead of a throwaway. 203 motions sit in that one folder, including
  `SitC01_L_{Agree,Disagree,Fear,Happy,Laugh,Sad}`, `SitC01A_T_{Angry,Explain}` and the transitions
  `Idle01_to_SitC01` / `SitC01_to_Idle01` / `Sit_to_Walk`.

**Why this matters beyond the slice:** the consuming project (Charon Express, a seated-passenger shot)
had been blocked trying to hand-author a seated pose — first with MPFB2 in Blender, then with Unreal's
PoseableMesh, both rejected. This motion library removes that problem entirely: the pose is an asset,
not a bone-math exercise. Intended chain once the bridge exists:
avatar → `SitC01*` → place in the greybox car → render an OpenPose/Depth pass → feed the video model
as a blocking reference.

## 🚪 Getting code INTO iClone — SETTLED 2026-08-29 → `docs/automation-entry-points.md`

Don't re-litigate this; it was measured, not guessed.
- ❌ **`iClone.exe -RunPython <script>` does NOT execute** — 4 arg forms tried (quoted / bare / `=` /
  with `-SilentMode`), each with a write-a-file-only canary, 200–300 s per launch. App came up healthy
  and responsive every time and never ran the file. The switch strings sit beside Character Creator
  strings, so they may belong to a shared CT/Core lib or to CC.
- ❌ **No headless RLPy.** `Bin64\iClonepy.exe` is CPython 3.8.8 and `import RLPy` *succeeds*, but the
  first singleton call (`RGlobal.GetFps()`) dies with **`0xC0000005`**. RLPy only binds inside the host
  process — which is exactly why this project needs an **embedded** server, not a CLI.
- ✅ **`Bin64\OpenPlugin\<name>\main.py` auto-loads at startup** (`Blender Pipeline Plugin` is a plain
  `main.py` — proof the pattern works), **but the folder needs admin to write.** One elevated install,
  then everything after is automatic.

⇒ Running the PoC today = **one human `Script → Load Python`**, or a one-time elevated `OpenPlugin`
install. The latter is not a workaround — `OpenPlugin` is where the bridge must live anyway.

## Confirmed API facts (authoritative — verified against `…\iClone 8\Bin64\RLPy.py`)

- **API surface is readable source:** `…\Bin64\RLPy.py` (SWIG wrapper, 11,317 lines, 211 classes)
  over `_RLPy.pyd`. No `.pyi`. SWIG signatures live in method `__doc__` at runtime, BUT many render
  funcs are `*args` overloads with **empty docstrings** — their real prototypes only appear in the
  `TypeError` when called wrong (that's how the render sig below was recovered).
- **`RTime` has no int constructor.** Build frame times via `RLPy.RGlobal.GetFps().IndexedFrameTime(n)`.
- **Load avatar:** `RFileIO.LoadFile(path)` → then `RScene.GetAvatars()` (no create-from-scratch factory).
- **Load motion:** `RFileIO.LoadMotion(strFilePath, kTime, spObject)` — confirmed signature.
  Returns `RStatus` (`.IsError()`); note its `repr()` is a useless proxy address — call methods, don't repr.
- **Render OpenPose (CONFIRMED):**
  `RGlobal.RenderImageSequenceOpenPoseKeyPoint(RTime start, RTime end, ROpenPoseKeyPointParam param, str path)`
  (a 3-arg overload without the path also exists). The other AOV passes
  (`RenderImageSequenceDepth/Normal/Canny`) almost certainly mirror this shape — confirm the same way.
- **`ROpenPoseKeyPointParam` fields:** `strPoseFormat, bFace, bHand, bWholeHand, bWholeFace, bEnableEars,
  fOpacity, fBoneGizmoScale, fHandGizmoScale, fFaceGizmoScale, bCheckBodyBlocking, fBlockingThreshold, …`
  No output-resolution field → render size comes from project/render settings (use `RGlobal.SetViewSize`
  or realtime render options to control it — not yet wired up).
- **Camera:** a fresh project has **0 camera objects** (`RScene.GetCameras()` == 0); rendering falls back
  to the preview viewport camera. `RScene.SetCurrentCamera`, `AddSwitchCameraKey(time, cam)` for cuts.
- **Motion proof technique:** `sc = avatar.GetSkeletonComponent()`; `sc.GetSkinBones()[i].WorldTransform().T()`
  → `RVector3` with `.X()/.Y()/.Z()` **methods** (not properties). Compare across two frames.
- **Runtime:** iClone's bundled **CPython 3.10**; full networking stdlib + `requests` + `websocket-client`;
  PySide2 `QtNetwork`/`QtWebSockets`.

## How to run a script in iClone 8
Top menu **Script → Load Python** → pick the `.py`. (Fallback: paste into the Python console.)
Scripts run on iClone's bundled interpreter, not system Python.

## MCP bridge plan (next phase, after the slice is proven)
Embedded socket server inside an OpenPlugin, pattern from
`…\OpenPlugin\Unity Pipeline Plugin\utp\link.py` (plain `socket` + non-blocking `select` +
`QTimer` pump on the main thread; `REventHandler.RegisterCallback` for events).
**`link.py` is GPL — copy the pattern, not the source**, to keep iCloneMCP license-clean.
External MCP server exposes tools: `load_avatar`, `load_motion`, `set_transform`, `add_camera`,
`switch_camera_key`, `render(pass, range, path)`.

## Files
- `iclone_api_probe.py` — read-only full API dump + networking probe → `Desktop\iclone_api_dump.json`.
- `poc_openpose_slice.py` — the vertical slice (current revision uses confirmed render sig).
- `docs/runs/icmcp_log_run2.txt` — the run that recovered the render signature (key evidence).
- `README.md`, `AGENTS.md`, `.gitignore`.
