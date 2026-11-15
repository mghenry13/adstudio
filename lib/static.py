"""Static ads: HTML templates drawn by Chrome at every size in one launch.

statics.json in the ad folder:
  {"brand": "my-brand",
   "statics": [{"name": "free-day", "template": "photo-headline",
                "headline": "...", "sub": "...", "cta": "...",
                "image": "<file, or clip id>@<seconds>",
                "sizes": ["1080x1350", "1080x1080", "1080x1920", "1200x628"]}]}
A template is templates/static/<name>.html (or one in the ad folder) with
{{placeholders}}. It is laid out with CSS that adapts to any size.
"""

import html
import os
import re

from . import media, overlay
from .util import BRANDS, TEMPLATES, Fail, Timer, load_json, out, rel, resolve

DEFAULT_SIZES = ["1080x1350", "1080x1080", "1080x1920"]


def _image(spec, ad_dir):
    """A file path, or '<clip>@<seconds>' to pull a still from footage."""
    if not spec:
        return ""
    if "@" in spec and not os.path.exists(resolve(spec, ad_dir)):
        cid, t = spec.rsplit("@", 1)
        m = media.find(cid)
        dst = os.path.join(ad_dir, "stills", "%s-%s.png" % (m["id"], t.replace(".", "_")))
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            media.frame(m, float(t), dst)
        return dst
    p = resolve(spec, ad_dir)
    if not os.path.exists(p):
        raise Fail("static image not found: %s" % spec)
    return p


def render(ad_dir):
    cfg = load_json(os.path.join(ad_dir, "statics.json"))
    if not cfg or not cfg.get("statics"):
        raise Fail("statics.json has no 'statics' list")
    brand = cfg.get("brand") or os.path.basename(os.path.dirname(ad_dir))
    b = load_json(os.path.join(BRANDS, brand, "brand.json"), {}) or {}
    jobs, outs = [], []
    for st in cfg["statics"]:
        tname = st.get("template", "photo-headline")
        tp = os.path.join(ad_dir, tname + ".html")
        if not os.path.exists(tp):
            tp = os.path.join(TEMPLATES, "static", tname + ".html")
        if not os.path.exists(tp):
            raise Fail("no static template '%s'" % tname)
        tpl = open(tp).read()
        vals = {"cta": b.get("cta", ""), "url": b.get("url", ""),
                "brand_name": b.get("name", brand)}
        vals.update(dict((k, v) for k, v in st.items() if isinstance(v, str)))
        img = _image(st.get("image"), ad_dir)
        logo = os.path.join(BRANDS, brand, st.get("logo") or b.get("logo") or "")
        fills = dict((k, overlay._rich(v)) for k, v in vals.items())
        fills["image"] = "file://" + img if img else ""
        fills["logo"] = "file://" + logo if os.path.isfile(logo) else ""
        fills["brand_css"] = "file://" + overlay.brand_css(brand)
        page = re.sub(r"\{\{(\w+)\}\}", lambda m: fills.get(m.group(1), ""), tpl)
        for size in st.get("sizes", DEFAULT_SIZES):
            w, h = [int(x) for x in size.lower().split("x")]
            dst = os.path.join(ad_dir, "exports", "static", "%s-%s.png" % (st["name"], size))
            title = "%s %s %s" % (html.escape(b.get("name", brand)), st["name"], size)
            jobs.append({"html": page.replace("{{title}}", title), "out": dst,
                         "width": w, "height": h, "scale": 1, "transparent": False})
            outs.append(dst)
    with Timer("statics (%d images)" % len(jobs)):
        overlay.shoot(jobs)
    for j in jobs:
        hp = j["out"] + ".html"
        if os.path.exists(hp):
            os.unlink(hp)
    for o in outs:
        out("  " + rel(o))
    return outs
