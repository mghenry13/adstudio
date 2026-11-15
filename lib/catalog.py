"""Search across shot logs and transcripts, so a chat asks for moments
instead of re-reading every log."""

import os
import re

from . import media
from .util import load_json, out


def _tokens(s):
    return re.findall(r"[a-z0-9']+", (s or "").lower())


def search(words, brand=None, limit=15):
    q = [w.lower() for w in words]
    hits = []
    for m in media.all_clips(brand):
        d = media.clip_dir(m["id"])
        shots = (load_json(os.path.join(d, "shots.json")) or {}).get("shots", [])
        for s in shots:
            text = _tokens(s.get("description", "")) + s.get("tags", []) + \
                _tokens(s.get("shot_type", "")) + _tokens(" ".join(s.get("issues", [])))
            score = sum(2 if w in s.get("tags", []) else 1 for w in q
                        if any(w in t for t in text))
            if score:
                score += s.get("quality", 3) / 10.0 + s.get("hook", 3) / 20.0
                hits.append((score, m["id"], s["start"], s["end"], "shot",
                             "q%s h%s %s" % (s.get("quality", "?"), s.get("hook", "?"),
                                             s.get("description", ""))))
        tr = load_json(os.path.join(d, "transcript.json")) or {}
        for s in tr.get("sentences", []):
            toks = _tokens(s["text"])
            score = sum(1 for w in q if any(w in t for t in toks))
            if score:
                hits.append((score, m["id"], s["start"], s["end"], "said", s["text"]))
    hits.sort(key=lambda h: -h[0])
    for score, cid, a, b, kind, text in hits[:limit]:
        out("%-44s %6.2f-%6.2f  %-4s %s" % (cid, a, b, kind, text[:110]))
    out("%d matches" % len(hits))
