"""Lokale Pruef-App: kleiner Webserver (nur Python-Standardbibliothek) + Browser-Oberflaeche.

Lauscht nur auf 127.0.0.1 - die Daten verlassen den Rechner nicht.
"""
from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import export
from .pipeline import load_project, page_image, save_project
from .validate import validate

STATIC = Path(__file__).parent / "static"


class ReviewState:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.project = load_project(self.out_dir)
        validate(self.project)
        self.lock = threading.Lock()
        self.by_id = {c["id"]: c for c in self.project["cells"]}
        self.synth_cache: dict[int, bytes] = {}

    def snapshot(self) -> dict:
        return {c["id"]: (c["status"], json.dumps(c["flags"], sort_keys=True), c["value"]) for c in self.project["cells"]}

    def update_cell(self, cid: str, action: str, value: str | None) -> dict:
        with self.lock:
            cell = self.by_id[cid]
            before = self.snapshot()
            if action == "bestaetigen":
                cell["human"] = "bestaetigt" if cell["value"] == cell.get("ocr_value") else "korrigiert"
            elif action == "korrigieren":
                v = "".join(ch for ch in (value or "") if ch.isdigit())
                cell["value"] = v
                cell["human"] = "korrigiert" if v != cell.get("ocr_value") else "bestaetigt"
            elif action == "zuruecksetzen":
                cell["value"] = cell.get("ocr_value", cell["value"])
                cell.pop("human", None)
            else:
                raise ValueError(action)
            summary = validate(self.project)
            save_project(self.out_dir, self.project)
            self.synth_cache.pop(cell["page"], None)
            after = self.snapshot()
            changed = [self._public(self.by_id[k]) for k in after if after[k] != before[k] or k == cid]
            return {"summary": summary, "changed": changed}

    @staticmethod
    def _public(c: dict) -> dict:
        return {k: c.get(k) for k in ("id", "value", "status", "flags", "human", "point", "angle")}

    def synthetic(self, page: int) -> bytes:
        with self.lock:
            if page not in self.synth_cache:
                self.synth_cache[page] = page_image(self.out_dir, self.project, page, "synthetisch")
            return self.synth_cache[page]


def make_handler(state: ReviewState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # ruhig bleiben
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            try:
                if not parts:
                    return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                if parts[0] == "static" and len(parts) == 2 and "/" not in parts[1] and ".." not in parts[1]:
                    f = STATIC / parts[1]
                    if f.is_file():
                        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                        if ctype.startswith("text/") or f.suffix == ".js":
                            ctype = ("text/javascript" if f.suffix == ".js" else ctype) + "; charset=utf-8"
                        return self._send(200, f.read_bytes(), ctype)
                if parts == ["api", "projekt"]:
                    with state.lock:
                        return self._json(state.project)
                if len(parts) == 4 and parts[:2] == ["api", "bild"]:
                    page, kind = int(parts[2]), parts[3]
                    if kind == "synthetisch":
                        return self._send(200, state.synthetic(page), "image/png")
                    return self._send(200, page_image(state.out_dir, state.project, page, kind), "image/jpeg")
                if parts == ["api", "export"]:
                    q = parse_qs(url.query)
                    fmt = q.get("format", ["csv"])[0]
                    with state.lock:
                        if fmt == "xy":
                            body, name = export.to_xy(state.project), "messwerte.xy"
                            ctype = "text/plain; charset=utf-8"
                        else:
                            body = "﻿" + export.to_csv(state.project, international=fmt == "csv-int")
                            name, ctype = "messwerte.csv", "text/csv; charset=utf-8"
                    stem = Path(state.project.get("source", "messwerte")).stem
                    return self._send(200, body.encode("utf-8"), ctype,
                                      {"Content-Disposition": f'attachment; filename="{stem}_{name}"'})
                self._send(404, b"nicht gefunden", "text/plain")
            except Exception as e:  # pragma: no cover - Fehler an die Oberflaeche melden
                self._json({"fehler": str(e)}, 500)

        def do_POST(self):
            url = urlparse(self.path)
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length) or b"{}")
                if url.path == "/api/zelle":
                    return self._json(state.update_cell(data["id"], data["aktion"], data.get("wert")))
                self._send(404, b"nicht gefunden", "text/plain")
            except Exception as e:
                self._json({"fehler": str(e)}, 400)

    return Handler


def serve(out_dir: str | Path, port: int = 8765, open_browser: bool = True) -> None:
    state = ReviewState(Path(out_dir))
    httpd = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), make_handler(state))
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit("Kein freier Port gefunden.")
    url = f"http://127.0.0.1:{port}/"
    print(f"Pruef-App laeuft: {url}   (beenden mit Strg+C)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet. Alle Aenderungen sind gespeichert.")
    finally:
        httpd.server_close()
