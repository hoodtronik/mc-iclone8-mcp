"""Minimal OpenEXR reader for iClone's depth EXRs (scanline, HALF channels, ZIP/ZIPS or NONE compression). numpy + zlib only.
# CLAUDE-NOTE (2026-09-26, hoodtronik fork): iClone RDepthParam.b16BitPng=True writes EXR (half RGBA, ZIP) — the real depth
# precision (8-bit PNG depth has only ~3 grey levels on subjects). cv2 in iClone/comfy builds can't read EXR, hence this.
"""
import struct, zlib
import numpy as np


def _header(b):
    i, hdr = 8, {}
    while b[i] != 0:
        j = b.index(b"\0", i); name = b[i:j].decode(); i = j + 1
        j = b.index(b"\0", i); typ = b[i:j].decode(); i = j + 1
        size = struct.unpack("<i", b[i:i + 4])[0]; i += 4
        hdr[name] = (typ, b[i:i + size]); i += size
    return hdr, i + 1


def _channels(raw):
    out, i = [], 0
    while raw[i] != 0:
        j = raw.index(b"\0", i); name = raw[i:j].decode(); i = j + 1
        ptype = struct.unpack("<i", raw[i:i + 4])[0]; i += 16
        out.append((name, ptype))
    return out


def read(path):
    """-> dict channel_name -> float32 array (H, W)."""
    b = open(path, "rb").read()
    hdr, pos = _header(b)
    chans = _channels(hdr["channels"][1])
    comp = hdr["compression"][1][0]
    x0, y0, x1, y1 = struct.unpack("<4i", hdr["dataWindow"][1])
    w, h = x1 - x0 + 1, y1 - y0 + 1
    lines_per = {0: 1, 2: 1, 3: 16}.get(comp)
    if lines_per is None:
        raise ValueError(f"unsupported EXR compression {comp}")
    if any(pt != 1 for _, pt in chans):
        raise ValueError("only HALF channels supported")
    nchunks = (h + lines_per - 1) // lines_per
    offsets = struct.unpack(f"<{nchunks}Q", b[pos:pos + 8 * nchunks])
    data = {n: np.zeros((h, w), np.float32) for n, _ in chans}
    for off in offsets:
        y, size = struct.unpack("<ii", b[off:off + 8])
        blk = b[off + 8:off + 8 + size]
        nlines = min(lines_per, y1 - y + 1)
        expected = nlines * len(chans) * w * 2
        if comp != 0 and size < expected:
            raw = np.frombuffer(zlib.decompress(blk), np.uint8).astype(np.int64)
            # undo predictor t[i] = (t[i-1] + t[i] - 128) & 0xff  ==  (t[0] + cumsum(t[1:] - 128)) & 0xff
            raw[1:] = raw[1:] - 128
            raw = (np.cumsum(raw) & 0xFF).astype(np.uint8)
            half = (raw.size + 1) // 2
            inter = np.empty_like(raw)
            inter[0::2] = raw[:half]
            inter[1::2] = raw[half:]
            buf = inter.tobytes()
        else:
            buf = blk
        arr = np.frombuffer(buf, np.float16)
        k = 0
        for ln in range(nlines):
            for n, _ in chans:
                data[n][y - y0 + ln] = arr[k:k + w]
                k += w
    return data
