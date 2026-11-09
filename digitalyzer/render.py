"""Synthetische Seite: die erkannten Werte werden mit den gelernten Ziffernbildern
an exakt der Position der Originalziffern neu gezeichnet.

Im Vergleich (Blinken oder Differenzbild) mit dem Original bleiben richtig erkannte
Ziffern nahezu unsichtbar, falsch erkannte Ziffern leuchten auf.
"""
from __future__ import annotations

import cv2
import numpy as np


def glyph_slots(cell: dict, templates: dict) -> list[tuple[int, int, int, int]]:
    """Positionen der Ziffern fuer den aktuellen Wert einer Zelle."""
    value = cell.get("value") or ""
    x, y, w, h = cell["box"]
    glyphs = cell.get("glyphs") or []
    if len(glyphs) == len(value) and value:
        return [(g[0], y, g[2], h) for g in glyphs]
    # sonst rechtsbuendig mit typischen Ziffernbreiten setzen
    widths = [max(2, int(round(templates.get(int(d), {}).get("aspect", 0.55) * h))) for d in value if d.isdigit()]
    gap = max(1, int(h * 0.08))
    total = sum(widths) + gap * (len(widths) - 1)
    right = x + w
    slots = []
    cx = right - total
    for wd in widths:
        slots.append((cx, y, wd, h))
        cx += wd + gap
    return slots


def render_page(shape: tuple[int, int], cells: list[dict], templates: dict) -> np.ndarray:
    out = np.full(shape, 255, np.uint8)
    H, W = shape
    for cell in cells:
        value = cell.get("value") or ""
        if not value:
            continue
        for d, (gx, gy, gw, gh) in zip([c for c in value if c.isdigit()], glyph_slots(cell, templates)):
            t = templates.get(int(d))
            if t is None or gw <= 0 or gh <= 0:
                continue
            img = cv2.resize(t["img"], (gw, gh), interpolation=cv2.INTER_LINEAR)
            x0, y0 = max(0, gx), max(0, gy)
            x1, y1 = min(W, gx + gw), min(H, gy + gh)
            if x1 <= x0 or y1 <= y0:
                continue
            sub = img[y0 - gy:y1 - gy, x0 - gx:x1 - gx]
            out[y0:y1, x0:x1] = np.minimum(out[y0:y1, x0:x1], sub)
    return out


def save_templates(path, templates: dict) -> None:
    arrays = {}
    for d, t in templates.items():
        arrays[f"img_{d}"] = t["img"]
        arrays[f"aspect_{d}"] = np.array([t["aspect"]], np.float32)
    np.savez_compressed(path, **arrays)


def load_templates(path) -> dict:
    data = np.load(path)
    tpl = {}
    for d in range(10):
        if f"img_{d}" in data:
            tpl[d] = {"img": data[f"img_{d}"], "aspect": float(data[f"aspect_{d}"][0])}
    return tpl
