"""Kommandozeile.

  python -m digitalyzer                     (App mit Projektuebersicht im Browser starten)
  python -m digitalyzer app [--arbeitsordner ORDNER]
  python -m digitalyzer analysieren SCAN.pdf [-o ORDNER]
  python -m digitalyzer pruefen ORDNER
  python -m digitalyzer exportieren ORDNER [-o DATEI] [--format tabelle|messpunkte|xy|xye]
  python -m digitalyzer SCAN.pdf            (analysieren und direkt pruefen)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ALIASES = {"start": "app", "process": "analysieren", "analyse": "analysieren", "review": "pruefen", "prüfen": "pruefen",
           "export": "exportieren"}


def _default_out(src: Path) -> Path:
    return src.with_name(src.stem + "_digitalisiert")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ALIASES:
        argv[0] = ALIASES[argv[0]]
    if not argv:
        argv = ["app"]
    # Kurzform: nur eine Datei angegeben
    if argv and argv[0] not in ("app", "analysieren", "pruefen", "exportieren", "-h", "--help") and Path(argv[0]).is_file():
        argv = ["analysieren", *argv, "--pruefen"]

    ap = argparse.ArgumentParser(prog="python -m digitalyzer",
                                 description="Messwerte aus gescannten Tabellen digitalisieren und pruefen.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("app", help="App mit Projektuebersicht starten (Dokumente hochladen, Einstellungen, Pruefung)")
    w.add_argument("--arbeitsordner", type=Path, help="Ordner fuer die Projekte (Standard: ~/DataDigititalyzer)")
    w.add_argument("--port", type=int, default=8765)
    w.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch oeffnen")

    a = sub.add_parser("analysieren", help="Scan (PDF oder Bild) auswerten")
    a.add_argument("scan", nargs="+", type=Path, help="PDF- oder Bilddatei(en)")
    a.add_argument("-o", "--ausgabe", type=Path, help="Projektordner (Standard: <Datei>_digitalisiert)")
    a.add_argument("--start", type=float, help="Startwinkel, falls nicht im Kopf lesbar")
    a.add_argument("--schritt", type=float, help="Schrittweite")
    a.add_argument("--ende", type=float, help="Endwinkel")
    a.add_argument("--pruefen", action="store_true", help="danach direkt die Pruef-App oeffnen")
    a.add_argument("--neu", action="store_true",
                   help="vorhandenes Projekt neu auswerten (alte projekt.json wird als Sicherung behalten)")

    r = sub.add_parser("pruefen", help="Pruef-App im Browser oeffnen")
    r.add_argument("ordner", type=Path)
    r.add_argument("--port", type=int, default=8765)
    r.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch oeffnen")

    e = sub.add_parser("exportieren", help="Messwerte als CSV, .xy oder .xye schreiben")
    e.add_argument("ordner", type=Path)
    e.add_argument("--format", choices=["tabelle", "messpunkte", "xy", "xye"], default="tabelle",
                   help="tabelle: wie im Scan, nach jeder Zaehlrate ihr statistischer Fehler (Standard); "
                        "messpunkte: eine Zeile je Punkt mit 2Theta, Fehler, Status und Hinweisen; "
                        "xy: 2Theta und Zaehlrate; xye: 2Theta, Zaehlrate und statistischer Fehler")
    e.add_argument("-o", "--ziel", type=Path, help="Zieldatei; Standard: <Ordner>/tabelle.csv, messpunkte.csv, messwerte.xy bzw. messwerte.xye")
    e.add_argument("--international", action="store_true", help="Komma als Trenner, Punkt als Dezimalzeichen")

    args = ap.parse_args(argv)

    if args.cmd == "app":
        from .server import serve
        serve(args.arbeitsordner, port=args.port, open_browser=not args.kein_browser)
        return 0

    if args.cmd == "analysieren":
        from .pipeline import process
        override = {k: v for k, v in (("start", args.start), ("step", args.schritt), ("finish", args.ende)) if v is not None}
        import datetime
        import shutil

        from .pipeline import PROJECT_FILE
        outs = []
        for src in args.scan:
            out = args.ausgabe if (args.ausgabe and len(args.scan) == 1) else \
                (args.ausgabe / src.stem if args.ausgabe else _default_out(src))
            existing = out / PROJECT_FILE
            if existing.exists() and not args.neu:
                # Schutz: Korrekturen aus der Pruefung nie stillschweigend ueberschreiben
                if args.pruefen:
                    print(f"Projekt existiert bereits ({out}) - oeffne die Pruefung. Neu auswerten mit --neu.")
                    outs.append(out)
                    continue
                print(f"Projekt existiert bereits: {out}\nNeu auswerten mit --neu (die alte Datei wird gesichert).")
                return 2
            if existing.exists():
                backup = out / f"projekt_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
                shutil.copy2(existing, backup)
                print(f"Sicherung der bisherigen Pruefung: {backup}")
            process(src, out, header_override=override or None)
            print(f"Projektordner: {out}")
            outs.append(out)
        if args.pruefen:
            from .server import serve
            serve(outs[0].resolve().parent, open_project=outs[0].resolve().name)
        return 0

    if args.cmd == "pruefen":
        from .pipeline import PROJECT_FILE
        from .server import serve
        folder = args.ordner.resolve()
        if not (folder / PROJECT_FILE).exists():
            print(f"Kein ausgewertetes Projekt in {folder}")
            return 2
        serve(folder.parent, port=args.port, open_browser=not args.kein_browser, open_project=folder.name)
        return 0

    if args.cmd == "exportieren":
        from . import export
        from .pipeline import load_project
        from .validate import validate
        project = load_project(args.ordner)
        validate(project)
        default_name = {"tabelle": "tabelle.csv", "messpunkte": "messpunkte.csv", "xy": "messwerte.xy",
                        "xye": "messwerte.xye"}[args.format]
        target = args.ziel or (args.ordner / default_name)
        export.write(project, target, international=args.international, fmt=args.format)
        s = project["summary"]
        print(f"Geschrieben: {target}  ({s['points']} Messpunkte; offen: {s['pruefen']} pruefen, {s['fehler']} Fehler)")
        if args.format == "xye":
            _, ausgelassen = export.xye_rows(project)
            if ausgelassen:
                print(f"  Achtung: {ausgelassen} Messpunkte ohne lesbare Zaehlrate oder Detektoranzahl n "
                      "fehlen in der .xye-Datei (Fehler nicht bestimmbar) - bitte in der Pruefung korrigieren.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
