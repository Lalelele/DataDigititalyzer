import numpy as np
import pytest

from digitalyzer.pipeline import prepare_page
from synth import make_series, render_page


@pytest.mark.parametrize("angle", [-4.0, -1.3, 0.0, 0.7, 2.5, 5.0])
def test_skew_and_grid(angle):
    pairs = make_series(400)
    page = render_page(pairs, angle=angle)
    pg = prepare_page(page)
    # gemessene Korrektur muss die kuenstliche Drehung aufheben
    assert abs(pg.angle + angle) < 0.15
    lay = pg.layout
    assert len(lay.columns) == 20
    assert lay.row_y.shape[0] == 40
    filled = sum(not c.empty for c in lay.cells)
    assert filled == 800


def test_partial_last_row_and_header_excluded():
    pairs = make_series(73)  # letzte Zeile nur 3 Paare
    pg = prepare_page(render_page(pairs, angle=-1.0))
    lay = pg.layout
    assert lay.row_y.shape[0] == 8
    filled = sorted((c.row, c.col) for c in lay.cells if not c.empty)
    assert len(filled) == 146
    assert max(c for r, c in filled if r == 7) == 5
    assert lay.header_box is not None


@pytest.mark.parametrize("blur", [1.6, 2.2, 2.6])
def test_grid_survives_blur(blur):
    # starke Unschaerfe laesst duenne Ziffern in der strengen Maske zerfallen; das Raster
    # darf dadurch keine Spalten verlieren (Regression)
    pairs = [(1, 100 + i % 50) for i in range(300)]  # n = '1': schmalste Ziffer
    pg = prepare_page(render_page(pairs, angle=2.0, blur=blur, n_gray=70))  # blasse, duenne '1' (etwa wie im echten Scan)
    assert len(pg.layout.columns) == 20
    assert sum(not c.empty for c in pg.layout.cells) == 600


@pytest.mark.parametrize("row_step", [17, 18, 20])
def test_dense_rows_touching(row_step):
    # Zeilen so dicht, dass sich die Ziffern uebereinanderliegender Zeilen beruehren
    # (keine Luecken mehr im Profil) - Regression fuer schlechte Scans
    pairs = make_series(600, seed=5)
    pg = prepare_page(render_page(pairs, angle=1.0, blur=1.3, row_step=row_step))
    assert len(pg.layout.columns) == 20
    assert pg.layout.row_y.shape[0] == 60
    assert sum(not c.empty for c in pg.layout.cells) == 1200


@pytest.mark.parametrize("kruemmung", [8, 12, 16])
def test_gekruemmtes_blatt_behaelt_randspalte(kruemmung):
    # Gewoelbtes Blatt: die Zeilen sinken zum linken Rand hin ab. Eine einzige Drehung kann das
    # nicht ausgleichen, die erste Spalte liegt daher durchgehend etwas tiefer als die
    # Zeilenmitte. Sie ist aber regelmaessig und darf nicht als Stoerung verworfen werden
    # (Regression: Seite 3 des Neutronenbeugungs-Scans verlor so die erste n-Spalte).
    pairs = make_series(400)
    pg = prepare_page(render_page(pairs, angle=-0.8, kruemmung=kruemmung))
    lay = pg.layout
    assert len(lay.columns) == 20
    assert lay.row_y.shape[0] == 40
    assert sum(not c.empty for c in lay.cells) == 800


@pytest.mark.parametrize("verblassen", [0.75, 0.8])
def test_blasser_oberer_rand_wird_ausgeglichen(verblassen):
    # Scan wird zum oberen Rand hin deutlich blasser (Neutronenbeugungs-Scan, Seite 32/33).
    # Ohne Kontrastausgleich fallen dort Ziffern ganz oder teilweise aus der Tintenmaske.
    pairs = make_series(400)
    ref = {(c.row, c.col): c.box[2] for c in prepare_page(render_page(pairs, angle=-0.8)).layout.cells}
    lay = prepare_page(render_page(pairs, angle=-0.8, verblassen=verblassen)).layout
    assert len(lay.columns) == 20
    assert lay.row_y.shape[0] == 40
    assert sum(not c.empty for c in lay.cells) == 800
    # Zellen der oberen Zeilen muessen die ganze Zahl umfassen, nicht nur Bruchstuecke
    oben = [c for c in lay.cells if c.row < 10]
    zu_schmal = sum(1 for c in oben if c.box[2] < ref[(c.row, c.col)] - 3)
    assert zu_schmal <= 2


def test_kontrastausgleich_laesst_kraeftige_tinte_unveraendert():
    from digitalyzer.preprocess import equalize_ink_contrast
    img = np.full((400, 400), 250, np.uint8)
    img[100:300:20, 50:350:30] = 90  # kraeftige Tinte (wie ein guter Scan)
    out = equalize_ink_contrast(img)
    assert np.abs(out.astype(int) - img.astype(int)).max() <= 1
    leer = np.full((400, 400), 240, np.uint8)  # nur Papier: Rauschen nicht verstaerken
    assert np.abs(equalize_ink_contrast(leer).astype(int) - 240).max() <= 1


def test_abgesetzte_fuehrende_ziffer_gehoert_zur_zahl():
    # Vierstellige Zaehlrate, deren fuehrende '1' etwas abgesetzt in der Luecke zwischen
    # n-Spalte und Zaehlratenspalte steht ('8' | '1' '157'). Sie liegt dem n-Band nur
    # wenige Pixel naeher, gehoert aber zur Zahl rechts (Seite 2, Zeile 65 im Testscan).
    from digitalyzer.layout import _assign_segments
    cols = [(862, 911), (912, 958), (984, 1036)]
    segs = [(919, 929), (962, 969), (976, 1006)]
    res = _assign_segments(segs, cols, ch=11.0)
    assert [c for _, _, c in res] == [1, 2, 2]


@pytest.mark.parametrize("abstand", [3, 5])
def test_abgesetzte_fuehrende_ziffer_bildet_keine_eigene_spalte(abstand):
    # Seite 4 des Neutronenbeugungs-Scans (paper-004): die fuehrende Ziffer dreistelliger
    # Zaehlraten steht etwas abgesetzt ('1 03'). Viele dreistellige Werte bilden im
    # Spaltenprofil ein eigenes schmales Band, das wieder mit der Zahl vereinigt werden muss
    # (Regression: 22 statt 20 Spalten, die '1' landete in einer eigenen Spalte).
    rng = np.random.default_rng(3)
    pairs = [(1 + i // 140, int(c)) for i, c in enumerate(rng.integers(70, 140, 400))]  # ~60 % dreistellig
    lay = prepare_page(render_page(pairs, angle=-0.8, abstand_fuehrend=abstand)).layout
    assert len(lay.columns) == 20
    assert lay.row_y.shape[0] == 40
    assert sum(not c.empty for c in lay.cells) == 800
