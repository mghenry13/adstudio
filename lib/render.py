"""Timeline to MP4.

Speed comes from three choices:
  1. Each segment renders to its own video-only file, cached by a hash of
     everything that affects its pixels. Editing one caption re-renders one
     segment; the rest are reused.
  2. Segments are joined with stream copy, so the join costs nothing.
  3. Audio for the whole ad is mixed in the same ffmpeg call that does the
     join. It is cheap, and mixing in one pass avoids clicks at the cuts.
Drafts cut from 720p SDR proxies at half size; finals read the originals.
"""

import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import media, overlay
from . import timeline as T
from .util import (BRANDS, RCACHE, Fail, Timer, config, file_sig, out, rel,
                   resolve, run, save_json, sha)

RENDER_VERSION = 4
EPS = 1e-4


def out_size(aspect, mode):
    W, H = T.ASPECTS[aspect]
    if mode == "draft":
        W, H = W // 2, H // 2
    return W - W % 2, H - H % 2


def brand_color(brand, value):
    """Accept '#rrggbb' or the name of a color variable from brand.css."""
    if re.match(r"^#[0-9a-fA-F]{6}$", value or ""):
        return value
    try:
        css = open(os.path.join(BRANDS, brand, "brand.css")).read()
    except IOError:
        css = ""
    m = re.search(r"--%s\s*:\s*(#[0-9a-fA-F]{6})" % re.escape(value or ""), css)
    if not m:
        raise Fail("color '%s' is not #rrggbb or a color in %s/brand.css" % (value, brand))
    return m.group(1)


def crop_fracs(sw, sh, W, H, seg):
    """Cover-fit crop as fractions of the source, centred on the focus point."""
    ar, sar = W / float(H), sw / float(sh)
    zoom = max(1.0, float(seg.get("zoom", 1.0)))
    if sar > ar:
        ch, cw = 1.0 / zoom, (ar / sar) / zoom
    else:
        cw, ch = 1.0 / zoom, (sar / ar) / zoom
    fx, fy = seg["focus"]
    cx = min(max(fx - cw / 2, 0.0), 1.0 - cw)
    cy = min(max(fy - ch / 2, 0.0), 1.0 - ch)
    return cw, ch, cx, cy


def _fit(seg, sw, sh, W, H):
    if seg.get("fit") == "contain":
        blur = max(4, W // 40)
        return ("split[fa][fb];[fa]scale=%d:%d:force_original_aspect_ratio=increase,"
                "crop=%d:%d,boxblur=%d:2[fbg];[fb]scale=%d:%d:"
                "force_original_aspect_ratio=decrease[ffg];"
                "[fbg][ffg]overlay=(W-w)/2:(H-h)/2,setsar=1"
                % (W, H, W, H, blur, W, H))
    cw, ch, cx, cy = crop_fracs(sw, sh, W, H, seg)
    return ("crop=iw*%.6f:ih*%.6f:iw*%.6f:ih*%.6f,scale=%d:%d:flags=bicubic,setsar=1"
            % (cw, ch, cx, cy, W, H))


def _slices(seg, overlays):
    """The parts of each overlay that fall inside this segment, in local time."""
    s, e = seg["start"], seg["start"] + seg["dur"]
    res = []
    for ov in overlays:
        if ov["start"] >= e - EPS or ov["end"] <= s + EPS:
            continue
        a, b = max(ov["start"], s) - s, min(ov["end"], e) - s
        f = ov.get("fade", 0)
        res.append({"ov": ov, "a": round(a, 4), "b": round(b, 4),
                    "fi": ov.get("fade_in", f) if ov["start"] >= s - EPS else 0,
                    "fo": ov.get("fade_out", f) if ov["end"] <= e + EPS else 0,
                    "off": round(max(0.0, s - ov["start"]), 4)})
    return res


def _seg_key(seg, R, W, H, mode, slices):
    spec = {"v": RENDER_VERSION, "mode": mode, "W": W, "H": H, "fps": R["fps"],
            "type": seg["type"], "frames": seg["frames"], "focus": seg["focus"],
            "zoom": seg.get("zoom", 1), "fit": seg.get("fit", "cover")}
    if seg["type"] == "clip":
        spec.update(fp=seg["meta"]["fingerprint"], a=seg["in"], b=seg["out"],
                    speed=seg["speed"])
    elif seg["type"] == "image":
        p = seg.get("path") or seg["meta"]["src"]
        spec.update(img=file_sig(p))
    else:
        spec.update(color=brand_color(R["brand"], seg["color"]))
    spec["ov"] = [[sl["ov"].get("key") or file_sig(sl["ov"]["video"]),
                   sl["a"], sl["b"], sl["fi"], sl["fo"], sl["off"], sl["ov"].get("track")]
                  for sl in slices]
    return sha(spec)[:24]


def _encoder(mode, W, H, fps):
    rate = "2500k" if mode == "draft" else ("16M" if max(W, H) >= 1920 else "10M")
    return ["-c:v", "h264_videotoolbox", "-b:v", rate, "-profile:v", "high",
            "-g", str(fps), "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-colorspace", "bt709"]


def _render_segment(seg, R, W, H, mode, slices, dst):
    fps, n, dur = R["fps"], seg["frames"], seg["dur"]
    if seg["type"] == "clip":
        m = seg["meta"]
        span = seg["out"] - seg["in"]
        hw = None
        if mode == "final" and m.get("hdr"):
            cw, ch, _, _ = crop_fracs(m["width"], m["height"], W, H, seg)
            k = min(1.0, max(W / (cw * m["width"]), H / (ch * m["height"])))
            hw = (int(math.ceil(m["width"] * k / 2) * 2), int(math.ceil(m["height"] * k / 2) * 2))
        args, pre = media.source_args(m, ss=seg["in"], t=span + 0.5,
                                      use_proxy=(mode == "draft"), hw_size=hw)
        chain = [pre] if pre else []
        if seg["speed"] != 1.0:
            chain.append("setpts=PTS/%.5f" % seg["speed"])
        chain.append(_fit(seg, m["width"], m["height"], W, H))
    elif seg["type"] == "image":
        p = seg.get("path") or seg["meta"]["src"]
        from .probe import image_size
        iw, ih = image_size(p)
        args = ["-loop", "1", "-framerate", str(fps), "-t", "%.3f" % (dur + 0.5), "-i", p]
        chain = [_fit(seg, iw, ih, W, H)]
    else:
        col = brand_color(R["brand"], seg["color"]).replace("#", "0x")
        args = ["-f", "lavfi", "-i", "color=c=%s:s=%dx%d:r=%d:d=%.3f" % (col, W, H, fps, dur + 0.5)]
        chain = []
    chain += ["fps=%d" % fps, "tpad=stop_mode=clone:stop_duration=1", "format=yuv420p"]
    moving = None                      # scene motion for overlays with "track"
    if seg["type"] == "clip" and any(sl["ov"].get("track") for sl in slices):
        from . import track
        m = seg["meta"]
        cw, ch, _, _ = crop_fracs(m["width"], m["height"], W, H, seg)
        moving = (track.motion(m, seg["in"], seg["out"]), W / cw, H / ch, seg["speed"])
    graph = ["[0:v]" + ",".join(chain) + "[b0]"]
    last = "b0"
    for i, sl in enumerate(slices):
        ov, k = sl["ov"], i + 1
        if ov.get("video"):
            args += ["-ss", "%.4f" % sl["off"], "-t", "%.4f" % (sl["b"] - sl["a"] + 0.5),
                     "-i", ov["video"]]
            f = "[%d:v]scale=%d:%d,format=rgba,setpts=PTS-STARTPTS+%.4f/TB" % (k, W, H, sl["a"])
        else:
            args += ["-loop", "1", "-framerate", str(fps), "-t", "%.3f" % (dur + 0.5),
                     "-i", ov["png"]]
            f = "[%d:v]format=rgba" % k
        if sl["fi"] > 0:
            f += ",fade=t=in:st=%.4f:d=%.4f:alpha=1" % (sl["a"], sl["fi"])
        if sl["fo"] > 0:
            f += ",fade=t=out:st=%.4f:d=%.4f:alpha=1" % (max(sl["a"], sl["b"] - sl["fo"]), sl["fo"])
        graph.append(f + "[o%d]" % k)
        xy = "0:0"
        if moving and ov.get("track"):
            from . import track
            pts, sx, sy, sp = moving
            gain = 1.0 if ov["track"] is True else float(ov["track"])
            # at most 9% of the frame width / 5% of its height, so text stays readable
            xy = "x='%s':y='%s'" % (track.expr(pts, sx * gain, "x", sl["a"], sp, 0.09 * W),
                                    track.expr(pts, sy * gain, "y", sl["a"], sp, 0.05 * H))
        graph.append("[%s][o%d]overlay=%s:eof_action=pass:enable='gte(t,%.4f)*lt(t,%.4f)'[b%d]"
                     % (last, k, xy, sl["a"], sl["b"], k))
        last = "b%d" % k
    tmp = dst + ".tmp.mp4"
    run(["ffmpeg", "-v", "error", "-y"] + args +
        ["-filter_complex", ";".join(graph), "-map", "[%s]" % last, "-an",
         "-frames:v", str(n), "-r", str(fps), "-video_track_timescale", "30000"]
        + _encoder(mode, W, H, fps) + [tmp])
    os.replace(tmp, dst)


def _atempo(speed):
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append("atempo=%.5f" % s)
    return ",".join(parts)


def _audio(R, mode):
    """Inputs and filter graph for the full mix. Input 0 is the video."""
    tl, total = R["tl"], R["total"]
    norm = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    args, graph, bus, speech = [], [], [], []
    k = 1
    for seg in R["segs"]:
        if seg["type"] != "clip" or seg["volume"] <= 0 or not seg["meta"].get("has_audio"):
            continue
        m = seg["meta"]
        src = os.path.join(media.clip_dir(m["id"]), "proxy.mp4") if mode == "draft" else m["src"]
        args += ["-ss", "%.4f" % seg["in"], "-t", "%.4f" % (seg["out"] - seg["in"]),
                 "-vn", "-i", src]
        f = "[%d:a]%s" % (k, norm)
        if seg["speed"] != 1.0:
            f += "," + _atempo(seg["speed"])
        f += (",volume=%.3f,afade=t=in:d=0.02,afade=t=out:st=%.4f:d=0.03,"
              "adelay=%d:all=1[s%d]" % (seg["volume"], max(0, seg["dur"] - 0.03),
                                        int(round(seg["start"] * 1000)), k))
        graph.append(f)
        speech.append("[s%d]" % k)
        k += 1
    for v in tl.get("vo") or []:
        args += ["-i", resolve(v["file"], R["dir"])]
        graph.append("[%d:a]%s,volume=%.2fdB,adelay=%d:all=1[s%d]"
                     % (k, norm, float(v.get("gain_db", 0)),
                        int(round(float(v.get("at", 0)) * 1000)), k))
        speech.append("[s%d]" % k)
        k += 1
    mu = tl.get("music")
    duck = bool(mu and mu.get("duck", True) and speech)
    if speech:
        if len(speech) > 1:
            graph.append("%samix=inputs=%d:normalize=0:dropout_transition=0[sp]"
                         % ("".join(speech), len(speech)))
        else:
            graph.append("%sanull[sp]" % speech[0])
        if duck:
            graph.append("[sp]asplit=2[spm][spk]")
            bus.append("[spm]")
        else:
            bus.append("[sp]")
    if mu:
        at = float(mu.get("at", 0))
        length = max(0.1, total - at)
        fo = float(mu.get("fade_out", 0.8))
        if mu.get("loop"):
            args += ["-stream_loop", "-1"]
        args += ["-ss", "%.3f" % float(mu.get("start", 0)), "-i",
                 resolve(mu["file"], R["dir"])]
        f = ("[%d:a]%s,asetpts=N/SR/TB,atrim=0:%.4f,volume=%.2fdB,afade=t=in:d=%.3f,"
             "afade=t=out:st=%.4f:d=%.3f,adelay=%d:all=1[mu]"
             % (k, norm, length, float(mu.get("gain_db", -16)),
                float(mu.get("fade_in", 0.05)), max(0, length - fo), fo,
                int(round(at * 1000))))
        graph.append(f)
        if duck:
            graph.append("[mu][spk]sidechaincompress=threshold=0.02:ratio=%g:"
                         "attack=15:release=350[mud]" % float(mu.get("duck_ratio", 8)))
            bus.append("[mud]")
        else:
            bus.append("[mu]")
        k += 1
    for s in tl.get("sfx") or []:
        args += ["-i", resolve(s["file"], R["dir"])]
        graph.append("[%d:a]%s,volume=%.2fdB,adelay=%d:all=1[x%d]"
                     % (k, norm, float(s.get("gain_db", -6)),
                        int(round(float(s.get("at", 0)) * 1000)), k))
        bus.append("[x%d]" % k)
        k += 1
    if not bus:
        return ["-f", "lavfi", "-t", "%.4f" % total, "-i",
                "anullsrc=r=48000:cl=stereo"], None
    tail = "alimiter=limit=0.94"
    if mode == "final":
        tail = "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000," + tail
    # atrim counts from the stream's own timestamps; reset them to a plain sample
    # clock first, or a seeked or delayed input can leave apad running forever
    graph.append("%samix=inputs=%d:normalize=0:dropout_transition=0,%s,apad,"
                 "asetpts=N/SR/TB,atrim=0:%.4f[aout]" % ("".join(bus), len(bus), tail, total))
    return args, ";".join(graph)


def render_aspect(ad_dir, aspect, mode):
    R = T.resolve(ad_dir, aspect)
    W, H = out_size(aspect, mode)
    os.makedirs(RCACHE, exist_ok=True)
    with Timer("overlays %s" % aspect, quiet=True) as t_ov:
        drawn = overlay.prepare(R["overlays"], R["brand"], aspect, W, H, ad_dir)
    jobs, files = [], []
    for seg in R["segs"]:
        sl = _slices(seg, R["overlays"])
        dst = os.path.join(RCACHE, "seg-%s.mp4" % _seg_key(seg, R, W, H, mode, sl))
        files.append(dst)
        if not os.path.exists(dst):
            jobs.append((seg, sl, dst))
    with Timer("segments %s" % aspect, quiet=True) as t_seg:
        workers = int(config().get("workers", 4))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(lambda j: _render_segment(j[0], R, W, H, mode, j[1], j[2]), jobs))
    name = "%s-%s" % (R["tl"].get("name", os.path.basename(ad_dir)), aspect.replace(":", "x"))
    sub = "previews" if mode == "draft" else "exports"
    dst = os.path.join(ad_dir, sub, name + ".mp4")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    lst = os.path.join(RCACHE, "list-%s.txt" % sha(files)[:16])
    with open(lst, "w") as f:
        f.write("".join("file '%s'\n" % p for p in files))
    with Timer("mix and join %s" % aspect, quiet=True) as t_mux:
        a_args, a_graph = _audio(R, mode)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst] + a_args
        if a_graph:
            cmd += ["-filter_complex", a_graph, "-map", "0:v", "-map", "[aout]"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", "%.4f" % R["total"],
                "-movflags", "+faststart", dst + ".tmp.mp4"]
        run(cmd)
        os.replace(dst + ".tmp.mp4", dst)
    out("  %-5s %dx%d  %5.2fs long  overlays %d drawn %.2fs | segments %d rendered, "
        "%d cached %.2fs | mix %.2fs" % (
            aspect, W, H, R["total"], drawn, t_ov.secs, len(jobs),
            len(files) - len(jobs), t_seg.secs, t_mux.secs))
    return {"aspect": aspect, "file": dst, "w": W, "h": H, "secs": R["total"],
            "rendered": len(jobs), "cached": len(files) - len(jobs)}


def render_ad(ad_dir, mode="draft", aspects=None, page=True):
    tl = T.load(ad_dir)
    results = []
    with Timer("%s %s" % ("preview" if mode == "draft" else "render", tl.get("name", "")),
               quiet=True):
        for a in T.aspects_for(tl, aspects):
            results.append(render_aspect(ad_dir, a, mode))
    for r in results:
        out("  " + rel(r["file"]))
    if page:
        write_preview_page(ad_dir, tl)
    out("  page: http://localhost:%s/%s/preview.html" % (config().get("preview_port", 8787), rel(ad_dir)))
    save_json(os.path.join(ad_dir, "render.json"),
              {"mode": mode, "at": int(time.time()), "results": results})
    return results


def write_preview_page(ad_dir, tl):
    from .page import write
    write(ad_dir, tl)
