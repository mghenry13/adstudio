"""Preview server: serves the workspace, takes feedback from the page, and tells
the page when to reload. Local only (binds to 127.0.0.1)."""

import json
import os
import posixpath
import re
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import versions
from .util import ADS, MEDIA, WORK, Fail, config, out

SERVED = ("ads", "brands", "library")      # nothing else is reachable


def ad_dir_for(ref):
    ref = (ref or "").strip("/")
    if not re.match(r"^[\w.-]+/[\w.-]+$", ref) or ".." in ref:
        raise Fail("bad ad reference")
    d = os.path.join(ADS, ref)
    if not os.path.exists(os.path.join(d, "timeline.json")):
        raise Fail("no such ad")
    return d


def heartbeat_path(ad_dir):
    return os.path.join(MEDIA, "listening-" + os.path.relpath(ad_dir, ADS).replace("/", "--"))


def listening(ad_dir):
    try:
        return time.time() - os.path.getmtime(heartbeat_path(ad_dir)) < 6
    except OSError:
        return False


def state(ad_dir):
    stamp = 0
    for n in ("preview.html", os.path.join("versions", "history.json")):
        try:
            stamp = max(stamp, int(os.path.getmtime(os.path.join(ad_dir, n)) * 1000))
        except OSError:
            pass
    from . import redo
    return {"stamp": stamp, "pending": versions.pending(ad_dir),
            "listening": listening(ad_dir), "runner": redo.status(ad_dir)}


_seen = {}


def _fresh():
    """Pick up edits to the page code without a server restart, so a
    long-running server never writes pages in an out-of-date layout."""
    import importlib
    from . import page
    for mod in (versions, page):
        m = os.path.getmtime(mod.__file__)
        if _seen.setdefault(mod.__name__, m) != m:
            _seen[mod.__name__] = m
            importlib.reload(mod)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, path):
        path = posixpath.normpath(urllib.parse.unquote(path.split("?", 1)[0].split("#", 1)[0]))
        parts = [p for p in path.split("/") if p and p not in (".", "..")]
        # Two narrow extras: the shared text styles, and per-clip thumbnails
        # and proxies for the brand page. Nothing else under media/ is served.
        if parts == ["tool", "overlay.css"]:
            from .util import TEMPLATES
            return os.path.join(TEMPLATES, "overlay.css")
        if (len(parts) == 4 and parts[:2] == ["media", "clips"]
                and parts[3] in ("thumb.jpg", "proxy.mp4") and not parts[2].startswith(".")):
            return os.path.join(WORK, *parts)
        if not parts or parts[0] not in SERVED or any(p.startswith(".") for p in parts):
            return os.path.join(WORK, "__nope__")
        return os.path.join(WORK, *parts)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/state":
            try:
                ad = urllib.parse.parse_qs(u.query).get("ad", [""])[0]
                return self._json(200, state(ad_dir_for(ad)))
            except Fail as e:
                return self._json(400, {"error": str(e)})
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if rng and os.path.isfile(path):
            return self._range(path, rng)
        return SimpleHTTPRequestHandler.do_GET(self)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        SimpleHTTPRequestHandler.end_headers(self)

    def _range(self, path, rng):
        """Byte ranges, so videos can be scrubbed."""
        size = os.path.getsize(path)
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if not m:
            return self.send_error(416)
        a = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2) or 0))
        b = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
        b = min(b, size - 1)
        if a > b:
            return self.send_error(416)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (a, b, size))
        self.send_header("Content-Length", str(b - a + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(a)
            left = b - a + 1
            while left > 0:
                chunk = f.read(min(1 << 16, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_POST(self):
        if self.path != "/api/feedback":
            return self._json(404, {"error": "not found"})
        _fresh()
        # Same-origin only: a page on another site must not be able to post here.
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        if origin and urllib.parse.urlparse(origin).netloc != host:
            return self._json(403, {"error": "cross-origin"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            d = json.loads(self.rfile.read(min(n, 20000)) or b"{}")
            text = str(d.get("text", "")).strip()[:4000]
            redo, delete = bool(d.get("redo", False)), d.get("delete")
            if not text and not redo and delete is None:
                raise Fail("comment is empty")
            ad = ad_dir_for(d.get("ad"))
            t = d.get("t")
            added = versions.add_feedback(
                ad, int(d.get("version")), text, redo=redo,
                t=float(t) if t is not None else None,
                delete=int(delete) if delete is not None else None)
            if redo and not versions.pending(ad):
                raise Fail("add a comment first")
            if redo and not listening(ad):
                from . import redo as runner     # no chat is waiting: start Claude
                runner.start(ad)
            return self._json(200, dict(state(ad), added=added))
        except (Fail, ValueError, TypeError) as e:
            return self._json(400, {"error": str(e)})


def serve(port=None):
    port = int(port or config().get("preview_port", 8787))
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        raise Fail("port %d is busy (%s). Set another: adstudio config preview_port <n>" % (port, e))
    out("adstudio preview server on http://localhost:%d  (ctrl-c to stop)" % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def wait(ad_dir, timeout=None):
    """Block until the page sends feedback with Redo. Prints it and returns.

    A chat runs this in the background; when it exits the chat is woken with
    the feedback, applies it, snapshots, and waits again.
    """
    hb = heartbeat_path(ad_dir)
    os.makedirs(MEDIA, exist_ok=True)
    t0 = time.time()
    try:
        while True:
            p = versions.pending(ad_dir)
            if p:
                for fb in p:
                    if fb.get("t") is None:
                        out("FEEDBACK on v%d (whole video): %s" % (fb["version"], fb["text"]))
                    else:
                        out("FEEDBACK on v%d at %s [%s]: %s" % (
                            fb["version"], versions.tc(fb["t"]),
                            versions.where(ad_dir, fb["version"], fb["t"]), fb["text"]))
                return p
            with open(hb, "w") as f:
                f.write(str(time.time()))
            if timeout and time.time() - t0 > timeout:
                out("no feedback yet")
                return []
            time.sleep(1.0)
    finally:
        try:
            os.unlink(hb)
        except OSError:
            pass
