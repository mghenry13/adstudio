"""timeline.json: the whole edit as data. See docs/TIMELINE.md for the schema.

resolve() turns a timeline into frame-exact segments and absolute-time
overlays. The renderer and the Premiere exporter both read that one result,
so a preview and its XML can never disagree about where a cut is.
"""

import os

from . import media, transcribe
from .util import ADS, BRANDS, Fail, load_json, resolve as rpath, save_json

ASPECTS = {"9:16": (1080, 1920), "4:5": (1080, 1350),
           "1:1": (1080, 1080), "16:9": (1920, 1080)}


def create(brand, ad):
    if not os.path.isdir(os.path.join(BRANDS, brand)):
        raise Fail("unknown brand '%s' (adstudio brand list)" % brand)
    d = os.path.join(ADS, brand, ad)
    p = os.path.join(d, "timeline.json")
    if os.path.exists(p):
        raise Fail("%s already exists" % p)
    save_json(p, {"version": 1, "brand": brand, "name": ad, "fps": 30,
                  "aspects": ["9:16"], "segments": [], "overlays": [],
                  "captions": None, "music": None, "sfx": []})
    return d


def load(ad_dir):
    tl = load_json(os.path.join(ad_dir, "timeline.json"))
    if not tl:
        raise Fail("timeline.json in %s is missing or not valid JSON" % ad_dir)
    return tl


def aspects_for(tl, arg):
    if arg in (None, ""):
        return [tl.get("aspects", ["9:16"])[0]]
    if arg == "all":
        return list(tl.get("aspects", ["9:16"]))
    out = [a.strip().replace("x", ":") for a in arg.split(",")]
    for a in out:
        if a not in ASPECTS:
            raise Fail("unknown aspect '%s' (have %s)" % (a, ", ".join(ASPECTS)))
    return out


def _focus(seg, aspect):
    f = (seg.get("focus_by_aspect") or {}).get(aspect) or seg.get("focus") or [0.5, 0.5]
    return [min(1.0, max(0.0, float(f[0]))), min(1.0, max(0.0, float(f[1])))]


def resolve(ad_dir, aspect):
    tl = load(ad_dir)
    fps = int(tl.get("fps", 30))
    brand = tl.get("brand")
    if not brand or not os.path.isdir(os.path.join(BRANDS, brand)):
        raise Fail("timeline has no valid 'brand'")
    if not tl.get("segments"):
        raise Fail("timeline has no segments yet")
    segs, pos = [], 0
    for i, s in enumerate(tl["segments"]):
        seg = dict(s)
        seg["index"] = i
        if "clip" in s:
            m = media.find(s["clip"])
            seg["meta"], seg["type"] = m, "clip"
            if m["kind"] == "image":
                seg["type"] = "image"
                dur = float(s.get("dur", 2.0))
            else:
                a, b = float(s.get("in", 0)), float(s.get("out", m["duration"]))
                if not (0 <= a < b <= m["duration"] + 0.05):
                    raise Fail("segment %d: in/out %.2f-%.2f outside clip (%.2fs)"
                               % (i, a, b, m["duration"]))
                seg["in"], seg["out"] = a, b
                seg["speed"] = float(s.get("speed", 1.0))
                if not 0.25 <= seg["speed"] <= 4:
                    raise Fail("segment %d: speed must be 0.25 to 4" % i)
                dur = (b - a) / seg["speed"]
        elif "image" in s:
            p = rpath(s["image"], ad_dir)
            if not os.path.exists(p):
                raise Fail("segment %d: image not found: %s" % (i, s["image"]))
            seg["type"], seg["path"] = "image", p
            dur = float(s.get("dur", 2.0))
        elif "color" in s:
            seg["type"] = "color"
            dur = float(s.get("dur", 2.0))
        else:
            raise Fail("segment %d needs 'clip', 'image' or 'color'" % i)
        seg["frames"] = max(1, int(round(dur * fps)))
        seg["start_f"] = pos
        seg["start"] = pos / float(fps)
        seg["dur"] = seg["frames"] / float(fps)
        seg["focus"] = _focus(s, aspect)
        seg["volume"] = float(s.get("volume", 1.0 if seg["type"] == "clip" else 0))
        pos += seg["frames"]
        segs.append(seg)
    total = pos / float(fps)

    caps = sorted(_captions(tl, segs) + _vo_captions(tl, ad_dir, pos / float(fps)),
                  key=lambda c: c["start"])
    for a0, b0 in (tl.get("captions") or {}).get("skip") or []:   # caption-free moments
        kept = []
        for c in caps:
            if c["end"] <= a0 or c["start"] >= b0:
                kept.append(c)
            elif c["start"] < a0 - 0.12:       # started before: just end it early
                kept.append(dict(c, end=a0))
        caps = kept
    for c, nxt in zip(caps, caps[1:]):     # one caption on screen at a time
        if c["end"] > nxt["start"]:
            c["end"] = nxt["start"]
    overlays = []
    for j, o in enumerate(list(tl.get("overlays") or []) + caps):
        if o.get("aspects") and aspect not in o["aspects"]:
            continue
        ov = dict(o)
        if "seg" in o:                 # times relative to one segment
            if not 0 <= int(o["seg"]) < len(segs):
                raise Fail("overlay %d: seg %s does not exist" % (j, o["seg"]))
            sg = segs[int(o["seg"])]
            ov["start"] = sg["start"] + float(o.get("start", 0))
            ov["end"] = sg["start"] + float(o.get("end", sg["dur"]))
            ov["end"] = min(ov["end"], sg["start"] + sg["dur"])
        else:
            ov["start"] = float(o.get("start", 0))
            ov["end"] = min(float(o.get("end", total)), total)
        if ov["end"] <= ov["start"]:
            continue
        ov["fade"] = float(o.get("fade", 0.12 if not o.get("_caption") else 0))
        for k in ("fade_in", "fade_out"):      # one side only, e.g. a fade to black
            if k in o:
                ov[k] = float(o[k])
        if o.get("gfx"):
            ov["video"] = os.path.join(ad_dir, "gfx", o["gfx"], "render-%s.mov"
                                       % aspect.replace(":", "x"))
            if not os.path.exists(ov["video"]):
                raise Fail("gfx '%s' not rendered for %s (run: adstudio gfx ...)"
                           % (o["gfx"], aspect))
        elif o.get("video"):
            ov["video"] = rpath(o["video"], ad_dir)
        overlays.append(ov)

    for key in ("music",):
        mu = tl.get(key)
        if mu and not os.path.exists(rpath(mu["file"], ad_dir)):
            raise Fail("music file not found: %s" % mu["file"])
    for s in tl.get("sfx") or []:
        if not os.path.exists(rpath(s["file"], ad_dir)):
            raise Fail("sfx file not found: %s" % s["file"])
    for i, v in enumerate(tl.get("vo") or []):
        if not v.get("file") or not os.path.exists(rpath(v["file"], ad_dir)):
            raise Fail("vo line %d has no audio yet (run: adstudio voice <brand>/<ad>)" % i)
    return {"tl": tl, "dir": ad_dir, "brand": brand, "fps": fps, "aspect": aspect,
            "segs": segs, "overlays": overlays, "total_f": pos, "total": total}


def _chunk(ws, max_words, max_chars):
    chunks, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        text_len = sum(len(x["w"]) for x in cur) + len(cur) - 1
        if (nxt is None or len(cur) >= max_words or w["w"][-1:] in ".?!,"
                or nxt["start"] - w["end"] > 0.45
                or text_len + 1 + len(nxt["w"]) > max_chars):
            chunks.append(cur)
            cur = []
    return chunks


def _emit(out, cfg, ch, a, b, to_tl):
    """One caption chunk. `build: true` reveals it word by word; `emphasis` words get *em*."""
    emph = set(w.lower().strip(".,?!") for w in cfg.get("emphasis") or [])

    def fmt(ws):
        parts = []
        for x in ws:
            w = x["w"]
            core = w.strip(".,?!")
            if core.lower() in emph:
                w = w.replace(core, "*%s*" % core)
            parts.append(w)
        text = " ".join(parts).rstrip(".,")
        return text.upper() if cfg.get("upper") else text

    base = {"style": cfg.get("style", "caption"), "pos": cfg.get("pos", "caption"),
            "size": cfg.get("size", 1), "_caption": True}
    if cfg.get("track"):
        base["track"] = cfg["track"]
    # a chunk that is just one of these words shows the image instead (a logo for a name)
    imgs = dict((k.lower(), v) for k, v in (cfg.get("word_images") or {}).items())
    key = lambda w: w["w"].strip(".,?!").lower()
    if len(ch) > 1 and any(key(w) in imgs for w in ch):
        parts, cur = [], []            # give each image word its own moment on screen
        for w in ch:
            if key(w) in imgs:
                if cur:
                    parts.append(cur)
                parts.append([w])
                cur = []
            else:
                cur.append(w)
        if cur:
            parts.append(cur)
        for i, part in enumerate(parts):
            pa = a if i == 0 else max(a, to_tl(part[0]["start"]))
            pb = b if i + 1 == len(parts) else max(pa + 0.04, to_tl(parts[i + 1][0]["start"]))
            _emit(out, cfg, part, pa, min(pb, b), to_tl)
        return
    if len(ch) == 1 and ch[0]["w"].strip(".,?!").lower() in imgs:
        spec = imgs[ch[0]["w"].strip(".,?!").lower()]
        if isinstance(spec, str):
            spec = {"image": spec}
        out.append(dict(spec, pos=spec.get("pos", base["pos"]), width=spec.get("width", 0.5),
                        start=a, end=b, _caption=True, fade=0))
        return
    if not cfg.get("build"):
        out.append(dict(base, text=fmt(ch), start=a, end=b))
        return
    for i in range(len(ch)):
        s0 = a if i == 0 else max(a, to_tl(ch[i]["start"]))
        e0 = b if i + 1 == len(ch) else max(s0 + 0.04, to_tl(ch[i + 1]["start"]))
        out.append(dict(base, text=fmt(ch[:i + 1]), start=s0, end=min(e0, b)))


def _vo_captions(tl, ad_dir, total):
    """Captions for voiceover lines, from the word timings `adstudio voice` saves."""
    from . import voice
    cfg = tl.get("captions")
    if not cfg:
        return []
    out = []
    for v in tl.get("vo") or []:
        if v.get("captions") is False or not v.get("file"):
            continue
        at = float(v.get("at", 0))
        ws = voice.words(rpath(v["file"], ad_dir), v.get("caption") or v.get("text"))
        line_cfg = dict(cfg, word_images=None) if v.get("word_images") is False else cfg
        chunks = _chunk(ws, int(cfg.get("max_words", 3)), int(cfg.get("max_chars", 18)))
        for k, ch in enumerate(chunks):
            a = at + ch[0]["start"]
            if k + 1 < len(chunks) and chunks[k + 1][0]["start"] - ch[-1]["end"] < 0.45:
                b = at + chunks[k + 1][0]["start"]
            else:
                b = at + ch[-1]["end"] + 0.18
            _emit(out, line_cfg, ch, a, min(b, total), lambda t, at=at: at + t)
    return out


def _captions(tl, segs):
    """Auto captions from the transcript of every clip segment that has sound."""
    cfg = tl.get("captions")
    if not cfg:
        return []
    max_words = int(cfg.get("max_words", 3))
    max_chars = int(cfg.get("max_chars", 18))
    upper = bool(cfg.get("upper", False))
    out = []
    for seg in segs:
        if seg["type"] != "clip" or seg["volume"] <= 0 or seg.get("captions") is False:
            continue
        ws = [w for w in transcribe.words(seg["meta"]["id"])
              if w["start"] >= seg["in"] - 0.06 and w["end"] <= seg["out"] + 0.12]
        chunks, cur = [], []
        for i, w in enumerate(ws):
            cur.append(w)
            nxt = ws[i + 1] if i + 1 < len(ws) else None
            text_len = sum(len(x["w"]) for x in cur) + len(cur) - 1
            brk = (nxt is None or len(cur) >= max_words
                   or w["w"][-1:] in ".?!,"
                   or nxt["start"] - w["end"] > 0.45
                   or text_len + 1 + len(nxt["w"]) > max_chars)
            if brk:
                chunks.append(cur)
                cur = []
        for k, ch in enumerate(chunks):
            to_tl = lambda t: seg["start"] + (t - seg["in"]) / seg["speed"]
            a = max(seg["start"], to_tl(ch[0]["start"]))
            if k + 1 < len(chunks) and chunks[k + 1][0]["start"] - ch[-1]["end"] < 0.45:
                b = to_tl(chunks[k + 1][0]["start"])     # hold until the next one
            else:
                b = to_tl(ch[-1]["end"]) + 0.18
            b = min(b, seg["start"] + seg["dur"])
            _emit(out, cfg, ch, a, b, to_tl)
    return out
