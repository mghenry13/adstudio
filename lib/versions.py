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
    # Line the two cuts up by clip, so one inserted or removed shot is
    # reported as exactly that instead of renumbering everything after it.
    import difflib
    la, lb = [_seg_label(x) for x in so], [_seg_label(x) for x in sn]
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, la, lb, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                f = _fields(so[i1 + k], sn[j1 + k], ["in", "out", "dur", "speed", "volume",
                                                     "focus", "zoom", "fit", "captions"])
                if f:
                    ch.append("Segment %d (%s): %s" % (j1 + k + 1, lb[j1 + k], ", ".join(f)))
            continue
        gone, came = la[i1:i2], lb[j1:j2]
        if op == "replace" and len(gone) == len(came):
            for k in range(len(came)):
                ch.append("Segment %d is now %s (was %s)" % (j1 + k + 1, came[k], gone[k]))
            continue
        for k, name in enumerate(came):
            ch.append("Added %s as segment %d" % (name, j1 + k + 1))
        for name in gone:
            ch.append("Removed %s" % name)
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


def waiting_comments(ad_dir):
    """Comments sent with Redo that no version has answered yet (the real records)."""
    res = []
    for v in history(ad_dir)["versions"]:
        for fb in v.get("feedback", []):
            if fb.get("status") == "requested":
                res.append(fb)
    return res


def _label(fb):
    return ("%s  " % tc(fb["t"]) if fb.get("t") is not None else "Whole video  ") + fb["text"]


def snapshot(ad_dir, note="", done=None):
    """Keep the current drafts as the next version.

    Every comment sent with Redo has to be accounted for: `done` lists the
    numbers (from `adstudio todo`) this version answers, or "all". Anything
    not listed stays waiting and moves to the new version, so a comment can
    never be marked done just because a version was saved."""
    waiting = waiting_comments(ad_dir)
    if waiting and done is None:
        raise Fail("%d comment%s waiting. Say which ones this version answers with "
                   "--done 1,2 (or --done all), then re-run:\n%s" % (
                       len(waiting), "s" if len(waiting) > 1 else "",
                       "\n".join("  %d. %s" % (i + 1, _label(f)) for i, f in enumerate(waiting))))
    if done == "all":
        done_set = set(range(1, len(waiting) + 1))
    else:
        done_set = set(int(x) for x in str(done or "").split(",") if x.strip())
        bad = [x for x in done_set if not 1 <= x <= len(waiting)]
        if bad:
            raise Fail("no waiting comment numbered %s (there are %d)" % (bad, len(waiting)))
    answered = set((waiting[i - 1].get("at"), waiting[i - 1]["text"]) for i in done_set)
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
    addressed, carried = None, []
    if prev:
        got = []
        for v in h["versions"]:
            for fb in v.get("feedback", []):
                if fb.get("status") == "requested" and (fb.get("at"), fb["text"]) in answered:
                    fb["status"], fb["done_in"] = "done", n
                    got.append(_label(fb))
        addressed = "\n".join(got) or None
        # Comments written but not yet sent must never be stranded on an old
        # version: they move to the new one, still unsent, still editable.
        carried = [f for f in prev.get("feedback", []) if f.get("status") in ("open", "note")]
        prev["feedback"] = [f for f in prev.get("feedback", []) if f not in carried]
        for f in carried:
            f["status"] = "open"
            f.setdefault("from", prev["n"])
    h["versions"].append({"n": n, "at": int(time.time()), "note": note,
                          "seconds": results[0]["secs"], "files": files,
                          "changes": changes, "answers": addressed,
                          "feedback": carried if prev else []})
    _save(ad_dir, h)
    render.write_preview_page(ad_dir, tl)
    out("saved v%d of %s" % (n, rel(ad_dir)))
    for c in changes:
        out("  - " + c)
    left = waiting_comments(ad_dir)
    if left:
        out("STILL WAITING (%d), not done yet:" % len(left))
        for i, f in enumerate(left):
            out("  %d. %s" % (i + 1, _label(f)))
    return n


def tc(t):
    """Seconds as m:ss.t, the way a comment's timecode is shown."""
    t = max(0.0, float(t))
    return "%d:%04.1f" % (int(t // 60), t % 60)


def add_feedback(ad_dir, n, text, redo=True, t=None, delete=None):
    """Comments collect as "open" (optionally pinned to a time in the video).
    Redo sends every open comment on that version to Claude at once."""
    h = history(ad_dir)
    v = next((x for x in h["versions"] if x["n"] == int(n)), None)
    if not v:
        raise Fail("no version %s" % n)
    fbs = v.setdefault("feedback", [])
    if delete is not None:
        fbs[:] = [f for f in fbs if not (f["at"] == delete and f["status"] == "open")]
    if text and text.strip():
        fb = {"text": text.strip(), "at": int(time.time() * 1000), "status": "open"}
        if t is not None:
            fb["t"] = round(max(0.0, min(float(t), v.get("seconds", 1e9))), 2)
        fbs.append(fb)
        v["_added"] = fb["at"]
    if redo:
        for f in fbs:
            if f["status"] in ("open", "note"):
                f["status"] = "requested"
    added = v.pop("_added", None)
    _save(ad_dir, h)
    from . import render
    render.write_preview_page(ad_dir, T.load(ad_dir))
    return added


def pending(ad_dir):
    """Feedback with Redo pressed that no later version has answered."""
    res = []
    for v in history(ad_dir)["versions"]:
        for fb in v.get("feedback", []):
            if fb.get("status") == "requested":
                res.append({"version": v["n"], "text": fb["text"], "t": fb.get("t")})
    res.sort(key=lambda r: (r["version"], r["t"] if r["t"] is not None else -1))
    return res


def where(ad_dir, n, t):
    """What is on screen at time t of version n, from that version's timeline."""
    tl = load_json(os.path.join(vdir(ad_dir), "v%d.json" % n))
    if not tl:
        return ""
    fps, pos = float(tl.get("fps", 30)), 0.0
    for i, s in enumerate(tl.get("segments", [])):
        if "clip" in s and "in" in s and "out" in s:
            d = (float(s["out"]) - float(s["in"])) / float(s.get("speed", 1) or 1)
        else:
            d = float(s.get("dur", 2.0))
        d = max(1, round(d * fps)) / fps
        if t < pos + d or i == len(tl["segments"]) - 1:
            src = ""
            if "clip" in s and "in" in s:
                src = ", source time %.2fs" % (float(s["in"]) + (t - pos) * float(s.get("speed", 1) or 1))
            return "segment %d (index %d, %s), %.2fs into it%s" % (
                i + 1, i, _seg_label(s), t - pos, src)
        pos += d
    return ""


def restore(ad_dir, n):
    src = os.path.join(vdir(ad_dir), "v%d.json" % int(n))
    tl = load_json(src)
    if not tl:
        raise Fail("no saved timeline for v%s" % n)
    save_json(os.path.join(ad_dir, "timeline.json"), tl)
    out("timeline.json is now the v%s edit (snapshot to keep it as a new version)" % n)
