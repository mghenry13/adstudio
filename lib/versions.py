"""Version history for an ad: every kept draft, what changed, and feedback.

ads/<brand>/<ad>/versions/
  history.json     the record (in git)
  vN.json          the timeline that produced version N (in git)
  vN-<aspect>.mp4  the draft video (not in git, re-renderable from vN.json)

The change list is computed by comparing timelines, so it reports what
actually changed rather than what someone remembers changing.
"""

import os
import shutil
import time

from . import timeline as T
from .util import Fail, load_json, out, rel, save_json


def vdir(ad_dir):
    return os.path.join(ad_dir, "versions")


def history(ad_dir):
    return load_json(os.path.join(vdir(ad_dir), "history.json"),
                     {"versions": []}) or {"versions": []}


def _save(ad_dir, h):
    save_json(os.path.join(vdir(ad_dir), "history.json"), h)


def _seg_label(s):
    if "clip" in s:
        return "clip %s" % s["clip"][:32]
    if "image" in s:
        return "image %s" % os.path.basename(s["image"])
    return "%s card" % s.get("color", "colour")


def _ov_label(o):
    if o.get("text"):
        return '"%s"' % o["text"].replace("\n", " ")
    return "animation %s" % o["gfx"] if o.get("gfx") else "image %s" % os.path.basename(
        o.get("image") or o.get("video") or "overlay")


WORDS = {"in": "starts at", "out": "ends at", "dur": "length", "size": "text size",
         "pos": "position", "gain_db": "volume (dB)", "at": "enters at",
         "max_words": "words per caption", "fit": "framing", "seg": "segment"}


def _fields(a, b, names):
    res = []
    for n in names:
        if a.get(n) != b.get(n):
            res.append("%s %s (was %s)" % (WORDS.get(n, n), _fmt(b.get(n)), _fmt(a.get(n))))
    return res


def _fmt(v):
    if v is None:
        return "default"
    if isinstance(v, float):
        return ("%.2f" % v).rstrip("0").rstrip(".")
    return str(v).replace("\n", " ")


def diff(old, new):
    """Plain-language list of differences between two timelines."""
    if not old:
        return ["First version"]
    ch = []
    so, sn = old.get("segments", []), new.get("segments", [])
    for i in range(max(len(so), len(sn))):
        if i >= len(so):
            ch.append("Added segment %d: %s" % (i + 1, _seg_label(sn[i])))
        elif i >= len(sn):
            ch.append("Removed segment %d: %s" % (i + 1, _seg_label(so[i])))
        elif _seg_label(so[i]) != _seg_label(sn[i]):
            ch.append("Segment %d is now %s (was %s)" % (i + 1, _seg_label(sn[i]),
                                                         _seg_label(so[i])))
        else:
            f = _fields(so[i], sn[i], ["in", "out", "dur", "speed", "volume",
                                       "focus", "zoom", "fit", "captions"])
            if f:
                ch.append("Segment %d (%s): %s" % (i + 1, _seg_label(sn[i]), ", ".join(f)))
    oo = dict((_ov_label(o), o) for o in old.get("overlays") or [])
    on = dict((_ov_label(o), o) for o in new.get("overlays") or [])
    gone = [k for k in oo if k not in on]
    came = [k for k in on if k not in oo]
    # A removed and an added overlay in the same slot read better as an edit.
    for k in list(came):
        twin = next((g for g in gone if oo[g].get("seg") == on[k].get("seg")
                     and oo[g].get("pos") == on[k].get("pos")
                     and oo[g].get("style") == on[k].get("style")), None)
        if twin:
            ch.append("Text changed: %s to %s" % (twin, k))
            gone.remove(twin)
            came.remove(k)
    ch += ["Added overlay %s" % k for k in came]
    ch += ["Removed overlay %s" % k for k in gone]
    for k in on:
        if k in oo:
            f = _fields(oo[k], on[k], ["style", "pos", "size", "start", "end", "seg",
                                       "fade", "align", "color", "bg", "y", "width"])
            if f:
                ch.append("Overlay %s: %s" % (k, ", ".join(f)))
    for key, label in (("captions", "Captions"), ("music", "Music")):
        a, b = old.get(key), new.get(key)
        if a != b:
            if not a:
                ch.append("%s turned on" % label)
            elif not b:
                ch.append("%s turned off" % label)
            else:
                ch.append("%s: %s" % (label, ", ".join(_fields(a, b, sorted(set(a) | set(b))))))
    xa = [(s["file"], s.get("at"), s.get("gain_db")) for s in old.get("sfx") or []]
    xb = [(s["file"], s.get("at"), s.get("gain_db")) for s in new.get("sfx") or []]
    for s in xb:
        if s not in xa:
            ch.append("Sound effect %s at %ss" % (os.path.basename(s[0]), _fmt(s[1])))
    for s in xa:
        if s not in xb:
            ch.append("Removed sound effect %s at %ss" % (os.path.basename(s[0]), _fmt(s[1])))
    f = _fields(old, new, ["fps", "aspects"])
    if f:
        ch.append("Settings: " + ", ".join(f))
    return ch or ["No changes to the edit"]


def snapshot(ad_dir, note=""):
    """Keep the current drafts as the next version."""
    from . import render
    tl = T.load(ad_dir)
    h = history(ad_dir)
    prev = h["versions"][-1] if h["versions"] else None
    prev_tl = load_json(os.path.join(vdir(ad_dir), "v%d.json" % prev["n"])) if prev else None
    changes = diff(prev_tl, tl)
    if prev and changes == ["No changes to the edit"]:
        raise Fail("nothing changed since v%d; no new version made" % prev["n"])
    results = render.render_ad(ad_dir, mode="draft", aspects="all", page=False)
    n = (prev["n"] + 1) if prev else 1
    os.makedirs(vdir(ad_dir), exist_ok=True)
    files = {}
    for r in results:
        name = "v%d-%s.mp4" % (n, r["aspect"].replace(":", "x"))
        shutil.copyfile(r["file"], os.path.join(vdir(ad_dir), name))
        files[r["aspect"]] = name
    save_json(os.path.join(vdir(ad_dir), "v%d.json" % n), tl)
    addressed = None
    if prev:
        for fb in prev.get("feedback", []):
            if fb.get("status") == "requested":
                fb["status"], fb["done_in"] = "done", n
                addressed = fb["text"]
    h["versions"].append({"n": n, "at": int(time.time()), "note": note,
                          "seconds": results[0]["secs"], "files": files,
                          "changes": changes, "answers": addressed, "feedback": []})
    _save(ad_dir, h)
    render.write_preview_page(ad_dir, tl)
    out("saved v%d of %s" % (n, rel(ad_dir)))
    for c in changes:
        out("  - " + c)
    return n


def add_feedback(ad_dir, n, text, redo=True):
    h = history(ad_dir)
    v = next((x for x in h["versions"] if x["n"] == int(n)), None)
    if not v:
        raise Fail("no version %s" % n)
    v.setdefault("feedback", []).append(
        {"text": text.strip(), "at": int(time.time()),
         "status": "requested" if redo else "note"})
    _save(ad_dir, h)
    from . import render
    render.write_preview_page(ad_dir, T.load(ad_dir))
    return v


def pending(ad_dir):
    """Feedback with Redo pressed that no later version has answered."""
    res = []
    for v in history(ad_dir)["versions"]:
        for fb in v.get("feedback", []):
            if fb.get("status") == "requested":
                res.append({"version": v["n"], "text": fb["text"]})
    return res


def restore(ad_dir, n):
    src = os.path.join(vdir(ad_dir), "v%d.json" % int(n))
    tl = load_json(src)
    if not tl:
        raise Fail("no saved timeline for v%s" % n)
    save_json(os.path.join(ad_dir, "timeline.json"), tl)
    out("timeline.json is now the v%s edit (snapshot to keep it as a new version)" % n)
