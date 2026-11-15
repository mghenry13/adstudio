"""Text and image overlays, drawn by Chrome from brand CSS.

Every overlay becomes one transparent full-frame PNG, so ffmpeg only has to
composite at 0,0 and all layout lives in templates/overlay.css. PNGs are
cached by content, and one Chrome launch draws every missing one.
"""

import html
import json
import os
import re

from .util import (BRANDS, RCACHE, ROOT, TEMPLATES, Fail, file_sig, resolve,
                   run, sha)

SHOOT = os.path.join(ROOT, "helpers", "shoot.mjs")


def design_width(W, H):
    return 1920 if W > H else 1080


def aspect_class(aspect):
    return "aspect-" + aspect.replace(":", "x")


def _rich(text):
    """Escape, then allow line breaks and *highlighted* words."""
    t = html.escape(text)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    return t.replace("\n", "<br>")


def brand_css(brand):
    p = os.path.join(BRANDS, brand, "brand.css")
    if not os.path.exists(p):
        raise Fail("brand '%s' has no brand.css" % brand)
    return p


def page(brand, aspect, body, extra_css=""):
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>adstudio overlay</title>"
            "<link rel='stylesheet' href='file://%s'>"
            "<link rel='stylesheet' href='file://%s'>"
            "<style>%s</style></head><body class='%s'>%s</body></html>"
            % (brand_css(brand), os.path.join(TEMPLATES, "overlay.css"),
               extra_css, aspect_class(aspect), body))


def overlay_html(ov, brand, aspect, ad_dir):
    cls = ["ov", "pos-" + ov.get("pos", "center"), "style-" + ov.get("style", "hook")]
    if ov.get("align"):
        cls.append("align-" + ov["align"])
    style = []
    if "y" in ov:                      # explicit vertical position, 0..1
        style.append("top:%.2f%%;bottom:auto;transform:none" % (ov["y"] * 100))
    tstyle = ["--size:%s" % ov.get("size", 1)]
    if ov.get("color"):
        tstyle.append("color:%s" % ov["color"])
    if ov.get("bg"):
        tstyle.append("background:%s" % ov["bg"])
    if ov.get("image"):
        src = resolve(ov["image"], ad_dir)
        if not os.path.exists(src):
            raise Fail("overlay image not found: %s" % ov["image"])
        inner = "<img src='file://%s' style='width:%.2fvw'>" % (
            src, float(ov.get("width", 0.4)) * 100)
    else:
        inner = "<span class='t' style='%s'>%s</span>" % (
            ";".join(tstyle), _rich(ov.get("text", "")))
    body = "<div class='%s' style='%s'>%s</div>" % (
        " ".join(cls), ";".join(style), inner)
    return page(brand, aspect, body)


def _sig_assets(brand, ov, ad_dir):
    sig = [file_sig(brand_css(brand)),
           file_sig(os.path.join(TEMPLATES, "overlay.css"))]
    if ov.get("image"):
        sig.append(file_sig(resolve(ov["image"], ad_dir)))
    return sig


def shoot(jobs):
    """jobs: [{"html" or "url", "out", "width", "height", "scale", "transparent"}]"""
    if not jobs:
        return
    payload = []
    for j in jobs:
        j = dict(j)
        if "html" in j:
            hp = j["out"] + ".html"
            os.makedirs(os.path.dirname(hp), exist_ok=True)
            with open(hp, "w") as f:
                f.write(j.pop("html"))
            j["url"] = "file://" + hp
        payload.append(j)
    r = run(["node", SHOOT], check=False, stdin=json.dumps({"jobs": payload}))
    if r.returncode != 0:
        raise Fail("overlay render failed: %s" % (r.stderr or r.stdout).strip()[-800:])
    for j in payload:
        hp = j["out"] + ".html"
        if os.path.exists(hp) and hp.startswith(RCACHE):
            os.unlink(hp)


def prepare(overlays, brand, aspect, W, H, ad_dir):
    """Give every text/image overlay a "png" path, rendering what is missing."""
    dw = design_width(W, H)
    dh = int(round(dw * H / float(W)))
    jobs, seen = [], set()
    os.makedirs(RCACHE, exist_ok=True)
    for ov in overlays:
        if ov.get("video"):
            continue
        spec = dict((k, ov.get(k)) for k in
                    ("text", "style", "pos", "align", "y", "size", "color", "bg",
                     "image", "width"))
        key = sha("ov1", spec, brand, aspect, W, H, _sig_assets(brand, ov, ad_dir))[:20]
        png = os.path.join(RCACHE, "ov-%s.png" % key)
        ov["png"], ov["key"] = png, key
        if not os.path.exists(png) and key not in seen:
            seen.add(key)
            jobs.append({"html": overlay_html(ov, brand, aspect, ad_dir),
                         "out": png, "width": dw, "height": dh,
                         "scale": W / float(dw), "transparent": True})
    shoot(jobs)
    return len(jobs)
