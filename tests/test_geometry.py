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
