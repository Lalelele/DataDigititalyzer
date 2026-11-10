"""Export: statistischer Fehler aus der Detektoranzahl, CSV-Spalten und .xye-Datei."""
import math

import pytest

from digitalyzer import export
from digitalyzer.validate import validate
from test_rules import _project


def test_stat_fehler_aus_detektoranzahl():
    # Zaehlrate je Detektor normiert: N = Z * n Ereignisse, sigma(Z) = sqrt(Z * n) / n = sqrt(Z / n)
    assert export.stat_fehler("78", "6") == pytest.approx(math.sqrt(13))
    assert export.stat_fehler(100, 4) == pytest.approx(5.0)
    assert export.stat_fehler("100", "1") == pytest.approx(10.0)
    # mehr Detektoren -> kleinerer Fehler bei gleicher Zaehlrate
    assert export.stat_fehler("100", "8") < export.stat_fehler("100", "2")
    # Z = 0: N = 1 ansetzen, damit der Punkt nicht unendlich gewichtet wird
    assert export.stat_fehler("0", "4") == pytest.approx(0.25)


@pytest.mark.parametrize("z, n", [("", "5"), ("80", ""), ("80", None), ("80", "0"), ("8?", "5"), ("80", "x")])
def test_stat_fehler_ohne_gueltige_werte(z, n):
    assert export.stat_fehler(z, n) is None


def _fertiges_projekt(pairs, override=None):
    p = _project(pairs, override)
    validate(p)
    return p


def test_messpunkte_csv_hat_fehlerspalte():
    p = _fertiges_projekt([(4, 100), (5, 80)] * 10)
    zeilen = export.to_csv(p).splitlines()
    kopf = zeilen[0].split(";")
    assert kopf[kopf.index("Zaehlrate") + 1] == "Stat_Fehler"
    erste = dict(zip(kopf, zeilen[1].split(";")))
    assert erste["Stat_Fehler"] == "5"  # sqrt(100 / 4), deutsches Format
    zweite = dict(zip(kopf, zeilen[2].split(";")))
    assert zweite["Stat_Fehler"] == "4"  # sqrt(80 / 5)
    intl = export.to_csv(p, international=True).splitlines()[3].split(",")
    assert intl[5] == "5"


def test_xye_drei_spalten_und_auslassen_ohne_n():
    leer = {"ocr1": "", "ocr2": "", "ziffern": ""}
    p = _fertiges_projekt([(4, 64)] * 20, {"s1z1s3": leer})
    pts, ausgelassen = export.xye_rows(p)
    assert ausgelassen == 1 and len(pts) == 19
    zeilen = export.to_xye(p).splitlines()
    assert zeilen[0].split() == ["10.0000", "64", "4.0000"]
    assert all(len(z.split()) == 3 for z in zeilen)


def test_write_erkennt_xye_an_der_endung(tmp_path):
    p = _fertiges_projekt([(4, 64)] * 10)
    ziel = export.write(p, tmp_path / "daten.xye")
    assert ziel.read_text(encoding="utf-8").splitlines()[0].split() == ["10.0000", "64", "4.0000"]
    assert export.write(p, tmp_path / "x.dat", fmt="xye").read_text().count("\n") == 10
