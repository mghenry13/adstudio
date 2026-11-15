"""Local transcription with Parakeet TDT v3 (FluidAudio / CoreML).

The Swift helper loads the model once and transcribes a whole batch. Its
sub-word tokens are merged here into words with start and end times, which is
what captions and "find the moment they say X" both need.
"""

import json
import os
import subprocess

from . import media
from .util import ROOT, Fail, Timer, load_json, out, save_json

BIN = os.path.join(ROOT, "bin", "parakeet")
PKG = os.path.join(ROOT, "helpers", "parakeet")
MODEL_DIR = os.path.expanduser(
    "~/Library/Application Support/FluidAudio/Models/parakeet-tdt-0.6b-v3")
SENTENCE_END = (".", "?", "!")


def build():
    if os.path.exists(BIN):
        return
    out("building parakeet helper (first run only)...")
    r = subprocess.run(["swift", "build", "-c", "release"], cwd=PKG,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail("swift build failed:\n" + (r.stderr or r.stdout)[-1500:])
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    os.replace(os.path.join(PKG, ".build", "release", "parakeet"), BIN)


def words_from_tokens(tokens):
    """SentencePiece tokens: a leading space or U+2581 starts a new word."""
    words, cur = [], None
    for t in tokens:
        raw = t["t"]
        starts = raw.startswith(("▁", " "))
        text = raw.replace("▁", "").strip()
        if not text:
            continue
        punct_only = all(not ch.isalnum() for ch in text)
        if cur is not None and (not starts or punct_only):
            cur["w"] += text
            cur["end"] = t["e"]
            cur["conf"] = min(cur["conf"], t.get("c", 1.0))
        else:
            if cur:
                words.append(cur)
            cur = {"w": text, "start": t["s"], "end": t["e"],
                   "conf": t.get("c", 1.0)}
    if cur:
        words.append(cur)
    for w in words:
        w["start"], w["end"] = round(w["start"], 3), round(w["end"], 3)
        w["conf"] = round(w["conf"], 3)
    return words


def sentences(words, max_gap=0.8):
    res, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        last = i == len(words) - 1
        gap = (words[i + 1]["start"] - w["end"]) if not last else 0
        if last or w["w"].endswith(SENTENCE_END) or gap > max_gap:
            res.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                        "text": " ".join(x["w"] for x in cur)})
            cur = []
    return res


def run_for(metas, force=False):
    todo = []
    for m in metas:
        d = media.clip_dir(m["id"])
        wav = os.path.join(d, "audio.wav")
        if not os.path.exists(wav):
            continue
        if force or not os.path.exists(os.path.join(d, "transcript.json")):
            todo.append((m, wav))
    if not todo:
        out("transcripts up to date")
        return
    build()
    if not os.path.isdir(MODEL_DIR):
        out("downloading the Parakeet speech model (first run only, about 500 MB)...")
    by_wav = dict((wav, m) for m, wav in todo)
    with Timer("transcribe %d clips" % len(todo)):
        p = subprocess.Popen([BIN, MODEL_DIR] + [w for _, w in todo],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
        for line in p.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            r = json.loads(line)
            m = by_wav.get(r["file"])
            if not m:
                continue
            if r.get("error"):
                out("  FAIL %s: %s" % (m["id"], r["error"]))
                continue
            words = words_from_tokens(r["tokens"])
            save_json(os.path.join(media.clip_dir(m["id"]), "transcript.json"),
                      {"text": r["text"], "words": words,
                       "sentences": sentences(words), "engine": "parakeet-tdt-0.6b-v3"})
            out("  %-36s %3d words in %.2fs  %s" % (
                m["id"], len(words), r["seconds"], r["text"][:70]))
        err = p.stderr.read()
        if p.wait() != 0:
            raise Fail("parakeet helper failed: %s" % err.strip()[-600:])


def words(cid):
    t = load_json(os.path.join(media.clip_dir(cid), "transcript.json"))
    return (t or {}).get("words", [])
