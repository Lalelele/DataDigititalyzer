"""Bildvorverarbeitung: Hintergrundausgleich, Begradigung, Binarisierung."""
from __future__ import annotations

import cv2
import numpy as np


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def normalize_background(gray: np.ndarray, kernel: int = 51) -> np.ndarray:
    """Teilt das Bild durch eine stark geglaettete Kopie.

    Gleicht Vergilbung, ungleichmaessige Ausleuchtung und graue Scanflaechen aus.
    Ergebnis: Papier ~255, Tinte dunkel.
    """
    k = kernel | 1
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k // 3 | 1, k // 3 | 1)))
    bg = cv2.GaussianBlur(bg, (k, k), 0)
    norm = cv2.divide(gray, bg, scale=255)
    return norm


def ink_mask(norm: np.ndarray) -> np.ndarray:
    """Binaere Maske der Tinte (255 = Tinte). Otsu auf dem normalisierten Bild."""
    _, mask = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return mask


def weak_ink_mask(norm: np.ndarray, level: int = 200) -> np.ndarray:
    """Grosszuegige Maske, die auch blasse/duenne Striche (z.B. '1') vollstaendig erfasst."""
    t, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    thr = max(t, min(level, (t + 255) / 2))
    return np.where(norm < thr, 255, 0).astype(np.uint8)


def remove_border_noise(mask: np.ndarray, margin_frac: float = 0.02) -> np.ndarray:
    """Entfernt grosse/dunkle Flaechen am Bildrand (Scannerdeckel, Schatten)."""
    h, w = mask.shape
    out = mask.copy()
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    mh, mw = int(h * margin_frac), int(w * margin_frac)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        touches = x <= mw or y <= mh or x + bw >= w - mw or y + bh >= h - mh
        huge = bw > w * 0.3 or bh > h * 0.3
        if touches or huge:
            out[labels == i] = 0
    return out


def paper_mask(gray: np.ndarray, erode_frac: float = 0.025) -> np.ndarray:
    """Maske der Papierflaeche (255) - schwarze Scanraender/Deckel werden ausgeschlossen."""
    small = cv2.GaussianBlur(gray, (0, 0), 3)
    _, bright = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Text schliessen, damit die Papierflaeche zusammenhaengend ist
    k = max(15, int(min(gray.shape) * 0.02)) | 1
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    n, labels, st, _ = cv2.connectedComponentsWithStats(bright, 8)
    if n <= 1:
        return np.full_like(gray, 255)
    biggest = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    paper = np.where(labels == biggest, 255, 0).astype(np.uint8)
    # Loecher (Tabellen-Inhalt) fuellen: konvexe Huelle der Papierflaeche
    cnts, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
    paper = np.zeros_like(gray)
    cv2.fillPoly(paper, [hull], 255)
    e = max(3, int(min(gray.shape) * erode_frac))
    return cv2.erode(paper, cv2.getStructuringElement(cv2.MORPH_RECT, (e, e)))


def _projection_score(mask_small: np.ndarray, angle: float) -> float:
    h, w = mask_small.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rot = cv2.warpAffine(mask_small, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    prof = rot.sum(axis=1, dtype=np.float64)
    return float(np.var(np.diff(prof)))


def estimate_skew(mask: np.ndarray, max_angle: float = 6.0) -> float:
    """Schaetzt den Schraeglagewinkel (Grad) ueber die Schaerfe des Zeilenprofils.

    Grob-fein-Suche: zuerst in 0.5-Grad-Schritten, dann in 0.02-Grad-Schritten.
    Funktioniert unabhaengig von Tabellenlinien, weil eng gesetzte Textzeilen
    im korrekt begradigten Bild das schaerfste horizontale Profil liefern.
    """
    scale = 1000.0 / max(mask.shape)
    small = cv2.resize(mask, None, fx=scale * 2, fy=scale * 2, interpolation=cv2.INTER_AREA) if scale < 0.5 else mask
    best = 0.0
    for step, span in ((0.5, max_angle), (0.1, 0.6), (0.02, 0.12)):
        angles = np.arange(best - span, best + span + 1e-9, step)
        scores = [_projection_score(small, a) for a in angles]
        best = float(angles[int(np.argmax(scores))])
    return best


def rotate(img: np.ndarray, angle: float, border: int = 255) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=border)


def rotation_matrix(shape, angle: float) -> np.ndarray:
    h, w = shape[:2]
    return cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
