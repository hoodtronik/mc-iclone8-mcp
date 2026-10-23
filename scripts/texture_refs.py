"""Offline texture-reference doctor for old 3D files (no iClone needed): list every texture/media path a file points at,
say which ones resolve, find the missing ones by file name, and optionally copy them where the importer will look.

  python scripts/texture_refs.py <file> [<file>...]                       # report
  python scripts/texture_refs.py <file> --search H:/_ARCHIVE F:/iCLONE    # + find missing ones by name under these roots
  python scripts/texture_refs.py <file> --search <roots> --apply          # + copy found files next to the file (FBX: into <name>.fbm)
  python scripts/texture_refs.py --scan-dir <folder> [--search ...]       # every supported file under a folder, summary only

Supported: .fbx (binary/ASCII; also checks <name>.fbm), .iProject/.iAvatar/.iProp/.ccProject/.ccAvatar (Reallusion _RLZeus
containers: zlib chunks are inflated), .duf/.dsf (DAZ, gzip JSON), .obj/.mtl, .blend (string scan), anything else (string scan).

# CLAUDE-NOTE (2026-10-23, hoodtronik fork): built for Ilyas's archive of old projects ("they look weird; usually the
# textures can't be found"). Findings that shaped it: iClone .iProject/.iAvatar EMBED their textures (only stray HDR/IBL
# paths are external), so in-iClone weirdness there is NOT a path problem (use texture_report). FBX exports are the real
# offenders: absolute paths to drives that no longer exist (D:/ANIMATION, F:/VIDEO/3D APPS/...), rescued only when the file
# sits in the sibling <name>.fbm folder, which FBX importers search by basename. --apply never overwrites and never deletes.
"""
import argparse
import gzip
import json
import os
import re
import shutil
import sys
import time
import zlib

EXT = r"png|jpg|jpeg|tga|bmp|dds|tif|tiff|psd|exr|hdr|webp|mp4|avi|mov|wav|mp3|imotion|iprop|iavatar|fbx|obj|mtl"
PAT = re.compile(rb"(?:[A-Za-z]:[\\/]|\\\\|\.{1,2}[\\/])[^\x00-\x1f\"<>|*?]{1,300}?\.(?:" + EXT.encode() + rb")(?![A-Za-z0-9])", re.I)
BARE = re.compile(rb"[A-Za-z0-9_\- ]{2,120}\.(?:png|jpg|jpeg|tga|bmp|dds|tif|tiff)(?![A-Za-z0-9])", re.I)  # mtl/duf relative names
SUPPORTED = (".fbx", ".iproject", ".iavatar", ".iprop", ".ccproject", ".ccavatar", ".duf", ".dsf", ".obj", ".mtl", ".blend")


def _found(blob, bare=False):
    out = set(m.group().decode("latin1") for m in PAT.finditer(blob))
    u = blob.decode("utf-16-le", "ignore").encode("latin1", "ignore")
    out |= set(m.group().decode("latin1") for m in PAT.finditer(u))
    if bare:
        out |= set(m.group().decode("latin1").strip() for m in BARE.finditer(blob))
    return out


def refs_of(path):
    ext = os.path.splitext(path)[1].lower()
    b = open(path, "rb").read()
    if ext in (".duf", ".dsf") and b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    refs = _found(b, bare=ext in (".mtl", ".duf", ".dsf"))
    if b[:7] == b"_RLZeus":  # Reallusion container: inflate every zlib stream
        for m in re.finditer(rb"\x78[\x01\x5e\x9c\xda]", b):
            try:
                d = zlib.decompressobj().decompress(b[m.start():m.start() + 64_000_000])
            except Exception:
                continue
            if d:
                refs |= _found(d)
    if ext == ".obj":  # follow mtllib
        for m in re.finditer(rb"^mtllib\s+(.+?)\s*$", b, re.M):
            mtl = os.path.join(os.path.dirname(path), m.group(1).decode("latin1"))
            if os.path.isfile(mtl):
                refs |= refs_of(mtl)
    refs.discard(os.path.basename(path))
    return sorted(refs)


INTERNAL = re.compile(r"^\./RL_|CharacterCreator\dTemp|IRayResource|[\\/]Temp[\\/]", re.I)


def resolve(ref, owner):
    """Where would an importer find this file today? Exact path, then sibling .fbm, then the owner's folder (by name)."""
    # CLAUDE-NOTE: CC/iClone shader resources (./RL_MR_*) and Iray temp images are app-internal, regenerated on load: not user textures.
    if INTERNAL.search(ref):
        return "INTERNAL", None
    here = os.path.dirname(owner)
    name = re.split(r"[\\/]", ref)[-1]
    cands = [ref] if re.match(r"^[A-Za-z]:[\\/]|^\\\\", ref) else [os.path.normpath(os.path.join(here, ref))]
    cands += [os.path.join(os.path.splitext(owner)[0] + ".fbm", name), os.path.join(here, name),
              os.path.join(here, "textures", name), os.path.join(here, "Textures", name)]
    for c in cands:
        if os.path.isfile(c):
            return "OK" if c == cands[0] else "LOCAL", c
    return "MISSING", None


def build_index(roots, budget_s=900, limit=2_000_000):
    idx, n, t0 = {}, 0, time.time()
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(("$RECYCLE", "System Volume")) and d not in ("node_modules", ".git", "Library")]
            for f in files:
                idx.setdefault(f.lower(), []).append(os.path.join(dirpath, f))
                n += 1
            if n >= limit or time.time() - t0 > budget_s:
                return idx, n, True
    return idx, n, False


def report(path, idx=None, apply=False, quiet=False):
    rows = []
    for ref in refs_of(path):
        st, where = resolve(ref, path)
        row = {"ref": ref, "status": st, "at": where}
        if st == "MISSING" and idx is not None:
            hits = idx.get(re.split(r"[\\/]", ref)[-1].lower(), [])
            if hits:
                row.update(status="FOUND", at=hits[0], alternatives=len(hits) - 1)
                if apply:
                    dst_dir = os.path.splitext(path)[0] + ".fbm" if path.lower().endswith(".fbx") else os.path.dirname(path)
                    os.makedirs(dst_dir, exist_ok=True)
                    dst = os.path.join(dst_dir, os.path.basename(hits[0]))
                    if not os.path.exists(dst):
                        shutil.copy2(hits[0], dst)
                        row["copied_to"] = dst
        rows.append(row)
    if not quiet:
        c = {s: sum(r["status"] == s for r in rows) for s in ("OK", "LOCAL", "FOUND", "MISSING", "INTERNAL")}
        print(f"== {path}\n   refs={len(rows)}  " + "  ".join(f"{k}={v}" for k, v in c.items()))
        for r in rows:
            if r["status"] not in ("OK", "INTERNAL"):
                print(f"   {r['status']:8s} {r['ref']}" + (f"\n            -> {r['at']}" if r["at"] else "") +
                      (f"  (copied to {r['copied_to']})" if r.get("copied_to") else ""))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--scan-dir")
    ap.add_argument("--search", nargs="+", help="roots to search for missing files by name")
    ap.add_argument("--apply", action="store_true", help="copy FOUND files next to the file (FBX: <name>.fbm). Never overwrites.")
    ap.add_argument("--json", help="write the full result here")
    ap.add_argument("--budget", type=int, default=900, help="seconds for indexing the search roots")
    a = ap.parse_args()
    files = list(a.files)
    if a.scan_dir:
        for dp, _d, fs in os.walk(a.scan_dir):
            files += [os.path.join(dp, f) for f in fs if f.lower().endswith(SUPPORTED)]
    if not files:
        ap.error("give files or --scan-dir")
    idx = None
    if a.search:
        idx, n, trunc = build_index(a.search, a.budget)
        print(f"indexed {n} files under {a.search}" + (" (TRUNCATED: raise --budget)" if trunc else ""))
    out = {}
    for f in files:
        try:
            out[f] = report(f, idx, a.apply, quiet=bool(a.scan_dir))
        except Exception as e:
            out[f] = [{"error": str(e)[:200]}]
    if a.scan_dir:
        for f, rows in out.items():
            bad = sum(r.get("status") == "MISSING" for r in rows)
            if rows and bad:
                print(f"{bad:4d}/{len(rows):<4d} missing  {f}")
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    sys.exit(main())
