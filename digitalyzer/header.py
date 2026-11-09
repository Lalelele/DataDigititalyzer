"""Auslesen des Seitenkopfs (Probe, Wellenlaenge, Start-/Endwinkel, Schrittweite)."""
from __future__ import annotations

import difflib
import re

LABELS = {
    "wavelength": ["wavelength", "wellenlange", "lambda"],
    "start": ["starting angle", "start angle", "startwinkel"],
    "finish": ["finishing angle", "final angle", "end angle", "endwinkel"],
    "step": ["step", "schrittweite"],
    "sample": ["sample", "probe"],
}
_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _label_of(text: str) -> str | None:
    t = re.sub(r"[^a-z ]", "", text.lower()).strip()
    if not t:
        return None
    best, score = None, 0.0
    for key, names in LABELS.items():
        for n in names:
            r = difflib.SequenceMatcher(None, t, n).ratio()
            if r > score:
                best, score = key, r
    return best if score >= 0.72 else None


def _parse_joined(text: str) -> dict:
    """Fallback fuer zusammengeklebten Text ('Startingangle9.89Finishingangle:34.84Step:0.05').

    Bezeichnungen werden unscharf in der Buchstabenfolge gesucht; der Wert ist die erste
    Zahl nach der Bezeichnung.
    """
    letters = [(i, ch) for i, ch in enumerate(text.lower()) if ch.isalpha()]
    compact = "".join(ch for _, ch in letters)
    found: dict = {}
    for key, names in LABELS.items():
        best = (0.0, None)
        for name in names:
            n = name.replace(" ", "")
            for start in range(0, max(1, len(compact) - len(n) + 1)):
                r = difflib.SequenceMatcher(None, compact[start:start + len(n)], n).ratio()
                if r > best[0]:
                    best = (r, start + len(n) - 1)
        if best[0] >= 0.75 and best[1] is not None and best[1] < len(letters):
            end = letters[best[1]][0] + 1
            if key == "sample":
                found[key] = text[end:].lstrip(" :")
                continue
            m = _NUM.search(text, end)
            if m:
                try:
                    found[key] = float(m.group(0).replace(",", "."))
                except ValueError:
                    pass
    return found


def parse_header(tokens: list[tuple[str, float, tuple[float, float, float, float]]]) -> dict:
    """tokens: (Text, Score, (x, y, w, h)) aus der Texterkennung.

    Bezeichnungen werden unscharf erkannt ("Fiaishing angle" -> finish); der Wert ist die
    erste Zahl rechts davon auf derselben Zeile bzw. eine Zahl im selben Token.
    """
    out: dict = {"raw": [t[0] for t in tokens]}
    if not tokens:
        return out
    hs = sorted(t[2][3] for t in tokens)
    line_tol = hs[len(hs) // 2] * 0.6
    for text, _, (x, y, w, h) in tokens:
        lab = _label_of(text.split(":")[0])
        if not lab:
            continue
        cy = y + h / 2
        rest = text.split(":", 1)[1] if ":" in text else ""
        if lab == "sample":
            right = [t for t in tokens if t[2][0] > x + w * 0.5 and abs(t[2][1] + t[2][3] / 2 - cy) < line_tol]
            right.sort(key=lambda t: t[2][0])
            val = (rest + " " + " ".join(t[0] for t in right)).strip()
            out["sample"] = val
            continue
        m = _NUM.search(rest)
        if not m:
            right = [t for t in tokens if t[2][0] > x + w * 0.5 and abs(t[2][1] + t[2][3] / 2 - cy) < line_tol
                     and _NUM.search(t[0]) and not _label_of(t[0].split(":")[0])]
            right.sort(key=lambda t: t[2][0])
            m = _NUM.search(right[0][0]) if right else None
        if m:
            try:
                out[lab] = float(m.group(0).replace(",", "."))
            except ValueError:
                pass
    # Fallback: Zeilen zusammenfuegen und darin suchen (fehlende Leerzeichen, verklebte Woerter)
    if not all(k in out for k in ("start", "finish", "step")):
        lines: list[list] = []
        for t in sorted(tokens, key=lambda t: t[2][1] + t[2][3] / 2):
            cy = t[2][1] + t[2][3] / 2
            if lines and abs(cy - lines[-1][0]) < line_tol:
                lines[-1][1].append(t)
            else:
                lines.append([cy, [t]])
        for _, toks in lines:
            joined = " ".join(t[0] for t in sorted(toks, key=lambda t: t[2][0]))
            for k, v in _parse_joined(joined).items():
                if k == "sample" and "sample" in out:
                    continue
                out.setdefault(k, v)
    if all(k in out for k in ("start", "finish", "step")) and out["step"] > 0:
        out["expected_points"] = int(round((out["finish"] - out["start"]) / out["step"])) + 1
    return out
