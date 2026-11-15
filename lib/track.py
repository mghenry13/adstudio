"""Camera motion of a footage span, so text can move with the scene.

`bin/track` (Swift, Apple Vision image registration) measures how far the
scene has moved since the first frame. Results are cached per clip and span.
Overlays with "track": true (and captions with "track": true) then ride that
motion, piece by piece, inside each segment.
"""

import json
import os
import subprocess

from . import media
from .util import ROOT, Fail, load_json, save_json

BIN = os.path.join(ROOT, "bin", "track")
SRC = os.path.join(ROOT, "helpers", "track", "main.swift")


def build():
    if os.path.exists(BIN) and os.path.getmtime(BIN) >= os.path.getmtime(SRC):
        return
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    r = subprocess.run(["swiftc", "-O", SRC, "-o", BIN], capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail("building the track helper failed:\n" + r.stderr[-1200:])


def motion(meta, a, b):
    """[(t, x, y)]: seconds from `a`, scene shift as fractions of the source frame."""
    d = media.clip_dir(meta["id"])
    cache = os.path.join(d, "track-%.3f-%.3f.json" % (a, b))
    got = load_json(cache)
    if got is not None:
        return [tuple(p) for p in got]
    build()
    src = os.path.join(d, "proxy.mp4")
    if not os.path.exists(src):
        src = meta["src"]
    r = subprocess.run([BIN, src, "%.4f" % a, "%.4f" % (b - a)], capture_output=True, text=True)
    pts = []
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            j = json.loads(line)
            pts.append((j["t"], j["x"], j["y"]))
    if not pts:
        pts = [(0.0, 0.0, 0.0)]
    save_json(cache, pts)
    return pts


def _sample(pts, step=0.2):
    """Thin and smooth: one point every `step` seconds, averaged around it."""
    if len(pts) < 2:
        return pts
    out, t, end = [], 0.0, pts[-1][0]
    while t <= end + 1e-6:
        near = [p for p in pts if abs(p[0] - t) <= step / 2] or [min(pts, key=lambda p: abs(p[0] - t))]
        out.append((t, sum(p[1] for p in near) / len(near), sum(p[2] for p in near) / len(near)))
        t += step
    return out


def expr(pts, scale, axis, t0, speed=1.0, limit=None):
    """ffmpeg expression (in t, segment time) for the shift in output pixels along
    one axis, measured from local time t0 so the text starts where it was placed."""
    s = _sample(pts)
    k = 1 if axis == "x" else 2
    base = _at(s, t0 * speed, k)
    pairs = [(p[0] / speed, (p[k] - base) * scale) for p in s]
    e = "%.2f" % pairs[-1][1]
    for (ta, va), (tb, vb) in reversed(list(zip(pairs, pairs[1:]))):
        lerp = "(%.2f+(%.2f)*(t-%.4f)/%.4f)" % (va, vb - va, ta, max(1e-3, tb - ta))
        e = "if(lt(t,%.4f),%s,%s)" % (tb, lerp, e)
    e = "if(lt(t,%.4f),%.2f,%s)" % (pairs[0][0], pairs[0][1], e)
    if limit:                          # big pans would carry text off the frame
        e = "clip(%s,%.1f,%.1f)" % (e, -limit, limit)
    return e


def _at(s, t, k):
    if t <= s[0][0]:
        return s[0][k]
    for a, b in zip(s, s[1:]):
        if a[0] <= t <= b[0]:
            f = (t - a[0]) / max(1e-6, b[0] - a[0])
            return a[k] + (b[k] - a[k]) * f
    return s[-1][k]
