"""Erkennung des Tabellenrasters (Spalten, Zeilen, Zellen) auf einer begradigten Seite.

Vorgehen (robust gegen Restschraeglage, leichte Blattkruemmung und Staub):
1. Spaltenbaender ueber das vertikale Tintenprofil finden.
2. Zeilen *je Spalte* ueber das horizontale Profil innerhalb des Bandes finden.
3. Zeilen der Spalten ueber ihre y-Position einander zuordnen (Nachbarspalte als Referenz,
   so dass eine langsame Drift von links nach rechts mitgefuehrt wird).
4. Kopfzeilen (Text, der ueber Spaltenluecken hinweg laeuft) abtrennen.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import cv2
import numpy as np

# leere Zeilen/Spalten erzeugen bei nanmedian harmlose Warnungen
warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)


@dataclass
class Cell:
    row: int
    col: int
    box: tuple[int, int, int, int]  # x, y, w, h im begradigten Seitenbild (Tintenumriss)
    empty: bool = False


@dataclass
class PageLayout:
    columns: list[tuple[int, int]]  # x0, x1 je Spaltenband
    row_y: np.ndarray  # (n_rows, n_cols) y-Mitte je Zeile/Spalte, NaN = keine Tinte
    cells: list[Cell] = field(default_factory=list)
    char_height: float = 0.0
    pitch: float = 0.0
    table_top: int = 0
    header_box: tuple[int, int, int, int] | None = None


def _runs(mask1d: np.ndarray) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, v in enumerate(mask1d):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask1d)))
    return runs


def remove_specks(mask: np.ndarray, ch: float, factor: float = 0.65) -> np.ndarray:
    """Entfernt Staubpunkte: kleine Flecken *ohne andere Tinte in der Naehe*.

    Bruchstuecke einer blassen, zerfallenen Ziffer liegen dicht beieinander und werden
    deshalb nicht entfernt - sie bilden zusammen (nach leichtem Aufweiten) eine Ziffer.
    """
    k = max(3, int(round(ch * 0.3))) | 1
    grown = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, labels, st, _ = cv2.connectedComponentsWithStats(grown, 8)
    small = (np.maximum(st[:, 2], st[:, 3]) - (k - 1)) < ch * factor
    small[0] = False
    out = mask.copy()
    out[small[labels] & (mask > 0)] = 0
    return out


def char_height(mask: np.ndarray) -> float:
    _, _, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    hs = st[1:, 3]
    ws = st[1:, 2]
    sel = hs[(hs > 6) & (hs < mask.shape[0] * 0.05) & (ws < hs * 2)]
    return float(np.median(sel)) if len(sel) else 14.0


def find_row_runs(profile: np.ndarray, ch: float, pitch: float | None = None,
                  run_h: float | None = None) -> list[tuple[float, float]]:
    """Zeilen in einem 1D-Profil: Bereiche mit Tinte; zu hohe Bereiche (durch Unschaerfe oder
    dichten Zeilenabstand zusammengewachsene Zeilen) werden an Minima geteilt.

    Die Anzahl Zeilen in einem zusammengewachsenen Block wird aus dem gemessenen
    Zeilenabstand `pitch` und der typischen Hoehe einer Einzelzeile `run_h` bestimmt.
    """
    if profile.max() <= 0:
        return []
    p = np.convolve(profile, np.ones(3) / 3, mode="same")
    on = p > max(p.max() * 0.04, 0.5)
    single = run_h or ch
    raw = _runs(on)
    # Bruchstuecke einer Ziffer (blasse/duenne Ziffern zerfallen senkrecht in Teile) wieder
    # zusammenfuegen, solange das Ergebnis nicht hoeher als eine Zeile wird
    merged: list[list[int]] = []
    for a, b in raw:
        if merged:
            pa, pb = merged[-1]
            if a - pb <= max(2, single * 0.35) and (b - pa) <= single * 1.3 and \
                    ((pb - pa) < single * 0.8 or (b - a) < single * 0.8):
                merged[-1][1] = b
                continue
        merged.append([a, b])
    runs = [(a, b) for a, b in merged if (b - a) >= ch * 0.35]
    out: list[tuple[float, float]] = []
    for a, b in runs:
        h = b - a
        if pitch:
            n = max(1, int(round((h - single) / pitch)) + 1)
        else:
            n = max(1, int(round(h / (ch * 1.35))))
        if n == 1 or h < single * 1.5:
            out.append((a, b))
            continue
        # an den n-1 tiefsten Minima teilen, nahe der gleichmaessigen Teilung
        step = (h - single) / (n - 1) if n > 1 else h
        cuts = [a]
        for k in range(1, n):
            guess = a + single / 2 + step * (k - 0.5)
            lo, hi = int(guess - step * 0.35), int(guess + step * 0.35)
            lo, hi = max(lo, a + 1), min(hi, b - 1)
            if hi <= lo:
                cuts.append(int(guess))
                continue
            cuts.append(lo + int(np.argmin(p[lo:hi])))
        cuts.append(b)
        out.extend((cuts[i], cuts[i + 1]) for i in range(n))
    return out


def _split_valleys(sm: np.ndarray, a: int, b: int, ch: float) -> list[tuple[int, int]]:
    """Teilt ein Spaltenband an tiefen Taelern (zwei Spalten, deren Luecke durch Unschaerfe zuwaechst)."""
    seg = sm[a:b]
    if len(seg) < ch * 1.2:
        return [(a, b)]
    peak = seg.max()
    best_i, best_v = None, None
    min_side = max(2, int(ch * 0.25))
    for i in range(min_side, len(seg) - min_side):
        v = seg[i]
        if v > 0.2 * peak or v != seg[max(0, i - 2):i + 3].min():
            continue
        left, right = seg[:i].max(), seg[i + 1:].max()
        if left > 0.45 * peak and right > 0.45 * peak and v < 0.35 * min(left, right):
            if best_v is None or v < best_v:
                best_i, best_v = i, v
    if best_i is None:
        return [(a, b)]
    cut = a + best_i
    return _split_valleys(sm, a, cut, ch) + _split_valleys(sm, cut + 1, b, ch)


def extended_ranges(cols: list[tuple[int, int]], width: int, ch: float) -> list[tuple[int, int]]:
    """x-Bereich je Spalte bis zur Mitte der Nachbarluecken.

    Rechtsbuendige lange Zahlen und leicht verzogene Seiten ragen ueber das (aus dem
    Gesamtprofil bestimmte) Spaltenband hinaus.
    """
    out = []
    for c, (x0, x1) in enumerate(cols):
        xa = (cols[c - 1][1] + x0) // 2 + 1 if c > 0 else max(0, x0 - int(ch))
        xb = (x1 + cols[c + 1][0]) // 2 if c + 1 < len(cols) else min(width, x1 + int(ch))
        out.append((xa, xb))
    return out


def _row_gap(mask: np.ndarray, a: int, cut: int, b: int, ch: float) -> float:
    """Median der zeilenweisen Luecke zwischen Tinte links und rechts von `cut`."""
    band = mask[:, a:b] > 0
    prof = band.sum(axis=1).astype(float)
    gaps = []
    for r0, r1 in find_row_runs(prof, ch):
        strip = band[int(r0):int(r1)]
        cols = strip.any(axis=0)
        left = np.nonzero(cols[:cut - a])[0]
        right = np.nonzero(cols[cut - a:])[0]
        if len(left) and len(right):
            gaps.append((cut - a + right[0]) - left[-1] - 1)
    return float(np.median(gaps)) if gaps else float("inf")


def estimate_pitch(profiles: list[np.ndarray], ch: float) -> float | None:
    """Zeilenabstand ueber die Autokorrelation der Spaltenprofile.

    Funktioniert auch, wenn sich die Ziffern uebereinanderliegender Zeilen beruehren
    (keine Luecken zwischen den Zeilen), weil nur die Periodizitaet ausgewertet wird.
    """
    lags = []
    lo, hi = max(3, int(ch * 0.9)), int(ch * 3.2)
    for p in profiles:
        if p.sum() == 0 or len(p) < hi * 4:
            continue
        nz = np.nonzero(p)[0]
        seg = p[nz[0]:nz[-1] + 1].astype(float)
        if len(seg) < hi * 4:
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, mode="full")[len(seg) - 1:]
        ac = ac / (ac[0] + 1e-9)
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] < 0.15:
            continue
        # erste deutliche Spitze bevorzugen (nicht ein Vielfaches des Abstands)
        for cand in range(lo, k):
            if ac[cand] >= 0.8 * ac[k] and ac[cand] >= ac[max(lo, cand - 1)] and ac[cand] >= ac[cand + 1]:
                k = cand
                break
        # parabolische Verfeinerung
        if lo < k < hi - 1:
            a_, b_, c_ = ac[k - 1], ac[k], ac[k + 1]
            den = a_ - 2 * b_ + c_
            k = k + (0.5 * (a_ - c_) / den if den else 0.0)
        lags.append(float(k))
    return float(np.median(lags)) if lags else None


def find_columns(mask: np.ndarray, ch: float) -> list[tuple[int, int]]:
    prof = (mask > 0).sum(axis=0).astype(float)
    smooth = np.convolve(prof, np.ones(3) / 3, mode="same")
    thr = max(smooth.max() * 0.08, 3)
    runs = _runs(smooth > thr)
    parts: list[tuple[int, int]] = []
    for a, b in runs:
        parts.extend(_split_valleys(smooth, a, b, ch))
    # Eine Trennung (Tal im Profil oder schmale Luecke) ist nur echt, wenn auch *zeilenweise*
    # eine deutliche Luecke besteht. Sonst wurde nur die fuehrende Ziffer mehrstelliger
    # Zahlen (z.B. die '1' bei 100..199) abgetrennt.
    # Grenze 1,0 Zeichenhoehen, gemessen an drei Neutronenbeugungs-Scans: der Abstand der
    # fuehrenden Ziffer zum Rest der Zahl betraegt 0 bis 0,42 Zeichenhoehen (je nach
    # Schreibmaschine/Scan), echte Spaltenluecken mindestens 2,6 Zeichenhoehen.
    # (Frueher 0,3 - zu knapp: auf einer Seite stand die '1' 5 px = 0,42 ch abgesetzt,
    # und die Zaehlratenspalte zerfiel in zwei Spalten.)
    joined: list[list[int]] = []
    for pa, pb in parts:
        if joined and pa - joined[-1][1] < ch * 0.6 and _row_gap(mask, joined[-1][0], pa, pb, ch) < ch * 1.0:
            joined[-1][1] = pb
        else:
            joined.append([pa, pb])
    merged = [(int(x0), int(x1)) for x0, x1 in joined]
    # nur Baender, die ueber eine nennenswerte Hoehe Tinte haben
    cols = []
    for a, b in merged:
        band = mask[:, a:b]
        rows_with_ink = (band.sum(axis=1) > 0).sum()
        if rows_with_ink > ch * 2.5 and (b - a) >= ch * 0.15:
            cols.append((int(a), int(b)))
    return cols


def analyze(mask: np.ndarray, weak_mask: np.ndarray | None = None, min_rows: int = 5,
            speck: float = 0.65, pitch_override: float = 0.0) -> PageLayout:
    """Analysiert eine begradigte Tintenmaske und liefert das Zellraster.

    mask:      strenge Maske (Otsu) - fuer die Spaltentrennung (schmale Luecken bleiben offen)
    weak_mask: grosszuegige Maske - fuer Zeilen und Zellumrisse (blasse Ziffern wie '1')
    """
    ch = char_height(mask)
    cols = find_columns(mask, ch)
    if weak_mask is not None:
        mask = remove_specks(weak_mask, ch, speck) if speck > 0 else weak_mask
    if not cols:
        return PageLayout(columns=[], row_y=np.zeros((0, 0)), char_height=ch)

    ext0 = extended_ranges(cols, mask.shape[1], ch)
    profiles0 = [(mask[:, a_:b_] > 0).sum(axis=1).astype(float) for a_, b_ in ext0]
    # Zeilenabstand ueber Autokorrelation - robust auch bei sich beruehrenden Zeilen
    pitch0 = pitch_override if pitch_override > 0 else estimate_pitch(profiles0, ch)
    # typische Hoehe einer einzelnen Zeile (Median der nicht zusammengewachsenen Bloecke)
    hs0 = np.array([b_ - a_ for p_ in profiles0 for a_, b_ in find_row_runs(p_, ch)], float)
    if pitch0 is not None and len(hs0):
        hs0 = hs0[hs0 < pitch0 * 1.2]
    run_h = float(np.median(hs0)) if len(hs0) else ch

    def rows_per_column(cols_):
        ext_ = extended_ranges(cols_, mask.shape[1], ch)
        out = []
        for a_, b_ in ext_:
            prof = (mask[:, a_:b_] > 0).sum(axis=1).astype(float)
            out.append(find_row_runs(prof, ch, pitch0, run_h))
        return out

    per_col = rows_per_column(cols)
    # Spalten mit sehr wenigen Zeilen (Staub, Randmarken, Seitenzahl) oder am Bildrand verwerfen
    counts = np.array([len(r) for r in per_col])
    edge = max(3, int(mask.shape[1] * 0.01))
    at_edge = np.array([a_ <= edge or b_ >= mask.shape[1] - edge for a_, b_ in cols])
    # Textspalten bestehen aus Zeilen in Zeichenhoehe; Papierkanten/Schatten liefern
    # durchgehende oder zerrissene Streifen
    # (Bezug: typische Zeilenhoehe der ganzen Seite - unabhaengig von der Unschaerfe)
    all_h = np.array([b_ - a_ for rr in per_col for a_, b_ in rr], float)
    typ_h = float(np.median(all_h)) if len(all_h) else ch

    def text_like(rr):
        if not rr:
            return False
        hs = np.array([b_ - a_ for a_, b_ in rr], float)
        return float(np.mean((hs >= typ_h * 0.6) & (hs <= typ_h * 1.5))) >= 0.6
    shape_ok = np.array([text_like(rr) for rr in per_col])
    keep_c = (counts >= max(min_rows, 0.3 * counts.max())) & ~at_edge & shape_ok
    if not keep_c.all():
        cols = [c for c, k in zip(cols, keep_c) if k]
        per_col = rows_per_column(cols)

    # Zeilenabstand (pitch)
    diffs = np.concatenate([np.diff([(r0 + r1) / 2 for r0, r1 in rr]) for rr in per_col if len(rr) > 2])
    diffs = diffs[diffs > ch * 0.8]
    pitch = float(np.median(diffs)) if len(diffs) else (pitch0 or ch * 1.5)
    if pitch_override > 0:
        pitch = pitch_override

    centers = [np.array([(r0 + r1) / 2 for r0, r1 in rr]) for rr in per_col]
    row_y = _match_rows(centers, pitch)

    # Spalten, deren Zeilen nicht zum gemeinsamen Raster passen (Randstoerungen), verwerfen
    if row_y.shape[1] > 2:
        ok = _grid_consistent(row_y, pitch)
        if not ok.all():
            cols = [c for c, k in zip(cols, ok) if k]
            per_col = rows_per_column(cols)
            centers = [np.array([(r0 + r1) / 2 for r0, r1 in rr]) for rr in per_col]
            row_y = _match_rows(centers, pitch)

    # Duenn belegte Zeilen (Staub zwischen den Zeilen, Einzelmarken) verwerfen.
    # Ausnahme: linksbuendig gefuellte Teilzeile (letzte Zeile einer Messreihe).
    n_cols = len(cols)
    fin = np.isfinite(row_y)
    filled = fin.sum(axis=1)
    dense = filled >= 0.3 * n_cols
    last_dense = int(np.max(np.where(dense)[0])) if dense.any() else -1
    # nur direkt nach der letzten vollen Zeile ist eine linksbuendige Teilzeile erlaubt
    left_contig = np.array([f > 0 and fin[r, :f].all() and r == last_dense + 1 for r, f in enumerate(filled)])
    sparse = ~dense & ~left_contig
    row_y = row_y[~sparse]

    # Tabellenblock: laengster Block von Zeilen mit regelmaessigem Abstand.
    # Kopf (Probe, Wellenlaenge ...) und Fusszeile (Seitenzahl) liegen mit groesserem
    # Abstand darueber/darunter und fallen so heraus.
    filled = np.isfinite(row_y).sum(axis=1)
    ymed = np.array([np.nanmedian(r) if f else np.nan for r, f in zip(row_y, filled)])
    blocks: list[list[int]] = []
    for r in np.where(filled > 0)[0]:
        if blocks and ymed[r] - ymed[blocks[-1][-1]] < pitch * 1.45:
            blocks[-1].append(int(r))
        else:
            blocks.append([int(r)])
    best = max(blocks, key=lambda bl: int(filled[bl].sum()))
    row_y = row_y[best[0]:best[-1] + 1]

    table_top = int(np.nanmin(row_y) - pitch * 0.6) if row_y.size else 0
    layout = PageLayout(columns=cols, row_y=row_y, char_height=ch, pitch=pitch, table_top=table_top)
    if table_top > ch:
        layout.header_box = (0, 0, mask.shape[1], max(0, table_top))
    layout.cells = _build_cells(mask, layout)
    return layout


def _grid_consistent(row_y: np.ndarray, pitch: float, max_scatter: float = 0.2,
                     max_offset: float = 0.4) -> np.ndarray:
    """Prueft je Spalte, ob ihre Zeilen zum gemeinsamen Zeilenraster passen.

    Die Abweichung jeder Spalte von der Zeilenmitte (Median ueber alle Spalten) wird in
    zwei Anteile zerlegt:

    - **Versatz**: der systematische Anteil (Median der Abweichung). Bei gekruemmten oder
      gewoelbten Blaettern liegen die aeusseren Spalten durchgehend etwas hoeher oder
      tiefer als die Seitenmitte, weil die Begradigung nur *einen* Winkel je Seite
      korrigiert. Das ist unschaedlich, die Zeilen werden je Spalte gefunden.
    - **Streuung**: die Abweichung um diesen Versatz. Echte Textspalten sind sehr
      regelmaessig (typisch < 0,05 Zeilenabstaende); Stoerungen am Rand (Lochung, Schatten,
      Notizen) liegen dagegen zufaellig zum Raster (Streuung um 0,25 Zeilenabstaende).

    Verworfen wird nur bei grosser Streuung oder einem Versatz nahe einem halben
    Zeilenabstand (dann ist die Zeilenzuordnung nicht mehr eindeutig).
    Rueckgabe: boolesches Array je Spalte (True = behalten).
    """
    med = np.nanmedian(row_y, axis=1, keepdims=True)
    d = row_y - med
    versatz = np.nanmedian(d, axis=0)
    streuung = np.nanmedian(np.abs(d - versatz), axis=0)
    # Spalten ganz ohne Zeilen (NaN) werden hier nicht bewertet (wie bisher: behalten)
    return ~((streuung > pitch * max_scatter) | (np.abs(versatz) > pitch * max_offset))


def _match_rows(centers: list[np.ndarray], pitch: float) -> np.ndarray:
    """Ordnet die Zeilenpositionen aller Spalten einem gemeinsamen Zeilenindex zu.

    Start bei der Spalte mit den meisten Zeilen; dann schrittweise nach links und rechts,
    jeweils mit der Nachbarspalte als Referenz (fuehrt Drift durch Restschraeglage mit).
    """
    n_cols = len(centers)
    ref = int(np.argmax([len(c) for c in centers]))
    # Index der Referenzspalte nach Abstand vergeben (Luecken = fehlende Zeilen, z.B.
    # zwischen Tabelle und Fusszeile), nicht einfach fortlaufend
    ref_map: dict[int, float] = {}
    idx = 0
    for i, y in enumerate(centers[ref]):
        if i:
            idx += max(1, int(round((y - centers[ref][i - 1]) / pitch)))
        ref_map[idx] = float(y)
    assign: dict[int, dict[int, float]] = {ref: ref_map}

    def match(col: int, prev: int) -> None:
        prev_map = assign[prev]
        prev_idx = np.array(sorted(prev_map))
        prev_y = np.array([prev_map[i] for i in prev_idx])
        ys = centers[col]
        res: dict[int, float] = {}
        if len(ys) == 0 or len(prev_y) == 0:
            assign[col] = res
            return
        d = np.array([y - prev_y[np.argmin(np.abs(prev_y - y))] for y in ys])
        shift = float(np.median(d)) if abs(np.median(d)) < pitch / 2 else 0.0
        for y in ys:
            k = int(np.argmin(np.abs(prev_y + shift - y)))
            off = y - prev_y[k] - shift
            # bei Abweichung: vom naechsten Nachbarn aus hochrechnen (nicht vom
            # Tabellenanfang, sonst summiert sich ein Fehler im Zeilenabstand auf)
            idx = int(prev_idx[k]) + int(round(off / pitch))
            exp_y = prev_y[k] + shift + round(off / pitch) * pitch
            if idx not in res or abs(res[idx] - exp_y) > abs(y - exp_y):
                res[idx] = float(y)
        assign[col] = res

    for c in range(ref + 1, n_cols):
        match(c, c - 1 if assign.get(c - 1) else ref)
    for c in range(ref - 1, -1, -1):
        match(c, c + 1 if assign.get(c + 1) else ref)

    all_idx = sorted({i for m in assign.values() for i in m})
    lo = min(all_idx)
    row_y = np.full((max(all_idx) - lo + 1, n_cols), np.nan)
    for c, m in assign.items():
        for i, y in m.items():
            row_y[i - lo, c] = y
    return row_y


def _assign_segments(segs: list[tuple[int, int]], cols: list[tuple[int, int]],
                     ch: float) -> list[tuple[int, int, int]]:
    """Ordnet die Tintenbloecke einer Zeile (x-Bereiche, von links nach rechts) den Spalten zu.

    1. Bloecke, die ein Spaltenband ueberlappen, gehoeren zur Spalte mit der groessten
       Ueberlappung.
    2. Bloecke in einer Luecke zwischen zwei Baendern (z. B. die etwas abgesetzte fuehrende
       '1' einer vierstelligen Zaehlrate) gehoeren zu dem *benachbarten Tintenblock* mit der
       kleineren Luecke - Ziffern einer Zahl stehen dichter beieinander als zwei Zahlen.
       Der Abstand zum Spaltenband allein ist hier unzuverlaessig: er unterscheidet sich oft
       nur um wenige Pixel.
    3. Ohne nahen Nachbarblock: naechstgelegenes Spaltenband (wie bisher); Bloecke weit
       ausserhalb aller Spalten werden verworfen.

    Rueckgabe: Liste (xa, xb, Spalte).
    """
    zuordnung: list[int | None] = []
    for xa, xb in segs:
        ov = np.array([max(0, min(xb, c1) - max(xa, c0)) for c0, c1 in cols])
        zuordnung.append(int(np.argmax(ov)) if ov.max() > 0 else None)
    out = []
    for i, (xa, xb) in enumerate(segs):
        c = zuordnung[i]
        if c is None:
            # naechster zugeordneter Nachbarblock links und rechts
            links = next((j for j in range(i - 1, -1, -1) if zuordnung[j] is not None), None)
            rechts = next((j for j in range(i + 1, len(segs)) if zuordnung[j] is not None), None)
            gap_l = xa - segs[links][1] if links is not None else np.inf
            gap_r = segs[rechts][0] - xb if rechts is not None else np.inf
            if min(gap_l, gap_r) < ch * 0.8 and gap_l != gap_r:
                c = zuordnung[links] if gap_l < gap_r else zuordnung[rechts]
            else:
                dist = np.array([max(c0 - xb, xa - c1, 0) for c0, c1 in cols])
                c = int(np.argmin(dist))
                if dist[c] > ch * 1.5:
                    continue  # Stoerung weit ausserhalb der Spalten
        out.append((xa, xb, c))
    return out


def _build_cells(mask: np.ndarray, lay: PageLayout) -> list[Cell]:
    """Zellen bilden: jeder Tintenblock einer Zeile wird der Spalte zugeordnet, mit der er
    sich am staerksten ueberlappt (bzw. der naechstgelegenen).

    Feste Zellgrenzen wuerden bei engen Luecken (rechtsbuendige Zahl direkt vor der
    naechsten Spalte) Teile der Nachbarziffer in die Zelle ziehen.
    """
    cells = []
    half = lay.pitch * 0.5
    cols = lay.columns
    if not cols:
        return cells
    x_lo = max(0, cols[0][0] - int(lay.char_height * 2))
    x_hi = min(mask.shape[1], cols[-1][1] + int(lay.char_height * 2))
    centers = np.array([(a + b) / 2 for a, b in cols])
    for r in range(lay.row_y.shape[0]):
        ys = lay.row_y[r]
        y_ref = float(np.nanmedian(ys)) if np.isfinite(ys).any() else None
        groups: dict[int, list[tuple[int, int, int, int]]] = {}
        if y_ref is not None:
            # leichte Drift ueber die Zeile: y je Spalte interpolieren
            idx = np.where(np.isfinite(ys))[0]
            y0, y1 = int(max(0, y_ref - half)), int(min(mask.shape[0], y_ref + half))
            strip = mask[y0:y1, x_lo:x_hi] > 0
            prof = strip.sum(axis=0)
            start = None
            segs = []
            for i, v in enumerate(list(prof) + [0]):
                if v and start is None:
                    start = i
                elif not v and start is not None:
                    segs.append((start, i))
                    start = None
            for a, b, c in _assign_segments([(a + x_lo, b + x_lo) for a, b in segs], cols, lay.char_height):
                xa, xb = a, b
                # Hoehe innerhalb der Zelle (lokale Zeilenposition der Spalte)
                yc = ys[c] if np.isfinite(ys[c]) else y_ref
                ya, yb = int(max(0, yc - half)), int(min(mask.shape[0], yc + half))
                sub = mask[ya:yb, xa:xb] > 0
                rows_ = np.nonzero(sub.any(axis=1))[0]
                if len(rows_) == 0:
                    continue
                groups.setdefault(c, []).append((xa, ya + int(rows_[0]), xb - xa, int(rows_[-1] - rows_[0] + 1)))
        for c, (x0, x1) in enumerate(cols):
            parts = groups.get(c)
            yc = ys[c] if np.isfinite(ys[c]) else (y_ref if y_ref is not None else 0)
            if not parts:
                cells.append(Cell(r, c, (x0, int(yc - lay.char_height / 2), x1 - x0, int(lay.char_height)), empty=True))
                continue
            xa = min(p[0] for p in parts)
            ya = min(p[1] for p in parts)
            xb = max(p[0] + p[2] for p in parts)
            yb = max(p[1] + p[3] for p in parts)
            # Hoehe begrenzen: mehr als ~1.6 Zeichenhoehen sind Stoerungen der Nachbarzeile
            if yb - ya > lay.char_height * 1.6:
                ya = int(yc - lay.char_height * 0.6)
                yb = int(yc + lay.char_height * 0.6)
            cells.append(Cell(r, c, (int(xa), int(ya), int(xb - xa), int(yb - ya))))
    return cells
