"""Footage catalog: ingest once, then everything reads cached derivatives.

Each clip gets media/clips/<id>/ holding:
  meta.json        probe data, source path, brand
  proxy.mp4        SDR, upright, 720 on the short side: what previews cut from
  audio.wav        16 kHz mono, for transcription
  transcript.json  words with timings (lib/transcribe.py)
  shots.json       shot log (lib/analyze.py)
The id is derived from file content, so renaming or moving footage is safe
and nothing is ever processed twice.
"""

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import probe as P
from .util import (CLIPS, IMAGE_EXT, VIDEO_EXT, Fail, Timer, fingerprint,
                   load_json, out, run, save_json, slug)

PROXY_SHORT = 720
VT_SDR = "color_matrix=bt709:color_primaries=bt709:color_transfer=bt709"


def clip_dir(cid):
    return os.path.join(CLIPS, cid)


def meta(cid):
    m = load_json(os.path.join(clip_dir(cid), "meta.json"))
    if not m:
        raise Fail("unknown clip '%s' (run: adstudio clips)" % cid)
    return m


def all_clips(brand=None, refs=False):
    """Usable footage only, unless refs=True (references are study material)."""
    res = []
    if not os.path.isdir(CLIPS):
        return res
    for cid in sorted(os.listdir(CLIPS)):
        m = load_json(os.path.join(CLIPS, cid, "meta.json"))
        if m and (brand is None or m.get("brand") == brand) \
                and (refs or not m.get("ref")):
            res.append(m)
    return res


def find(ref, refs=False):
    """Accept a full id or any unambiguous fragment of one."""
    if os.path.exists(os.path.join(clip_dir(ref), "meta.json")):
        return meta(ref)
    hits = [m for m in all_clips(refs=refs) if ref.lower() in m["id"].lower()
            or ref.lower() in m["name"].lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise Fail("no clip matches '%s'" % ref)
    raise Fail("'%s' is ambiguous: %s" % (ref, ", ".join(h["id"] for h in hits[:8])))


def transpose_for(rotation):
    r = int(rotation) % 360
    return {90: "transpose=2", 270: "transpose=1",
            180: "hflip,vflip"}.get(r, "")


def source_args(m, ss=None, t=None, use_proxy=True, hw_size=None):
    """ffmpeg input args plus a filter prefix that yields upright SDR frames.

    HDR originals are tone-mapped in hardware (VideoToolbox), which runs at
    roughly ten times realtime on 4K and needs no extra ffmpeg filters.
    """
    seek = []
    if ss is not None:
        seek += ["-ss", "%.4f" % ss]
    if t is not None:
        seek += ["-t", "%.4f" % t]
    proxy = os.path.join(clip_dir(m["id"]), "proxy.mp4")
    if m["kind"] == "image":
        return ["-loop", "1", "-framerate", "30"] + (["-t", "%.4f" % t] if t else []) + ["-i", m["src"]], ""
    if use_proxy and os.path.exists(proxy):
        return seek + ["-i", proxy], ""
    if not os.path.exists(m["src"]):
        raise Fail("source file missing for %s: %s" % (m["id"], m["src"]))
    if m.get("hdr"):
        # hw_size (display w, h) lets VideoToolbox resize while it tone-maps,
        # which avoids pulling full 4K frames back to the CPU.
        size = ""
        if hw_size:
            sw, sh = hw_size
            if abs(int(m.get("rotation", 0))) % 180 == 90:
                sw, sh = sh, sw
            size = "w=%d:h=%d:" % (sw, sh)
        dl = "p010le" if "10" in (m.get("pix_fmt") or "") else "nv12"
        pre = "scale_vt=%s%s,hwdownload,format=%s" % (size, VT_SDR, dl)
        tr = transpose_for(m.get("rotation", 0))
        if tr:
            pre += "," + tr
        return (["-display_rotation", "0", "-noautorotate",
                 "-hwaccel", "videotoolbox",
                 "-hwaccel_output_format", "videotoolbox_vld"]
                + seek + ["-i", m["src"]]), pre
    return seek + ["-i", m["src"]], ""


def _build_proxy(m):
    d = clip_dir(m["id"])
    dst = os.path.join(d, "proxy.mp4")
    if os.path.exists(dst):
        return False
    w, h = m["width"], m["height"]
    if w <= h:
        pw, ph = PROXY_SHORT, int(round(h * PROXY_SHORT / float(w) / 2)) * 2
    else:
        pw, ph = int(round(w * PROXY_SHORT / float(h) / 2)) * 2, PROXY_SHORT
    if min(w, h) <= PROXY_SHORT:
        pw, ph = w - w % 2, h - h % 2
    args, pre = source_args(m, use_proxy=False, hw_size=(pw, ph))
    vf = (pre + "," if pre else "") + "scale=%d:%d,setsar=1,format=yuv420p" % (pw, ph)
    fps = "%d/%d" % (m["rate_num"], m["rate_den"])
    gop = max(6, int(round(m["fps"] / 2)))
    cmd = (["ffmpeg", "-v", "error", "-y"] + args +
           ["-vf", vf, "-r", fps, "-fps_mode", "cfr",
            "-c:v", "h264_videotoolbox", "-b:v", "3M", "-g", str(gop),
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000",
            "-movflags", "+faststart", dst + ".tmp.mp4"])
    run(cmd)
    os.replace(dst + ".tmp.mp4", dst)
    return True


def _build_audio(m):
    d = clip_dir(m["id"])
    dst = os.path.join(d, "audio.wav")
    if os.path.exists(dst) or not m.get("has_audio"):
        return False
    src = os.path.join(d, "proxy.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1",
         "-ar", "16000", "-c:a", "pcm_s16le", dst + ".tmp.wav"])
    os.replace(dst + ".tmp.wav", dst)
    return True


def _collect(paths):
    files = []
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        if os.path.isdir(p):
            for base, dirs, names in os.walk(p):
                dirs[:] = [x for x in dirs if not x.startswith(".")]
                for n in sorted(names):
                    if n.lower().endswith(VIDEO_EXT + IMAGE_EXT) and not n.startswith("."):
                        files.append(os.path.join(base, n))
        elif os.path.isfile(p):
            files.append(p)
        else:
            raise Fail("not found: %s" % p)
    return files


def _register(path, brand):
    fp = fingerprint(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}[_ -]+", "", stem)   # drop a leading date
    cid = "%s-%s" % (slug(stem, 44), fp[:6])
    mp = os.path.join(clip_dir(cid), "meta.json")
    old = load_json(mp)
    if old:
        if old.get("src") != path or old.get("brand") != brand:
            old["src"], old["brand"] = path, brand
            save_json(mp, old)
        return old, False
    is_img = path.lower().endswith(IMAGE_EXT)
    m = {"id": cid, "brand": brand, "src": path,
         "name": os.path.basename(path), "fingerprint": fp,
         "kind": "image" if is_img else "video", "added": int(time.time())}
    if is_img:
        w, h = P.image_size(path)
        m.update({"width": w, "height": h, "duration": 0, "fps": 30.0,
                  "rate_num": 30, "rate_den": 1, "has_audio": False,
                  "hdr": False, "rotation": 0})
    else:
        m.update(P.probe(path))
    save_json(mp, m)
    return m, True


def ingest(paths, brand, workers=3, quiet=False):
    files = _collect(paths)
    if not files:
        raise Fail("no video or image files found")
    with Timer("register %d files" % len(files), quiet=quiet):
        metas = [_register(f, brand) for f in files]

    def work(pair):
        m, _ = pair
        if m["kind"] != "video":
            return m, False
        made = _build_proxy(m)
        _build_audio(m)
        return m, made

    with Timer("proxies", quiet=quiet):
        with ThreadPoolExecutor(max_workers=workers) as ex:
            done = list(ex.map(work, metas))
    new = sum(1 for _, made in done if made)
    for m, made in ([] if quiet else done):
        tag = "new " if made else "have"
        extra = " HDR>SDR" if m.get("hdr") else ""
        out("  %s  %-36s %5.1fs %dx%d %.4gfps%s" % (
            tag, m["id"], m.get("duration", 0), m["width"], m["height"],
            m["fps"], extra))
    if not quiet:
        out("%d clips, %d newly processed" % (len(done), new))
    return [m for m, _ in done]


def frame(m, t, dst, full=True):
    """One upright SDR still from a clip."""
    args, pre = source_args(m, ss=t, use_proxy=not full)
    vf = (pre + "," if pre else "") + "format=rgb24"
    run(["ffmpeg", "-v", "error", "-y"] + args +
        ["-vf", vf, "-frames:v", "1", dst])
    return dst


def sheet(m, dst, start=0.0, end=None, cols=5, rows=4, width=1600):
    """Contact sheet so a clip can be read at a glance without playing it."""
    end = min(end or m["duration"], m["duration"])
    n = cols * rows
    step = max((end - start) / float(n), 0.04)
    tw = width // cols
    args, _ = source_args(m, ss=start, t=end - start)
    run(["ffmpeg", "-v", "error", "-y"] + args +
        ["-vf", "fps=1/%.5f,scale=%d:-2,tile=%dx%d:padding=4:margin=4" % (step, tw, cols, rows),
         "-frames:v", "1", dst])
    times = [round(start + i * step, 2) for i in range(n)]
    return dst, times, step
