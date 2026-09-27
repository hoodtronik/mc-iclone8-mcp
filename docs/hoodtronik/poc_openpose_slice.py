# poc_openpose_slice.py
# iCloneMCP proof-of-concept vertical slice:
#   one avatar  ->  one motion clip  ->  one camera  ->  one OpenPose image-sequence render to disk.
#
# Run inside iClone 8:  Script -> Load Python -> pick this file.
# All output is teed to OUTPUT_DIR\icmcp_log.txt.
#
# Render signature (confirmed from the SWIG overload error in a prior run):
#   RGlobal.RenderImageSequenceOpenPoseKeyPoint(RTime start, RTime end,
#                                               ROpenPoseKeyPointParam param, str output_path)

import os
import sys
import traceback

import RLPy

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
# CLAUDE-NOTE: this repo was authored on the WORK PC, where the Reallusion library sits at the
# default `C:\Users\Public\Documents\Reallusion`. The HOME PC (verified 2026-08-29) has that folder
# EMPTY and keeps its real library on `F:\iCLONE` (4,466 avatars / 37,651 motions) — the location is
# recorded in HKCU:\Software\Reallusion\...\OpenFolderPath. Rather than hardcode one machine, resolve
# at run time by taking the first candidate that exists, so one script serves both boxes.
AVATAR_CANDIDATES = [
    # CLAUDE-NOTE: prefer a standard ActorCore avatar over ActorCore *Crowd*. Run 2 loaded a Crowd
    # avatar and the motion never took; the suspected cause is a Crowd rig <-> "1.Human Male"
    # motion-skeleton mismatch. Crowd entries stay last as fallbacks only.
    r"F:\iCLONE\Reallusion Templates\Actor\Character\ActorCore\Party_M_0001.iavatar",
    r"C:\Users\Public\Documents\Reallusion\Reallusion Templates\Actor\Character\ActorCore\Party_M_0001.iavatar",
    r"C:\Users\Public\Documents\Reallusion\Reallusion Templates\Actor\Character\ActorCore Crowd\Party_M_0001.iAvatar",
]
MOTION_CANDIDATES = [
    # CLAUDE-NOTE: SitC01 (seated idle) instead of "Talk Serious". It proves the slice AND is the exact
    # pose the Charon Express blocking needs, so a green run is immediately useful rather than a
    # throwaway. Emotional variants live beside it (SitC01_L_{Happy,Sad,Fear,Agree,...}).
    r"F:\iCLONE\Custom\iClone 7 Custom\MographMotion\01_Male\SitC01.iMotion",
    r"C:\Users\Public\Documents\Reallusion\Reallusion Templates\Animation\Motion\1.Human Male\Perform\Talk Serious.rlMotion",
]
OUTPUT_DIR  = os.path.join(os.path.expanduser("~"), "Desktop", "icmcp_openpose")
START_FRAME = 0
END_FRAME   = 60

os.makedirs(OUTPUT_DIR, exist_ok=True)


def _first_existing(candidates, what):
    for p in candidates:
        if os.path.exists(p):
            return p
    raise SystemExit(
        "[icmcp] FATAL: no %s found. Tried:\n  %s\n"
        "Edit the *_CANDIDATES list at the top of this script to point at this machine's library."
        % (what, "\n  ".join(candidates)))


AVATAR_PATH = _first_existing(AVATAR_CANDIDATES, "avatar")
MOTION_PATH = _first_existing(MOTION_CANDIDATES, "motion")


class _Tee(object):
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data); s.flush()
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


_log_path = os.path.join(OUTPUT_DIR, "icmcp_log.txt")
_log_file = open(_log_path, "w", encoding="utf-8")
_orig_stdout = sys.stdout
sys.stdout = _Tee(_orig_stdout, _log_file)


def log(msg):
    print("[icmcp] " + str(msg))


def status_str(st):
    fn = getattr(st, "IsError", None)
    if callable(fn):
        try:
            return "IsError()=%s" % fn()
        except Exception:
            pass
    return repr(st)


try:
    fps = RLPy.RGlobal.GetFps()

    def frame_time(n):
        # CLAUDE-NOTE: RTime has no int constructor (RTime() only); build frame times via RFps.
        return fps.IndexedFrameTime(n)

    def goto(frame):
        RLPy.RGlobal.SetTime(frame_time(frame))
        RLPy.RGlobal.ForceViewportUpdate()

    def sample_bone_positions(sc, frame):
        """World positions of a few spread-out bones at a frame -> list of (x,y,z)."""
        goto(frame)
        bones = sc.GetSkinBones()
        n = len(bones)
        if n == 0:
            return []
        idxs = sorted(set([n // 4, n // 2, (3 * n) // 4, n - 1])) if n >= 4 else range(n)
        pts = []
        for i in idxs:
            t = bones[i].WorldTransform().T()
            pts.append((t.X(), t.Y(), t.Z()))
        return pts

    log("Log file: %s" % _log_path)

    # ----- STEP 1: load avatar -------------------------------------------
    log("Loading avatar: %s" % AVATAR_PATH)
    before = set(a.GetID() for a in RLPy.RScene.GetAvatars())
    st = RLPy.RFileIO.LoadFile(AVATAR_PATH)
    log("LoadFile %s" % status_str(st))
    avatars = RLPy.RScene.GetAvatars()
    new_avatars = [a for a in avatars if a.GetID() not in before]
    avatar = new_avatars[-1] if new_avatars else (avatars[-1] if avatars else None)
    if avatar is None:
        log("ERROR: no avatar after load."); raise SystemExit(1)
    log("Avatar: %s" % avatar.GetName())
    sc = avatar.GetSkeletonComponent()

    # ----- STEP 2: load motion, then PROVE it via bone movement ----------
    log("Loading motion: %s" % MOTION_PATH)
    pts_a_before = sample_bone_positions(sc, START_FRAME)  # pose pre-motion (for reference)
    st = RLPy.RFileIO.LoadMotion(MOTION_PATH, frame_time(0), avatar)
    log("LoadMotion %s ; clip count now=%d" % (status_str(st), sc.GetClipCount()))

    # Definitive check: do bones occupy different world positions at two frames?
    pts0 = sample_bone_positions(sc, START_FRAME)
    pts1 = sample_bone_positions(sc, (START_FRAME + END_FRAME) // 2)
    moved = False
    if pts0 and len(pts0) == len(pts1):
        for (a0, b0) in zip(pts0, pts1):
            if any(abs(x - y) > 1e-4 for x, y in zip(a0, b0)):
                moved = True
                break
    if moved:
        log("MOTION CONFIRMED: bones move between frame %d and %d." % (START_FRAME, (START_FRAME + END_FRAME) // 2))
    else:
        log("WARNING: bones do not move across frames -- motion did NOT take (skeleton mismatch?).")

    # ----- STEP 3: range + scrub to mid so the pose is visible -----------
    RLPy.RGlobal.SetStartTime(frame_time(START_FRAME))
    RLPy.RGlobal.SetEndTime(frame_time(END_FRAME))
    goto((START_FRAME + END_FRAME) // 2)
    log("Range frames %d..%d; scrubbed to middle." % (START_FRAME, END_FRAME))

    # ----- STEP 4: camera (none in a fresh project -> preview view) ------
    cams = RLPy.RScene.GetCameras()
    log("Cameras: %d" % len(cams))
    if len(cams) > 0:
        RLPy.RScene.SetCurrentCamera(cams[0])
        log("Active camera: %s" % cams[0].GetName())
    else:
        log("Rendering from current preview viewport camera.")

    # ----- STEP 5: OpenPose image-sequence render ------------------------
    op = RLPy.ROpenPoseKeyPointParam()
    op.bFace = True
    op.bHand = True
    op.bWholeHand = True
    op.bWholeFace = True
    op.fOpacity = 1.0
    out_path = os.path.join(OUTPUT_DIR, "openpose.png")  # iClone appends the frame index
    log("Rendering OpenPose frames %d..%d -> %s" % (START_FRAME, END_FRAME, out_path))
    before_files = set(os.listdir(OUTPUT_DIR))
    try:
        st = RLPy.RGlobal.RenderImageSequenceOpenPoseKeyPoint(
            frame_time(START_FRAME), frame_time(END_FRAME), op, out_path)
        log("Render returned: %s" % status_str(st))
    except Exception:
        log("Render call raised:")
        traceback.print_exc()

    # ----- STEP 6: confirm frames on disk --------------------------------
    new_files = sorted(set(os.listdir(OUTPUT_DIR)) - before_files)
    pngs = [f for f in new_files if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    if pngs:
        log("SUCCESS: %d image(s) written. First few: %s" % (len(pngs), pngs[:5]))
    else:
        log("No image files appeared in %s . New files: %s" % (OUTPUT_DIR, new_files))

except SystemExit:
    pass
except Exception:
    log("UNHANDLED ERROR:")
    traceback.print_exc()
finally:
    log("=== run complete; log saved to %s ===" % _log_path)
    sys.stdout = _orig_stdout
    try:
        _log_file.close()
    except Exception:
        pass
