# -*- coding: utf-8 -*-
"""Bus (ancien trucks_process.ps1 avec bus_go.html)."""
from __future__ import annotations

import os
import re
from typing import List, Optional

from .common import (JobError, Log, Plan, ReportError, escape_html, int_text, newest_file, read_mesures,
                     read_template, sibling_file, split_stamp, sum_text, update_files, val, write_text)
from .options import JobOptions

REPORT_NAME = "rapport_a_imprimer.html"
PDF_NAME = "rapport_a_imprimer.pdf"
KEYS_F = ("1106", "1206", "1135", "1235", "1158", "1007")
KEY_O = "0543"
KEY_R = "0403"
PAGE_WIDTH_PX = 909


def _replace_position(page: str, left: int, top: int, text: str, log: Log) -> str:
    """Remplace le contenu du <div class="t"> situe a (left, top) en conservant sa balise."""
    rx = re.compile(r'<div class="t" style="left:%dpx;top:%dpx;[^"]*">.*?</div>' % (left, top), re.S)
    m = rx.search(page)
    if not m:
        log("ATTENTION : zone HTML introuvable : left=%d, top=%d" % (left, top))
        return page
    tag_end = m.group(0).index(">")
    return page[:m.start()] + m.group(0)[:tag_end + 1] + escape_html(text) + "</div>" + page[m.end():]


def _num_value(h, key: str, fallback: str = "----") -> str:
    return int_text(h, key, fallback)


def print_css(scale_percent: float, shift_percent: float) -> str:
    scale = "%.2f" % (scale_percent / 100.0)
    shift_px = round(PAGE_WIDTH_PX * shift_percent / 100.0, 1) + 0.0
    return "@media print{.page{transform-origin:0 0;transform:translateX(%.1fpx) scale(%s)}}" % (shift_px, scale)


def _find_inputs(folder: str):
    f = newest_file(folder, "F")
    if not f:
        raise JobError("Fichier requis introuvable : .F")
    stem = os.path.splitext(os.path.basename(f))[0]
    o = sibling_file(folder, stem, "O")
    r = sibling_file(folder, stem, "R")
    if not o:
        raise JobError("Fichier requis introuvable : .O (%s.O)" % stem)
    if not r:
        raise JobError("Fichier requis introuvable : .R (%s.R)" % stem)
    return f, o, r, stem


def build_report(folder: str, stamp: str, template: str, out_path: str, shift: float, scale: float,
                 log: Log) -> None:
    f_path, o_path, r_path, plate = _find_inputs(folder)
    F, O, R = read_mesures(f_path), read_mesures(o_path), read_mesures(r_path)
    date_s, time_s = split_stamp(stamp)
    pages = re.split(r'(?=<div class="page">)', read_template(template))
    if len(pages) < 4:
        raise ReportError("Le modele bus doit contenir trois pages.")

    def rp(i: int, left: int, top: int, text: str) -> None:
        pages[i] = _replace_position(pages[i], left, top, text, log)

    # PAGE 1 : en-tete anglais, matricule, ripage (.R)
    rp(1, 106, 132, "Date: " + date_s)
    rp(1, 291, 132, "Time: " + time_s)
    rp(1, 106, 155, "Print Date  : " + date_s)
    rp(1, 288, 155, "Print Time: 0")
    rp(1, 616, 375, ": " + plate)
    rp(1, 220, 597, val(R, "0401", "--") + " m/km")
    rp(1, 220, 621, val(R, "0402", "--") + " m/km")

    # Freins (page 1) : 1100/1101 poids G/D, 1120/1121 force G/D, 1125 desequilibre, 1128 efficacite,
    # 1103/1104 ovalisation (essieu 1) ; 12xx = essieu 2 ; 1150/1151/1155/1156/1157 = frein de parking.
    i = lambda k, fb: int_text(F, k, fb)  # noqa: E731
    brake = [
        (194, 682, "Left: " + i("1120", "---") + " daN"),
        (326, 682, "Right: " + i("1121", "---") + " daN"),
        (458, 683, "IMBA.: " + i("1125", "-") + " %"),
        (546, 682, "Left w.: " + i("1100", "---") + " daN"),
        (669, 682, "Right w.: " + i("1101", "---") + " daN"),
        (792, 682, "Eff.: " + i("1128", "--") + " %"),
        (194, 703, "Left.: " + i("1103", "---") + " %"),
        (326, 703, "Right.: " + i("1104", "---") + " %"),
        (194, 723, "Left: " + i("1220", "---") + " daN"),
        (326, 723, "Right: " + i("1221", "---") + " daN"),
        (458, 724, "IMBA.: " + i("1225", "-") + " %"),
        (546, 723, "Left w.: " + i("1200", "---") + " daN"),
        (669, 723, "Right w.: " + i("1201", "---") + " daN"),
        (792, 723, "Eff.: " + i("1228", "--") + " %"),
        (194, 745, "Left.: " + i("1203", "---") + " %"),
        (326, 745, "Right.: " + i("1204", "---") + " %"),
        (194, 766, "Left: " + i("1150", "---") + " daN"),
        (326, 766, "Right: " + i("1151", "---") + " daN"),
        (458, 767, "IMBA.: " + i("1155", "-") + " %"),
        (194, 787, "Left.: " + i("1156", "---") + " %"),
        (326, 787, "Right.: " + i("1157", "---") + " %"),
        (106, 845, "S.B. Force: " + sum_text(F, ("1124", "1224"), "------") + " daN"),
        (396, 845, "S.B. Eff.: " + i("1000", "--") + " %"),
        (106, 868, "P.B. Force: " + i("1154", "------") + " daN"),
        (396, 868, "P.B. Eff.: " + i("1001", "--") + " %"),
        (106, 891, "E.B. Force: " + i("1004", "------") + " daN"),
        (396, 891, "E.B. Eff.: " + i("1002", "--") + " %"),
    ]
    for left, top, text in brake:
        rp(1, left, top, text)

    # PAGE 2 : en-tete francais, matricule, opacimetre (.O)
    rp(2, 108, 135, "Date: " + date_s)
    rp(2, 300, 135, "Heure: " + time_s)
    rp(2, 108, 159, "Date d'impre: " + date_s)
    rp(2, 298, 159, "Heure d'impression: 0")
    rp(2, 630, 372, ": " + plate)
    rp(2, 270, 596, ": " + val(O, "0538", "--,--") + " (1/m)")
    rp(2, 270, 617, ": " + _num_value(O, "0531"))
    rp(2, 270, 638, ": " + _num_value(O, "0532"))
    rp(2, 270, 659, ": ----")        # 0539 semble etre une limite d'opacite, pas un regime moteur

    table_rx = re.compile(r'<table style="left:494px;top:592px">.*?</table>', re.S)
    tm = table_rx.search(pages[2])
    if tm:
        table = tm.group(0)
        rows = (("1", val(O, "0533", "--,--"), val(O, "0535", "----")),
                ("2", val(O, "0534", "--,--"), val(O, "0536", "----")))
        for n, k, t in rows:
            new = '<tr><td class="n">%s</td><td>%s</td><td>----</td><td>%s</td></tr>' % (
                n, escape_html(k), escape_html(t))
            table = re.sub(r'<tr><td class="n">%s</td>.*?</tr>' % n, lambda _m, new=new: new, table, flags=re.S)
        pages[2] = pages[2][:tm.start()] + table + pages[2][tm.end():]
    else:
        log("ATTENTION : tableau opacimetre introuvable ; les cellules du modele sont conservees.")

    # PAGE 3 : matricule, date, heure
    rp(3, 90, 107, "Matricule: " + plate)
    rp(3, 613, 107, "Date: " + date_s)
    rp(3, 756, 107, "Heure: " + time_s)

    html = "".join(pages).replace("</style>", print_css(scale, shift) + "</style>")
    write_text(out_path, html)
    log("Rapport genere : " + out_path)


def make_plan(opt: JobOptions, folder: str, stamp: str, log: Log) -> Plan:
    # Controles faits AVANT toute modification des fichiers.
    f_path, o_path, r_path, _plate = _find_inputs(folder)
    if "1106" not in read_mesures(f_path) or KEY_O not in read_mesures(o_path) \
            or KEY_R not in read_mesures(r_path):
        raise JobError("Champs date attendus absents des fichiers .F/.O/.R "
                       "(1106 / 0543 / 0403). Aucun fichier modifie.\n"
                       "Verifiez le type de vehicule choisi.")

    def update(lg: Log) -> int:
        return update_files([(f_path, KEYS_F), (o_path, (KEY_O,)), (r_path, (KEY_R,))],
                            stamp, "cyclic", lg)

    def build(template: str, out: str) -> None:
        build_report(folder, stamp, template, out, opt.bus_shift, opt.bus_scale, log)

    return Plan(label="BUS", template_name=opt.tpl_bus, template_required=True,
                report_name=REPORT_NAME, pdf_name=PDF_NAME, update=update, build=build,
                move_paths=lambda: [p for p in (f_path, o_path, r_path) if os.path.exists(p)],
                conflict_default="rename", chrome_virtual_time=False, chrome_as_uri=True)
