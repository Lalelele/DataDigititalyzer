"""Export der (geprueften) Messwerte."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .validate import build_sequence


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
        w.writerow({k: _fmt(v, dec) if isinstance(v, float) else v for k, v in r.items()})
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


FORMATS = ("tabelle", "messpunkte", "xy")


def write(project: dict, target: str | Path, international: bool = False, fmt: str | None = None) -> Path:
    """Schreibt den Export. fmt: 'tabelle' (wie im Scan), 'messpunkte' (eine Zeile je Punkt)
    oder 'xy'; ohne Angabe: .xy/.dat/.txt -> xy, sonst Tabelle."""
    target = Path(target)
    if fmt is None:
        fmt = "xy" if target.suffix.lower() in (".xy", ".dat", ".txt") else "tabelle"
    if fmt == "xy":
        text = to_xy(project)
    elif fmt == "messpunkte":
        text = to_csv(project, international)
    else:
        text = to_table_csv(project, international)
    # utf-8-sig: Excel erkennt die Kodierung (Umlaute) unter Windows korrekt
    target.write_text(text, encoding="utf-8-sig" if target.suffix.lower() == ".csv" else "utf-8", newline="")
    return target
