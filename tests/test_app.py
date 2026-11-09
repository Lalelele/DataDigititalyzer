"""Einstellungen, Vorschau, Projektverwaltung der App und Uebernahme von Korrekturen."""
import cv2
import pytest

from digitalyzer.pipeline import carry_over, prepare_page
from digitalyzer.server import App
from digitalyzer.settings import Settings
from synth import make_series, render_page


def test_settings_parse_and_clamp():
    s = Settings.from_dict({"winkel_auto": "false", "winkel": "1,5", "empfindlichkeit": "999",
                            "paare": "ja", "start": "", "schritt": "0.05", "unbekannt": 3})
    assert s.winkel_auto is False and s.winkel == 1.5
    assert s.empfindlichkeit == 250  # begrenzt
    assert s.paare == "ja" and s.start is None and s.schritt == 0.05
    assert s.header_override() == {"step": 0.05}
    assert Settings.from_dict(s.to_dict()) == s


def test_manual_angle_and_crop():
    page = render_page(make_series(200), angle=2.0)
    auto = prepare_page(page)
    manual = prepare_page(page, Settings(winkel_auto=False, winkel=auto.angle))
    assert abs(manual.angle - auto.angle) < 1e-9
    assert len(manual.layout.columns) == 20
    # rechte Haelfte ausblenden -> nur noch linke Spalten
    half = prepare_page(page, Settings(rand_rechts=50))
    assert 0 < len(half.layout.columns) < 20


@pytest.fixture()
def app(tmp_path):
    return App(tmp_path / "ws")


def test_project_upload_preview_settings(app):
    img = render_page(make_series(300), angle=-1.5)
    ok, buf = cv2.imencode(".png", img)
    pid = app.create_project("Messung 1.png", buf.tobytes())
    pid2 = app.create_project("Messung 1.png", buf.tobytes())
    assert pid != pid2  # kein Ueberschreiben
    projects = {p["id"]: p for p in app.list_projects()}
    assert projects[pid]["scan"] and not projects[pid]["ausgewertet"]
    info = app.info(pid)
    assert info["seiten"] == 1 and info["einstellungen"]["winkel_auto"] is True
    pv = app.preview(pid, 0, {"empfindlichkeit": 210})
    assert pv["bild"].startswith("data:image/jpeg;base64,")
    assert pv["info"]["spalten"] == 20 and pv["info"]["zellen"] == 600
    assert abs(pv["info"]["winkel"] - 1.5) < 0.15
    saved = app.save_settings(pid, {"winkel": 0.3, "winkel_auto": True})
    assert app.info(pid)["einstellungen"]["winkel"] == 0.3 == saved["winkel"]
    with pytest.raises(KeyError):
        app.project_dir("../etwas")
    with pytest.raises(ValueError):
        app.create_project("notiz.txt", b"x")


def test_carry_over_keeps_manual_values():
    def proj(boxes, size=(1000, 1000)):
        return {"pages": [{"index": 0, "width": size[0], "height": size[1], "pitch": 20}],
                "series": [{"id": 0, "header": {}, "pages": [0]}],
                "cells": [{"id": f"c{i}", "page": 0, "row": i, "col": 1, "box": b, "value": "50", "ocr_value": "50",
                           "agree": 3, "n_engines": 3} for i, b in enumerate(boxes)]}
    old = proj([[100, 100, 20, 14], [100, 121, 20, 14]])
    old["cells"][1].update(value="57", human="korrigiert")
    # neue Auswertung mit doppelter Aufloesung (Vergroesserung 2) und leicht verschobenem Raster
    new = proj([[202, 203, 40, 28], [201, 245, 40, 28]], size=(2000, 2000))
    assert carry_over(old, new) == 1
    assert new["cells"][1]["value"] == "57" and new["cells"][1]["human"] == "korrigiert"
    assert new["cells"][0].get("human") is None
