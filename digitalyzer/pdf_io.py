"""Einlesen von PDF-Scans und Bilddateien."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def _decode(data: bytes) -> np.ndarray | None:
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)


def _page_image(doc, page, render_dpi: int) -> np.ndarray:
    """Graustufenbild einer PDF-Seite.

    Bei gescannten PDFs wird das eingebettete Scanbild in *Originalaufloesung* entnommen
    (kein Qualitaetsverlust durch erneutes Rendern). Das gilt nur, wenn die Seite genau ein
    Bild enthaelt und dieses die Seite (fast) ganz bedeckt - sonst (mehrere Bilder,
    Vektorinhalt, kleines Bild wie ein Logo auf einer Textseite, nicht lesbares Bildformat)
    wird die Seite mit `render_dpi` gerendert.
    """
    import pymupdf  # PyMuPDF

    img = None
    imgs = page.get_images(full=True)
    if len(imgs) == 1:
        rects = page.get_image_rects(imgs[0][0])
        page_area = abs(page.rect)
        covered = sum(abs(r & page.rect) for r in rects) / page_area if page_area else 0.0
        if covered >= 0.85:
            info = doc.extract_image(imgs[0][0])
            img = _decode(info["image"])
            # Seitendrehung im PDF beruecksichtigen
            rot = page.rotation % 360
            if img is not None and rot:
                img = np.rot90(img, k={90: 3, 180: 2, 270: 1}[rot]).copy()
    if img is None:
        pix = page.get_pixmap(dpi=render_dpi, colorspace=pymupdf.csGRAY)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()
    return img


def _open_pdf(path: Path):
    """Oeffnet eine PDF-Datei; nicht lesbare Dateien ergeben eine verstaendliche Meldung."""
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception as e:
        raise ValueError("PDF kann nicht gelesen werden (beschaedigt oder kein PDF).") from e
    if doc.page_count == 0:
        doc.close()
        raise ValueError("PDF enthaelt keine Seiten.")
    return doc


def load_pages(path: str | Path, render_dpi: int = 300) -> list[np.ndarray]:
    """Liefert je Seite ein Graustufenbild (siehe `_page_image`)."""
    path = Path(path)
    if path.suffix.lower() in IMAGE_EXT:
        return [_load_image(path)]
    with _open_pdf(path) as doc:
        return [_page_image(doc, page, render_dpi) for page in doc]


def _load_image(path: Path) -> np.ndarray:
    # imdecode statt imread: funktioniert unter Windows auch mit Umlauten im Pfad
    img = _decode(path.read_bytes())
    if img is None or min(img.shape[:2]) == 0:
        raise ValueError("Bild kann nicht gelesen werden (beschaedigt oder unbekanntes Format).")
    return img


def page_count(path: str | Path) -> int:
    path = Path(path)
    if path.suffix.lower() in IMAGE_EXT:
        return 1
    with _open_pdf(path) as doc:
        return doc.page_count


def load_page(path: str | Path, index: int, render_dpi: int = 300) -> np.ndarray:
    """Eine einzelne Seite laden (fuer die schnelle Vorschau)."""
    path = Path(path)
    if path.suffix.lower() in IMAGE_EXT:
        return _load_image(path)
    with _open_pdf(path) as doc:
        if not 0 <= index < doc.page_count:
            raise KeyError(f"Seite {index + 1} gibt es nicht (das Dokument hat {doc.page_count} Seiten).")
        return _page_image(doc, doc[index], render_dpi)


def write_image(path: str | Path, img: np.ndarray, quality: int = 92) -> None:
    """Schreibt ein Bild (unicode-sichere Pfade unter Windows)."""
    path = Path(path)
    ext = path.suffix.lower()
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        raise IOError(f"Bild konnte nicht geschrieben werden: {path}")
    path.write_bytes(buf.tobytes())
