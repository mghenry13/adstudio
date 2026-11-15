"""References: ads and images to model new work on.

A reference is ingested like footage (proxy, transcript) but flagged so it
never shows up as usable footage. On top of that it gets:
  - cut times from scene detection, so pacing is measured rather than guessed
  - a contact sheet
  - a Gemini breakdown: hook, beat structure, on-screen text, sound, and what
    to borrow. Saved as reference.json next to the proxy.
References are for studying structure and style. Their footage, music and
copy are not ours to reuse.
"""

import base64
import json
import os
import re

from . import analyze, media, transcribe
from .util import (IMAGE_EXT, MEDIA, Fail, Timer, config, load_json, out, rel,
                   run, save_json)

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "format": {"type": "STRING"},
        "hook": {"type": "OBJECT", "properties": {
            "seconds": {"type": "NUMBER"}, "what_happens": {"type": "STRING"},
            "on_screen_text": {"type": "STRING"}, "why_it_works": {"type": "STRING"}}},
        "beats": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "start": {"type": "NUMBER"}, "end": {"type": "NUMBER"},
            "role": {"type": "STRING"}, "visual": {"type": "STRING"},
            "on_screen_text": {"type": "STRING"}, "spoken": {"type": "STRING"}},
            "required": ["start", "end", "role", "visual"]}},
        "text_style": {"type": "STRING"},
        "layout": {"type": "STRING"},
        "colors": {"type": "ARRAY", "items": {"type": "STRING"}},
        "pacing": {"type": "STRING"},
        "sound": {"type": "STRING"},
        "cta": {"type": "STRING"},
        "borrow": {"type": "ARRAY", "items": {"type": "STRING"}},
        "avoid": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["summary", "format", "text_style", "borrow"]}

PROMPT = """This is a REFERENCE the editor wants to learn from, not footage to reuse.
Break down how it is built so a new ad for %(brand)s can follow the same approach
with different footage and words. %(note)s
%(facts)s
Describe: the format in a few words; the hook (first seconds); the beats in order
with times, each beat's role (hook, problem, proof, product, offer, cta and so on),
what is on screen, any on-screen text and what is said; the text style (font feel,
size, color, placement, animation); layout and framing; main colors as hex;
pacing; sound (music feel, effects, voice); the call to action.
Finish with "borrow": specific techniques worth copying, and "avoid": things that
would not suit %(brand)s. Be literal about what you see and hear."""


def cuts(proxy, thresh=0.3):
    r = run(["ffmpeg", "-v", "info", "-i", proxy, "-vf",
             "select='gt(scene,%.2f)',showinfo" % thresh, "-an", "-f", "null", "-"],
            check=False)
    return [round(float(x), 2) for x in re.findall(r"pts_time:([0-9.]+)", r.stderr)]


def add(brand, src, note=""):
    if src.startswith(("http://", "https://")):
        d = os.path.join(MEDIA, "ref-downloads")
        os.makedirs(d, exist_ok=True)
        with Timer("download reference"):
            r = run(["yt-dlp", "--no-playlist", "-f", "mp4/bv*+ba/b", "--merge-output-format",
                     "mp4", "-o", os.path.join(d, "%(title).60B-%(id)s.%(ext)s"),
                     "--print", "after_move:filepath", src])
        src = r.stdout.strip().splitlines()[-1]
    src = os.path.abspath(os.path.expanduser(src))
    if not os.path.exists(src):
        raise Fail("not found: %s" % src)
    m, _ = media._register(src, brand)
    m["ref"], m["note"] = True, note
    save_json(os.path.join(media.clip_dir(m["id"]), "meta.json"), m)
    d = media.clip_dir(m["id"])
    facts = ""
    if m["kind"] == "video":
        with Timer("reference proxy"):
            media._build_proxy(m)
            media._build_audio(m)
        if m.get("has_audio"):
            transcribe.run_for([m])
        c = cuts(os.path.join(d, "proxy.mp4"))
        n = len(c) + 1
        m["cuts"] = c
        m["avg_shot"] = round(m["duration"] / n, 2)
        save_json(os.path.join(d, "meta.json"), m)
        media.sheet(m, os.path.join(d, "sheet.png"))
        tr = load_json(os.path.join(d, "transcript.json")) or {}
        facts = ("Measured: %.1fs long, %d shots, cuts at %s seconds.\nSpoken: %s"
                 % (m["duration"], n, c[:60], tr.get("text", "(none)")))
        out("  %d shots, average %.2fs each" % (n, m["avg_shot"]))
    try:
        data = breakdown(m, note, facts)
        save_json(os.path.join(d, "reference.json"), data)
    except Fail as e:
        out("  breakdown skipped: %s" % e)
    show(m["id"])
    return m


def breakdown(m, note="", facts=""):
    key = analyze._key()
    d = media.clip_dir(m["id"])
    if m["kind"] == "image":
        tmp = os.path.join(d, "ref.jpg")
        run(["ffmpeg", "-v", "error", "-y", "-i", m["src"], "-vf",
             "scale='min(1600,iw)':-2", "-q:v", "3", tmp])
        with open(tmp, "rb") as f:
            part = {"inline_data": {"mime_type": "image/jpeg",
                                    "data": base64.b64encode(f.read()).decode()}}
    else:
        path = analyze._analysis_file(m)
        if os.path.getsize(path) <= analyze.INLINE_LIMIT:
            with open(path, "rb") as f:
                part = {"inline_data": {"mime_type": "video/mp4",
                                        "data": base64.b64encode(f.read()).decode()}}
        else:
            up = analyze._upload(path, key)
            part = {"file_data": {"mime_type": "video/mp4", "file_uri": up["uri"]}}
        part["video_metadata"] = {"fps": 4 if m["duration"] < 45 else 2}
    prompt = PROMPT % {"brand": analyze._brand_line(m.get("brand")), "note": note,
                       "facts": facts}
    body = {"contents": [{"parts": [part, {"text": prompt}]}],
            "generationConfig": {"temperature": 0.2,
                                 "responseMimeType": "application/json",
                                 "responseSchema": SCHEMA}}
    with Timer("reference breakdown"):
        res = analyze._http("POST", "%s/v1beta/models/%s:generateContent"
                            % (analyze.API, config()["gemini_model"]), key, body=body)
    cand = (res.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    try:
        return json.loads(text)
    except ValueError:
        raise Fail("Gemini did not return JSON for the reference")


def refs(brand=None):
    return [m for m in media.all_clips(brand, refs=True) if m.get("ref")]


def listing(brand=None):
    rows = refs(brand)
    for m in rows:
        r = load_json(os.path.join(media.clip_dir(m["id"]), "reference.json")) or {}
        out("%-44s %-10s %-5s %s" % (m["id"], m.get("brand", ""), m["kind"],
                                     (r.get("format") or m.get("note") or "")[:70]))
    out("%d references" % len(rows))


def show(ref):
    m = media.find(ref, refs=True)
    d = media.clip_dir(m["id"])
    out("%s  (%s, %s)  %s" % (m["id"], m["kind"], m.get("brand"), m["src"]))
    if m.get("note"):
        out("note: %s" % m["note"])
    if m["kind"] == "video":
        out("length %.1fs, %d shots, average %.2fs; cuts at %s" % (
            m["duration"], len(m.get("cuts", [])) + 1, m.get("avg_shot", 0), m.get("cuts", [])))
        out("contact sheet: %s" % os.path.join(d, "sheet.png"))
    r = load_json(os.path.join(d, "reference.json"))
    if not r:
        out("no breakdown yet (needs a Gemini key: adstudio key gemini)")
        return
    out(json.dumps(r, indent=1, ensure_ascii=False))
