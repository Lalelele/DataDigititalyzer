"""Ziffernerkennung mit zwei unabhaengigen Verfahren.

A) RapidOCR (PaddleOCR-Modelle ueber ONNX, laeuft lokal ohne GPU) auf jedem Zellausschnitt,
   in zwei Vergroesserungsstufen (Bildvarianten).
B) Ein Ziffernklassifikator, der die Schrift *des jeweiligen Dokuments* lernt:
   Einzelziffern werden ausgeschnitten; Ziffern, bei denen A sicher ist, dienen als
   Trainingsbeispiele; danach wird jede Ziffer per k-naechste-Nachbarn neu klassifiziert.
   Weil alle Ziffern einer Seite aus derselben Schrift stammen und gleich unscharf sind,
   korrigiert die Mehrheit gleich aussehender Ziffern einzelne Fehllesungen von A.

Die Mittelwertbilder je Ziffer (Templates) werden ausserdem fuer die "synthetische Seite"
der Pruefansicht verwendet.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import cv2
import numpy as np

FEAT_H, FEAT_W = 20, 16
_BIAS = 0.35  # Rundung bei der Schaetzung der Ziffernanzahl aus der Breite (gemessen)
_LOOKALIKE = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1",
                            "i": "1", "!": "1", "]": "1", "[": "1", "S": "5", "s": "5", "B": "8",
                            "Z": "2", "z": "2", "g": "9", "q": "9", "b": "6", "G": "6"})


def digits_only(text: str) -> str:
    """Nur Ziffern behalten; typische Verwechslungen (O->0, l->1 ...) vorher umsetzen."""
    return re.sub(r"[^0-9]", "", text.translate(_LOOKALIKE))


# --------------------------------------------------------------------------------------
# A) RapidOCR
# --------------------------------------------------------------------------------------
class RapidEngine:
    """Duenne Huelle um RapidOCR (nur Erkennungsstufe, Zellen sind bereits ausgeschnitten)."""

    def __init__(self) -> None:
        import logging
        import warnings

        warnings.filterwarnings("ignore")
        # Die ONNX Runtime kann Nutzungsdaten an Microsoft senden - ausdruecklich abschalten,
        # die Verarbeitung soll vollstaendig lokal bleiben.
        try:
            import onnxruntime

            onnxruntime.disable_telemetry_events()
        except Exception:
            pass
        try:
            from rapidocr_onnxruntime import RapidOCR  # lokal, pip-installierbar
        except ImportError as e:
            import sys

            raise SystemExit(
                f"Die Texterkennung (rapidocr-onnxruntime) ist nicht installiert: {e}\n"
                f"Verwendetes Python: {sys.version.split()[0]}. Benoetigt wird 64-Bit-Python 3.11-3.13 "
                "(empfohlen 3.12) und:  py -3.12 -m pip install -r requirements.txt") from e

        self._ocr = RapidOCR()
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)

    def _rec(self, imgs: list[np.ndarray]) -> list[tuple[str, float]]:
        rec = getattr(self._ocr, "text_recognizer", None) or getattr(self._ocr, "text_rec")
        out = rec(imgs)
        res = out[0] if isinstance(out, tuple) else out
        return [(str(r[0]), float(r[1])) for r in res]

    def read_cells(self, norm: np.ndarray, boxes: list[tuple[int, int, int, int]], scale: float,
                   pad: int = 3, batch: int = 256, blur: float = 0.0) -> list[tuple[str, str, float]]:
        """Liest Zellen; liefert je Zelle (Ziffern, Rohtext, Score).

        blur: leichtes Weichzeichnen vor dem Lesen (verbindet duenne, zerrissene Striche)."""
        if blur > 0:
            norm = cv2.GaussianBlur(norm, (0, 0), blur)
        crops = []
        h_img, w_img = norm.shape
        for x, y, w, h in boxes:
            cr = norm[max(0, y - pad):min(h_img, y + h + pad), max(0, x - pad):min(w_img, x + w + pad)]
            cr = cv2.resize(cr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            cr = cv2.copyMakeBorder(cr, 8, 8, 16, 16, cv2.BORDER_CONSTANT, value=255)
            crops.append(cv2.cvtColor(cr, cv2.COLOR_GRAY2BGR))
        out: list[tuple[str, str, float]] = []
        for i in range(0, len(crops), batch):
            for raw, score in self._rec(crops[i:i + batch]):
                out.append((digits_only(raw), raw, score))
        return out

    def read_text(self, img: np.ndarray) -> list[tuple[str, float, tuple[float, float, float, float]]]:
        """Volle Texterkennung (Erkennung + Lesen) - fuer den Seitenkopf."""
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        res, _ = self._ocr(img)
        out = []
        for box, text, score in res or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append((str(text), float(score), (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))))
        return out


# --------------------------------------------------------------------------------------
# Ziffern-Segmentierung
# --------------------------------------------------------------------------------------
def _gap_segments(prof: np.ndarray) -> list[list[int]]:
    segs, start = [], None
    for i, v in enumerate(prof):
        if v > 0 and start is None:
            start = i
        elif v == 0 and start is not None:
            segs.append([start, i])
            start = None
    if start is not None:
        segs.append([start, len(prof)])
    return segs


def segment_glyphs(weak: np.ndarray, box: tuple[int, int, int, int], digit_w: float,
                   target: int | None = None) -> list[tuple[int, int, int, int]]:
    """Zerlegt eine Zelle in Einzelziffern (Seitenkoordinaten).

    Zuerst an Luecken im Spaltenprofil; durch Unschaerfe verschmolzene Ziffern werden
    anhand der typischen Ziffernbreite (bzw. der erwarteten Anzahl `target`) an den
    tiefsten Stellen des Profils getrennt; zerbrochene Ziffern werden zusammengefuegt.
    """
    x, y, w, h = box
    sub = weak[y:y + h, x:x + w] > 0
    if sub.size == 0 or not sub.any():
        return []
    prof = sub.sum(axis=0).astype(float)
    segs = _gap_segments(prof)
    # Fragmente (sehr schmal, z.B. abgerissener Strich) an Nachbarn haengen
    merged: list[list[int]] = []
    for s in segs:
        if merged and (s[1] - s[0] < digit_w * 0.25) and (s[0] - merged[-1][1] <= 2):
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    segs = merged

    def split_widest() -> bool:
        i = max(range(len(segs)), key=lambda k: segs[k][1] - segs[k][0])
        a, b = segs[i]
        if b - a < 4:
            return False
        lo, hi = a + max(2, int((b - a) * 0.3)), b - max(2, int((b - a) * 0.3))
        if hi <= lo:
            cut = (a + b) // 2
        else:
            cut = lo + int(np.argmin(prof[lo:hi]))
        segs[i:i + 1] = [[a, cut], [cut, b]]
        return True

    # natuerliche Trennung breiter Bloecke
    if target is None:
        changed = True
        while changed:
            changed = False
            for i, (a, b) in enumerate(list(segs)):
                k = int((b - a) / digit_w + _BIAS)
                if k >= 2:
                    step = (b - a) / k
                    cuts = [a]
                    for j in range(1, k):
                        g = a + step * j
                        lo, hi = int(g - step * 0.3), int(g + step * 0.3) + 1
                        cuts.append(lo + int(np.argmin(prof[lo:hi])) if hi > lo else int(g))
                    cuts.append(b)
                    segs[i:i + 1] = [[cuts[j], cuts[j + 1]] for j in range(k)]
                    changed = True
                    break
    else:
        guard = 0
        while len(segs) < target and guard < 10:
            if not split_widest():
                break
            guard += 1
        while len(segs) > target and len(segs) > 1:
            # kleinste Luecke schliessen
            gaps = [segs[k + 1][0] - segs[k][1] for k in range(len(segs) - 1)]
            k = int(np.argmin(gaps))
            segs[k:k + 2] = [[segs[k][0], segs[k + 1][1]]]

    out = []
    for a, b in segs:
        col = sub[:, a:b]
        ys = np.nonzero(col.any(axis=1))[0]
        if len(ys) == 0:
            continue
        out.append((x + a, y + int(ys[0]), b - a, int(ys[-1] - ys[0] + 1)))
    return out


def glyph_feature(norm: np.ndarray, gbox: tuple[int, int, int, int], cell_box: tuple[int, int, int, int]) -> np.ndarray:
    """Merkmalsvektor einer Ziffer: Grauwerte, seitenverhaeltnistreu auf 20x16 skaliert.

    Vertikal wird die Hoehe der ganzen Zelle verwendet (alle Ziffern gleich hoch),
    so bleibt die Lage innerhalb der Zeile erhalten.
    """
    gx, _, gw, _ = gbox
    _, cy, _, chh = cell_box
    pad = 1
    crop = norm[max(0, cy - pad):cy + chh + pad, max(0, gx - pad):gx + gw + pad]
    ink = 1.0 - crop.astype(np.float32) / 255.0
    h, w = ink.shape
    if h == 0 or w == 0:
        return np.zeros(FEAT_H * FEAT_W + 1, np.float32)
    s = FEAT_H / h
    nw = max(1, min(FEAT_W, int(round(w * s))))
    small = cv2.resize(ink, (nw, FEAT_H), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((FEAT_H, FEAT_W), np.float32)
    off = (FEAT_W - nw) // 2
    canvas[:, off:off + nw] = small
    v = canvas.ravel()
    v = v - v.mean()
    v = v / (np.linalg.norm(v) + 1e-6)
    return np.concatenate([v, [min(w / max(h, 1), 2.0) * 0.5]]).astype(np.float32)


# --------------------------------------------------------------------------------------
# B) dokumentspezifischer Ziffernklassifikator
# --------------------------------------------------------------------------------------
@dataclass
class GlyphModel:
    train_x: np.ndarray
    train_y: np.ndarray
    k: int = 7

    def predict(self, feats: np.ndarray, exclude: np.ndarray | None = None, chunk: int = 2048):
        """kNN-Klassifikation. `exclude[i]` = Index des Trainingsbeispiels, das die Abfrage i
        selbst ist (wird ignoriert, sonst wuerde jede Ziffer sich selbst bestaetigen)."""
        labels = np.zeros(len(feats), np.int8)
        conf = np.zeros(len(feats), np.float32)
        second = np.full(len(feats), -1, np.int8)
        if len(self.train_x) == 0:
            return labels - 1, conf, second
        for s in range(0, len(feats), chunk):
            sim = feats[s:s + chunk] @ self.train_x.T
            if exclude is not None:
                ex = exclude[s:s + chunk]
                rows = np.where(ex >= 0)[0]
                sim[rows, ex[rows]] = -np.inf
            k = min(self.k, sim.shape[1])
            idx = np.argpartition(-sim, k - 1, axis=1)[:, :k]
            for r in range(sim.shape[0]):
                w = np.maximum(sim[r, idx[r]], 0) + 1e-3
                votes = np.bincount(self.train_y[idx[r]], weights=w, minlength=10)
                order = np.argsort(-votes)
                labels[s + r] = order[0]
                second[s + r] = order[1] if votes[order[1]] > 0 else -1
                conf[s + r] = votes[order[0]] / votes.sum()
        return labels, conf, second


def build_templates(norm_pages: list[np.ndarray], glyphs: list[tuple[int, tuple, tuple]], labels: np.ndarray,
                    size: tuple[int, int] = (40, 28)) -> dict:
    """Mittelwertbild je Ziffer (fuer die synthetische Seite) + typische Breite je Ziffer."""
    th, tw = size
    acc = {d: [] for d in range(10)}
    widths = {d: [] for d in range(10)}
    for (page, gbox, cbox), lab in zip(glyphs, labels):
        if lab < 0 or len(acc[lab]) >= 300:
            continue
        gx, _, gw, _ = gbox
        _, cy, _, chh = cbox
        crop = norm_pages[page][cy:cy + chh, gx:gx + gw]
        if crop.size == 0:
            continue
        acc[lab].append(cv2.resize(crop, (tw, th), interpolation=cv2.INTER_AREA).astype(np.float32))
        widths[lab].append(gw / max(chh, 1))
    tpl = {}
    for d in range(10):
        if acc[d]:
            tpl[d] = {"img": np.mean(acc[d], axis=0).astype(np.uint8), "aspect": float(np.median(widths[d]))}
    return tpl


def collapse_repeats(s: str) -> str:
    """'1166' -> '16' (so wie eine CTC-Texterkennung gleiche Nachbarzeichen zusammenzieht)."""
    return "".join(ch for i, ch in enumerate(s) if i == 0 or s[i - 1] != ch)


def combine(cands: list[str]) -> tuple[str, int, list[str]]:
    """Mehrheitsentscheid. Liefert (Wert, Anzahl uebereinstimmender Verfahren, Alternativen).

    Reihenfolge: OCR-Varianten zuerst, Ziffernklassifikator zuletzt. Sonderfall: liest die
    OCR '6', der Ziffernklassifikator aber zwei Ziffern '66', dann hat die OCR gleiche
    Nachbarziffern zusammengezogen (bekannte Schwaeche) - der Klassifikator zaehlt die
    Ziffern geometrisch und wird bevorzugt.
    """
    present = [c for c in cands if c]
    if not present:
        return "", 0, []
    b = cands[-1]
    if b and len(set(b)) < len(b):
        others = [c for c in cands[:-1] if c]
        if others and all(c != b and collapse_repeats(b) == collapse_repeats(c) and len(c) < len(b) for c in others):
            return b, 1, sorted(set(others))
    cnt = Counter(present)
    (best, n), = cnt.most_common(1)
    # Gleichstand: das letzte Verfahren (Ziffernklassifikator) entscheidet
    ties = [v for v, k in cnt.items() if k == n]
    if len(ties) > 1 and cands[-1] in ties:
        best = cands[-1]
    alts = [v for v in cnt if v != best]
    return best, n, alts
