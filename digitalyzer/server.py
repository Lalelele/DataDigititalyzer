"""Lokale App: Projekte verwalten, Scans auswerten, Ergebnisse pruefen und exportieren.

Kleiner Webserver aus der Python-Standardbibliothek, lauscht nur auf 127.0.0.1 - die
Daten verlassen den Rechner nicht.

Arbeitsordner: jedes Dokument ist ein Projekt in einem eigenen Unterordner:
  <Arbeitsordner>/<Projekt>/scan.pdf      hochgeladene Datei (Kopie)
  <Arbeitsordner>/<Projekt>/info.json     Name, Herkunft, Einstellungen
  <Arbeitsordner>/<Projekt>/projekt.json  Ergebnis der Auswertung + Pruefung (siehe pipeline.py)
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import mimetypes
import re
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import export
from .pdf_io import IMAGE_EXT, load_page, page_count
from .pipeline import PROJECT_FILE, load_project, page_image, preview, process, save_project
from .settings import DESCRIPTION, Settings
from .validate import validate

STATIC = Path(__file__).parent / "static"
INFO_FILE = "info.json"
SCAN_EXT = {".pdf"} | IMAGE_EXT
MAX_UPLOAD = 500 * 1024 * 1024


# --------------------------------------------------------------------------- Pruefung
class ReviewState:
    """Ein ausgewertetes Projekt im Speicher; jede Aenderung wird sofort gespeichert."""

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


# --------------------------------------------------------------------------- Auswertung im Hintergrund
class Job:
    def __init__(self):
        self.running = True
        self.fraction = 0.0
        self.messages: list[str] = []
        self.error: str | None = None
        self.started = _dt.datetime.now().isoformat(timespec="seconds")
        self.finished: str | None = None

    def public(self) -> dict:
        return {"laeuft": self.running, "fortschritt": round(self.fraction, 3), "meldungen": self.messages[-200:],
                "fehler": self.error, "gestartet": self.started, "beendet": self.finished}


class App:
    def __init__(self, workspace: Path):
        self.ws = Path(workspace).expanduser().resolve()
        self.ws.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.reviews: dict[str, ReviewState] = {}
        self.jobs: dict[str, Job] = {}
        self.engine = None
        self.engine_lock = threading.Lock()
        self.page_cache: dict[tuple, object] = {}

    # ---------- Projekte ----------
    def project_dir(self, pid: str) -> Path:
        if not re.fullmatch(r"[\w\-. ]+", pid) or pid in (".", ".."):
            raise KeyError("Ungueltiger Projektname")
        d = self.ws / pid
        if not d.is_dir():
            raise KeyError(f"Projekt nicht gefunden: {pid}")
        return d

    @staticmethod
    def scan_file(d: Path) -> Path | None:
        for f in sorted(d.iterdir()):
            if f.is_file() and f.stem == "scan" and f.suffix.lower() in SCAN_EXT:
                return f
        return None

    def read_info(self, d: Path) -> dict:
        f = d / INFO_FILE
        info = {}
        if f.exists():
            try:
                info = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                info = {}
        info.setdefault("name", d.name)
        info.setdefault("einstellungen", Settings().to_dict())
        return info

    def write_info(self, d: Path, info: dict) -> None:
        (d / INFO_FILE).write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")

    def project_summary(self, d: Path) -> dict:
        info = self.read_info(d)
        scan = self.scan_file(d)
        out = {"id": d.name, "name": info.get("name", d.name), "quelle": info.get("quelle"),
               "erstellt": info.get("erstellt"), "scan": scan is not None, "ausgewertet": (d / PROJECT_FILE).exists()}
        job = self.jobs.get(d.name)
        if job:
            out["job"] = job.public() | {"meldungen": job.messages[-1:]}
        if out["ausgewertet"]:
            try:
                rs = self.reviews.get(d.name)
                summ = rs.project.get("summary") if rs else None
                if summ is None:
                    proj = load_project(d)
                    summ = proj.get("summary") or validate(proj)
                out["summary"] = {k: summ.get(k) for k in ("points", "ok", "pruefen", "fehler", "bestaetigt", "korrigiert")}
                out["summary"]["series"] = [{"points": s.get("points"), "expected": s.get("expected")}
                                            for s in summ.get("series", [])]
            except Exception as e:
                out["fehler"] = str(e)
        return out

    def list_projects(self) -> list[dict]:
        items = []
        for d in self.ws.iterdir():
            if d.is_dir() and (self.scan_file(d) or (d / PROJECT_FILE).exists()):
                items.append(self.project_summary(d))
        items.sort(key=lambda x: x.get("erstellt") or "", reverse=True)
        return items

    def create_project(self, filename: str, data: bytes) -> str:
        filename = Path(filename).name
        ext = Path(filename).suffix.lower()
        if ext not in SCAN_EXT:
            raise ValueError("Bitte eine PDF- oder Bilddatei (PNG, JPG, TIF) waehlen.")
        stem = re.sub(r"[^\w\-. ]+", "_", Path(filename).stem).strip(" .") or "scan"
        with self.lock:
            pid, k = stem, 2
            while (self.ws / pid).exists():
                pid, k = f"{stem}_{k}", k + 1
            d = self.ws / pid
            d.mkdir()
        (d / f"scan{ext}").write_bytes(data)
        self.write_info(d, {"name": stem, "quelle": filename,
                            "erstellt": _dt.datetime.now().isoformat(timespec="seconds"),
                            "einstellungen": Settings().to_dict()})
        return pid

    def review(self, pid: str) -> ReviewState:
        with self.lock:
            if pid not in self.reviews:
                self.reviews[pid] = ReviewState(self.project_dir(pid))
            return self.reviews[pid]

    # ---------- Vorschau ----------
    def page(self, pid: str, index: int):
        d = self.project_dir(pid)
        scan = self.scan_file(d)
        if scan is None:
            raise KeyError("Zu diesem Projekt gibt es keine Scan-Datei (nur Pruefung moeglich).")
        key = (pid, index)
        with self.lock:
            if key not in self.page_cache:
                if len(self.page_cache) > 8:
                    self.page_cache.clear()
                self.page_cache[key] = load_page(scan, index)
            return self.page_cache[key]

    def preview(self, pid: str, index: int, settings: dict | None) -> dict:
        st = Settings.from_dict(settings)
        img, info = preview(self.page(pid, index), st)
        return {"bild": "data:image/jpeg;base64," + base64.b64encode(img).decode("ascii"), "info": info}

    def info(self, pid: str) -> dict:
        d = self.project_dir(pid)
        out = self.project_summary(d)
        info = self.read_info(d)
        out["einstellungen"] = Settings.from_dict(info.get("einstellungen")).to_dict()
        scan = self.scan_file(d)
        out["seiten"] = page_count(scan) if scan else 0
        job = self.jobs.get(pid)
        if job:
            out["job"] = job.public()
        return out

    def save_settings(self, pid: str, settings: dict) -> dict:
        d = self.project_dir(pid)
        info = self.read_info(d)
        info["einstellungen"] = Settings.from_dict(settings).to_dict()
        self.write_info(d, info)
        return info["einstellungen"]

    # ---------- Auswertung ----------
    def start_analysis(self, pid: str, settings: dict | None) -> dict:
        d = self.project_dir(pid)
        scan = self.scan_file(d)
        if scan is None:
            raise KeyError("Zu diesem Projekt gibt es keine Scan-Datei.")
        with self.lock:
            if any(j.running for j in self.jobs.values()):
                raise RuntimeError("Es laeuft bereits eine Auswertung. Bitte warten, bis sie fertig ist.")
            job = Job()
            self.jobs[pid] = job
        st = Settings.from_dict(settings if settings is not None else self.read_info(d).get("einstellungen"))
        self.save_settings(pid, st.to_dict())
        info = self.read_info(d)

        def run():
            try:
                with self.engine_lock:
                    if self.engine is None:
                        job.messages.append("Lade Texterkennung ...")
                        from .recognize import RapidEngine
                        self.engine = RapidEngine()
                    engine = self.engine

                def log(msg: str):
                    job.messages.append(msg)

                def prog(frac: float, msg: str):
                    job.fraction = max(job.fraction, frac)

                process(scan, d, log=log, settings=st, progress=prog, engine=engine,
                        source_name=info.get("quelle") or scan.name)
                with self.lock:
                    self.reviews.pop(pid, None)  # neu laden
                job.fraction = 1.0
            except SystemExit as e:
                job.error = str(e)
            except Exception as e:  # pragma: no cover - Fehler sichtbar machen
                job.error = f"{type(e).__name__}: {e}"
                job.messages.append(traceback.format_exc(limit=3))
            finally:
                job.running = False
                job.finished = _dt.datetime.now().isoformat(timespec="seconds")

        threading.Thread(target=run, daemon=True).start()
        return job.public()

    def status(self, pid: str) -> dict:
        self.project_dir(pid)
        job = self.jobs.get(pid)
        return job.public() if job else {"laeuft": False, "fortschritt": 0, "meldungen": [], "fehler": None}


# --------------------------------------------------------------------------- HTTP
def make_handler(app: App):
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

        def _static(self, name: str):
            f = STATIC / name
            if not f.is_file():
                return self._send(404, b"nicht gefunden", "text/plain")
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if f.suffix == ".js":
                ctype = "text/javascript"
            if ctype.startswith("text/"):
                ctype += "; charset=utf-8"
            return self._send(200, f.read_bytes(), ctype)

        # ---- GET ----
        def do_GET(self):
            url = urlparse(self.path)
            parts = [unquote(p) for p in url.path.split("/") if p]
            try:
                if not parts:
                    return self._static("start.html")
                if parts[0] == "pruefen" and len(parts) == 2:
                    app.project_dir(parts[1])
                    return self._static("pruefen.html")
                if parts[0] == "static" and len(parts) == 2 and ".." not in parts[1]:
                    return self._static(parts[1])
                if parts == ["api", "projekte"]:
                    return self._json({"arbeitsordner": str(app.ws), "projekte": app.list_projects()})
                if parts == ["api", "einstellungen"]:
                    return self._json({"standard": Settings().to_dict(), "beschreibung": DESCRIPTION})
                if len(parts) >= 4 and parts[:2] == ["api", "p"]:
                    pid, rest = parts[2], parts[3:]
                    if rest == ["info"]:
                        return self._json(app.info(pid))
                    if rest == ["status"]:
                        return self._json(app.status(pid))
                    if rest == ["projekt"]:
                        rs = app.review(pid)
                        with rs.lock:
                            return self._json(rs.project)
                    if len(rest) == 3 and rest[0] == "bild":
                        rs = app.review(pid)
                        page, kind = int(rest[1]), rest[2]
                        if kind == "synthetisch":
                            return self._send(200, rs.synthetic(page), "image/png")
                        return self._send(200, page_image(rs.out_dir, rs.project, page, kind), "image/jpeg")
                    if rest == ["export"]:
                        return self._export(pid, parse_qs(url.query).get("format", ["tabelle"])[0])
                self._send(404, b"nicht gefunden", "text/plain")
            except KeyError as e:
                self._json({"fehler": str(e).strip("'\"")}, 404)
            except Exception as e:  # pragma: no cover
                self._json({"fehler": str(e)}, 500)

        def _export(self, pid: str, fmt: str):
            rs = app.review(pid)
            with rs.lock:
                if fmt == "xye":
                    body, name, ctype = export.to_xye(rs.project), "messwerte.xye", "text/plain; charset=utf-8"
                elif fmt == "xy":
                    body, name, ctype = export.to_xy(rs.project), "messwerte.xy", "text/plain; charset=utf-8"
                elif fmt.startswith("tabelle"):
                    body = "﻿" + export.to_table_csv(rs.project, international=fmt == "tabelle-int")
                    name, ctype = "tabelle.csv", "text/csv; charset=utf-8"
                else:
                    body = "﻿" + export.to_csv(rs.project, international=fmt == "csv-int")
                    name, ctype = "messpunkte.csv", "text/csv; charset=utf-8"
            stem = Path(rs.project.get("source", "messwerte")).stem
            fname = f"{stem}_{name}"
            ascii_name = re.sub(r"[^\w\-. ]", "_", fname)
            return self._send(200, body.encode("utf-8"), ctype, {
                "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(fname)}"})

        # ---- POST ----
        def do_POST(self):
            url = urlparse(self.path)
            parts = [unquote(p) for p in url.path.split("/") if p]
            try:
                length = int(self.headers.get("Content-Length", 0))
                if parts == ["api", "hochladen"]:
                    if length > MAX_UPLOAD:
                        return self._json({"fehler": "Datei zu gross"}, 413)
                    name = parse_qs(url.query).get("name", ["scan.pdf"])[0]
                    pid = app.create_project(name, self.rfile.read(length))
                    return self._json({"id": pid})
                data = json.loads(self.rfile.read(length) or b"{}")
                if len(parts) == 4 and parts[:2] == ["api", "p"]:
                    pid, action = parts[2], parts[3]
                    if action == "zelle":
                        return self._json(app.review(pid).update_cell(data["id"], data["aktion"], data.get("wert")))
                    if action == "vorschau":
                        return self._json(app.preview(pid, int(data.get("seite", 0)), data.get("einstellungen")))
                    if action == "einstellungen":
                        return self._json({"einstellungen": app.save_settings(pid, data.get("einstellungen") or {})})
                    if action == "analyse":
                        return self._json(app.start_analysis(pid, data.get("einstellungen")))
                self._send(404, b"nicht gefunden", "text/plain")
            except KeyError as e:
                self._json({"fehler": str(e).strip("'\"")}, 404)
            except (ValueError, RuntimeError) as e:
                self._json({"fehler": str(e)}, 400)
            except Exception as e:  # pragma: no cover
                self._json({"fehler": f"{type(e).__name__}: {e}"}, 500)

    return Handler


def default_workspace() -> Path:
    return Path.home() / "DataDigititalyzer"


def serve(workspace: str | Path | None = None, port: int = 8765, open_browser: bool = True,
          open_project: str | None = None) -> None:
    app = App(Path(workspace) if workspace else default_workspace())
    httpd = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), make_handler(app))
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit("Kein freier Port gefunden.")
    url = f"http://127.0.0.1:{port}/" + (f"pruefen/{quote(open_project)}" if open_project else "")
    print(f"DataDigititalyzer laeuft: {url}   (beenden mit Strg+C)")
    print(f"Arbeitsordner: {app.ws}")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet. Alle Aenderungen sind gespeichert.")
    finally:
        httpd.server_close()
