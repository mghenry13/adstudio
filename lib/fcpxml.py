"""Premiere Pro export: FCP7 XML (xmeml v4), which Premiere imports natively.

Layout of the sequence:
  V1        footage from the ORIGINAL files, reframed with Basic Motion;
            colour cards and stills as PNGs
  V2..      text and image overlays as full-frame transparent PNGs,
            HyperFrames animations as their alpha MOVs
  A1        clip audio, linked to V1
  A2        music
  A3..      sound effects

Known limits, also printed after every export:
  - speed changes are not written; the clip is placed at normal speed
  - overlay fades are not written; add them in Premiere
  - HDR sources are linked as they are: set the sequence to Rec.709 once
"""

import os
import shutil
from urllib.parse import quote
from xml.sax.saxutils import escape

from . import overlay, probe
from . import timeline as T
from .render import brand_color, crop_fracs
from .util import Fail, Timer, out, rel, resolve, run, slug


def _rate(fps, pad):
    tb = int(round(fps))
    ntsc = abs(fps - tb) > 0.001
    return ("%s<rate><timebase>%d</timebase><ntsc>%s</ntsc></rate>"
            % (pad, tb, "TRUE" if ntsc else "FALSE"))


def _url(path):
    return "file://localhost" + quote(os.path.abspath(path))


class Files(object):
    """Each media file is defined once, then referenced by id."""

    def __init__(self, seq_fps):
        self.ids, self.seq_fps = {}, seq_fps

    def ref(self, path, kind, pad, **kw):
        if path in self.ids:
            return '%s<file id="%s"/>' % (pad, self.ids[path])
        fid = "file-%d" % (len(self.ids) + 1)
        self.ids[path] = fid
        fps = kw.get("fps", self.seq_fps)
        dur = kw.get("duration_f", int(3600 * self.seq_fps))
        x = ['%s<file id="%s">' % (pad, fid),
             "%s  <name>%s</name>" % (pad, escape(os.path.basename(path))),
             "%s  <pathurl>%s</pathurl>" % (pad, escape(_url(path))),
             _rate(fps, pad + "  "),
             "%s  <duration>%d</duration>" % (pad, dur),
             "%s  <media>" % pad]
        if kind in ("video", "still"):
            x += ["%s    <video><samplecharacteristics><width>%d</width>"
                  "<height>%d</height></samplecharacteristics></video>"
                  % (pad, kw["width"], kw["height"])]
        if kind == "audio" or kw.get("has_audio"):
            x += ["%s    <audio><samplecharacteristics><depth>16</depth>"
                  "<samplerate>%d</samplerate></samplecharacteristics>"
                  "<channelcount>%d</channelcount></audio>"
                  % (pad, kw.get("audio_rate", 48000), kw.get("channels", 2) or 2)]
        x += ["%s  </media>" % pad, "%s</file>" % pad]
        return "\n".join(x)


def _motion(scale, horiz, vert, pad):
    return "\n".join([
        "%s<filter><effect>" % pad,
        "%s  <name>Basic Motion</name><effectid>basic</effectid>" % pad,
        "%s  <effectcategory>motion</effectcategory><effecttype>motion</effecttype>" % pad,
        "%s  <mediatype>video</mediatype>" % pad,
        "%s  <parameter><parameterid>scale</parameterid><name>Scale</name>"
        "<valuemin>0</valuemin><valuemax>1000</valuemax><value>%.3f</value></parameter>"
        % (pad, scale),
        "%s  <parameter><parameterid>center</parameterid><name>Center</name>"
        "<value><horiz>%.6f</horiz><vert>%.6f</vert></value></parameter>" % (pad, horiz, vert),
        "%s</effect></filter>" % pad])


def _level(db, pad):
    return ("%s<filter><effect><name>Audio Levels</name><effectid>audiolevels</effectid>"
            "<effectcategory>audiolevels</effectcategory><effecttype>audiolevels</effecttype>"
            "<mediatype>audio</mediatype><parameter><parameterid>level</parameterid>"
            "<name>Level</name><valuemin>0</valuemin><valuemax>3.98109</valuemax>"
            "<value>%.5f</value></parameter></effect></filter>" % (pad, 10 ** (db / 20.0)))


def _item(cid, name, start, end, tin, tout, fps, file_xml, extra=""):
    pad = "            "
    x = ['          <clipitem id="%s">' % cid,
         "%s<name>%s</name>" % (pad, escape(name)),
         "%s<duration>%d</duration>" % (pad, max(tout, end - start)),
         _rate(fps, pad),
         "%s<start>%d</start><end>%d</end>" % (pad, start, end),
         "%s<in>%d</in><out>%d</out>" % (pad, tin, tout),
         file_xml]
    if extra:
        x.append(extra)
    x.append("          </clipitem>")
    return "\n".join(x)


def _lanes(items):
    """Greedy track assignment so overlapping items never share a track."""
    lanes = []
    for it in sorted(items, key=lambda i: i["s"]):
        for lane in lanes:
            if lane[-1]["e"] <= it["s"]:
                lane.append(it)
                break
        else:
            lanes.append([it])
    return lanes


def export(ad_dir, aspect_arg=None):
    tl = T.load(ad_dir)
    aspect = T.aspects_for(tl, aspect_arg)[0]
    with Timer("premiere xml"):
        dst, notes = _export(ad_dir, aspect)
    out("  " + rel(dst))
    for n in notes:
        out("  note: " + n)
    out("  In Premiere: File > Import, pick the .xml. Check the first reframed "
        "clip's position against the preview.")
    return dst


def _export(ad_dir, aspect):
    R = T.resolve(ad_dir, aspect)
    W, H = T.ASPECTS[aspect]
    fps = R["fps"]
    f = lambda secs: int(round(secs * fps))
    name = "%s-%s" % (R["tl"].get("name", "ad"), aspect.replace(":", "x"))
    assets = os.path.join(ad_dir, "exports", "xml-assets")
    os.makedirs(assets, exist_ok=True)
    files, notes = Files(fps), []
    overlay.prepare(R["overlays"], R["brand"], aspect, W, H, ad_dir)

    v1, a1 = [], []
    for seg in R["segs"]:
        i, s, e = seg["index"] + 1, seg["start_f"], seg["start_f"] + seg["frames"]
        if seg["type"] == "clip":
            m = seg["meta"]
            if not os.path.exists(m["src"]):
                raise Fail("original file missing: %s" % m["src"])
            if seg["speed"] != 1.0:
                notes.append("segment %d has speed %.2f; placed at normal speed" % (i - 1, seg["speed"]))
            tin = f(seg["in"])
            cw, ch, cx, cy = crop_fracs(m["width"], m["height"], W, H, seg)
            shown_w, shown_h = W / cw, H / ch
            scale = 100.0 * shown_w / m["width"]
            dx = (0.5 - (cx + cw / 2)) * shown_w
            dy = (0.5 - (cy + ch / 2)) * shown_h
            fx = files.ref(m["src"], "video", "            ", fps=m["fps"],
                           duration_f=int(round(m["duration"] * m["fps"])),
                           width=m["width"], height=m["height"],
                           has_audio=m.get("has_audio"),
                           audio_rate=m.get("audio_rate", 48000),
                           channels=m.get("audio_channels", 2))
            link = ""
            if m.get("has_audio") and seg["volume"] > 0:
                link = ("            <link><linkclipref>v1-%d</linkclipref><mediatype>video</mediatype>"
                        "<trackindex>1</trackindex></link>\n"
                        "            <link><linkclipref>a1-%d</linkclipref><mediatype>audio</mediatype>"
                        "<trackindex>1</trackindex></link>" % (i, i))
            v1.append(_item("v1-%d" % i, m["name"], s, e, tin, tin + seg["frames"], fps, fx,
                            _motion(scale, dx / W, dy / H, "            ")
                            + ("\n" + link if link else "")))
            if link:
                a1.append(_item("a1-%d" % i, m["name"], s, e, tin, tin + seg["frames"], fps,
                                '            <file id="%s"/>' % files.ids[m["src"]],
                                "            <sourcetrack><mediatype>audio</mediatype>"
                                "<trackindex>1</trackindex></sourcetrack>\n"
                                + (_level(_db(seg["volume"]), "            ") + "\n"
                                   if seg["volume"] != 1.0 else "") + link))
        else:
            if seg["type"] == "color":
                p = os.path.join(assets, "card-%02d.png" % (i - 1))
                col = brand_color(R["brand"], seg["color"]).replace("#", "0x")
                run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                     "color=c=%s:s=%dx%d" % (col, W, H), "-frames:v", "1", p])
                iw, ih, extra = W, H, ""
            else:
                p = seg.get("path") or seg["meta"]["src"]
                iw, ih = probe.image_size(p)
                cw, ch, cx, cy = crop_fracs(iw, ih, W, H, seg)
                extra = _motion(100.0 * (W / cw) / iw,
                                (0.5 - (cx + cw / 2)) / cw, (0.5 - (cy + ch / 2)) / ch,
                                "            ")
            fx = files.ref(p, "still", "            ", width=iw, height=ih)
            v1.append(_item("v1-%d" % i, os.path.basename(p), s, e, 0, seg["frames"], fps, fx,
                            "            <stillframe>TRUE</stillframe>"
                            + ("\n" + extra if extra else "")))

    ov_items = []
    for j, ov in enumerate(R["overlays"]):
        s, e = f(ov["start"]), f(ov["end"])
        if e <= s:
            continue
        if ov.get("video"):
            p, kind = ov["video"], "video"
            label = os.path.basename(os.path.dirname(p))
        else:
            label = slug(ov.get("text") or os.path.basename(ov.get("image", "image")), 30)
            p = os.path.join(assets, "ov-%02d-%s.png" % (j, label))
            shutil.copyfile(ov["png"], p)
            kind = "still"
        ov_items.append({"s": s, "e": e, "path": p, "kind": kind, "label": label,
                         "cap": bool(ov.get("_caption")), "j": j})
        if ov.get("fade") and not ov.get("_caption"):
            pass
    if any(o.get("fade") for o in R["overlays"] if not o.get("_caption")):
        notes.append("overlay fades are not written to XML; add them in Premiere")
    caps = [o for o in ov_items if o["cap"]]
    vtracks = ([caps] if caps else []) + _lanes([o for o in ov_items if not o["cap"]])

    music, sfx = [], []
    mu = R["tl"].get("music")
    if mu:
        p = resolve(mu["file"], ad_dir)
        at, off = float(mu.get("at", 0)), float(mu.get("start", 0))
        music.append({"s": f(at), "e": R["total_f"], "path": p, "in": f(off),
                      "db": float(mu.get("gain_db", -16)), "dur": probe.audio_duration(p)})
    for sx in R["tl"].get("sfx") or []:
        p = resolve(sx["file"], ad_dir)
        d = probe.audio_duration(p)
        s = f(float(sx.get("at", 0)))
        sfx.append({"s": s, "e": min(R["total_f"], s + max(1, f(d))), "path": p,
                    "in": 0, "db": float(sx.get("gain_db", -6)), "dur": d})

    x = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE xmeml>", '<xmeml version="4">',
         '  <sequence id="adstudio-%s">' % slug(name),
         "    <name>%s</name>" % escape(name),
         "    <duration>%d</duration>" % R["total_f"],
         _rate(fps, "    "),
         "    <timecode>" + _rate(fps, "") + "<string>00:00:00:00</string><frame>0</frame>"
         "<displayformat>NDF</displayformat></timecode>",
         "    <media>", "      <video>",
         "        <format><samplecharacteristics>" + _rate(fps, "")
         + "<width>%d</width><height>%d</height><anamorphic>FALSE</anamorphic>"
           "<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
           "<colordepth>24</colordepth></samplecharacteristics></format>" % (W, H),
         "        <track>"] + v1 + ["        </track>"]
    n = 0
    for lane in vtracks:
        x.append("        <track>")
        for o in lane:
            n += 1
            if o["kind"] == "still":
                fx = files.ref(o["path"], "still", "            ", width=W, height=H)
                extra = "            <stillframe>TRUE</stillframe>"
            else:
                fx = files.ref(o["path"], "video", "            ", width=W, height=H,
                               duration_f=o["e"] - o["s"])
                extra = ""
            x.append(_item("ov-%d" % n, o["label"], o["s"], o["e"], 0, o["e"] - o["s"],
                           fps, fx, extra))
        x.append("        </track>")
    x += ["      </video>", "      <audio>", "        <numOutputChannels>2</numOutputChannels>",
          "        <format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>"
          "</samplecharacteristics></format>",
          "        <track>"] + a1 + ["        </track>"]
    n = 0
    for lane in ([music] if music else []) + _lanes(sfx):
        x.append("        <track>")
        for o in lane:
            n += 1
            fx = files.ref(o["path"], "audio", "            ",
                           duration_f=max(1, f(o["dur"])))
            x.append(_item("au-%d" % n, os.path.basename(o["path"]), o["s"], o["e"],
                           o["in"], o["in"] + (o["e"] - o["s"]), fps, fx,
                           "            <sourcetrack><mediatype>audio</mediatype>"
                           "<trackindex>1</trackindex></sourcetrack>\n"
                           + _level(o["db"], "            ")))
        x.append("        </track>")
    x += ["      </audio>", "    </media>", "  </sequence>", "</xmeml>"]

    if any(s["type"] == "clip" and s["meta"].get("hdr") for s in R["segs"]):
        notes.append("HDR sources are linked as shot: set the sequence working "
                     "color space to Rec.709 so Premiere tone-maps them")
    dst = os.path.join(ad_dir, "exports", name + ".xml")
    with open(dst, "w") as fh:
        fh.write("\n".join(x) + "\n")
    return dst, notes


def _db(vol):
    import math
    return 20 * math.log10(max(vol, 1e-4))
