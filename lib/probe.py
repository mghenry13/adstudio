"""Clip metadata via ffprobe, including HDR and rotation."""

import json

from .util import Fail, run

HDR_TRANSFERS = ("arib-std-b67", "smpte2084")   # HLG (iPhone), PQ


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,r_frame_rate,"
             "avg_frame_rate,pix_fmt,color_transfer,color_primaries,"
             "sample_rate,channels:stream_side_data=rotation:"
             "format=duration", "-of", "json", path])
    d = json.loads(r.stdout)
    streams = d.get("streams", [])
    vid = next((s for s in streams if s.get("codec_type") == "video"), None)
    aud = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if vid is None:
        raise Fail("no video stream in %s" % path)
    num, den = [int(x) for x in vid["r_frame_rate"].split("/")]
    if not den:
        raise Fail("bad frame rate in %s" % path)
    rot = 0
    for sd in vid.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(round(float(sd["rotation"])))
    sw, sh = int(vid["width"]), int(vid["height"])
    w, h = (sh, sw) if abs(rot) % 180 == 90 else (sw, sh)
    return {"duration": float(d["format"].get("duration") or 0),
            "width": w, "height": h,             # as the viewer sees it
            "stored_width": sw, "stored_height": sh, "rotation": rot,
            "rate_num": num, "rate_den": den, "fps": num / float(den),
            "codec": vid.get("codec_name"),
            "pix_fmt": vid.get("pix_fmt"),
            "transfer": vid.get("color_transfer"),
            "hdr": vid.get("color_transfer") in HDR_TRANSFERS,
            "has_audio": aud is not None,
            "audio_rate": int(aud["sample_rate"]) if aud else 48000,
            "audio_channels": int(aud.get("channels", 2)) if aud else 0}


def image_size(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", path])
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def audio_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path])
    return float(r.stdout.strip() or 0)
