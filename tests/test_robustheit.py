"""Robustheit: ungewoehnliche Eingaben, nicht lesbare Dateien, abgebrochene Auswertung und
Schutz der lokalen App. Keine dieser Situationen darf zum Absturz oder Datenverlust fuehren."""
import http.client
import threading
from http.server import ThreadingHTTPServer

import cv2
import numpy as np
import pymupdf
import pytest

from digitalyzer import pipeline
from digitalyzer.pdf_io import load_page, load_pages, page_count
from digitalyzer.pipeline import prepare_page, preview, process
from digitalyzer.server import App, Job, make_handler
from synth import make_series, render_page


class Attrappe:
    """Ersatz fuer die Texterkennung (schnell, ohne Modelle): liest jede Zelle als '5'."""

    def __init__(self, fehler: bool = False):
        self.fehler = fehler

    def read_cells(self, norm, boxes, scale=1.0, blur=0.0):
        if self.fehler:
            raise RuntimeError("Texterkennung abgestuerzt")
        return [("5", "5", 0.9) for _ in boxes]

    def read_text(self, img):
        return []


# ------------------------------------------------------------------ Seiten ohne Tabelle
@pytest.mark.parametrize("art", ["rauschen", "schwarz", "leer", "linie", "winzig"])
def test_seite_ohne_tabelle_ergibt_leeres_raster(art):
    rng = np.random.default_rng(1)
    img = {
        "rauschen": rng.integers(0, 255, (1200, 900), dtype=np.uint8),
        "schwarz": np.full((1200, 900), 10, np.uint8),
        "leer": np.full((1200, 900), 245, np.uint8),
        "linie": cv2.line(np.full((1200, 900), 245, np.uint8), (50, 600), (850, 600), 20, 3),
        "winzig": np.full((20, 20), 200, np.uint8),
    }[art]
    lay = prepare_page(img).layout
    assert lay.columns == [] and lay.cells == []
    preview(img)  # Vorschau darf ebenfalls nicht abstuerzen


def test_farbbild_wird_verarbeitet():
    gray = render_page(make_series(200))
    for img in (cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(gray, cv2.COLOR_GRAY2BGRA)):
        assert len(prepare_page(img).layout.columns) == 20


# ------------------------------------------------------------------ Dateien lesen
def test_nicht_lesbare_dateien_geben_verstaendliche_meldung(tmp_path):
    (tmp_path / "kaputt.pdf").write_bytes(b"%PDF-1.4 kein pdf")
    (tmp_path / "leer.pdf").write_bytes(b"")
    (tmp_path / "kaputt.png").write_bytes(b"\x89PNG kein bild")
    for name in ("kaputt.pdf", "leer.pdf", "kaputt.png"):
        with pytest.raises(ValueError, match="kann nicht gelesen werden"):
            load_pages(tmp_path / name)
    with pytest.raises(ValueError):
        page_count(tmp_path / "kaputt.pdf")


def _pdf_mit_bild(path, bild, rect=None):
    cv2.imwrite(str(path.with_suffix(".png")), bild)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(rect or page.rect, filename=str(path.with_suffix(".png")))
    if rect is not None:
        page.insert_text((200, 400), "Text auf der Seite", fontsize=20)
    doc.save(path)
    doc.close()


def test_scanbild_in_originalaufloesung_kleines_bild_wird_gerendert(tmp_path):
    bild = render_page(make_series(100))
    _pdf_mit_bild(tmp_path / "scan.pdf", bild)
    assert load_pages(tmp_path / "scan.pdf")[0].shape == bild.shape  # eingebettetes Bild, unveraendert
    # kleines Bild (z. B. Logo) auf einer Textseite: ganze Seite rendern, nicht nur das Bild
    _pdf_mit_bild(tmp_path / "logo.pdf", bild, pymupdf.Rect(20, 20, 160, 220))
    seite = load_pages(tmp_path / "logo.pdf", render_dpi=100)[0]
    assert abs(seite.shape[0] - 842 / 72 * 100) <= 1 and abs(seite.shape[1] - 595 / 72 * 100) <= 1
    with pytest.raises(KeyError, match="Seite 3"):
        load_page(tmp_path / "scan.pdf", 2)


def test_nicht_lesbare_datei_hinterlaesst_keinen_projektordner(tmp_path):
    (tmp_path / "kaputt.pdf").write_bytes(b"kein pdf")
    with pytest.raises(ValueError):
        process(tmp_path / "kaputt.pdf", tmp_path / "out", log=lambda m: None, engine=Attrappe())
    assert not (tmp_path / "out").exists()


# ------------------------------------------------------------------ abgebrochene Auswertung
def test_abgebrochene_auswertung_laesst_bisheriges_ergebnis_unveraendert(tmp_path):
    cv2.imwrite(str(tmp_path / "s.png"), render_page(make_series(100), angle=1.0))
    out = tmp_path / "out"
    alt = process(tmp_path / "s.png", out, log=lambda m: None, engine=Attrappe())
    bild_alt = (out / alt["pages"][0]["original"]).read_bytes()
    json_alt = (out / pipeline.PROJECT_FILE).read_text(encoding="utf-8")
    # neue Auswertung mit anderer Vergroesserung bricht in der Texterkennung ab
    st = pipeline.Settings(vergroesserung=2.0)
    with pytest.raises(RuntimeError):
        process(tmp_path / "s.png", out, log=lambda m: None, engine=Attrappe(fehler=True), settings=st)
    # Projektdatei und Seitenbilder passen weiter zusammen (gleiche Bildgroesse wie im Projekt)
    assert (out / pipeline.PROJECT_FILE).read_text(encoding="utf-8") == json_alt
    assert (out / alt["pages"][0]["original"]).read_bytes() == bild_alt


# ------------------------------------------------------------------ App
@pytest.fixture()
def app(tmp_path):
    return App(tmp_path / "ws")


def test_upload_nicht_lesbarer_datei_legt_kein_projekt_an(app):
    with pytest.raises(ValueError, match="PDF kann nicht gelesen werden"):
        app.create_project("messung.pdf", b"%PDF-1.4 kaputt")
    with pytest.raises(ValueError, match="Bild kann nicht gelesen werden"):
        app.create_project("messung.png", b"kein bild")
    assert app.list_projects() == [] and list(app.ws.iterdir()) == []


def test_korrektur_waehrend_laufender_auswertung_wird_abgelehnt(app):
    ok, buf = cv2.imencode(".png", render_page(make_series(100)))
    pid = app.create_project("m.png", buf.tobytes())
    job = Job()
    app.jobs[pid] = job  # Auswertung laeuft
    with pytest.raises(RuntimeError, match="gerade neu ausgewertet"):
        app.update_cell(pid, "s1z1s1", "bestaetigen", None)


@pytest.fixture()
def server(app):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _anfrage(port, methode, pfad, headers=None, body=None):
    con = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    con.request(methode, pfad, body=body, headers=headers or {})
    r = con.getresponse()
    r.read()
    con.close()
    return r.status


def test_nur_anfragen_der_app_selbst(server):
    port = server
    assert _anfrage(port, "GET", "/api/projekte") == 200
    assert _anfrage(port, "GET", "/api/projekte", {"Host": f"localhost:{port}"}) == 200
    # fremder Host-Name (DNS-Rebinding) und fremder Ursprung (andere Webseite im Browser)
    assert _anfrage(port, "GET", "/api/projekte", {"Host": f"boese.example:{port}"}) == 403
    assert _anfrage(port, "POST", "/api/p/x/zelle", {"Origin": "http://boese.example"}, b"{}") == 403
    assert _anfrage(port, "POST", "/api/p/x/zelle", {"Origin": f"http://127.0.0.1:{port}"}, b"{}") == 404
    # statische Dateien nur aus dem static-Ordner
    assert _anfrage(port, "GET", "/static/start.js") == 200
    assert _anfrage(port, "GET", "/static/..%2Fserver.py") == 404
    assert _anfrage(port, "GET", "/static/%2Fetc%2Fpasswd") == 404
