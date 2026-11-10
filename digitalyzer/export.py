"""Export der (geprueften) Messwerte."""
from __future__ import annotations

import csv
import io
import math
from pathlib import Path

from .validate import build_sequence


def stat_fehler(zaehlrate, n) -> float | None:
    """Statistischer Fehler (1 Sigma) einer Zaehlrate, die ueber n Detektoren gemittelt ist.

    Die Zaehlrate Z ist je Detektor normiert; tatsaechlich registriert wurden N = Z * n
    Ereignisse. Nach der Poisson-Statistik ist sigma(N) = sqrt(N), also

        sigma(Z) = sqrt(Z * n) / n = sqrt(Z / n)

    Je mehr Detektoren zu einem Punkt beigetragen haben, desto kleiner ist sein Fehler.
    Bei Z = 0 wird N = 1 angesetzt (sonst waere sigma = 0 und der Punkt erhielte in einer
    Anpassung unendliches Gewicht). Ohne gueltiges n (fehlt, unlesbar, < 1) oder ohne
    gueltige Zaehlrate: None.
    """
    z, k = _to_int(zaehlrate), _to_int(n)
    if z is None or k is None or z < 0 or k < 1:
        return None
    return math.sqrt(max(z * k, 1)) / k


def _to_int(v) -> int | None:
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _fmt(v, decimal: str) -> str:
    if v is None:
        return ""
    s = f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
    return s.replace(".", decimal)


def rows(project: dict) -> list[dict]:
    out = []
    for pt in build_sequence(project):
        c, n = pt["count"], pt["n"]
        notes = [f["msg"] for cell in (n, c) if cell for f in cell.get("flags", [])]
        out.append({
            "Messreihe": pt["series"] + 1,
            "Index": pt["index"],
            "2Theta": pt["angle"],
            "n": n["value"] if n else "",
            "Zaehlrate": c["value"],
            "Stat_Fehler": stat_fehler(c["value"], n["value"] if n else None),
            "Seite": c["page"] + 1,
            "Zeile": c["row"] + 1,
            "Spalte": c["col"] + 1,
            "Status_n": n["status"] if n else "",
            "Status_Zaehlrate": c["status"],
            "Hinweise": " | ".join(notes),
        })
    return out


def to_csv(project: dict, international: bool = False) -> str:
    """CSV: standardmaessig fuer deutsches Excel (Semikolon, Dezimalkomma)."""
    sep, dec = (",", ".") if international else (";", ",")
    data = rows(project)
    buf = io.StringIO()
    fields = list(data[0].keys()) if data else ["Index"]
    w = csv.DictWriter(buf, fieldnames=fields, delimiter=sep, lineterminator="\n")
    w.writeheader()
    for r in data:
        w.writerow({k: _fmt(v, dec) if isinstance(v, float) else ("" if v is None else v) for k, v in r.items()})
    return buf.getvalue()


def table_rows(project: dict) -> list[list[str]]:
    """Die Tabelle genau wie im Scan: eine Zeile je Scanzeile, Werte in Spaltenreihenfolge.

    Seiten werden in ihrer Reihenfolge aneinandergehaengt. Eine unlesbare Zelle bleibt als
    leeres Feld stehen, damit alle folgenden Werte an ihrem Platz bleiben. Die letzte,
    unvollstaendige Zeile einer Messreihe ist entsprechend kuerzer.
    """
    grid: dict[tuple[int, int], dict[int, str]] = {}
    for c in project["cells"]:
        if c.get("status") == "leer":
            continue
        grid.setdefault((c["page"], c["row"]), {})[c["col"]] = c.get("value") or ""
    out = []
    for key in sorted(grid):
        cols = grid[key]
        out.append([cols.get(i, "") for i in range(max(cols) + 1)])
    return out


def to_table_csv(project: dict, international: bool = False) -> str:
    """Tabelle wie im Scan, ohne Kopfzeile und Zusatzspalten - nur die Werte."""
    sep = "," if international else ";"
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=sep, lineterminator="\n")
    w.writerows(table_rows(project))
    return buf.getvalue()


def to_xy(project: dict) -> str:
    """Einfaches Zwei-Spalten-Format (2Theta  Zaehlrate) fuer Auswerteprogramme."""
    lines = []
    for r in rows(project):
        if r["2Theta"] is not None and r["Zaehlrate"]:
            lines.append(f"{r['2Theta']:.4f}  {r['Zaehlrate']}")
    return "\n".join(lines) + "\n"


def xye_rows(project: dict) -> tuple[list[tuple[float, int, float]], int]:
    """Punkte fuer .xye: (2Theta, Zaehlrate, Fehler). Zweiter Rueckgabewert: Anzahl der
    Punkte, die mangels gueltiger Zaehlrate oder gueltigem n ausgelassen wurden."""
    out, skipped = [], 0
    for r in rows(project):
        z = _to_int(r["Zaehlrate"])
        if r["2Theta"] is None:
            continue
        if z is None or r["Stat_Fehler"] is None:
            skipped += 1
            continue
        out.append((r["2Theta"], z, r["Stat_Fehler"]))
    return out, skipped


def to_xye(project: dict) -> str:
    """Drei Spalten (2Theta  Zaehlrate  Fehler), durch Leerzeichen getrennt, ohne Kopfzeile -
    lesbar fuer GSAS-II, FullProf, TOPAS, Jana u. a. Der Fehler ist der statistische Fehler
    aus der Detektoranzahl n (siehe `stat_fehler`)."""
    pts, _ = xye_rows(project)
    return "".join(f"{a:.4f}  {z}  {e:.4f}\n" for a, z, e in pts)


FORMATS = ("tabelle", "messpunkte", "xy", "xye")


def write(project: dict, target: str | Path, international: bool = False, fmt: str | None = None) -> Path:
    """Schreibt den Export. fmt: 'tabelle' (wie im Scan), 'messpunkte' (eine Zeile je Punkt),
    'xy' oder 'xye'; ohne Angabe: .xye -> xye, .xy/.dat/.txt -> xy, sonst Tabelle."""
    target = Path(target)
    if fmt is None:
        suffix = target.suffix.lower()
        fmt = "xye" if suffix == ".xye" else "xy" if suffix in (".xy", ".dat", ".txt") else "tabelle"
    if fmt == "xye":
        text = to_xye(project)
    elif fmt == "xy":
        text = to_xy(project)
    elif fmt == "messpunkte":
        text = to_csv(project, international)
    else:
        text = to_table_csv(project, international)
    # utf-8-sig: Excel erkennt die Kodierung (Umlaute) unter Windows korrekt
    target.write_text(text, encoding="utf-8-sig" if target.suffix.lower() == ".csv" else "utf-8", newline="")
    return target
