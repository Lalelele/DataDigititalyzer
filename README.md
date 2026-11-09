# DataDigititalyzer

Digitalisiert Messwerte aus **alten, gescannten Tabellen** (PDF oder Bild) in eine Tabelle.
Das Programm arbeitet **vollständig lokal** und läuft unter Windows und Linux. Jeder erkannte
Wert behält seine Position im Scan, damit ein Mensch ihn **direkt neben dem Original**
kontrollieren kann.

Entwickelt und getestet an Messprotokollen der Neutronenbeugung. Jede Zeile enthält 10 Paare
aus *Detektoranzahl n* und *Zählrate*. Der Seitenkopf nennt Probe, Wellenlänge, Start- und
Endwinkel sowie die Schrittweite.

---

## Schnellstart

### Installation (einmalig)

Benötigt wird **64-Bit-Python 3.11, 3.12 oder 3.13**, empfohlen ist **3.12**. Für die neueste
Version Python 3.15 und für 32-Bit-Python gibt es das Paket `onnxruntime` (noch) nicht, und
die Installation bricht dann mit „conflicting dependencies … onnxruntime“ ab.

**Windows:**
1. Python 3.12 (64-Bit, „Windows installer (64-bit)“) von <https://www.python.org/downloads/>
   installieren und dabei „Add python.exe to PATH“ anhaken. Mit dem neuen
   Python-Installationsmanager geht es auch per `py install 3.12`. Eine bereits installierte
   andere Python-Version kann bleiben.
2. Im Ordner dieses Repositorys doppelt auf **`installieren.bat`** klicken. Das Skript wählt
   automatisch eine passende Python-Version.

Oder von Hand:

```bash
py -3.12 -m pip install -r requirements.txt
```

Die Frage nach „paths longer than 260 characters“ kann mit **N** beantwortet werden.

**Linux:**

```bash
python3 -m pip install -r requirements.txt
```

Alternativ als Befehl `digitalyzer` installieren: `pip install .`

Alle Pakete kommen als fertige Wheels über `pip`. Es muss **kein** Zusatzprogramm wie Tesseract
installiert werden. Die Erkennungsmodelle sind im Paket `rapidocr-onnxruntime` enthalten, ein
Internetzugang wird zur Laufzeit nicht benötigt.

### Benutzung

```bash
python -m digitalyzer scan.pdf
```

1. Der Scan wird ausgewertet (etwa 30 s für 4 Seiten). Das Ergebnis landet im Ordner `scan_digitalisiert/`.
2. Die **Prüf-App** öffnet sich im Browser. Sie läuft nur lokal unter `http://127.0.0.1:8765`.
3. Offene Punkte durchgehen (Taste **N**) und mit **Enter** bestätigen oder Ziffern tippen und mit **Enter** korrigieren.
4. **Exportieren** (oben rechts): CSV für Excel oder `.xy` (2θ, Zählrate).

Unter Windows geht es auch ohne Kommandozeile: die PDF-Datei mit der Maus auf
`digitalisieren.bat` ziehen. Das Skript verwendet automatisch die passende Python-Version.
Von Hand: `py -3.12 -m digitalyzer scan.pdf`. Unter Linux: `./digitalisieren.sh scan.pdf`.

Alle Korrekturen werden **sofort** gespeichert. Die Prüfung lässt sich jederzeit beenden und
später fortsetzen:

```bash
python -m digitalyzer pruefen scan_digitalisiert
```

### Weitere Befehle

| Befehl | Zweck |
|---|---|
| `python -m digitalyzer analysieren a.pdf b.pdf` | mehrere Scans auswerten (je ein Projektordner) |
| `python -m digitalyzer analysieren scan.pdf --neu` | erneut auswerten; die bisherige Prüfung wird als `projekt_<Zeit>.json` gesichert |
| `python -m digitalyzer analysieren scan.pdf --start 9.89 --schritt 0.05` | Winkel vorgeben, falls der Kopf unlesbar ist |
| `python -m digitalyzer pruefen ORDNER [--port 8765] [--kein-browser]` | Prüf-App öffnen |
| `python -m digitalyzer exportieren ORDNER [-o werte.csv\|werte.xy] [--international]` | Export ohne Browser |

Ein vorhandenes Projekt wird nie stillschweigend überschrieben.

---

## Die Prüf-App

| Ansicht | Inhalt |
|---|---|
| **Prüftabelle** (F1) | Jede Zelle zeigt den **Bildausschnitt aus dem Scan** und **direkt daneben den erkannten Wert**, zeilengetreu wie im Original. Die Farben zeigen den Status. Mit „nur Zeilen mit offenen Punkten“ bleiben nur die Stellen übrig, die geprüft werden müssen. |
| **Seite** (F2) | Die ganze Seite mit fünf Modi: **Original + Werte** (Wert farbig neben jeder Zahl), **Nur Original**, **Nachgezeichnet**, **Blinken** und **Differenz** (siehe unten). Ein Klick auf eine Zahl wählt die Zelle aus. |
| **Diagramm** (F3) | Die erkannten Zählraten über 2θ. Lesefehler fallen dort als Spitzen oder Einbrüche auf. Ein Klick auf einen Punkt springt zur Zelle. |

Die **Detailspalte** rechts zeigt für die gewählte Zelle:
- einen vergrößerten Ausschnitt mit den Nachbarzellen,
- die Lesarten aller Erkennungsverfahren,
- die Regelverstöße und, falls vorhanden, einen Korrekturvorschlag (Taste **V**).

**Nachgezeichnet, Blinken, Differenz:** Das Programm lernt aus dem Dokument selbst, wie jede
Ziffer 0–9 in genau dieser Schrift und Unschärfe aussieht. Mit diesen Ziffernbildern zeichnet
es die *erkannten* Werte an exakt derselben Stelle neu. Stimmt ein Wert, bleibt das
Differenzbild an dieser Stelle hell, und beim Blinken ändert sich kaum etwas. Ein falsch
gelesener Wert, etwa „6“ statt „46“, erscheint als **roter Fleck** und springt sofort ins Auge.
So fallen auch Fehler auf, die keine Regel findet.

| Status | Bedeutung |
|---|---|
| 🟩 ok | alle drei Erkennungsverfahren einig, keine Regel verletzt |
| 🟨 prüfen | Verfahren uneinig oder Wert passt nicht recht zum Verlauf |
| 🟥 Regelverstoß | eine Plausibilitätsregel ist verletzt |
| 🟦 bestätigt | von Hand geprüft, Wert unverändert |
| 🟪 korrigiert | von Hand geändert (der ursprünglich erkannte Wert bleibt gespeichert) |

Tasten: Pfeile wechseln die Zelle · Ziffern überschreiben · **Enter** übernehmen · **Esc**
verwerfen · **N**/**Umschalt+N** nächster/vorheriger offener Punkt · **V** Vorschlag übernehmen ·
**O R S B D** Seitenmodi · **Bild↑/↓** Seite · **?** Hilfe.

---

## Wie es funktioniert

```
PDF ─► Seitenbild ─► Papier finden ─► Hintergrund ─► Schräglage ─► Raster ─► 3 Lesarten ─► Abgleich ─► Regeln ─► Prüf-App
      (Original-     (Scanränder     ausgleichen    messen und     (Spalten,   je Zelle       (Mehrheit)                 ─► CSV/.xy
       auflösung)     ausblenden)                   begradigen     Zeilen)
```

1. **Seitenbild:** Das eingebettete Scanbild wird in Originalauflösung aus dem PDF entnommen, also ohne Qualitätsverlust durch erneutes Rendern.
2. **Vorverarbeitung:**
   - Die Papierfläche wird erkannt, schwarze Scannerränder werden ausgeblendet.
   - Das Bild wird durch eine stark weichgezeichnete Kopie geteilt. Das gleicht Vergilbung und ungleichmäßige Ausleuchtung aus.
   - Die **Schräglage** wird über die Schärfe des Zeilenprofils gemessen (Grob-fein-Suche, ±6°, Genauigkeit etwa 0,02°) und korrigiert. Jeder Scan wird dabei einzeln vermessen.
   - Für die Spaltentrennung dient eine strenge Schwarz-Weiß-Maske, für blasse Ziffern wie dünne „1“ eine großzügige.
3. **Raster:**
   - Spalten werden über das senkrechte Tintenprofil gefunden. Eine Trennung gilt nur, wenn auch die Lücke *in den einzelnen Zeilen* groß genug ist. So wird die führende „1“ dreistelliger Zahlen nicht als eigene Spalte abgetrennt.
   - Zeilen werden **je Spalte** gesucht und dann über die Spalten hinweg zugeordnet. Dadurch stören leichte Blattkrümmungen nicht.
   - Kopf und Seitenzahl werden über den abweichenden Zeilenabstand abgetrennt. Staub, Papierkanten und eine unvollständige letzte Zeile werden erkannt.
   - Jeder Tintenblock einer Zeile wird der Spalte zugeordnet, mit der er sich am stärksten überlappt. So gerät auch bei eng stehenden Spalten keine Nachbarziffer in eine Zelle.
4. **Drei unabhängige Lesarten je Zelle:**
   - **RapidOCR** (PaddleOCR-Modelle über die ONNX Runtime, lokal) in **zwei Vergrößerungen**.
   - Ein **dokumentspezifischer Ziffernklassifikator**: Die Zellen werden geometrisch in Einzelziffern zerlegt. Ziffern, bei denen die OCR sicher ist, dienen als Lernbeispiele, danach wird jede Ziffer per k-nächste-Nachbarn neu bestimmt.
   - Die Ziffernanzahl ermittelt der Klassifikator aus der Geometrie. Er fängt damit eine bekannte OCR-Schwäche ab, nämlich zusammengezogene Doppelziffern („6“ statt „66“).
5. **Abgleich und Regeln:**
   - Die Lesarten werden per Mehrheit abgeglichen.
   - Danach greifen die Plausibilitätsregeln (siehe unten). Erfüllt bei einem Regelverstoß eine der anderen Lesarten die Regeln, wird sie vorgeschlagen. Die Zelle bleibt trotzdem zur Prüfung markiert.

### Plausibilitätsregeln

| Regel | findet |
|---|---|
| Anzahl der Messpunkte = (Ende − Start) / Schritt + 1 | verlorene oder doppelte Zeilen |
| Detektoranzahl n liegt zwischen 1 und 9 und ändert sich nur um ±1; ein einzelner abweichender Wert (5‑3‑5) ist ein Lesefehler und wird mit Vorschlag markiert | fast jeden Lesefehler in der n-Spalte |
| Zählrate gegen ihre Nachbarn im Winkelverlauf (auch über Zeilen- und Seitenumbrüche hinweg): grobe Sprünge nach oben, Einbrüche > 4σ (Poisson) nach unten; Peakspitzen sind ausgenommen | fehlende oder zusätzliche Ziffern, Ziffernverwechslungen |
| Kopfangaben gegen die Punktzahl | z. B. „5“ statt „0.05“ (verlorener Dezimalpunkt) |

---

## Ergebnisse mit dem Beispielscan (4 Seiten, 200 dpi, unscharf)

| | |
|---|---|
| gefundene Messpunkte | **3004 von 3004** laut Kopf erwarteten |
| Zellen „ok“ (alle Verfahren einig, Regeln erfüllt) | 5855 von 6008 (97,5 %) |
| zur Prüfung markiert | 153 Zellen (2,5 %), meist schon mit richtigem Vorschlag |
| Stichprobe von 192 zufälligen „ok“-Zellen, von Hand nachgelesen | alle richtig |
| Robustheit: Seiten zusätzlich um +3° … −4° gedreht | identisches Raster; 1 Wert weicht ab, und dieser ist markiert |
| … zusätzlich stärker unscharf | 17 Werte weichen ab, **alle** markiert, keiner als „ok“ durchgerutscht |

Laufzeit: etwa 30 s für 4 Seiten auf einem normalen Rechner (CPU).

---

## Projektordner

```
scan_digitalisiert/
  projekt.json            alle Zellen: Position im Scan, Lesarten, Wert, Status, Korrekturen
  ziffern.npz             gelernte Ziffernbilder (für die Nachzeichnung)
  seiten/original_001.jpg begradigtes Originalbild
  seiten/kontrast_001.jpg begradigt + Hintergrund ausgeglichen
  messwerte.csv           (nach Export)
```

Die CSV enthält je Messpunkt: Messreihe, Index, 2θ, n, Zählrate, Seite, Zeile, Spalte,
Status beider Zellen und Hinweise. Damit bleibt jeder Wert auf seine Stelle im Scan
zurückführbar.

---

## Grenzen und Ideen

- Das Raster ist auf **Tabellen aus gedruckten Ziffern** ausgelegt. Handschrift erkennt RapidOCR deutlich schlechter. Dann hilft vor allem der Ziffernklassifikator, wenn genug Beispiele bestätigt sind.
- Die Paarbildung (n, Zählrate) wird automatisch erkannt: abwechselnd einstellige und mehrstellige Spalten. Andere Layouts werden als reine Wertespalten gelesen.
- Die Seiten werden **begradigt** angezeigt, nicht im ursprünglichen Winkel.
- Mögliche Erweiterungen:
  - Korrekturen als Trainingsdaten für weitere Dokumente nutzen.
  - Kopfwerte in der App bearbeiten (bisher über `--start`/`--schritt`).
  - Ein beschriftetes PDF zum Archivieren exportieren.

---

## Entwicklung

```bash
pip install -e ".[test]"
python -m pytest -q
```

Die Tests erzeugen **künstliche Scans** mit bekannter Wahrheit: gedreht (−4° … +5°),
unscharf, verrauscht, mit Staub, Scannerrand, Kopf und Seitenzahl. Sie prüfen
Begradigung, Raster, Regeln, Kopfauswertung und einen kompletten Durchlauf. Echte
Messdaten sind nicht im Repository, `*.pdf` steht in `.gitignore`.

| Modul | Aufgabe |
|---|---|
| `pdf_io.py` | Seitenbilder aus PDF/Bild |
| `preprocess.py` | Papiermaske, Hintergrundausgleich, Schräglage, Masken |
| `layout.py` | Spalten, Zeilen, Zellen |
| `recognize.py` | RapidOCR, Ziffernzerlegung, Ziffernklassifikator, Abgleich |
| `header.py` | Seitenkopf auslesen (unscharfe Zuordnung der Bezeichnungen) |
| `validate.py` | Messreihe aufbauen, Regeln, Status, Kopfabgleich |
| `render.py` | Nachzeichnung der erkannten Werte |
| `pipeline.py` | Gesamtablauf, Projektdatei |
| `server.py`, `static/` | Prüf-App (Python-Standardbibliothek + HTML/JS, ohne Internet) |
| `export.py` | CSV / `.xy` |
