"""Gesamtablauf: Scan -> Seitenbilder -> Raster -> Erkennung -> Pruefung -> Projektordner.

Der Projektordner enthaelt:
  projekt.json          alle Zellen mit Position, Kandidaten, Wert, Status (Herkunft jedes Werts)
  seiten/original_NNN.jpg   begradigtes Originalbild je Seite
  seiten/kontrast_NNN.jpg   begradigt + Hintergrund ausgeglichen (fuer Differenzbild)
  ziffern.npz           gelernte Ziffernbilder (fuer die synthetische Seite)
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from . import header as header_mod
from . import layout as layout_mod
from . import preprocess as pp
from . import recognize as rec
from . import render
from .pdf_io import load_pages, write_image
from .validate import reconcile_header, resolve_with_rules, validate

PROJECT_FILE = "projekt.json"
TEMPLATE_FILE = "ziffern.npz"


@dataclass
class PreparedPage:
    original: np.ndarray  # begradigt, Graustufen
    norm: np.ndarray  # begradigt, Hintergrund ausgeglichen
    strict: np.ndarray
    weak: np.ndarray
    angle: float
    layout: layout_mod.PageLayout


def prepare_page(gray: np.ndarray, max_skew: float = 6.0) -> PreparedPage:
    paper = pp.paper_mask(gray)
    norm = pp.normalize_background(gray)
    angle = pp.estimate_skew(pp.ink_mask(norm) & paper, max_angle=max_skew)
    original = pp.rotate(gray, angle, border=255)
    norm = pp.rotate(norm, angle, border=255)
    paper = pp.rotate(paper, angle, border=0)
    strict = pp.ink_mask(norm) & paper
    weak = pp.weak_ink_mask(norm) & paper
    lay = layout_mod.analyze(strict, weak)
    return PreparedPage(original, norm, strict, weak, angle, lay)


def _log(msg: str, cb: Callable[[str], None] | None) -> None:
    (cb or print)(msg)


def process(source: str | Path, out_dir: str | Path, log: Callable[[str], None] | None = None,
            header_override: dict | None = None) -> dict:
    source, out_dir = Path(source), Path(out_dir)
    (out_dir / "seiten").mkdir(parents=True, exist_ok=True)

    _log(f"Lese {source.name} ...", log)
    grays = load_pages(source)
    _log(f"  {len(grays)} Seite(n)", log)

    engine = rec.RapidEngine()
    pages: list[PreparedPage] = []
    project: dict = {"version": 1, "source": source.name, "created": _dt.datetime.now().isoformat(timespec="seconds"),
                     "pages": [], "cells": [], "series": []}

    # ---------------- Seiten vorbereiten, Raster erkennen, Kopf lesen ----------------
    for i, g in enumerate(grays):
        pg = prepare_page(g)
        pages.append(pg)
        lay = pg.layout
        n_cells = sum(not c.empty for c in lay.cells)
        _log(f"  Seite {i + 1}: Schraeglage {pg.angle:+.2f} Grad, {len(lay.columns)} Spalten, "
             f"{lay.row_y.shape[0]} Zeilen, {n_cells} Zellen", log)
        orig_name, norm_name = f"seiten/original_{i + 1:03d}.jpg", f"seiten/kontrast_{i + 1:03d}.jpg"
        write_image(out_dir / orig_name, pg.original)
        write_image(out_dir / norm_name, pg.norm)

        hdr = None
        if lay.header_box and lay.table_top > lay.char_height * 2:
            region = pg.norm[:lay.table_top]
            if (pg.strict[:lay.table_top] > 0).sum() > lay.char_height ** 2 * 3:
                hdr = header_mod.parse_header(engine.read_text(region))
                if not any(k in hdr for k in ("start", "step", "wavelength", "sample")):
                    hdr = None
        project["pages"].append({
            "index": i, "original": orig_name, "kontrast": norm_name,
            "width": int(g.shape[1]), "height": int(pg.original.shape[0]),
            "angle": round(pg.angle, 3), "columns": [list(map(int, c)) for c in lay.columns],
            "pitch": lay.pitch, "char_height": lay.char_height, "table_top": lay.table_top, "header": hdr,
        })

    # Serien: eine neue Messreihe beginnt auf jeder Seite mit Kopfangaben (Start/Schritt)
    series: list[dict] = []
    for p in project["pages"]:
        h = p["header"]
        if not series or (h and "start" in h and "step" in h):
            series.append({"id": len(series), "header": h or {}, "pages": []})
        series[-1]["pages"].append(p["index"])
    if header_override:
        for s in series:
            s["header"].update(header_override)
            h = s["header"]
            if all(k in h for k in ("start", "finish", "step")) and h["step"] > 0:
                h["expected_points"] = int(round((h["finish"] - h["start"]) / h["step"])) + 1
    project["series"] = series

    # ---------------- Zellen sammeln ----------------
    cells: list[dict] = []
    for pi, pg in enumerate(pages):
        lay = pg.layout
        # leere Zellen am Ende der letzten Zeile sind keine Daten (Teilzeile)
        last_row = lay.row_y.shape[0] - 1
        filled_last = [c.col for c in lay.cells if c.row == last_row and not c.empty]
        tail_from = (max(filled_last) + 1) if filled_last else 0
        for c in lay.cells:
            if c.empty and c.row == last_row and c.col >= tail_from:
                continue
            cells.append({"id": f"s{pi + 1}z{c.row + 1}s{c.col + 1}", "page": pi, "row": c.row, "col": c.col,
                          "box": list(map(int, c.box)), "empty": bool(c.empty)})

    # ---------------- A) RapidOCR in zwei Vergroesserungen ----------------
    scales = (1.5, 2.5)
    for k, sc in enumerate(scales):
        _log(f"Texterkennung (RapidOCR, Vergroesserung {sc}x) ...", log)
        for pi, pg in enumerate(pages):
            idx = [j for j, c in enumerate(cells) if c["page"] == pi and not c["empty"]]
            res = engine.read_cells(pg.norm, [tuple(cells[j]["box"]) for j in idx], scale=sc)
            for j, (val, raw, score) in zip(idx, res):
                cells[j].setdefault("cand", {})[f"ocr{k + 1}"] = val
                cells[j].setdefault("raw", {})[f"ocr{k + 1}"] = raw
                cells[j].setdefault("score", {})[f"ocr{k + 1}"] = round(score, 3)

    # ---------------- B) dokumentspezifischer Ziffernklassifikator ----------------
    _log("Lerne die Ziffernformen dieses Dokuments ...", log)
    ch = float(np.median([p["char_height"] for p in project["pages"]]))
    # typische Ziffernbreite: Median der Breite einstelliger Zellen (schmale Zellen)
    narrow = [c["box"][2] for c in cells if not c["empty"] and c["box"][2] < ch * 1.2]
    digit_w = float(np.median(narrow)) if len(narrow) >= 20 else ch * 0.77
    digit_w = min(max(digit_w, ch * 0.6), ch * 0.95)

    glyph_meta: list[tuple[int, tuple, tuple]] = []  # (Seite, Ziffernbox, Zellbox)
    glyph_cell: list[int] = []
    feats = []
    for j, c in enumerate(cells):
        if c["empty"]:
            c["glyphs"] = []
            continue
        # Ziffernanzahl unabhaengig von der OCR aus der Geometrie bestimmen
        gl = rec.segment_glyphs(pages[c["page"]].weak, tuple(c["box"]), digit_w=digit_w)
        c["glyphs"] = [list(map(int, g)) for g in gl]
        for g in gl:
            glyph_meta.append((c["page"], g, tuple(c["box"])))
            glyph_cell.append(j)
            feats.append(rec.glyph_feature(pages[c["page"]].norm, g, tuple(c["box"])))
    feats_arr = np.array(feats, np.float32) if feats else np.zeros((0, rec.FEAT_H * rec.FEAT_W + 1), np.float32)
    glyph_cell_arr = np.array(glyph_cell)

    def training_labels(use_b: np.ndarray | None) -> np.ndarray:
        """Label je Ziffer aus sicheren Zellen (-1 = nicht zum Lernen verwenden)."""
        lab = np.full(len(feats_arr), -1, np.int16)
        pos = 0
        for j, c in enumerate(cells):
            ng = len(c["glyphs"])
            a = c.get("cand", {})
            v = a.get("ocr1")
            if ng and v and v == a.get("ocr2") and len(v) == ng:
                ok = True
                if use_b is not None:
                    ok = "".join(str(int(d)) for d in use_b[pos:pos + ng]) == v
                if ok:
                    lab[pos:pos + ng] = [int(d) for d in v]
            pos += ng
        return lab

    labels_b = None
    for round_ in range(2):  # zweite Runde lernt nur noch aus Zellen, bei denen A und B einig sind
        lab = training_labels(labels_b)
        train = np.where(lab >= 0)[0]
        model = rec.GlyphModel(feats_arr[train], lab[train].astype(np.int8))
        exclude = np.full(len(feats_arr), -1)
        exclude[train] = np.arange(len(train))
        labels_b, conf_b, second_b = model.predict(feats_arr, exclude=exclude)
        _log(f"  Runde {round_ + 1}: {len(train)} sichere Ziffern als Lernbeispiele", log)

    pos = 0
    for c in cells:
        ng = len(c["glyphs"])
        if c["empty"]:
            continue
        c["cand"]["ziffern"] = "".join(str(int(d)) for d in labels_b[pos:pos + ng])
        c["score"]["ziffern"] = round(float(np.prod(conf_b[pos:pos + ng])) if ng else 0.0, 3)
        pos += ng

    templates = rec.build_templates([p.norm for p in pages], glyph_meta, labels_b)
    render.save_templates(out_dir / TEMPLATE_FILE, templates)

    # ---------------- Abgleich ----------------
    for c in cells:
        cand = c.get("cand", {})
        order = [cand.get("ocr1", ""), cand.get("ocr2", ""), cand.get("ziffern", "")]
        value, agree, alts = rec.combine(order)
        c["value"], c["agree"], c["alternatives"], c["n_engines"] = value, agree, alts, 3
        c["ocr_value"] = value
        c.pop("empty")
    project["cells"] = cells
    for note in reconcile_header(project):
        _log(f"  Kopf: {note}", log)
    n_rule = resolve_with_rules(project)
    if n_rule:
        _log(f"  {n_rule} Zellen: andere Lesart gewaehlt, weil sie die Plausibilitaetsregeln erfuellt", log)
    summary = project["summary"]
    save_project(out_dir, project)
    _log(f"Fertig: {summary['points']} Messpunkte, {summary['ok']} Zellen ok, {summary['pruefen']} pruefen, "
         f"{summary['fehler']} Regelverstoesse", log)
    for s in project["series"]:
        h = s.get("header") or {}
        if h:
            _log("  Kopf: " + ", ".join(f"{k}={h[k]}" for k in ("sample", "wavelength", "start", "finish", "step") if k in h), log)
        else:
            _log("  Kopf nicht lesbar - Winkel mit --start/--schritt angeben", log)
        if s.get("expected"):
            state = "vollstaendig" if s["points"] == s["expected"] else "ABWEICHUNG"
            _log(f"  Messreihe {s['id'] + 1}: {s['points']} von {s['expected']} erwarteten Punkten ({state})", log)
    return project


def save_project(out_dir: str | Path, project: dict) -> None:
    """Atomar speichern (erst temporaere Datei, dann umbenennen) - kein Datenverlust bei Absturz."""
    out_dir = Path(out_dir)
    fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_dir / PROJECT_FILE)


def load_project(out_dir: str | Path) -> dict:
    with open(Path(out_dir) / PROJECT_FILE, encoding="utf-8") as f:
        return json.load(f)


def render_synthetic(out_dir: str | Path, project: dict, page: int) -> np.ndarray:
    templates = render.load_templates(Path(out_dir) / TEMPLATE_FILE)
    p = project["pages"][page]
    cells = [c for c in project["cells"] if c["page"] == page]
    return render.render_page((p["height"], p["width"]), cells, templates)


def page_image(out_dir: str | Path, project: dict, page: int, kind: str) -> bytes:
    if kind == "synthetisch":
        ok, buf = cv2.imencode(".png", render_synthetic(out_dir, project, page))
        return buf.tobytes()
    key = "kontrast" if kind == "kontrast" else "original"
    return (Path(out_dir) / project["pages"][page][key]).read_bytes()
