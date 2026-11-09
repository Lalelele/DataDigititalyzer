"""Erzeugt kuenstliche Scanseiten im Format (n, Zaehlrate) x 10 Paare je Zeile.

So lassen sich Raster, Begradigung und Erkennung ohne echte (ggf. vertrauliche)
Messdaten testen - mit bekannter Wahrheit.
"""
from __future__ import annotations

import cv2
import numpy as np

from digitalyzer.preprocess import rotate


def make_series(n_points: int, seed: int = 0) -> list[tuple[int, int]]:
    rng = np.random.default_rng(seed)
    x = np.arange(n_points)
    bg = 60 + 0.05 * x
    peaks = sum(a * np.exp(-0.5 * ((x - c) / 2.0) ** 2) for a, c in ((1500, 40), (600, 95), (2400, 150)))
    counts = rng.poisson(bg + peaks)
    ns = np.clip(5 + (x // 40), 1, 8)
    return [(int(n), int(c)) for n, c in zip(ns, counts)]


def render_page(pairs: list[tuple[int, int]], header: bool = True, pairs_per_row: int = 10,
                angle: float = 0.0, blur: float = 1.2, seed: int = 0,
                total_points: int | None = None, n_gray: int = 25,
                row_step: int = 22, kruemmung: float = 0.0,
                verblassen: float = 0.0) -> np.ndarray:
    """kruemmung: senkt die Zeilen zum linken Rand hin um bis zu so viele Pixel ab
    (gewoelbtes Blatt, wie bei Seite 3 des Neutronenbeugungs-Scans). Die Seitenmitte und
    die rechte Haelfte bleiben gerade, daher kann eine einzige Drehung das nicht ausgleichen.

    verblassen: Anteil (0..1), um den die Tinte am oberen Seitenrand heller ist als unten
    (ungleichmaessig belichteter oder verblasster Scan, wie beim Neutronenbeugungs-Scan
    Seite 32/33). Der Uebergang ist linear ueber die Seitenhoehe."""
    W, H = 1650, 2300
    img = np.full((H, W), 245, np.uint8)
    font, scale, th = cv2.FONT_HERSHEY_COMPLEX, 0.62, 1
    y = 180
    if header:
        cv2.putText(img, "Sample:   Test (Alloy 1 - 295 K)", (160, 140), font, 0.8, 30, 1, cv2.LINE_AA)
        cv2.putText(img, "Wavelength:   1.376 A    Starting angle:   9.89    Finishing angle:   "
                    f"{9.89 + 0.05 * ((total_points or len(pairs)) - 1):.2f}    Step:   0.05", (160, 190), font, 0.55, 30, 1, cv2.LINE_AA)
        y = 250
    col_x = []
    x = 175
    for _ in range(pairs_per_row):
        col_x.append((x, x + 70))  # n links, Zaehlrate rechtsbuendig
        x += 128
    for i in range(0, len(pairs), pairs_per_row):
        for k, (n, c) in enumerate(pairs[i:i + pairs_per_row]):
            xn, xc = col_x[k]
            cv2.putText(img, str(n), (xn, y), font, scale, n_gray, th, cv2.LINE_AA)
            s = str(c)
            (tw, _), _ = cv2.getTextSize(s, font, scale, th)
            cv2.putText(img, s, (xc + 40 - tw, y), font, scale, 25, th, cv2.LINE_AA)
        y += row_step
    cv2.putText(img, "Page 2", (780, 2150), font, 0.7, 30, 1, cv2.LINE_AA)
    if kruemmung:
        xm = W / 2
        xs = np.arange(W, dtype=np.float32)
        dy = kruemmung * np.clip((xm - xs) / xm, 0, None) ** 2  # Absenkung links, quadratisch
        map_x, map_y = np.meshgrid(xs, np.arange(H, dtype=np.float32))
        img = cv2.remap(img, map_x, map_y - dy[None, :], cv2.INTER_LINEAR, borderValue=245)
    if verblassen:
        staerke = 1.0 - verblassen * (1.0 - np.arange(H, dtype=np.float32) / H)  # oben blass
        img = (245.0 - (245.0 - img.astype(np.float32)) * staerke[:, None]).astype(np.uint8)
    rng = np.random.default_rng(seed)
    for _ in range(40):  # Staub
        cv2.circle(img, (int(rng.integers(0, W)), int(rng.integers(0, H))), int(rng.integers(1, 3)), 60, -1)
    img = cv2.copyMakeBorder(img, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=35)  # Scannerrand
    if angle:
        img = rotate(img, angle, border=35)
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    noise = rng.normal(0, 5, img.shape)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
