"""Voiceover lines: scratch text-to-speech through Runware, or your own recordings.

A timeline's "vo" list holds one entry per line:

    {"text": "Right on Detroit Ave in Lakewood.", "at": 9.8, "gain_db": 0}
    {"file": "vo/my-take-01.wav", "at": 9.8}

`adstudio voice <brand>/<ad>` fills in "file" for entries that only have text
(Fish Audio S2.1 Pro on Runware by default, using your Runware key) and
transcribes every line so captions can follow the words. Drop in your own
recording by setting "file"; run `voice` again and the captions follow it.
"""

import json
import os
import time
import urllib.request
import uuid

from . import transcribe
from .util import Fail, Timer, config, load_json, out, read_key, run, save_json, sha

API = "https://api.runware.ai/v1"
DEFAULTS = {"voice_model": "fishaudio:s2.1@pro",
            "voice_id": "bf322df2096a46f18c579d0baa36f41d",   # Adrian, steady narrator
            "voice_speed": 1.0}
STOCK = {"adrian": "bf322df2096a46f18c579d0baa36f41d",
         "ethan": "536d3a5e000945adb7038665781a4aca",
         "jordan": "79d0bd3e4e5444b18f7b6d89b5927bf1",
         "laura": "e3cd384158934cc9a01029cd7d278634",
         "sarah": "933563129e564b19a115bedd57b7406a",
         "hannah": "9a9cf47702da476aa4629e2506d4a857",
         "selene": "b347db033a6549378b48d00acb0d06cd"}


def settings():
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in config().items() if k in DEFAULTS})
    cfg["voice_id"] = STOCK.get(str(cfg["voice_id"]).lower(), cfg["voice_id"])
    return cfg


def _post(key, tasks):
    req = urllib.request.Request(API, data=json.dumps(tasks).encode(),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise Fail("Runware said %s: %s" % (e.code, e.read().decode()[:400]))
    if body.get("errors"):
        raise Fail("Runware error: %s" % body["errors"][0].get("message", body["errors"]))
    return body.get("data", [])


def tts(text, dst, cfg=None):
    """Speak `text` into the WAV file `dst`. Returns dst."""
    cfg = cfg or settings()
    key = read_key("runware")
    if not key:
        raise Fail("no Runware key yet. Run: adstudio key runware --paste")
    task = str(uuid.uuid4())
    speech = {"text": text, "voice": cfg["voice_id"]}
    if float(cfg.get("voice_speed", 1)) != 1:
        speech["speed"] = float(cfg["voice_speed"])
    data = _post(key, [{"taskType": "audioInference", "taskUUID": task,
                        "model": cfg["voice_model"], "speech": speech,
                        "outputFormat": "WAV", "deliveryMethod": "async"}])
    url, t0 = None, time.time()
    while not url:
        url = next((d.get("audioURL") for d in data if d.get("audioURL")), None)
        if url:
            break
        if time.time() - t0 > 180:
            raise Fail("Runware took too long on: %s" % text[:60])
        time.sleep(1.0)
        data = _post(key, [{"taskType": "getResponse", "taskUUID": task}])
    tmp = dst + ".part"
    urllib.request.urlretrieve(url, tmp)
    # trim the silence the model leaves at the ends, so "at" means the first word
    run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af",
         "silenceremove=start_periods=1:start_threshold=-45dB,"
         "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
         "-ar", "48000", dst])
    os.remove(tmp)
    return dst


def words_path(path):
    return os.path.splitext(path)[0] + ".words.json"


def _transcribe(paths):
    """Word timings for VO files, with the same Parakeet helper as footage."""
    todo = [p for p in paths if not os.path.exists(words_path(p))
            or os.path.getmtime(words_path(p)) < os.path.getmtime(p)]
    if not todo:
        return
    transcribe.build()
    wavs = {}
    for p in todo:                      # Parakeet wants 16 kHz mono
        w = os.path.splitext(p)[0] + ".16k.wav"
        run(["ffmpeg", "-v", "error", "-y", "-i", p, "-ac", "1", "-ar", "16000", w])
        wavs[w] = p
    r = run([transcribe.BIN, transcribe.MODEL_DIR] + list(wavs))
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            j = json.loads(line)
            if j.get("file") in wavs and not j.get("error"):
                save_json(words_path(wavs[j["file"]]),
                          {"text": j["text"], "words": transcribe.words_from_tokens(j["tokens"])})
    for w in wavs:
        os.remove(w)


def words(path):
    return (load_json(words_path(path)) or {}).get("words", [])


def build(ad_dir, force=False):
    """Make any missing VO files for the ad, then transcribe them."""
    from .timeline import load
    from .util import resolve as rpath
    p = os.path.join(ad_dir, "timeline.json")
    tl = load(ad_dir)
    lines = tl.get("vo") or []
    if not lines:
        raise Fail('timeline has no "vo" lines yet')
    cfg = settings()
    os.makedirs(os.path.join(ad_dir, "vo"), exist_ok=True)
    made = 0
    with Timer("voice %d lines" % len(lines)):
        for i, v in enumerate(lines):
            if not v.get("text") and not v.get("file"):
                raise Fail("vo line %d needs 'text' or 'file'" % i)
            sig = sha("vo1", v.get("text"), cfg["voice_model"], cfg["voice_id"],
                      cfg.get("voice_speed"))[:12]
            scratch = v.get("text") and (not v.get("file") or v.get("_sig"))
            if scratch and (force or v.get("_sig") != sig
                            or not os.path.exists(rpath(v["file"], ad_dir))):
                rel_file = "vo/line-%02d-%s.wav" % (i + 1, sig)
                tts(v["text"], os.path.join(ad_dir, rel_file), cfg)
                v["file"], v["_sig"] = rel_file, sig
                made += 1
                out("  line %d  %s" % (i + 1, v["text"][:60]))
        save_json(p, tl)
        _transcribe([rpath(v["file"], ad_dir) for v in lines])
    out("%d new, %d reused (voice %s)" % (made, len(lines) - made, cfg["voice_id"]))
