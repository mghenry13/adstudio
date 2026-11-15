"""Shot logs from Gemini: what is in each clip, where, and how usable it is.

One call per clip, made once and cached as shots.json. The model sees the
720p SDR proxy plus the Parakeet transcript, and must answer in a fixed JSON
schema so the catalog can be searched without re-reading footage.

The key is per user (see `adstudio key gemini`) and is sent in a header,
never in a URL, so it cannot end up in logs or error messages.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import media
from .util import (BRANDS, Fail, Timer, config, load_json, out, read_key, run,
                   save_json)

API = "https://generativelanguage.googleapis.com"
INLINE_LIMIT = 14 * 1024 * 1024
PROMPT_VERSION = 2

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "setting": {"type": "STRING"},
        "people": {"type": "ARRAY", "items": {"type": "STRING"}},
        "shots": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {
                "start": {"type": "NUMBER"},
                "end": {"type": "NUMBER"},
                "description": {"type": "STRING"},
                "shot_type": {"type": "STRING", "enum": [
                    "talking-head", "wide", "medium", "close-up", "detail",
                    "pov", "screen", "b-roll", "other"]},
                "camera": {"type": "STRING", "enum": [
                    "static", "handheld", "pan", "tilt", "push-in", "pull-out",
                    "tracking", "whip", "other"]},
                "speech": {"type": "BOOLEAN"},
                "quality": {"type": "INTEGER"},
                "hook": {"type": "INTEGER"},
                "issues": {"type": "ARRAY", "items": {"type": "STRING"}},
                "subject_x": {"type": "NUMBER"},
                "subject_y": {"type": "NUMBER"},
                "tags": {"type": "ARRAY", "items": {"type": "STRING"}}},
            "required": ["start", "end", "description", "shot_type", "camera",
                         "speech", "quality", "hook", "subject_x", "subject_y",
                         "tags"]}},
        "best_moments": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"start": {"type": "NUMBER"}, "end": {"type": "NUMBER"},
                           "why": {"type": "STRING"}},
            "required": ["start", "end", "why"]}}},
    "required": ["summary", "shots", "best_moments"]}

PROMPT = """You are logging raw footage for a video editor who makes short social ads.
Brand: %(brand)s. %(note)s
The clip is %(duration).2f seconds long.%(transcript)s

Write a shot log. Split the clip wherever the framing, subject or action
changes in a way an editor would cut on. A single continuous take can still be
several entries if what happens changes.

For every shot give:
- start and end in seconds from the start of the clip, to one decimal place
- description: one plain sentence saying who or what is on screen and what happens
- shot_type and camera from the allowed values
- speech: true if someone is talking to camera or dialogue matters
- quality: 1 to 5 for technical usability (focus, exposure, stability, framing)
- hook: 1 to 5 for how well it would stop someone scrolling in the first second
- issues: any of shaky, soft-focus, dark, overexposed, noisy-audio, wind,
  obstructed, awkward-start, awkward-end. Empty list if none.
- subject_x, subject_y: where the main subject sits in the frame, as fractions
  from 0 to 1 measured from the left and from the top. Used to reframe.
- tags: 3 to 8 lowercase search words (people, objects, place, mood, action)

Then list best_moments: the few ranges most worth using in an ad, with a short reason.
Be literal. Do not invent details you cannot see or hear."""


class GeminiError(Fail):
    pass


class QuotaError(GeminiError):
    """The key's daily allowance is used up. Retrying today cannot help."""


def _key():
    k = read_key("gemini")
    if not k:
        raise Fail("no Gemini key yet. Run: adstudio key gemini")
    return k


def _http(method, url, key, body=None, headers=None, timeout=300, raw=False):
    h = {"x-goog-api-key": key}
    h.update(headers or {})
    data = body
    if body is not None and not isinstance(body, (bytes, bytearray)):
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = r.read()
                if raw:
                    return r.headers, payload
                return json.loads(payload or b"{}")
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", "replace")
            last = "HTTP %s: %s" % (e.code, err[:300])
            if e.code == 429 and ("per day" in err or "free_tier" in err):
                import re
                wait = re.search(r"retry in ([0-9hms.]+)", err)
                free = "free_tier" in err
                raise QuotaError(
                    "Gemini daily limit reached%s%s. %s" % (
                        " (free tier)" if free else "",
                        ", resets in about %s" % wait.group(1).split(".")[0] + "s"
                        if wait else "",
                        "Turn on billing for this key's project in Google AI Studio "
                        "to lift the limit." if free else ""))
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise GeminiError("Gemini request failed. " + last)
        except Exception as e:           # network hiccup
            last = str(e)
            time.sleep(2 ** attempt)
    raise GeminiError("Gemini gave up after 4 tries. " + str(last))


def check_gemini():
    """One cheap call that proves the key works and the model exists."""
    try:
        d = _http("GET", API + "/v1beta/models?pageSize=200", _key(), timeout=30)
    except Fail as e:
        return "key check failed: %s" % e
    names = [m["name"].split("/")[-1] for m in d.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    want = config()["gemini_model"]
    if want in names:
        return "key works, model %s is available" % want
    flash = sorted(n for n in names if "flash" in n and "image" not in n and "tts" not in n)
    return ("key works, but model %s is not offered to it. Available flash models: %s"
            % (want, ", ".join(flash[-6:]) or "none"))


def _upload(path, key):
    size = os.path.getsize(path)
    hdrs, _ = _http("POST", API + "/upload/v1beta/files", key,
                    body={"file": {"display_name": os.path.basename(path)}},
                    headers={"X-Goog-Upload-Protocol": "resumable",
                             "X-Goog-Upload-Command": "start",
                             "X-Goog-Upload-Header-Content-Length": str(size),
                             "X-Goog-Upload-Header-Content-Type": "video/mp4"},
                    raw=True)
    url = hdrs.get("x-goog-upload-url")
    if not url:
        raise GeminiError("Gemini upload did not return an upload URL")
    with open(path, "rb") as f:
        _, payload = _http("POST", url, key, body=f.read(),
                           headers={"X-Goog-Upload-Offset": "0",
                                    "X-Goog-Upload-Command": "upload, finalize",
                                    "Content-Type": "video/mp4"}, raw=True)
    info = json.loads(payload)["file"]
    for _ in range(120):
        if info.get("state") == "ACTIVE":
            return info
        if info.get("state") == "FAILED":
            raise GeminiError("Gemini could not process the uploaded video")
        time.sleep(1.5)
        info = _http("GET", API + "/v1beta/" + info["name"], key, timeout=30)
    raise GeminiError("Gemini upload never became ready")


def _analysis_file(m):
    """Small clips go as they are. Long ones get a lighter copy to upload."""
    d = media.clip_dir(m["id"])
    proxy = os.path.join(d, "proxy.mp4")
    if os.path.getsize(proxy) <= INLINE_LIMIT:
        return proxy
    dst = os.path.join(d, "analysis.mp4")
    if not os.path.exists(dst):
        run(["ffmpeg", "-v", "error", "-y", "-i", proxy,
             "-vf", "scale='if(gt(iw,ih),-2,480)':'if(gt(iw,ih),480,-2)',fps=12",
             "-c:v", "h264_videotoolbox", "-b:v", "700k", "-c:a", "aac",
             "-b:a", "64k", "-ac", "1", dst + ".tmp.mp4"])
        os.replace(dst + ".tmp.mp4", dst)
    return dst


def _brand_line(brand):
    b = load_json(os.path.join(BRANDS, brand or "", "brand.json"), {}) or {}
    return "%s (%s)" % (b.get("name", brand or "unknown"), b.get("url", ""))


def analyze_clip(m, note="", model=None):
    key = _key()
    model = model or config()["gemini_model"]
    path = _analysis_file(m)
    tr = load_json(os.path.join(media.clip_dir(m["id"]), "transcript.json")) or {}
    transcript = ""
    if tr.get("sentences"):
        transcript = "\nSpeech, timed by a transcriber:\n" + "\n".join(
            "  %.1f-%.1f  %s" % (s["start"], s["end"], s["text"]) for s in tr["sentences"])
    prompt = PROMPT % {"brand": _brand_line(m.get("brand")), "note": note,
                       "duration": m["duration"], "transcript": transcript}
    # Gemini samples one frame a second by default, which is too coarse to
    # place cuts in short clips, so short clips are sampled more densely.
    fps = 4 if m["duration"] < 30 else (2 if m["duration"] < 150 else 1)
    uploaded = None
    if os.path.getsize(path) <= INLINE_LIMIT:
        with open(path, "rb") as f:
            video = {"inline_data": {"mime_type": "video/mp4",
                                     "data": base64.b64encode(f.read()).decode()}}
    else:
        uploaded = _upload(path, key)
        video = {"file_data": {"mime_type": "video/mp4", "file_uri": uploaded["uri"]}}
    video["video_metadata"] = {"fps": fps}
    body = {"contents": [{"parts": [video, {"text": prompt}]}],
            "generationConfig": {"temperature": 0.2,
                                 "responseMimeType": "application/json",
                                 "responseSchema": SCHEMA,
                                 "mediaResolution": "MEDIA_RESOLUTION_LOW"}}
    try:
        d = _http("POST", "%s/v1beta/models/%s:generateContent" % (API, model), key, body=body)
    finally:
        if uploaded:
            try:
                _http("DELETE", API + "/v1beta/" + uploaded["name"], key, timeout=30)
            except Fail:
                pass
    cand = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    try:
        data = json.loads(text)
    except ValueError:
        raise GeminiError("Gemini returned something that is not JSON for %s (finish: %s)"
                          % (m["id"], cand.get("finishReason")))
    u = d.get("usageMetadata", {})
    data["_usage"] = {"model": model, "in": u.get("promptTokenCount", 0),
                      "out": u.get("candidatesTokenCount", 0)
                      + u.get("thoughtsTokenCount", 0)}
    return data


IMAGE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "kind": {"type": "STRING", "enum": ["photo", "logo", "graphic", "screenshot",
                                            "product-shot", "illustration", "other"]},
        "text_in_image": {"type": "STRING"},
        "quality": {"type": "INTEGER"},
        "hook": {"type": "INTEGER"},
        "subject_x": {"type": "NUMBER"},
        "subject_y": {"type": "NUMBER"},
        "colors": {"type": "ARRAY", "items": {"type": "STRING"}},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["summary", "kind", "quality", "hook", "subject_x", "subject_y", "tags"]}

IMAGE_PROMPT = """You are logging a still image for an editor who makes short social ads.
Brand: %(brand)s. %(note)s
Give: summary (one plain sentence: who or what is shown), kind, any text visible
in the image, quality 1 to 5 (sharpness, exposure, framing), hook 1 to 5 (would it
stop someone scrolling), subject_x and subject_y (where the main subject sits,
fractions from the left and top), the main colors as hex, and 3 to 8 lowercase
search tags. Be literal."""


def analyze_image(m, note="", model=None):
    key = _key()
    model = model or config()["gemini_model"]
    tmp = os.path.join(media.clip_dir(m["id"]), "analysis.jpg")
    run(["ffmpeg", "-v", "error", "-y", "-i", m["src"], "-vf",
         "scale='min(1600,iw)':-2", "-frames:v", "1", "-q:v", "3", tmp])
    with open(tmp, "rb") as f:
        part = {"inline_data": {"mime_type": "image/jpeg",
                                "data": base64.b64encode(f.read()).decode()}}
    os.unlink(tmp)
    body = {"contents": [{"parts": [part, {"text": IMAGE_PROMPT % {
        "brand": _brand_line(m.get("brand")), "note": note}}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json",
                             "responseSchema": IMAGE_SCHEMA}}
    d = _http("POST", "%s/v1beta/models/%s:generateContent" % (API, model), key, body=body)
    cand = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    try:
        r = json.loads(text)
    except ValueError:
        raise GeminiError("Gemini returned something that is not JSON for %s" % m["id"])
    u = d.get("usageMetadata", {})
    # Stored in the same shape as a video shot log, so search treats both alike.
    return {"summary": r["summary"], "kind": r.get("kind"),
            "text_in_image": r.get("text_in_image", ""), "colors": r.get("colors", []),
            "shots": [{"start": 0, "end": 0, "description": r["summary"],
                       "shot_type": "other", "camera": "static", "speech": False,
                       "quality": r["quality"], "hook": r["hook"], "issues": [],
                       "subject_x": r["subject_x"], "subject_y": r["subject_y"],
                       "tags": r["tags"] + ([r["kind"]] if r.get("kind") else [])}],
            "best_moments": [],
            "_usage": {"model": model, "in": u.get("promptTokenCount", 0),
                       "out": u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)}}


def save_shots(m, data, source="gemini"):
    dur = m.get("duration") or 0
    shots = []
    for s in data.get("shots", []):
        a, b = max(0.0, float(s["start"])), float(s["end"])
        if dur:
            b = min(b, dur)
        if b <= a and m.get("kind") != "image":
            continue
        s = dict(s, start=round(a, 2), end=round(b, 2))
        s["tags"] = [str(t).lower() for t in s.get("tags", [])]
        shots.append(s)
    data = dict(data, shots=shots, source=source, prompt_version=PROMPT_VERSION,
                at=int(time.time()))
    save_json(os.path.join(media.clip_dir(m["id"]), "shots.json"), data)
    return data


def run_for(metas, backend=None, note="", force=False):
    todo = [m for m in metas if m["kind"] in ("video", "image") and (
        force or not os.path.exists(os.path.join(media.clip_dir(m["id"]), "shots.json")))]
    if not todo:
        out("shot logs up to date")
        return
    if backend == "runware":
        raise Fail("the Runware analysis backend is not built yet; analysis uses the Gemini key")
    _key()
    tin = tout = done = 0

    stop = []

    def work(m):
        if stop:                         # daily limit hit: do not keep asking
            return m, None, None
        try:
            fn = analyze_image if m["kind"] == "image" else analyze_clip
            return m, save_shots(m, fn(m, note)), None
        except QuotaError as e:
            stop.append(str(e))
            return m, None, None
        except Fail as e:
            return m, None, str(e).splitlines()[0][:200]

    with Timer("analyze %d files" % len(todo)):
        # free-tier keys allow only a few requests a minute: `adstudio config analyze_workers 1`
        with ThreadPoolExecutor(max_workers=int(config().get("analyze_workers", 4))) as ex:
            for m, data, err in ex.map(work, todo):
                if err:
                    out("  FAIL %s: %s" % (m["id"], err))
                    continue
                if data is None:
                    continue
                done += 1
                u = data.get("_usage", {})
                tin, tout = tin + u.get("in", 0), tout + u.get("out", 0)
                out("  %-40s %2d shots  %s" % (m["id"], len(data["shots"]),
                                               data.get("summary", "")[:80]))
    out("analyzed %d of %d (tokens: %d in, %d out)" % (done, len(todo), tin, tout))
    if stop:
        out("STOPPED: %s" % stop[0])
        out("  %d files are waiting; the next `adstudio sync` or `analyze --all` "
            "picks them up." % (len(todo) - done))
