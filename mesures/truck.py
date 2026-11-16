# -*- coding: utf-8 -*-
"""Camion lourd (ancien trucks_process.ps1 avec camion_lourd.html)."""
from __future__ import annotations

import os
import re
from typing import List

from .common import (JobError, Log, Plan, ReportError, escape_html, int_text, newest_file, read_mesures,
                     read_template, sibling_file, split_stamp, sum_text, update_files, val, write_text)
from .options import JobOptions

REPORT_NAME = "rapport_camion.html"
PDF_NAME = "rapport_camion.pdf"
KEYS_F = ("1106", "1206", "1135", "1235", "1158", "1007")
KEY_O = "0543"
KEY_R = "0403"
PRINT_RULE = ".page{margin:0;box-shadow:none;page-break-after:always;break-after:page}"


def _set_span(page: str, left: str, top: str, value: str) -> str:
    """Remplace le texte du <span class="t"> a (left, top) ; la zone doit exister une seule fois."""
    rx = re.compile(r'(<span class="t" style="left:%spt;top:%spt;[^"]*">)(.*?)(</span>)'
                    % (re.escape(left), re.escape(top)), re.S)
    count = len(rx.findall(page))
    if count != 1:
        raise ReportError("Zone de texte HTML absente ou ambigue : left=%spt, top=%spt (trouve : %d)"
                          % (left, top, count))
    safe = escape_html(value)
    return rx.sub(lambda m: m.group(1) + safe + m.group(3), page, count=1)


def _format_slip(raw: str) -> str:
    if raw.strip() == "":
        return "----"
    v = raw.strip().replace(".", ",")
    m = re.match(r"^([+-]?)0+(\d+,\d+)$", v)
    return m.group(1) + m.group(2) if m else v


def _calc_imba(left: str, right: str) -> str:
    if re.match(r"^\d+$", left) and re.match(r"^\d+$", right):
        l, r = int(left), int(right)
        den = min(l, r)
        if den > 0:
            return str(int(round(abs(l - r) * 100.0 / den)))
        if l == 0 and r == 0:
            return "0"
    return "----"


def _find_inputs(folder: str):
    f = newest_file(folder, "F")
    if not f:
        raise JobError("Fichier de mesures .F introuvable.")
    stem = os.path.splitext(os.path.basename(f))[0]
    o = sibling_file(folder, stem, "O")
    r = sibling_file(folder, stem, "R")
    if not o:
        raise JobError("Fichier requis introuvable : .O (%s.O)" % stem)
    if not r:
        raise JobError("Fichier requis introuvable : .R (%s.R)" % stem)
    return f, o, r, stem


def _check_types_and_keys(f_path: str, o_path: str, r_path: str):
    F, O, R = read_mesures(f_path), read_mesures(o_path), read_mesures(r_path)
    if (val(F, "0320", ""), val(O, "0320", ""), val(R, "0320", "")) != (".F", ".O", ".R"):
        raise JobError("Les extensions .F/.O/.R ne correspondent pas aux types de mesures attendus.\n"
                       "Verifiez le type de vehicule choisi.")
    for key in KEYS_F:
        if key not in F:
            raise JobError("Champ date %s absent du fichier .F" % key)
    if KEY_O not in O:
        raise JobError("Champ date 0543 absent du fichier .O")
    if KEY_R not in R:
        raise JobError("Champ date 0403 absent du fichier .R")


def build_report(folder: str, stamp: str, template: str, out_path: str, shift: float, log: Log) -> None:
    f_path, o_path, r_path, plate = _find_inputs(folder)
    F, O, R = read_mesures(f_path), read_mesures(o_path), read_mesures(r_path)
    date_s, time_s = split_stamp(stamp)

    report = read_template(template)
    pages = re.split(r'(?=<div class="page")', report)
    if len(pages) != 4:
        raise ReportError("Le modele doit contenir 3 pages A4 (pages detectees : %d)." % (len(pages) - 1))

    # Rend la couche texte visible et retire seulement les glyphes SVG (<use>) ; les cadres restent.
    if not re.search(r"\.t\{[^}]*color:transparent", report):
        raise ReportError("Style de couche texte .t introuvable dans le modele HTML.")
    report = re.sub(r"(\.t\{[^}]*?)color:transparent", r"\1color:#000000", report, count=1)
    report = re.sub(r"<use\b[^>]*/>", "", report, flags=re.I)
    pages = re.split(r'(?=<div class="page")', report)

    def blanks(p: str, left_top):
        for left, top in left_top:
            p = _set_span(p, left, top, "")
        return p

    # ---- PAGE 1 : ripage + freins ----
    p = pages[1]
    p = _set_span(p, "96.01", "92.21", date_s)
    p = blanks(p, [("107.22", "92.21"), ("110.02", "92.21"), ("121.23", "92.21")])
    p = _set_span(p, "218.11", "92.21", time_s)
    p = _set_span(p, "126.57", "107.33", date_s)
    p = blanks(p, [("137.78", "107.33"), ("140.58", "107.33"), ("151.79", "107.33")])
    p = _set_span(p, "239.75", "107.33", time_s)
    p = _set_span(p, "408.80", "249.27", plate)
    p = _set_span(p, "144.00", "393.52", _format_slip(val(R, "0401", "----")))
    p = _set_span(p, "144.00", "408.64", _format_slip(val(R, "0402", "----")))
    it = lambda k, fb="----": int_text(F, k, fb)  # noqa: E731
    for left, top, key, fb in (
            ("147.00", "449.75", "1121", "----"), ("239.48", "449.75", "1120", "----"),
            ("334.24", "450.16", "1125", "----"), ("389.06", "449.75", "1101", "----"),
            ("475.77", "449.75", "1100", "----"), ("537.16", "449.75", "1128", "----"),
            ("147.00", "477.11", "1151", "----"), ("239.48", "477.11", "1150", "----")):
        p = _set_span(p, left, top, it(key, fb))
    p = _set_span(p, "334.24", "477.52", _calc_imba(val(F, "1151", ""), val(F, "1150", "")))
    p = _set_span(p, "149.54", "490.79", it("1156", "---"))
    p = _set_span(p, "242.01", "490.79", it("1157", "---"))
    for left, top, key, fb in (
            ("147.00", "504.47", "1221", "----"), ("239.48", "504.47", "1220", "----"),
            ("334.24", "504.88", "1225", "----"), ("389.06", "504.47", "1201", "----"),
            ("475.77", "504.47", "1200", "----"), ("537.16", "504.47", "1228", "----"),
            ("149.54", "518.15", "1203", "---"), ("242.01", "518.15", "1204", "---")):
        p = _set_span(p, left, top, it(key, fb))
    p = _set_span(p, "122.34", "556.04", sum_text(F, ("1124", "1224"), "------"))
    p = _set_span(p, "304.01", "555.76", it("1000", "--"))
    p = _set_span(p, "122.34", "571.16", it("1154", "------"))
    p = _set_span(p, "304.01", "570.88", it("1001", "--"))
    p = _set_span(p, "122.34", "586.28", it("1004", "------"))
    p = _set_span(p, "304.01", "586.00", it("1002", "--"))
    pages[1] = p

    # ---- PAGE 2 : opacimetre ----
    p = pages[2]
    p = _set_span(p, "98.56", "92.80", date_s)
    p = blanks(p, [("109.64", "92.80"), ("112.40", "92.80"), ("123.48", "92.80")])
    p = _set_span(p, "230.24", "92.80", time_s)
    p = _set_span(p, "130.44", "108.24", date_s)
    p = blanks(p, [("141.52", "108.24"), ("144.29", "108.24"), ("155.36", "108.24")])
    p = _set_span(p, "287.10", "108.24", "1")        # le champ heure d'impression contient seulement 1
    p = _set_span(p, "417.06", "247.56", plate)
    ot = lambda k, fb="----": int_text(O, k, fb)  # noqa: E731
    p = _set_span(p, "182.48", "393.90", val(O, "0538", "--,--"))
    p = _set_span(p, "181.79", "408.88", ot("0531"))
    p = _set_span(p, "186.80", "408.88", "")
    idle = ot("0532")
    if idle == "0":
        idle = "----"
    p = _set_span(p, "181.40", "421.30", idle)
    p = _set_span(p, "181.40", "434.74", "----")
    for top1, top2, key in (("408.40", "407.38", "0533"), ("425.20", "424.18", "0534")):
        p = _set_span(p, "358.68", top1, val(O, key, "--,--"))
        p = _set_span(p, "363.68", top2, "")
        p = _set_span(p, "366.19", top1, "")
        p = _set_span(p, "417.48", top2, "----")
        p = _set_span(p, "476.28", top1, ot("0531"))
        p = _set_span(p, "481.28", top1, "")
    pages[2] = p

    # ---- PAGE 3 : en-tete ----
    p = pages[3]
    p = _set_span(p, "106.31", "74.28", plate)
    p = _set_span(p, "430.99", "74.09", date_s)
    p = blanks(p, [("442.06", "74.09"), ("444.83", "74.09"), ("455.91", "74.09")])
    p = _set_span(p, "530.22", "74.09", time_s)
    p = blanks(p, [("541.29", "74.09"), ("544.06", "74.09"), ("555.14", "74.09"), ("557.91", "74.09")])
    pages[3] = p

    html = "".join(pages)
    if PRINT_RULE not in html:
        raise ReportError("Regle CSS d'impression introuvable ; decalage non applique.")
    html = html.replace(PRINT_RULE, PRINT_RULE[:-1] + ";transform:translateX(%g%%)}" % shift)
    write_text(out_path, html)
    log("Rapport genere : " + out_path)


def make_plan(opt: JobOptions, folder: str, stamp: str, log: Log) -> Plan:
    # Controles faits AVANT toute modification des fichiers.
    f_path, o_path, r_path, _plate = _find_inputs(folder)
    _check_types_and_keys(f_path, o_path, r_path)

    def update(lg: Log) -> int:
        return update_files([(f_path, KEYS_F), (o_path, (KEY_O,)), (r_path, (KEY_R,))],
                            stamp, "linear", lg, reset_on_other=True, strict=True)

    def build(template: str, out: str) -> None:
        build_report(folder, stamp, template, out, opt.camion_shift, log)

    return Plan(label="CAMION LOURD", template_name=opt.tpl_camion, template_required=True,
                report_name=REPORT_NAME, pdf_name=PDF_NAME, update=update, build=build,
                move_paths=lambda: [p for p in (f_path, o_path, r_path) if os.path.exists(p)],
                conflict_default="overwrite", chrome_virtual_time=False, chrome_as_uri=True)
