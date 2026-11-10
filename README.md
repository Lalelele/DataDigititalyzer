# DataDigititalyzer

Digitalisiert Messwerte aus **alten, gescannten Tabellen** (PDF oder Bild) in eine Tabelle.
Das Programm arbeitet **vollständig lokal** und läuft unter Windows und Linux. Jeder erkannte
Wert behält seine Position im Scan, damit ein Mensch ihn **direkt neben dem Original**
kontrollieren kann.

Entwickelt und getestet an Messprotokollen der Neutronenbeugung. Jede Zeile enthält 10 Paare
aus *Detektoranzahl n* und *Durchschnittl. Intensität*. Der Seitenkopf nennt Probe, Wellenlänge, Start- und
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

**Windows:** Doppelklick auf **`digitalisieren.bat`**. **Linux:** `./digitalisieren.sh`. Oder von Hand:

```bash
py -3.12 -m digitalyzer
```

Die App öffnet sich im Browser. Sie läuft nur lokal unter `http://127.0.0.1:8765`. Das
schwarze Fenster muss offen bleiben, sein Schließen beendet die App.

1. **Dokument auswählen:** links „PDF oder Bild auswählen …“ oder die Datei ins Fenster ziehen. Jedes Dokument wird ein Projekt im **Arbeitsordner** (Standard: `DataDigititalyzer` im Benutzerordner, z. B. `C:\Users\<Name>\DataDigititalyzer`).
2. **Einstellungen prüfen:** Die **Vorschau** zeigt sofort die begradigte Seite mit den erkannten Spalten (blau, dem Verlauf der Spalte folgend und nur über die Tabellenhöhe), Zellen (rot), leeren Zellen (blaue Rahmen: Wert erwartet, aber keine Tinte gefunden) und Zeilennummern (grün), dazu Winkel, Spalten-, Zeilen- und Zellenzahl. Jede Änderung einer Einstellung aktualisiert die Vorschau. Siehe [Einstellungen](#einstellungen).
3. **Scan starten:** Die Erkennung läuft im Hintergrund mit Fortschrittsanzeige (etwa 10 s pro Seite).
4. **Prüfung öffnen:** offene Punkte durchgehen (Taste **N**) und mit **Enter** bestätigen oder Ziffern tippen und mit **Enter** korrigieren.
5. **Exportieren** (oben rechts in der Prüfung): standardmäßig die **Tabelle wie im Scan** als CSV (siehe [Export](#export)).

Alle Korrekturen werden **sofort** gespeichert. Über „◀ Projekte“ geht es zurück zur
Übersicht, die Prüfung lässt sich jederzeit fortsetzen. **Neu auswerten** (z. B. mit
geänderten Einstellungen) übernimmt bereits von Hand geprüfte Werte, soweit die Zellen an
derselben Stelle wieder erkannt werden.

Eine PDF direkt auf `digitalisieren.bat` zu ziehen, wertet sie ohne Startseite aus und öffnet
gleich die Prüfung (Ergebnis im Ordner `<Datei>_digitalisiert` daneben).

### Einstellungen

Normalerweise ist nichts einzustellen. Bei schlechten Scans hilft die Vorschau beim Nachjustieren:

| Problem in der Vorschau | Einstellung |
|---|---|
| Raster schief, Zellen verrutschen | **Drehwinkel**: in Schritten von 0,1° korrigieren, oder automatische Erkennung abschalten und den Winkel vorgeben |
| Seite sehr schief eingelegt | **Suchbereich Schräglage** vergrößern |
| Blasse Ziffern fehlen (leere Zellen) | **Empfindlichkeit** erhöhen (z. B. 215); **Blasse Bereiche angleichen** muss eingeschaltet sein |
| Scan wird zu einem Rand hin blasser, dort fehlen Ziffern oder Ziffernteile | **Blasse Bereiche angleichen** (Standard: an) |
| Flecken/Rauschen werden zu Zellen | Empfindlichkeit verringern oder **Staubfilter** erhöhen |
| Zeilen doppelt oder zusammengelegt | **Zeilenabstand** setzen (den Wert aus der Vorschau-Info übernehmen und anpassen) |
| Stempel, Notizen oder Lochung am Rand stören | **Ausschnitt**: Ränder ausblenden |
| Sehr kleine Schrift / niedrige Auflösung | **Bild vergrößern** auf 1,5 oder 2 |
| Dünne, zerrissene Ziffern werden falsch gelesen | **Glättung für die Texterkennung** (Standard 0,7) |
| Kopf (Startwinkel, Schritt) unlesbar oder fehlt | **Kopfangaben** eintragen |
| Spalten nicht als (n, Durchschnittl. Intensität)-Paare erkannt | **Paare** auf „ja“ setzen |
| Eine Randspalte fehlt (Vorschau zeigt 19 statt 20 Spalten) bei stark gewölbtem Blatt | **Drehwinkel** in Schritten von 0,1° nachstellen, bis die Zeilen am betroffenen Rand gerade liegen; notfalls die Seite flacher neu scannen |

Die Einstellungen werden je Projekt gespeichert (`info.json`).

### Befehle ohne App


| Befehl | Zweck |
|---|---|
| `python -m digitalyzer` bzw. `python -m digitalyzer app [--arbeitsordner ORDNER]` | App mit Projektübersicht starten |
| `python -m digitalyzer scan.pdf` | Scan direkt auswerten und Prüfung öffnen |
| `python -m digitalyzer analysieren a.pdf b.pdf` | mehrere Scans auswerten (je ein Projektordner) |
| `python -m digitalyzer analysieren scan.pdf --neu` | erneut auswerten; die bisherige Prüfung wird als `projekt_<Zeit>.json` gesichert |
| `python -m digitalyzer analysieren scan.pdf --start 9.89 --schritt 0.05` | Winkel vorgeben, falls der Kopf unlesbar ist |
| `python -m digitalyzer pruefen ORDNER [--port 8765] [--kein-browser]` | Prüfung eines Projektordners öffnen |
| `python -m digitalyzer exportieren ORDNER [--format tabelle\|messpunkte\|xy] [-o datei] [--international]` | Export ohne Browser |

Ein vorhandenes Projekt wird nie stillschweigend überschrieben.

---

## Die Prüf-App

| Ansicht | Inhalt |
|---|---|
| **Prüftabelle** (F1) | Jede Zelle zeigt den **Bildausschnitt aus dem Scan** und **direkt daneben den erkannten Wert**, zeilengetreu wie im Original. Die Farben zeigen den Status. Mit „nur Zeilen mit offenen Punkten“ bleiben nur die Stellen übrig, die geprüft werden müssen. |
| **Seite** (F2) | Die ganze Seite mit fünf Modi: **Original + Werte** (Wert farbig neben jeder Zahl), **Nur Original**, **Nachgezeichnet**, **Blinken** und **Differenz** (siehe unten). Ein Klick auf eine Zahl wählt die Zelle aus. |
| **Diagramm** (F3) | Die erkannten Durchschnittl. Intensitäten über 2θ. Lesefehler fallen dort als Spitzen oder Einbrüche auf. Ein Klick auf einen Punkt springt zur Zelle. |

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
   - **Kontrastausgleich:** Wird der Scan zu einem Rand hin blasser, wird die Tinte dort auf das Niveau der übrigen Seite verstärkt (je Umgebung von etwa drei Zeilen × anderthalb Spalten, höchstens dreifach). Ohne diesen Schritt fallen blasse Ziffern aus den Tintenmasken, weil deren Schwellen für die ganze Seite gelten. Kräftige Bereiche und leeres Papier bleiben unverändert.
   - Die **Schräglage** wird über die Schärfe des Zeilenprofils gemessen (Grob-fein-Suche, ±6°, Genauigkeit etwa 0,02°) und korrigiert. Jeder Scan wird dabei einzeln vermessen.
   - Für die Spaltentrennung dient eine strenge Schwarz-Weiß-Maske, für blasse Ziffern wie dünne „1“ eine großzügige.
3. **Raster:**
   - Spalten werden über das senkrechte Tintenprofil gefunden. Eine Trennung gilt nur, wenn auch die Lücke *in den einzelnen Zeilen* groß genug ist. So wird die führende „1“ dreistelliger Zahlen nicht als eigene Spalte abgetrennt, auch wenn sie etwas abgesetzt steht („1 03“). Als echte Trennung gilt eine Lücke ab einer Zeichenhöhe; in den Testscans stehen führende Ziffern höchstens 0,42 Zeichenhöhen ab, echte Spalten mindestens 2,6.
   - Zeilen werden **je Spalte** gesucht und dann über die Spalten hinweg zugeordnet. Dadurch stören leichte Blattkrümmungen nicht.
   - Spalten, deren Zeilen nicht zum gemeinsamen Raster passen, werden als Störung verworfen (Lochung, Schatten, Notizen am Rand). Dabei zählt nur die **Streuung** der Zeilenpositionen, nicht ein gleichmäßiger **Versatz**: Bei einem gewölbten Blatt liegen die äußeren Spalten durchgehend etwas höher oder tiefer als die Seitenmitte, weil die Begradigung nur einen Winkel je Seite korrigiert. Solche Spalten bleiben erhalten, solange der Versatz unter 0,4 Zeilenabständen liegt.
   - Der **Zeilenabstand** wird über die Autokorrelation des Profils gemessen. So werden auch Zeilen sauber getrennt, deren Ziffern sich bei dichtem Zeilenabstand berühren.
   - Blasse Ziffern, die in mehrere Bruchstücke zerfallen, werden wieder zusammengefügt. Der Staubfilter entfernt nur Flecken, die **keine Tinte in der Nähe** haben.
   - Kopf und Seitenzahl werden über den abweichenden Zeilenabstand abgetrennt. Staub, Papierkanten und eine unvollständige letzte Zeile werden erkannt.
   - Jeder Tintenblock einer Zeile wird der Spalte zugeordnet, mit der er sich am stärksten überlappt. So gerät auch bei eng stehenden Spalten keine Nachbarziffer in eine Zelle. Ein Block in der Lücke zwischen zwei Spalten (z. B. die etwas abgesetzte führende „1“ einer vierstelligen Zahl) gehört zum benachbarten Block mit der kleineren Lücke.
4. **Drei unabhängige Lesarten je Zelle:**
   - **RapidOCR** (PaddleOCR-Modelle über die ONNX Runtime, lokal) in **zwei Bildvarianten**: unverändert (2,5-fach vergrößert) und leicht geglättet (3-fach). Die Glättung verbindet dünne, zerrissene Striche.
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
| Durchschnittl. Intensität gegen ihre Nachbarn im Winkelverlauf (auch über Zeilen- und Seitenumbrüche hinweg): grobe Sprünge nach oben, Einbrüche > 4σ (Poisson) nach unten; Peakspitzen sind ausgenommen | fehlende oder zusätzliche Ziffern, Ziffernverwechslungen |
| Kopfangaben gegen die Punktzahl | z. B. „5“ statt „0.05“ (verlorener Dezimalpunkt) |

---

## Ergebnisse mit den Beispielscans

Gemessen mit RapidOCR 1.4.4 (wird unter Python 3.12 installiert). Als Referenz für die
Messung dienen die geprüften Werte des guten Scans.

| | guter Scan (4 Seiten, 200 dpi, unscharf) | schlechter Scan (Seite 5, 150 dpi, dünne zerrissene Ziffern, gewölbt) |
|---|---|---|
| gefundene Messpunkte | **3004 von 3004** laut Kopf | **704 von 704** (71 Zeilen) |
| Werte richtig | > 99,9 % | 98,2 % |
| Zellen „ok“ | 5991 von 6008, Stichprobe von Hand nachgelesen: alle richtig | 1112 von 1408, alle richtig |
| zur Prüfung markiert | 17 Zellen | 296 Zellen (21 %), meist schon mit richtigem Vorschlag |
| falsche Werte **ohne** Markierung | 0 | 0 |

Vor den Verbesserungen für dichte Zeilen und zerfallende Ziffern wurden im schlechten Scan
76 statt 71 Zeilen gefunden, und nur 88,6 % der Werte standen an der richtigen Stelle.

Robustheit: Werden die Seiten des guten Scans zusätzlich um +3° bis −4° gedreht, bleibt das
Raster identisch, und 1 Wert weicht ab. Mit zusätzlicher Unschärfe weichen 17 Werte ab. In
beiden Fällen sind **alle** Abweichungen markiert.

---

## Export

| Format | Inhalt |
|---|---|
| **Tabelle wie im Scan** (Standard) | Eine Zeile je Scanzeile, die Werte in der Reihenfolge des Originals (`n;Durchschnittl. Intensität;n;Durchschnittl. Intensität;…`), ohne Überschrift und Zusatzspalten. Die Seiten werden lückenlos aneinandergehängt, die letzte unvollständige Zeile ist entsprechend kürzer. Eine unlesbare Zelle bleibt als leeres Feld stehen, damit alle anderen Werte an ihrem Platz bleiben. |
| **Messpunkte** | Eine Zeile je Messpunkt: Messreihe, Index, 2θ, n, Durchschnittl. Intensität, statistischer Fehler (`Stat_Fehler`), Seite, Zeile, Spalte, Status beider Zellen, Hinweise. Damit ist jeder Wert auf seine Stelle im Scan zurückführbar. |
| **.xy** | Zwei Spalten: 2θ und Durchschnittl. Intensität, für Auswerteprogramme. |
| **.xye** | Drei Spalten: 2θ, Durchschnittl. Intensität und statistischer Fehler, durch Leerzeichen getrennt, ohne Kopfzeile. Lesbar u. a. für GSAS-II, FullProf, TOPAS und Jana. Messpunkte ohne lesbare Durchschnittl. Intensität oder ohne lesbares n fehlen, weil ihr Fehler nicht bestimmbar ist; die Kommandozeile meldet ihre Anzahl. Vorher in der Prüfung korrigieren. |

### Statistischer Fehler

Die Durchschnittl. Intensität I ist je Detektor normiert: Zu einem Messpunkt haben n Detektoren
beigetragen, tatsächlich registriert wurden also N = I · n Ereignisse. Nach der
Poisson-Statistik ist σ(N) = √N, für die Durchschnittl. Intensität folgt

    σ(I) = √(I · n) / n = √(I / n)

Bei gleicher Durchschnittl. Intensität ist der Fehler also umso kleiner, je mehr Detektoren
beteiligt waren (Beispiel: I = 100 → σ = 5 bei n = 4, σ = 3,54 bei n = 8). Bei I = 0 wird
N = 1 angesetzt, damit der Punkt in einer Anpassung kein unendliches Gewicht erhält. Ohne lesbares n bleibt
der Fehler leer. Der Fehler wird mit vier Nachkommastellen ausgegeben.

Für Excel mit deutschen Einstellungen wird das Semikolon als Trenner verwendet,
„international“ verwendet das Komma. In der App wählt man das Format links neben
„Exportieren“. Von der Kommandozeile:

```bash
python -m digitalyzer exportieren scan_digitalisiert
```

Das schreibt `scan_digitalisiert/tabelle.csv`. Mit `--format messpunkte`, `--format xy` oder
`--format xye` entstehen die anderen Formate (`messpunkte.csv`, `messwerte.xy`, `messwerte.xye`).

Sind beim Export noch Zellen offen, fragt die App nach. Exportiert wird immer der aktuelle
Stand inklusive aller Korrekturen.

---

## Projektordner

```
<Arbeitsordner>/<Projekt>/
  scan.pdf                Kopie des hochgeladenen Dokuments
  info.json               Name, Herkunft, Einstellungen
  projekt.json            alle Zellen: Position im Scan, Lesarten, Wert, Status, Korrekturen
  ziffern.npz             gelernte Ziffernbilder (für die Nachzeichnung)
  seiten/original_001.jpg begradigtes Originalbild
  seiten/kontrast_001.jpg begradigt + Hintergrund ausgeglichen
  tabelle.csv             (nach Export)
```

---

## Datenschutz

Alles läuft lokal. Die App lauscht nur auf `127.0.0.1`, also nur auf dem eigenen Rechner.
Andere Webseiten, die im selben Browser geöffnet sind, können sie nicht ansprechen: Die App
beantwortet nur Anfragen an ihre eigene Adresse und nimmt Änderungen nur von ihren eigenen
Seiten an.
Neuere Versionen der ONNX Runtime (die Grundlage der Texterkennung) senden von sich aus
Nutzungsdaten an Microsoft. Die Funktion `disable_telemetry_events()` allein verhindert das
nicht, nachgewiesen mit ONNX Runtime 1.31. DataDigititalyzer setzt deshalb beim Start
zusätzlich `ORT_DISABLE_TELEMETRY=1`. Damit war in Tests kein Verbindungsversuch mehr
festzustellen.

---

## Grenzen und Ideen

- Das Raster ist auf **Tabellen aus gedruckten Ziffern** ausgelegt. Handschrift erkennt RapidOCR deutlich schlechter. Dann hilft vor allem der Ziffernklassifikator, wenn genug Beispiele bestätigt sind.
- Die Paarbildung (n, Durchschnittl. Intensität) wird automatisch erkannt: abwechselnd einstellige und mehrstellige Spalten. Andere Layouts werden als reine Wertespalten gelesen.
- Die Seiten werden **begradigt** angezeigt, nicht im ursprünglichen Winkel.
- Eine Seite mit **nur ein oder zwei Tabellenzeilen** wird nicht als Tabelle erkannt (zu wenig Zeilen, um sie von Staub und Randmarken zu unterscheiden). Fehlen dadurch Messpunkte, meldet die Prüfung „x von y erwarteten Punkten (ABWEICHUNG)“.
- Seiten ohne erkennbare Tabelle (Deckblatt, leere oder stark verrauschte Seite) ergeben ein leeres Raster und werden übersprungen. Quer liegende Scans ohne Drehangabe im PDF und invertierte Scans (helle Schrift auf dunklem Grund) werden nicht erkannt.
- Nicht lesbare Dateien (beschädigt, kein PDF, unbekanntes Bildformat) werden schon beim Hochladen abgelehnt.
- Mögliche Erweiterungen:
  - Korrekturen als Trainingsdaten für weitere Dokumente nutzen.
  - Mehrere Dokumente nacheinander automatisch auswerten (Warteschlange).
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
| `settings.py` | Einstellungen mit Beschreibung für die Oberfläche |
| `server.py`, `static/` | App: Projekte, Upload, Vorschau, Auswertung im Hintergrund, Prüfung (Python-Standardbibliothek + HTML/JS, ohne Internet) |
| `export.py` | CSV / `.xy` |
