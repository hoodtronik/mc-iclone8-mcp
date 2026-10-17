"""Facial performance: stock expression clips (.iTalk, e.g. Digital Soul) on a character's FACE track.
Tools: list_expressions, face_performance.
# CLAUDE-NOTE (2026-10-17, measured on iClone 8.75): RFileIO.LoadFile(<.iTalk>) with the avatar selected, at the
# playhead, puts the clip on the face track (RIFaceComponent clip; Awkward_F = 2.67 s) and drives expression weights
# (Eye_Wide 0.75, Brow_Raise_Inner 0.68, Mouth_Smile 0.27 mid-clip); the body clip is untouched. Visemes from
# load_vocal live on their own track, so expressions and lip-sync combine. Chain clips at end + 1 frame (same rule as
# body clips) to cover a line.
"""
import os

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

EXPR_ROOTS = [os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Reallusion",
                           "Reallusion Templates", "Animation", "Expression")]


def catalog(roots=None):
    """{category path (relative, '/'-separated): [clip stems]} for every .iTalk under the expression roots."""
    out = {}
    for root in roots or EXPR_ROOTS:
        for d, _, files in os.walk(root):
            clips = sorted(os.path.splitext(f)[0] for f in files if f.lower().endswith(".italk"))
            if clips:
                rel = os.path.relpath(d, root).replace("\\", "/")
                out.setdefault(rel, []).extend(clips)
    return out


def resolve(name, roots=None):
    """A clip path from an absolute path, a stem ('Amused'), 'Category/Stem' or a category tail ('Pleased' -> its
    first clip). Case-insensitive."""
    if os.path.isfile(name):
        return name
    want = name.lower().replace("\\", "/")
    if want.endswith(".italk"):                      # iClone embeds Python 3.8: no str.removesuffix
        want = want[:-6]
    roots = roots or EXPR_ROOTS
    hits = []
    for root in roots:
        for d, _, files in os.walk(root):
            rel = os.path.relpath(d, root).replace("\\", "/").lower()
            for f in sorted(files):
                if not f.lower().endswith(".italk"):
                    continue
                stem = os.path.splitext(f)[0].lower()
                full = (rel + "/" + stem).lstrip("./")
                if stem == want or full == want or full.endswith("/" + want):
                    return os.path.join(d, f)
                if rel.split("/")[-1].split(".", 1)[-1] == want or rel.endswith("/" + want):
                    hits.append(os.path.join(d, f))
    if hits:
        return hits[0]
    raise FileNotFoundError(f"no .iTalk expression matches {name!r} (see list_expressions)")


# ------------------------------------------------------------------------------------------------------ RLPy side
def _face_clips(fc):
    out = []
    for i in range(fc.GetClipCount()):
        c = fc.GetClip(i)
        out.append((c.ClipTimeToSceneTime(RLPy.RTime.FromValue(0)).ToInt(), c.GetClipLength().ToInt()))
    return out


def _body_clips(av):
    sk = av.GetSkeletonComponent()
    return [(sk.GetClip(i).ClipTimeToSceneTime(RLPy.RTime.FromValue(0)).ToInt(), sk.GetClip(i).GetClipLength().ToInt())
            for i in range(sk.GetClipCount())]


def _top_weights(fc, t, n=6):
    names = list(fc.GetExpressionNames(""))
    w = list(fc.GetExpressionWeights(t, names))
    return sorted([(k, round(x, 2)) for k, x in zip(names, w) if abs(x) > 0.05], key=lambda p: -abs(p[1]))[:n]


def _load_face_clip(av, path, ticks):
    fc = av.GetFaceComponent()
    before = _face_clips(fc)
    now = RLPy.RGlobal.GetTime()
    try:
        RLPy.RGlobal.SetTime(RLPy.RTime.FromValue(ticks))
        RLPy.RScene.ClearSelectObjects()
        RLPy.RScene.SelectObject(av)
        RLPy.RFileIO.LoadFile(path)
    finally:
        RLPy.RScene.ClearSelectObjects()
        RLPy.RGlobal.SetTime(now)
    after = _face_clips(fc)
    new = [c for c in after if c not in before] or [c for c in after if c[0] <= ticks < c[0] + max(1, c[1])]
    if not new:
        raise RuntimeError(f"loading {os.path.basename(path)} put no face clip on {av.GetName()}")
    return min(new, key=lambda c: abs(c[0] - ticks))


def face_performance(args):
    """Put expression clips on an avatar's face track: clips=[{clip, at_s, until_s?}] (until_s chains the clip)."""
    from tools.motion_director import _avatar
    av = _avatar(args["avatar"])
    fps = RLPy.RGlobal.GetFps()
    tick_per_frame = fps.IndexedFrameTime(1).ToInt()
    body_before = _body_clips(av)
    placed = []
    for item in args["clips"]:
        path = resolve(item["clip"])
        t = int(round(float(item.get("at_s", 0)) * 6000))
        until = int(round(float(item["until_s"]) * 6000)) if item.get("until_s") is not None else None
        while True:
            c0, clen = _load_face_clip(av, path, t)
            placed.append({"clip": os.path.splitext(os.path.basename(path))[0], "start_s": round(c0 / 6000.0, 2),
                           "seconds": round(clen / 6000.0, 2)})
            if until is None or clen <= 0 or c0 + clen >= until:
                break
            t = c0 + clen + tick_per_frame                  # chain at end + 1 frame
    if _body_clips(av) != body_before:
        raise RuntimeError(f"loading expressions changed {av.GetName()}'s BODY clips - check the .iTalk files")
    mid = RLPy.RTime.FromValue(int(round((placed[0]["start_s"] + placed[0]["seconds"] / 2) * 6000)))
    return {"ok": True, "avatar": av.GetName(), "placed": placed,
            "top_weights_mid_first": _top_weights(av.GetFaceComponent(), mid)}


def list_expressions(args):
    cat = catalog()
    f = (args.get("filter") or "").lower()
    rows = {k: v for k, v in cat.items() if not f or f in k.lower() or any(f in c.lower() for c in v)}
    return {"ok": True, "roots": EXPR_ROOTS, "categories": len(rows),
            "clips": {k: v[: int(args.get("limit_per_category", 30))] for k, v in sorted(rows.items())}}


def register(registry):
    registry["list_expressions"] = {
        "handler": list_expressions, "main_thread": False,
        "description": "List stock facial expression clips (.iTalk) by category (e.g. Digital Soul/4.Feel_Like/1.Pleased). "
                       "filter matches category or clip names.",
        "inputSchema": {"type": "object", "properties": {"filter": {"type": "string"},
                                                         "limit_per_category": {"type": "integer"}}}}
    registry["face_performance"] = {
        "handler": face_performance, "main_thread": True, "timeout": 600,
        "description": "FACIAL PERFORMANCE: put expression clips on an avatar's face track: clips=[{clip, at_s, "
                       "until_s?}] where clip is a stem ('Amused'), 'Category/Stem', a mood folder ('Pleased', 'Sad', "
                       "'Excited') or a path; until_s chains it to fill a line. Combines with load_vocal lip-sync. "
                       "Returns placed clips and the strongest expression weights mid-clip.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "clips": {"type": "array", "items": {"type": "object"}}},
            "required": ["avatar", "clips"]}}
