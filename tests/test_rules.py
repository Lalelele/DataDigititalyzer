from digitalyzer.header import parse_header
from digitalyzer.recognize import collapse_repeats, combine, digits_only
from digitalyzer.validate import resolve_with_rules, validate


def _project(pairs, cand_override=None):
    cells = []
    for i, (n, c) in enumerate(pairs):
        row, k = divmod(i, 10)
        for col, v in ((2 * k, n), (2 * k + 1, c)):
            cid = f"s1z{row + 1}s{col + 1}"
            cand = {"ocr1": str(v), "ocr2": str(v), "ziffern": str(v)}
            if cand_override and cid in cand_override:
                cand = cand_override[cid]
            value, agree, alts = combine([cand["ocr1"], cand["ocr2"], cand["ziffern"]])
            cells.append({"id": cid, "page": 0, "row": row, "col": col, "box": [0, 0, 1, 1], "value": value,
                          "ocr_value": value, "cand": cand, "agree": agree, "n_engines": 3})
    header = {"start": 10.0, "step": 0.1, "finish": 10.0 + 0.1 * (len(pairs) - 1), "expected_points": len(pairs)}
    return {"cells": cells, "series": [{"id": 0, "header": header, "pages": [0]}], "pages": [{}]}


def test_clean_series_is_ok():
    pairs = [(5, 50 + (i % 3)) for i in range(30)]
    p = _project(pairs)
    s = validate(p)
    assert s["ok"] == 60 and s["fehler"] == 0 and s["points"] == 30
    assert p["series"][0]["complete"] is True


def test_detector_outlier_and_suggestion():
    pairs = [(5, 50)] * 30
    # n in Punkt 12 (Zeile 2, Spalte 5) als 3 gelesen
    p = _project(pairs, {"s1z2s5": {"ocr1": "3", "ocr2": "3", "ziffern": "5"}})
    validate(p)
    cell = next(c for c in p["cells"] if c["id"] == "s1z2s5")
    assert cell["status"] == "fehler"
    assert any(f.get("suggest") == "5" for f in cell["flags"])
    # korrekte Nachbarn duerfen nicht mitmarkiert werden
    neighbours = [c for c in p["cells"] if c["id"] in ("s1z2s3", "s1z2s7")]
    assert all(c["status"] == "ok" for c in neighbours)
    assert resolve_with_rules(p) == 1
    assert cell["value"] == "5" and cell["status"] == "pruefen"


def test_count_spike_and_missing_digit():
    pairs = [(8, 60)] * 30
    p = _project(pairs, {"s1z1s8": {"ocr1": "6", "ocr2": "6", "ziffern": "60"},     # Ziffer verloren
                         "s1z2s2": {"ocr1": "660", "ocr2": "660", "ziffern": "660"}})  # Ziffer zu viel
    validate(p)
    by = {c["id"]: c for c in p["cells"]}
    assert by["s1z1s8"]["status"] == "fehler"
    assert by["s1z2s2"]["status"] == "fehler"
    resolve_with_rules(p)
    assert by["s1z1s8"]["value"] == "60"           # plausible Lesart gewaehlt
    assert by["s1z2s2"]["status"] == "fehler"      # keine plausible Alternative -> bleibt rot


def test_peak_is_not_flagged():
    counts = [60, 62, 120, 400, 1500, 3600, 2400, 900, 250, 90, 61, 58] + [60] * 18
    p = _project([(8, c) for c in counts])
    validate(p)
    assert p["summary"]["fehler"] == 0 and p["summary"]["pruefen"] == 0


def test_human_override_wins():
    p = _project([(5, 50)] * 20, {"s1z1s4": {"ocr1": "9000", "ocr2": "9000", "ziffern": "9000"}})
    validate(p)
    c = next(c for c in p["cells"] if c["id"] == "s1z1s4")
    assert c["status"] == "fehler"
    c["human"] = "bestaetigt"
    validate(p)
    assert c["status"] == "bestaetigt"


def test_combine_and_ctc_repeat_rule():
    assert combine(["35", "35", "35"]) == ("35", 3, [])
    assert combine(["35", "36", "35"])[0] == "35"
    # OCR zieht '66' zu '6' zusammen, Ziffernklassifikator zaehlt zwei Ziffern
    assert combine(["6", "6", "66"])[0] == "66"
    assert combine(["7", "", "77"])[0] == "77"
    assert collapse_repeats("1166") == "16"
    assert digits_only("l O5|") == "1051"


def test_header_parsing_fuzzy():
    toks = [("Sample:", .7, (182, 236, 60, 20)), ("Al203 (Alloy 1-295K)", .8, (310, 234, 200, 20)),
            ("Step:", .8, (968, 286, 40, 15)), ("160.04", .8, (878, 287, 50, 15)), ("9.89", .6, (635, 288, 30, 15)),
            ("1.376 A", .8, (356, 290, 50, 15)), ("Fiaishing angle:", .8, (708, 291, 120, 15)),
            ("Starting angle:", .8, (460, 292, 110, 15)), ("Wavelength:", .8, (184, 293, 90, 15)),
            ("0.05", .7, (1043, 286, 30, 15))]
    h = parse_header(toks)
    assert h["start"] == 9.89 and h["finish"] == 160.04 and h["step"] == 0.05 and h["wavelength"] == 1.376
    assert h["expected_points"] == 3004
