"""Kompletter Durchlauf auf kuenstlichen Scans (dauert ca. 20-40 s)."""
import json

import pymupdf
import pytest

from digitalyzer import export
from digitalyzer.pdf_io import write_image
from digitalyzer.pipeline import load_project, process
from synth import make_series, render_page


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    pairs = make_series(1000, seed=3)
    pages = [render_page(pairs[:500], header=True, angle=1.8, seed=1, total_points=len(pairs)),
             render_page(pairs[500:], header=False, angle=-2.6, blur=1.4, seed=2)]
    doc = pymupdf.open()
    for i, img in enumerate(pages):
        f = tmp / f"p{i}.jpg"
        write_image(f, img, quality=85)
        pg = doc.new_page(width=img.shape[1] * 72 / 200, height=img.shape[0] * 72 / 200)
        pg.insert_image(pg.rect, filename=str(f))
    pdf = tmp / "scan.pdf"
    doc.save(pdf)
    out = tmp / "projekt"
    process(pdf, out, log=lambda m: None)
    return pairs, out


def test_all_points_found_and_header_read(run):
    pairs, out = run
    p = load_project(out)
    s = p["series"][0]
    assert s["header"]["start"] == pytest.approx(9.89)
    assert s["header"]["step"] == pytest.approx(0.05)
    assert s["expected"] == len(pairs) == s["points"]


def test_values_correct_or_flagged(run):
    pairs, out = run
    p = load_project(out)
    rows = export.rows(p)
    assert len(rows) == len(pairs)
    wrong_silent = 0
    wrong = 0
    for (n, c), r in zip(pairs, rows):
        for truth, val, status in ((n, r["n"], r["Status_n"]), (c, r["Zaehlrate"], r["Status_Zaehlrate"])):
            if str(truth) != val:
                wrong += 1
                if status == "ok":
                    wrong_silent += 1
    # Entscheidend: falsche Werte duerfen (fast) nie als "ok" durchgehen
    assert wrong_silent <= 2, f"{wrong_silent} falsche Werte als ok markiert"
    assert wrong <= 0.03 * 2 * len(pairs)


def test_export_formats(run, tmp_path):
    _, out = run
    p = load_project(out)
    csv_de = export.to_csv(p)
    assert csv_de.splitlines()[0].startswith("Messreihe;Index;2Theta")
    assert ";9,89;" in csv_de.splitlines()[1]
    xy = export.to_xy(p).splitlines()
    assert xy[0].startswith("9.8900")
    target = export.write(p, tmp_path / "m.csv")
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM fuer Excel
    json.dumps(p)  # Projekt bleibt serialisierbar
