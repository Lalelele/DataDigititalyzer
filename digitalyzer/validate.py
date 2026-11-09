"""Plausibilitaetspruefung und Statusvergabe.

Arbeitet direkt auf dem Projekt-Dictionary (siehe pipeline.py) und kann nach jeder
Korrektur in der Pruefansicht erneut ausgefuehrt werden.

Status je Zelle:
  ok          - alle Erkennungsverfahren einig, keine Regel verletzt
  pruefen     - Verfahren uneinig oder schwacher Hinweis einer Regel
  fehler      - Regel verletzt (z.B. Detektoranzahl springt, Ausreisser, leere Zelle)
  bestaetigt  - von Hand geprueft und unveraendert uebernommen
  korrigiert  - von Hand geaendert
"""
from __future__ import annotations

import math

HUMAN = ("bestaetigt", "korrigiert")


def assign_kinds(project: dict) -> None:
    """Spaltentyp je Seite bestimmen: 'n' (Detektoranzahl, einstellig) oder 'count'.

    Paarweise Anordnung (n, Zaehlrate) wird erkannt, wenn sich schmale einstellige und
    breitere Spalten abwechseln. Sonst sind alle Spalten 'count'.
    """
    by_page: dict[int, dict[int, list[str]]] = {}
    for c in project["cells"]:
        by_page.setdefault(c["page"], {}).setdefault(c["col"], []).append(c["value"])
    kinds: dict[tuple[int, int], str] = {}
    for p, cols in by_page.items():
        single = {}
        for col, vals in cols.items():
            v = [x for x in vals if x]
            single[col] = (sum(1 for x in v if len(x) == 1) / len(v)) if v else 0
        ncols = len(cols)
        mode = (project.get("settings") or {}).get("paare", "auto")
        if mode == "ja":
            paired = ncols % 2 == 0
        elif mode == "nein":
            paired = False
        else:
            paired = ncols % 2 == 0 and all(single.get(i, 0) >= 0.8 for i in range(0, ncols, 2)) \
                and sum(single.get(i, 0) for i in range(1, ncols, 2)) / max(1, ncols // 2) < 0.5
        for col in cols:
            kinds[(p, col)] = ("n" if col % 2 == 0 else "count") if paired else "count"
    for c in project["cells"]:
        c["kind"] = kinds[(c["page"], c["col"])]


def build_sequence(project: dict) -> list[dict]:
    """Messpunkte in Lesereihenfolge (Seite -> Zeile -> Spaltenpaar) mit Winkel."""
    cells = sorted(project["cells"], key=lambda c: (c["page"], c["row"], c["col"]))
    series_by_page = {s_page: s for s in project["series"] for s_page in s["pages"]}
    points: list[dict] = []
    pending_n = None
    for c in cells:
        if c.get("empty_slot"):
            continue
        if c["kind"] == "n":
            pending_n = c
            continue
        pt = {"count": c, "n": pending_n if pending_n and pending_n["page"] == c["page"]
              and pending_n["row"] == c["row"] and pending_n["col"] == c["col"] - 1 else None,
              "series": series_by_page.get(c["page"], {}).get("id", 0)}
        pending_n = None
        points.append(pt)
    # Index und Winkel je Serie
    counters: dict[int, int] = {}
    for pt in points:
        sid = pt["series"]
        i = counters.get(sid, 0)
        counters[sid] = i + 1
        pt["index"] = i
        s = next((s for s in project["series"] if s["id"] == sid), None)
        h = (s or {}).get("header") or {}
        pt["angle"] = round(h["start"] + i * h["step"], 6) if "start" in h and "step" in h else None
        for cell in (pt["count"], pt["n"]):
            if cell is not None:
                cell["point"] = i
                cell["angle"] = pt["angle"]
                cell["series"] = sid
    return points


def _int(v: str):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _count_neighbours(points: list[dict], vals: list, i: int) -> tuple[int | None, int | None, float | None]:
    """Direkte Nachbarn (vorher/nachher) und Median der weiteren Umgebung (+-5 Punkte)."""
    sid = points[i]["series"]
    prev = next((vals[j] for j in range(i - 1, max(-1, i - 3), -1) if vals[j] is not None and points[j]["series"] == sid), None)
    nxt = next((vals[j] for j in range(i + 1, min(len(vals), i + 3)) if vals[j] is not None and points[j]["series"] == sid), None)
    win = [vals[j] for j in range(max(0, i - 5), min(len(vals), i + 6))
           if j != i and vals[j] is not None and points[j]["series"] == sid]
    med = float(sorted(win)[len(win) // 2]) if win else None
    return prev, nxt, med


def count_flag(v: int, prev: int | None, nxt: int | None, local: float | None = None) -> dict | None:
    """Plausibilitaet einer Zaehlrate im Vergleich zu ihren Nachbarn im Winkelverlauf."""
    nb = [x for x in (prev, nxt) if x is not None]
    if not nb:
        return None
    pred = sum(nb) / len(nb)
    tol = 4 * math.sqrt(max(pred, 1.0)) + 0.35 * pred
    hi, lo = max(nb), min(nb)
    txt = ", ".join(map(str, nb))
    # nach oben: Peaks koennen steil sein -> nur grobe Spruenge (fehlende/zusaetzliche Ziffer);
    # nach unten: ein Einbruch unter beide Nachbarn um > 4 Sigma (Poisson) ist physikalisch
    # praktisch ausgeschlossen
    if v > 3 * hi + 10 or (v < lo and lo - v > 4 * math.sqrt(max(lo, 1.0)) + 0.05 * lo):
        return {"sev": "error", "msg": f"starker Ausreißer (Nachbarn {txt})"}
    # Peakspitze: liegen die Nachbarn selbst deutlich ueber dem Untergrund der Umgebung,
    # gehoert der Punkt zu einem Peak und darf beide Nachbarn uebertreffen
    in_peak = local is not None and hi > local + 4 * math.sqrt(max(local, 1.0))
    if abs(v - pred) > tol and not (lo <= v <= hi) and not (v > hi and in_peak):
        return {"sev": "warn", "msg": f"passt nicht zum Verlauf (Nachbarn {txt})"}
    return None


def resolve_with_rules(project: dict) -> int:
    """Bei Regelverstoss: eine andere Lesart waehlen, falls diese die Regeln erfuellt.

    Beispiel: OCR liest '6', der Ziffernklassifikator '46'; die Nachbarn sind 53 und 48.
    Dann wird '46' uebernommen. Die Zelle bleibt zur Pruefung markiert (Verfahren uneinig),
    der Vorschlag ist aber bereits der plausible Wert. Liefert die Anzahl Aenderungen.
    """
    validate(project)
    points = build_sequence(project)
    vals = [_int(p["count"]["value"]) for p in points]
    changed = 0
    for i, p in enumerate(points):
        c = p["count"]
        if c.get("human") in HUMAN or not any(f["sev"] in ("error", "warn") for f in c["flags"]):
            continue
        alts = [a for a in dict.fromkeys((c.get("cand") or {}).values()) if a and a != c["value"]]
        prev, nxt, local = _count_neighbours(points, vals, i)
        for a in alts:
            if _int(a) is not None and count_flag(int(a), prev, nxt, local) is None:
                c["value"] = a
                c["chosen_by_rule"] = True
                vals[i] = int(a)
                changed += 1
                break
    for p in points:
        c = p["n"]
        if c is None or c.get("human") in HUMAN:
            continue
        sug = next((f.get("suggest") for f in c["flags"] if f.get("suggest")), None)
        if sug and sug in (c.get("cand") or {}).values():
            c["value"] = sug
            c["chosen_by_rule"] = True
            changed += 1
    validate(project)
    return changed


def reconcile_header(project: dict) -> list[str]:
    """Kopfangaben gegen die gezaehlten Messpunkte abgleichen.

    Typischer OCR-Fehler: verlorener Dezimalpunkt ('5' statt '0.05'). Passt die Schrittweite
    erst nach Verschieben des Kommas zu (Ende - Start) / (Punkte - 1), wird sie korrigiert.
    Fehlende Angaben werden aus den uebrigen abgeleitet. Jede Aenderung wird vermerkt.
    """
    validate(project)
    notes: list[str] = []
    for s in project["series"]:
        h = s.get("header") or {}
        n = s.get("points") or 0
        if n < 2:
            continue
        hint = h.setdefault("hinweise", [])
        st, fi, sp = h.get("start"), h.get("finish"), h.get("step")
        if st is not None and fi is not None:
            derived = (fi - st) / (n - 1)
            if sp is None or abs(sp - derived) > 1e-6 * max(1.0, abs(derived)):
                fixed = None
                if sp:
                    for k in range(-5, 6):
                        if abs(sp * 10 ** k - derived) < 1e-6 * max(1.0, abs(derived)):
                            fixed = sp * 10 ** k
                            break
                if fixed is not None:
                    msg = f"Schrittweite '{sp:g}' als {fixed:g} gelesen (Dezimalpunkt fehlte; passt zu {n} Punkten)"
                    h["step"] = round(fixed, 8)
                    hint.append(msg)
                    notes.append(msg)
        elif sp is not None and st is not None and fi is None:
            h["finish"] = round(st + (n - 1) * sp, 6)
            hint.append("Endwinkel nicht lesbar - aus Start, Schrittweite und Punktzahl berechnet (keine unabhängige Kontrolle)")
        elif sp is not None and fi is not None and st is None:
            h["start"] = round(fi - (n - 1) * sp, 6)
            hint.append("Startwinkel nicht lesbar - aus Ende, Schrittweite und Punktzahl berechnet (keine unabhängige Kontrolle)")
        if all(k in h for k in ("start", "finish", "step")) and h["step"] > 0:
            h["expected_points"] = int(round((h["finish"] - h["start"]) / h["step"])) + 1
    validate(project)
    return notes


def validate(project: dict) -> dict:
    """Prueft alle Regeln, setzt flags/status je Zelle und liefert eine Zusammenfassung."""
    for c in project["cells"]:
        c["flags"] = []
    assign_kinds(project)
    points = build_sequence(project)
    for c in project["cells"]:
        if not c["value"] and not c.get("empty_slot"):
            c["flags"].append({"sev": "error", "msg": "Zelle leer oder unlesbar"})
        elif c["value"] and _int(c["value"]) is None:
            c["flags"].append({"sev": "error", "msg": "keine ganze Zahl"})

    # fehlende n-Zelle bei paarweisem Layout (z.B. Ziffer zu blass zum Erkennen)
    paired_pages = {c["page"] for c in project["cells"] if c["kind"] == "n"}
    for p in points:
        if p["n"] is None and p["count"]["page"] in paired_pages:
            p["count"]["flags"].append({"sev": "error", "msg": "zugehörige Detektoranzahl n fehlt"})

    # --- Detektoranzahl n: 1..9, aendert sich abschnittsweise nur um +-1 ---
    ns = [(_int(p["n"]["value"]) if p["n"] else None, p) for p in points]

    def neighbour(i: int, step: int, skip: set[int]) -> int | None:
        j = i + step
        while 0 <= j < len(ns):
            if ns[j][0] is not None and ns[j][1]["series"] == ns[i][1]["series"] and j not in skip:
                return ns[j][0]
            j += step
        return None

    outliers: set[int] = set()
    for i, (n, p) in enumerate(ns):
        if p["n"] is None or n is None:
            continue
        if not 1 <= n <= 9:
            p["n"]["flags"].append({"sev": "error", "msg": f"Detektoranzahl {n} außerhalb 1..9"})
            outliers.add(i)
            continue
        prev, nxt = neighbour(i, -1, set()), neighbour(i, 1, set())
        if prev is not None and nxt is not None and prev == nxt and n != prev:
            p["n"]["flags"].append({"sev": "error", "msg": f"Ausreißer im Detektorverlauf ({prev}-{n}-{nxt})",
                                    "suggest": str(prev)})
            outliers.add(i)
    for i, (n, p) in enumerate(ns):
        if p["n"] is None or n is None or i in outliers:
            continue
        # Nachbarn, die selbst Ausreisser sind, ueberspringen - sonst wuerden korrekte Werte
        # neben einer Fehllesung ebenfalls markiert
        prev, nxt = neighbour(i, -1, outliers), neighbour(i, 1, outliers)
        if (prev is not None and abs(n - prev) > 1) or (nxt is not None and abs(n - nxt) > 1):
            p["n"]["flags"].append({"sev": "error", "msg": "Detektoranzahl springt um mehr als 1"})

    # --- Zaehlraten: glatter Verlauf (Poisson-Statistik), Ausreisser markieren ---
    vals = [_int(p["count"]["value"]) for p in points]
    for i, p in enumerate(points):
        v = vals[i]
        if v is None:
            continue
        flag = count_flag(v, *_count_neighbours(points, vals, i))
        if flag:
            p["count"]["flags"].append(flag)

    for c in project["cells"]:
        if c.get("chosen_by_rule") and c.get("human") not in HUMAN and c["value"] != c.get("ocr_value"):
            c["flags"].append({"sev": "info", "msg": f"Lesart nach Plausibilität gewählt (Mehrheit war {c.get('ocr_value') or 'leer'})"})

    # --- Status je Zelle ---
    summary = {"ok": 0, "pruefen": 0, "fehler": 0, "bestaetigt": 0, "korrigiert": 0}
    for c in project["cells"]:
        if c.get("empty_slot"):
            c["status"] = "leer"
            continue
        if c.get("human") in HUMAN:
            c["status"] = c["human"]
        elif any(f["sev"] == "error" for f in c["flags"]):
            c["status"] = "fehler"
        elif c.get("agree", 0) < c.get("n_engines", 3) or c["flags"]:
            c["status"] = "pruefen"
        else:
            c["status"] = "ok"
        summary[c["status"]] = summary.get(c["status"], 0) + 1

    # --- Serien: Anzahl Messpunkte gegen Kopfangaben ---
    for s in project["series"]:
        got = sum(1 for p in points if p["series"] == s["id"])
        s["points"] = got
        exp = (s.get("header") or {}).get("expected_points")
        s["expected"] = exp
        s["complete"] = (exp == got) if exp else None
    summary["points"] = len(points)
    summary["series"] = [{"id": s["id"], "points": s["points"], "expected": s["expected"],
                          "header": {k: v for k, v in (s.get("header") or {}).items() if k != "raw"}}
                         for s in project["series"]]
    project["summary"] = summary
    return summary
