"""Scene QA: see MOTION, not just stills.
Tools: filmstrip (rendered contact sheet over a frame range, optional crop on one avatar) · motion_qa (per-frame bone
sampling -> foot slide / pops / overlaps as numbers).
# CLAUDE-NOTE (2026-10-16): built after the park-bench scene looked "janky" while single stills looked fine. Jank lives
# BETWEEN frames, so every polish iteration is: motion_qa numbers + a filmstrip, fix, re-measure. The metric math is
# pure (no RLPy) so it is unit-tested offline; sampling/rendering are thin RLPy wrappers.
"""
import base64
import io
import math
import os

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

# Major CC3/CC4 bones (present on CC and ActorCore avatars). Missing names are skipped.
QA_BONES = ["CC_Base_Hip", "CC_Base_Spine02", "CC_Base_Head", "CC_Base_L_Upperarm", "CC_Base_R_Upperarm",
            "CC_Base_L_Forearm", "CC_Base_R_Forearm", "CC_Base_L_Hand", "CC_Base_R_Hand", "CC_Base_L_Thigh",
            "CC_Base_R_Thigh", "CC_Base_L_Calf", "CC_Base_R_Calf", "CC_Base_L_Foot", "CC_Base_R_Foot",
            "CC_Base_L_ToeBase", "CC_Base_R_ToeBase"]


# ----------------------------------------------------------------------------------------------- pure metric helpers
def _hdist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _median(xs):
    s = sorted(xs)
    if not s:
        return 0.0
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


def analyze_avatar(frames, bones, fps, step=1, pop_cm=20.0, root_pop_cm_s=450.0, moving_cm_s=20.0, top=5):
    """frames: sampled frame indices; bones: {bone: [(x, y, z) per frame]} (world cm). Returns the avatar's metrics.

    foot slide: while the avatar travels, one foot should be planted (~0 cm/s). stance speed = the SLOWER foot's
    horizontal speed per frame; slide_ratio = median stance speed / median hip speed over moving frames
    (glide ~1.0; a clean walk ~0.1-0.3). Uses ToeBase when present (the Foot bone is the ankle).
    pops: hip-relative bone jump > pop_cm per 1/30 s (scaled to the sampling interval), or hip world speed > root_pop_cm_s.
    # CLAUDE-NOTE (2026-10-16, measured): a clean walk's swing foot moves 12.7 cm/frame at 30 fps (filmstrip-checked), so
    # 12 cm flagged healthy strides; 20 cm per 1/30 s keeps real snaps (clip seams moved bones 50+ cm).
    # CLAUDE-NOTE (2026-10-16, measured): foot z can read constant during a walk (ankle at the floor-contact offset), so
    # the slide metric deliberately uses horizontal speed only."""
    dt = step / float(fps)
    hip = bones.get("CC_Base_Hip")
    out = {"frames": [frames[0], frames[-1]] if frames else [], "samples": len(frames)}
    if not hip or len(frames) < 3:
        return dict(out, error="needs CC_Base_Hip and >= 3 samples")
    hip_v = [_hdist(hip[i], hip[i - 1]) / dt for i in range(1, len(frames))]
    lf = bones.get("CC_Base_L_ToeBase") or bones.get("CC_Base_L_Foot")
    rf = bones.get("CC_Base_R_ToeBase") or bones.get("CC_Base_R_Foot")
    moving = [i for i, v in enumerate(hip_v, 1) if v > moving_cm_s]
    out["moving_frames"] = len(moving)
    out["hip_speed_cm_s"] = round(_median([hip_v[i - 1] for i in moving]), 1) if moving else 0.0
    if lf and rf and moving:
        stance = [min(_hdist(lf[i], lf[i - 1]), _hdist(rf[i], rf[i - 1])) / dt for i in moving]
        out["stance_foot_speed_cm_s"] = round(_median(stance), 1)
        out["slide_ratio"] = round(out["stance_foot_speed_cm_s"] / max(out["hip_speed_cm_s"], 1e-6), 2)
        stride = [_hdist(lf[i], rf[i]) for i in moving]
        out["max_stride_cm"] = round(max(stride), 1)
    # CLAUDE-NOTE (2026-10-17, DuskStreet jogger, measured): a clean jog (hip ~350-385 cm/s) swings the toe 21.3 cm per
    # frame every stride, so the walk-tuned 20 cm flagged every step. Scale both thresholds with the gait speed above
    # a brisk walk (200 cm/s); walks are unchanged and clip seams (50+ cm) still flag at jog speed (~35 cm).
    gait = max(1.0, out["hip_speed_cm_s"] / 200.0)
    pop_cm, root_pop_cm_s = pop_cm * gait, max(root_pop_cm_s, 1.6 * out["hip_speed_cm_s"])
    pops = []
    for i in range(1, len(frames)):
        worst, which = 0.0, None
        for name, pts in bones.items():
            if name == "CC_Base_Hip":
                continue
            a = [p - h for p, h in zip(pts[i], hip[i])]
            b = [p - h for p, h in zip(pts[i - 1], hip[i - 1])]
            d = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
            if d > worst:
                worst, which = d, name
        root = hip_v[i - 1]
        if worst > pop_cm * step * 30.0 / fps or root > root_pop_cm_s:
            pops.append({"frame": frames[i], "bone": which, "bone_jump_cm": round(worst, 1), "hip_speed_cm_s": round(root, 1)})
    pops.sort(key=lambda p: (p["hip_speed_cm_s"] > root_pop_cm_s, p["bone_jump_cm"]), reverse=True)
    out["pop_count"] = len(pops)
    out["pops"] = pops[:top]
    return out


def find_overlaps(frames, hips, min_cm=40.0):
    """hips: {avatar: [(x, y, z) per frame]} -> [{a, b, from, to, min_cm}] runs where two hips are closer than min_cm."""
    names = sorted(hips)
    runs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            cur = None
            for k, f in enumerate(frames):
                d = _hdist(hips[a][k], hips[b][k])
                if d < min_cm:
                    if cur is None:
                        cur = {"a": a, "b": b, "from": f, "to": f, "min_cm": d}
                    cur["to"], cur["min_cm"] = f, min(cur["min_cm"], d)
                elif cur is not None:
                    runs.append(cur); cur = None
            if cur is not None:
                runs.append(cur)
    for r in runs:
        r["min_cm"] = round(r["min_cm"], 1)
    return runs


def frame_list(args, default_count=8):
    """frames=[...] or start_frame/end_frame/count (inclusive, evenly spaced)."""
    if args.get("frames"):
        return [int(f) for f in args["frames"]]
    s, e = int(args["start_frame"]), int(args["end_frame"])
    n = max(1, int(args.get("count", default_count)))
    if n == 1 or e <= s:
        return [s]
    return sorted({int(round(s + (e - s) * i / (n - 1))) for i in range(n)})


def contact_sheet(images, labels, cols=4, tile_width=480):
    """PIL images -> one labelled grid image."""
    from PIL import Image, ImageDraw
    tiles = []
    for im in images:
        im = im.convert("RGB")
        h = max(1, int(round(im.height * tile_width / float(im.width))))
        tiles.append(im.resize((tile_width, h), Image.LANCZOS))
    cols = max(1, min(cols, len(tiles)))
    rows = (len(tiles) + cols - 1) // cols
    th = max(t.height for t in tiles)
    sheet = Image.new("RGB", (cols * tile_width + (cols - 1) * 4, rows * th + (rows - 1) * 4), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    for i, (t, lab) in enumerate(zip(tiles, labels)):
        x, y = (i % cols) * (tile_width + 4), (i // cols) * (th + 4)
        sheet.paste(t, (x, y))
        draw.rectangle([x, y, x + 8 * len(lab) + 8, y + 16], fill=(0, 0, 0))
        draw.text((x + 4, y + 2), lab, fill=(255, 255, 0))
    return sheet


def crop_box(pixels, width, height, margin=0.25, aspect=None):
    """Bounding box of projected points (None = behind camera) + margin, clamped; optional fixed aspect (w/h)."""
    pts = [p for p in pixels if p is not None]
    if not pts:
        return None
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    w, h = max(x1 - x0, 8.0), max(y1 - y0, 8.0)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    w, h = w * (1 + 2 * margin), h * (1 + 2 * margin)
    if aspect:
        if w / h < aspect:
            w = h * aspect
        else:
            h = w / aspect
    x0, y0 = max(0, int(cx - w / 2)), max(0, int(cy - h / 2))
    x1, y1 = min(width, int(cx + w / 2)), min(height, int(cy + h / 2))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return (x0, y0, x1, y1)


# ------------------------------------------------------------------------------------------------------ RLPy side
def _avatars(names=None):
    avs = list(RLPy.RScene.GetAvatars())
    if names:
        have = {a.GetName(): a for a in avs}
        missing = [n for n in names if n not in have]
        if missing:
            raise ValueError(f"no avatar(s) {missing}; have {sorted(have)}")
        avs = [have[n] for n in names]
    return avs


def _bone_map(av):
    sk = av.GetSkeletonComponent()
    by = {b.GetName(): b for b in sk.GetSkinBones()}
    return {n: by[n] for n in QA_BONES if n in by}


def _sample(avs, frames):
    """{avatar: {bone: [(x, y, z)]}} by moving the playhead (bone WorldTransform follows SetTime, measured 10-16)."""
    fps = RLPy.RGlobal.GetFps()
    maps = {a.GetName(): _bone_map(a) for a in avs}
    data = {n: {b: [] for b in m} for n, m in maps.items()}
    now = RLPy.RGlobal.GetTime()
    try:
        for f in frames:
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(int(f)))
            for n, m in maps.items():
                for b, node in m.items():
                    wt = node.WorldTransform()      # hold before .T() (dangling SWIG ref otherwise)
                    t = wt.T()
                    data[n][b].append((t.x, t.y, t.z))
    finally:
        RLPy.RGlobal.SetTime(now)
    return data


def motion_qa(args):
    """Sample avatars' major bones every `step` frames over a range and report foot slide, pops and hip overlaps."""
    fps = RLPy.RGlobal.GetFps()
    end_default = fps.GetFrameIndex(RLPy.RGlobal.GetProjectLength())
    s = int(args.get("start_frame", 0)); e = int(args.get("end_frame", end_default))
    step = max(1, int(args.get("step", 1)))
    if e <= s:
        raise ValueError("end_frame must be > start_frame")
    frames = list(range(s, e + 1, step))
    if len(frames) * max(1, len(args.get("avatars") or RLPy.RScene.GetAvatars())) > 20000:
        raise ValueError(f"{len(frames)} frames x avatars is too many samples; raise step or narrow the range")
    avs = _avatars(args.get("avatars"))
    data = _sample(avs, frames)
    fsec = fps.ToFloat()
    report = {n: analyze_avatar(frames, b, fsec, step, float(args.get("pop_cm", 20.0))) for n, b in data.items()}
    overlaps = find_overlaps(frames, {n: b["CC_Base_Hip"] for n, b in data.items() if "CC_Base_Hip" in b},
                             float(args.get("overlap_cm", 40.0)))
    _mark_on_screen(overlaps, data, frames)
    flags = []
    for n, r in report.items():
        if r.get("slide_ratio", 0) > 0.5:
            flags.append(f"{n}: feet slide (slide_ratio {r['slide_ratio']}, stance foot {r['stance_foot_speed_cm_s']} cm/s "
                         f"vs hip {r['hip_speed_cm_s']} cm/s) - gliding, not stepping")
        if r.get("pop_count"):
            flags.append(f"{n}: {r['pop_count']} pop frame(s), worst at frame {r['pops'][0]['frame']}")
    for o in overlaps:
        if o.get("on_screen", True):
            flags.append(f"{o['a']} / {o['b']} hips within {o['min_cm']} cm ON SCREEN, frames {o['from']}-{o['to']}")
    off = [o for o in overlaps if not o.get("on_screen", True)]
    if off:
        flags.append(f"{len(off)} overlap run(s) only off-screen (e.g. walkers queued at the same start/end spot)")
    return {"ok": True, "fps": fsec, "range": [s, e], "step": step, "flags": flags, "avatars": report, "overlaps": overlaps[:20]}


def _mark_on_screen(overlaps, data, frames):
    """Tag each overlap run with on_screen: is either hip inside the current camera's view at any sampled frame of the
    run? Uses the viewport aspect (render aspect may differ slightly). Leaves runs untagged if projection fails."""
    try:
        from tools.icmcp_extra import _project, _viewport
        vp = _viewport(); vw, vh = vp.width(), vp.height()
        fps = RLPy.RGlobal.GetFps()
    except Exception:
        return
    now = RLPy.RGlobal.GetTime()
    try:
        for o in overlaps:
            idx = [k for k, f in enumerate(frames) if o["from"] <= f <= o["to"]]
            seen = False
            for k in idx[::max(1, len(idx) // 6)]:
                t = fps.IndexedFrameTime(frames[k]); RLPy.RGlobal.SetTime(t)
                cam = RLPy.RScene.GetCurrentCamera(); W = cam.WorldTransform(); P = W.T(); Q = W.R()
                hfov = cam.GetAngleOfView(t)
                for name in (o["a"], o["b"]):
                    px = _project(data[name]["CC_Base_Hip"][k], (P.x, P.y, P.z), (Q.x, Q.y, Q.z, Q.w), hfov, vw, vh)
                    if px and 0 <= px[0] <= vw and 0 <= px[1] <= vh:
                        seen = True
                if seen:
                    break
            o["on_screen"] = seen
    finally:
        RLPy.RGlobal.SetTime(now)


def filmstrip(args):
    """Render frames through the current camera and tile them into one labelled contact sheet (MCP image)."""
    from PIL import Image
    from tools.icmcp_extra import _win, _qrot_inv, _project
    frames = frame_list(args)
    if len(frames) > 24:
        raise ValueError("at most 24 frames per filmstrip")
    out_dir = _win(args.get("output_dir") or os.path.join(os.environ.get("TEMP", r"C:\Temp"), "icmcp_filmstrip"))
    os.makedirs(out_dir, exist_ok=True)
    fps = RLPy.RGlobal.GetFps()
    focus = _avatars([args["focus"]])[0] if args.get("focus") else None
    fmap = _bone_map(focus) if focus else {}
    now = RLPy.RGlobal.GetTime()
    images, labels, crops = [], [], []
    try:
        for f in frames:
            t = fps.IndexedFrameTime(int(f))
            RLPy.RGlobal.SetTime(t)
            p = os.path.join(out_dir, "f%05d.png" % f)
            if os.path.exists(p):
                os.remove(p)
            RLPy.RGlobal.RenderImage(p)
            if not os.path.exists(p):
                raise RuntimeError(f"RenderImage wrote nothing for frame {f} ({p})")
            im = Image.open(p); im.load()
            if fmap:
                cam = RLPy.RScene.GetCurrentCamera(); W = cam.WorldTransform(); P = W.T(); Q = W.R()
                hfov = cam.GetAngleOfView(t)
                pts = []
                for node in fmap.values():
                    wt = node.WorldTransform(); v = wt.T()
                    pts.append(_project((v.x, v.y, v.z), (P.x, P.y, P.z), (Q.x, Q.y, Q.z, Q.w), hfov, im.width, im.height))
                box = crop_box(pts, im.width, im.height, float(args.get("margin", 0.3)), aspect=0.75)
                crops.append(box)
                if box:
                    im = im.crop(box)
            images.append(im)
            labels.append("f%d  %.2fs" % (f, f / fps.ToFloat()))
    finally:
        RLPy.RGlobal.SetTime(now)
    sheet = contact_sheet(images, labels, int(args.get("cols", 4)), int(args.get("tile_width", 360 if fmap else 480)))
    path = os.path.join(out_dir, "filmstrip.png")
    sheet.save(path)
    buf = io.BytesIO(); sheet.save(buf, "PNG")
    out = {"ok": True, "path": path, "frames": frames, "size": list(sheet.size)}
    if fmap:
        out["off_screen_frames"] = [f for f, c in zip(frames, crops) if c is None]
    if args.get("return_image", True):
        out["_image_png_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
    return out


def register(registry):
    def reg(name, fn, desc, props, req):
        registry[name] = {"handler": fn, "main_thread": True, "description": desc,
                          "inputSchema": {"type": "object", "properties": props, "required": req}}
    rng = {"start_frame": {"type": "integer"}, "end_frame": {"type": "integer"}}
    reg("filmstrip", filmstrip, "EYES FOR MOTION: render frames (frames=[...] or start/end/count) through the current camera and "
        "return ONE labelled contact sheet. focus=<avatar> crops every tile on that avatar (follows it as it moves).",
        dict(rng, frames={"type": "array", "items": {"type": "integer"}}, count={"type": "integer"},
             focus={"type": "string"}, margin={"type": "number"}, cols={"type": "integer"}, tile_width={"type": "integer"},
             output_dir={"type": "string"}, return_image={"type": "boolean"}), [])
    reg("motion_qa", motion_qa, "Measure motion quality over a frame range: per avatar foot slide (slide_ratio ~1 = gliding, "
        "<0.3 = planted steps), pops (bone/hip jumps between frames) and hip overlaps between avatars. Returns flags + numbers.",
        dict(rng, avatars={"type": "array", "items": {"type": "string"}}, step={"type": "integer"},
             pop_cm={"type": "number", "description": "bone jump threshold in cm per 1/30 s (default 20)"}, overlap_cm={"type": "number"}), [])
