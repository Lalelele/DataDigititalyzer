"""Einstellungen fuer die Auswertung eines Scans.

Alle Werte haben sinnvolle Voreinstellungen ("automatisch"). Sie koennen in der App je
Projekt angepasst werden, wenn ein Scan schlecht erkannt wird. Die Beschreibungen hier
werden direkt in der Oberflaeche angezeigt.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class Settings:
    # --- Geometrie ---
    winkel_auto: bool = True
    winkel: float = 0.0
    max_winkel: float = 6.0
    # --- Ausschnitt (Prozent der Seite, nach dem Begradigen) ---
    rand_oben: float = 0.0
    rand_unten: float = 0.0
    rand_links: float = 0.0
    rand_rechts: float = 0.0
    papierrand: float = 2.5
    # --- Bild ---
    vergroesserung: float = 1.0
    kontrastausgleich: bool = True
    empfindlichkeit: int = 200
    staubfilter: float = 0.65
    # --- Raster ---
    zeilenabstand: float = 0.0
    paare: str = "auto"
    # --- Erkennung ---
    ocr_glaettung: float = 0.7
    # --- Kopfangaben (leer = aus dem Scan lesen) ---
    start: float | None = None
    schritt: float | None = None
    ende: float | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "Settings":
        s = cls()
        if not d:
            return s
        for f in fields(cls):
            if f.name not in d:
                continue
            v = d[f.name]
            if v in ("", None):
                setattr(s, f.name, None if f.name in ("start", "schritt", "ende") else getattr(s, f.name))
                continue
            try:
                if f.name in ("winkel_auto", "kontrastausgleich"):
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "ja", "on")
                elif f.name == "paare":
                    v = str(v) if str(v) in ("auto", "ja", "nein") else "auto"
                elif f.name == "empfindlichkeit":
                    v = int(float(v))
                else:
                    v = float(str(v).replace(",", "."))
            except (TypeError, ValueError):
                continue
            setattr(s, f.name, v)
        s.clamp()
        return s

    def clamp(self) -> None:
        self.max_winkel = min(max(self.max_winkel, 0.5), 20.0)
        self.winkel = min(max(self.winkel, -45.0), 45.0)
        for k in ("rand_oben", "rand_unten", "rand_links", "rand_rechts"):
            setattr(self, k, min(max(getattr(self, k), 0.0), 45.0))
        self.papierrand = min(max(self.papierrand, 0.0), 15.0)
        self.vergroesserung = min(max(self.vergroesserung, 0.5), 3.0)
        self.empfindlichkeit = int(min(max(self.empfindlichkeit, 120), 250))
        self.staubfilter = min(max(self.staubfilter, 0.0), 1.5)
        self.zeilenabstand = max(self.zeilenabstand, 0.0)
        self.ocr_glaettung = min(max(self.ocr_glaettung, 0.0), 2.0)

    def to_dict(self) -> dict:
        return asdict(self)

    def header_override(self) -> dict:
        out = {}
        for key, name in (("start", "start"), ("schritt", "step"), ("ende", "finish")):
            v = getattr(self, key)
            if v is not None:
                out[name] = float(v)
        return out


# Beschreibung fuer die Oberflaeche: (Gruppe, Feld, Bezeichnung, Typ, Hilfe, min, max, Schritt)
DESCRIPTION = [
    ("Geometrie", "winkel_auto", "Schräglage automatisch erkennen", "bool",
     "Misst die Schräglage jeder Seite selbst. Ausschalten, um den Winkel unten vorzugeben.", None, None, None),
    ("Geometrie", "winkel", "Drehwinkel (Grad)", "number",
     "Bei automatischer Erkennung: zusätzliche Feinkorrektur. Sonst: der verwendete Winkel. "
     "Positiv = gegen den Uhrzeigersinn.", -45, 45, 0.05),
    ("Geometrie", "max_winkel", "Suchbereich Schräglage (± Grad)", "number",
     "Größer wählen, wenn eine Seite sehr schief eingelegt wurde.", 0.5, 20, 0.5),
    ("Ausschnitt", "rand_oben", "oben ausblenden (%)", "number",
     "Bereich am oberen Seitenrand ignorieren (z. B. Stempel, Notizen).", 0, 45, 0.5),
    ("Ausschnitt", "rand_unten", "unten ausblenden (%)", "number", "", 0, 45, 0.5),
    ("Ausschnitt", "rand_links", "links ausblenden (%)", "number", "", 0, 45, 0.5),
    ("Ausschnitt", "rand_rechts", "rechts ausblenden (%)", "number", "", 0, 45, 0.5),
    ("Ausschnitt", "papierrand", "Papierkante ausblenden (%)", "number",
     "Streifen entlang der erkannten Papierkante, der ignoriert wird (Schatten, Lochung).", 0, 15, 0.5),
    ("Bild", "vergroesserung", "Bild vergrößern (Faktor)", "number",
     "Für sehr kleine Schrift bzw. niedrige Scanauflösung: 1,5 oder 2 versuchen.", 0.5, 3, 0.25),
    ("Bild", "kontrastausgleich", "Blasse Bereiche angleichen", "bool",
     "Verstärkt die Tinte dort, wo der Scan blasser ist (z. B. zum oberen Rand hin), auf das Niveau der übrigen Seite. Kräftige Bereiche bleiben unverändert.", None, None, None),
    ("Bild", "empfindlichkeit", "Empfindlichkeit für blasse Ziffern", "number",
     "Höher = auch sehr blasse Striche gelten als Tinte (Standard 200, Bereich 120–250). "
     "Bei Flecken/Rauschen verringern.", 120, 250, 5),
    ("Bild", "staubfilter", "Staubfilter (Anteil einer Ziffernhöhe)", "number",
     "Isolierte Flecken unter dieser Größe werden entfernt. 0 = aus.", 0, 1.5, 0.05),
    ("Raster", "zeilenabstand", "Zeilenabstand (Pixel, 0 = automatisch)", "number",
     "Nur setzen, wenn Zeilen zusammengelegt oder doppelt erkannt werden.", 0, 200, 0.5),
    ("Raster", "paare", "Paare (n, Durchschnittl. Intensität)", "select:auto|ja|nein",
     "Ob sich die Spalten für Detektoranzahl und Durchschnittl. Intensität abwechseln.", None, None, None),
    ("Erkennung", "ocr_glaettung", "Glättung für die Texterkennung", "number",
     "Leichtes Weichzeichnen hilft bei dünnen, zerrissenen Ziffern (Standard 0,7; 0 = aus).", 0, 2, 0.1),
    ("Kopfangaben", "start", "Startwinkel 2θ (leer = aus Scan)", "number", "", None, None, 0.01),
    ("Kopfangaben", "schritt", "Schrittweite (leer = aus Scan)", "number", "", None, None, 0.001),
    ("Kopfangaben", "ende", "Endwinkel (leer = aus Scan)", "number", "", None, None, 0.01),
]
