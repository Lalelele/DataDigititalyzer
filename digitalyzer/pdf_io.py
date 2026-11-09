"""Einlesen von PDF-Scans und Bilddateien."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def _decode(data: bytes) -> np.ndarray | None:
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)


def load_pages(path: str | Path, render_dpi: int = 300) -> list[np.ndarray]:
    """Liefert je Seite ein Graustufenbild.

    Bei gescannten PDFs wird das eingebettete Scanbild in *Originalaufloesung*
    entnommen (kein Qualitaetsverlust durch erneutes Rendern). Enthaelt eine Seite
    mehrere Bilder oder Vektorinhalt, wird sie mit `render_dpi` gerendert.
    """
    path = Path(path)
    if path.suffix.lower() in IMAGE_EXT:
        # imdecode statt imread: funktioniert unter Windows auch mit Umlauten im Pfad
        img = _decode(path.read_bytes())
        if img is None:
            raise ValueError(f"Bild kann nicht gelesen werden: {path}")
        return [img]

    import pymupdf  # PyMuPDF

    pages: list[np.ndarray] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            imgs = page.get_images(full=True)
            img = None
            if len(imgs) == 1:
                info = doc.extract_image(imgs[0][0])
                img = _decode(info["image"])
                # Seitendrehung im PDF beruecksichtigen
                rot = page.rotation % 360
                if img is not None and rot:
                    img = np.rot90(img, k={90: 3, 180: 2, 270: 1}[rot]).copy()
            if img is None:
                pix = page.get_pixmap(dpi=render_dpi, colorspace=pymupdf.csGRAY)
                img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()
            pages.append(img)
    return pages


def write_image(path: str | Path, img: np.ndarray, quality: int = 92) -> None:
    """Schreibt ein Bild (unicode-sichere Pfade unter Windows)."""
    path = Path(path)
    ext = path.suffix.lower()
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        raise IOError(f"Bild konnte nicht geschrieben werden: {path}")
    path.write_bytes(buf.tobytes())
