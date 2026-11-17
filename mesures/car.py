# -*- coding: utf-8 -*-
"""Voitures : essence (update_report.ps1) et gazole (update_report_go_O.ps1)."""
from __future__ import annotations

import html as html_lib
import math
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List, Optional

from .common import (JobError, Log, Plan, ReportError, find_files, newest_file, read_mesures, read_template,
                     split_stamp, update_files, write_text)
from .options import JobOptions

MODE_ESSENCE = "ESSENCE"
MODE_GAZOLE = "GAZOLE"
REPORT_NAME = "rapport_a_imprimer.html"
PDF_NAME = "rapport_a_imprimer.pdf"

# extension -> cles a remplacer (date dans [MESURES], CRC dans [CRC])
EXT_KEYS = {
    "F": ("0427", "0450", "0468"),
    "O": ("0543",),
    "G": ("0513",),
    "R": ("0403",),
    "S": ("0416",),
}


def detect_mode(folder: str) -> str:
    """Un fichier .O sans fichier .G = GAZOLE, sinon ESSENCE."""
    if find_files(folder, "O") and not find_files(folder, "G"):
        return MODE_GAZOLE
    return MODE_ESSENCE


def update_measure_files(folder: str, stamp: str, log: Log) -> int:
    """process_files.ps1 : date et CRC dans tous les fichiers .F .O .G .R .S du dossier."""
    specs = []
    for ext, keys in EXT_KEYS.items():
        for path in find_files(folder, ext):
            specs.append((path, keys))
    if not specs:
        return 0
    return update_files(specs, stamp, "cyclic", log, always_write=True, warn_missing=False)


# ---------------------------------------------------------------------------
# Lecture des mesures et formatage
# ---------------------------------------------------------------------------
def _to_int(text: str) -> Optional[int]:
    text = text.strip()
    if re.match(r"^[+-]?\d+$", text):
        return int(text)
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def int_of(h: Dict[str, str], key: str) -> Optional[str]:
    """'049' -> '49' ; vide ou absent -> None."""
    v = h.get(key)
    if v is None or v == "":
        return None
    n = _to_int(v.lstrip("+"))
    return None if n is None else str(n)


def _round_away(x: float) -> int:
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def pct(a: int, b: int) -> Optional[str]:
    if not b:
        return None
    return str(_round_away(100.0 * a / b))


def _parse_decimal(text: str) -> Optional[Decimal]:
    try:
        d = Decimal(text.strip())
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _format_signed(d: Decimal, decimal_sep: str) -> str:
    """Un chiffre apres la virgule, signe + pour les valeurs positives, 0 sans signe."""
    if d == 0:
        return "0" + decimal_sep + "0"
    text = format(d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f").replace(".", decimal_sep)
    return "+" + text if d > 0 else text


def rip(h: Dict[str, str], key: str) -> Optional[str]:
    """'-01.6' -> '-1.6' ; '+04.1' -> '+4.1' ; 0 -> '0.0'."""
    d = _parse_decimal(h[key]) if key in h else None
    return None if d is None else _format_signed(d, ".")


def rip_comma(h: Dict[str, str], key: str) -> Optional[str]:
    """Version gazole : '-01.6' -> '-1,6' ; '+04.1' -> '+4,1' ; 0 -> '0,0'."""
    d = _parse_decimal(h[key]) if key in h else None
    return None if d is None else _format_signed(d, ",")


def dec(h: Dict[str, str], key: str) -> Optional[str]:
    """'00,00' -> '0,00' ; '11,70' -> '11,70'."""
    v = h.get(key)
    if v is None or v == "":
        return None
    m = re.match(r"^(\d+),(\d+)$", v)
    if m:
        return str(int(m.group(1))) + "," + m.group(2)
    n = _to_int(v)
    return None if n is None else str(n)


def oval(h: Dict[str, str], key: str) -> Optional[str]:
    v = h.get(key)
    if v is None or v == "":
        return None
    n = _to_int(v)
    return None if n is None else str(n)


def raw_value(h: Dict[str, str], key: str, fallback: str) -> str:
    v = h.get(key)
    if v is None or v.strip() == "":
        return fallback
    return v.strip()


class Measures:
    """Valeurs lues dans les fichiers .F .R .S .G .O les plus recents du dossier."""

    def __init__(self, folder: str):
        self.f_path = newest_file(folder, "F")
        self.F = read_mesures(self.f_path)
        self.R = read_mesures(newest_file(folder, "R"))
        self.S = read_mesures(newest_file(folder, "S"))
        self.G = read_mesures(newest_file(folder, "G"))
        self.o_path = newest_file(folder, "O")
        self.O = read_mesures(self.o_path)
        # matricule = nom des fichiers sans extension
        self.mat = os.path.splitext(os.path.basename(self.f_path))[0] if self.f_path else ""

        F = self.F
        i = lambda k: int_of(F, k)  # noqa: E731
        self.w1g, self.w1d, self.w1t = i("0420"), i("0421"), i("0422")
        self.w2g, self.w2d, self.w2t = i("0423"), i("0424"), i("0425")
        self.wtot = i("0426")
        self.b1g, self.b1d, self.b1diff = i("0430"), i("0431"), i("0434")
        self.b2g, self.b2d, self.b2diff = i("0438"), i("0439"), i("0442")
        self.eff_fs = i("0446")
        s1t, s2t = i("0447"), i("0448")
        self.pg, self.pd, self.eff_fp = i("0460"), i("0461"), i("0465")

        self.eff1 = None
        if s1t is not None and self.w1t is not None:
            self.eff1 = pct(int(s1t), int(self.w1t))
        self.eff2 = None
        if s2t is not None and self.w2t is not None:
            self.eff2 = pct(int(s2t), int(self.w2t))
        self.pdiff = None
        if self.pg is not None and self.pd is not None:
            a, b = int(self.pg), int(self.pd)
            self.pdiff = pct(abs(a - b), max(a, b))

    def date_time(self, stamp: str):
        if stamp == "" and "0427" in self.F:
            stamp = self.F["0427"]
        return split_stamp(stamp)


# ---------------------------------------------------------------------------
# Rapport ESSENCE (update_report.ps1)
# ---------------------------------------------------------------------------
def _set_token(div: str, rx: str, new: str, cls: str, log: Log) -> str:
    """Remplace le premier texte correspondant a rx (ignore les balises) par <span class=cls>new</span>."""
    plain: List[str] = []
    mp: List[int] = []
    i, n = 0, len(div)
    while i < n:
        c = div[i]
        if c == "<":
            j = div.find(">", i)
            if j < 0:
                break
            i = j + 1
            continue
        if c == "&":
            j = div.find(";", i)
            if j >= 0:
                plain.append("?")
                mp.append(i)
                i = j + 1
                continue
        plain.append(c)
        mp.append(i)
        i += 1
    m = re.search(rx, "".join(plain))
    if not m:
        log("  ATTENTION : motif introuvable : " + rx)
        return div
    deleted = set(mp[k] for k in range(m.start(), m.end()))
    first = mp[m.start()]
    safe = html_lib.escape(new, quote=False)
    out: List[str] = []
    for i in range(n):
        if i == first:
            out.append('<span class="%s">%s</span>' % (cls, safe))
        if i in deleted:
            continue
        out.append(div[i])
    return "".join(out)


def _edit_div(page: str, x: str, y: str, edits, log: Log) -> str:
    rx = '<div class="t m0 %s h\\w+ %s [^"]*">.*?</div>' % (x, y)
    m = re.search(rx, page, re.S)
    if not m:
        log("  ATTENTION : bloc introuvable : %s %s" % (x, y))
        return page
    div = m.group(0)
    for pattern, val, cls in edits:
        if val is not None and val != "":
            div = _set_token(div, pattern, str(val), cls, log)
    return page[: m.start()] + div + page[m.end():]


_RX_DATE = r"\d{2}/\d{2}/\d{4}"
_RX_TIME = r"\d{2}:\d{2}:\d{2}"
_RX_GAUCHE_L = r"(?<=gauche: )\d+"
_RX_DROIT_L = r"(?<=droit: )\d+"
_RX_DROITE_L = r"(?<=droite: )\d+"
_RX_GAUCHE_U = r"(?<=Gauche: )\d+"
_RX_DROITE_U = r"(?<=Droite: )\d+"
_RX_DIFF = r"(?<=Diff\.: )\d+"
_RX_EFF = r"(?<=Eff\.: )\d+"
_RX_DASH = r"-{3}"


def build_report_essence(folder: str, stamp: str, template: str, out_path: str, log: Log) -> None:
    M = Measures(folder)
    date_s, time_s = M.date_time(stamp)
    F, R, S, G = M.F, M.R, M.S, M.G

    if not os.path.isfile(template):
        raise ReportError("modele introuvable : " + template)
    html = read_template(template)
    cut = html.find('<div id="pf2"')
    if cut < 0:
        raise ReportError("page 2 introuvable dans le modele")
    body = html.find("<body")
    if body < 0:
        raise ReportError("balise <body> introuvable dans le modele")
    head, p1, p2 = html[:body], html[body:cut], html[cut:]

    nv, nb = "nv", "nb"
    ops1 = [
        ("x2", "y3", [(_RX_DATE, date_s, nv)]),
        ("x2", "y4", [(_RX_DATE, date_s, nv)]),
        ("x3", "y5", [(_RX_TIME, time_s, nv)]),
        # ripage
        ("x5", "y15", [(r"[+-]?\d+\.\d+", rip(R, "0401"), nb)]),
        ("x5", "y17", [(r"[+-]?\d+\.\d+", rip(R, "0402"), nb)]),
        # suspension (S) + poids par essieu (F)
        ("x2", "y19", [(_RX_GAUCHE_L, int_of(S, "0410"), nv)]),
        ("x6", "y1c", [(_RX_DROITE_L, int_of(S, "0411"), nv)]),
        ("x9", "y1e", [(_RX_DIFF, int_of(S, "0412"), nb)]),
        ("xa", "y1f", [(_RX_GAUCHE_L, M.w1g, nv), (_RX_DROIT_L, M.w1d, nv)]),
        ("x2", "y1a", [(_RX_GAUCHE_L, int_of(S, "0413"), nv)]),
        ("x7", "y1a", [(_RX_DROITE_L, int_of(S, "0414"), nv)]),
        ("x9", "y20", [(_RX_DIFF, int_of(S, "0415"), nb)]),
        ("xa", "y21", [(_RX_GAUCHE_L, M.w2g, nv), (_RX_DROIT_L, M.w2d, nv)]),
        # freins de service essieu 1
        ("x2", "y2b", [(_RX_GAUCHE_U, M.b1g, nv)]),
        ("xb", "y22", [(_RX_DROITE_U, M.b1d, nv)]),
        ("x1", "y23", [(_RX_DIFF, M.b1diff, nb)]),
        ("xc", "y24", [(_RX_GAUCHE_L, M.w1g, nv), (_RX_DROIT_L, M.w1d, nv), (_RX_EFF, M.eff1, nv)]),
        # frein de parking
        ("x2", "y2d", [(_RX_GAUCHE_U, M.pg, nv)]),
        ("xb", "y33", [(_RX_DROITE_U, M.pd, nv)]),
        ("xd", "y26", [(_RX_DIFF, M.pdiff, nb)]),
        # freins de service essieu 2
        ("x2", "y2f", [(_RX_GAUCHE_U, M.b2g, nv)]),
        ("xb", "y35", [(_RX_DROITE_U, M.b2d, nv)]),
        ("x1", "y27", [(_RX_DIFF, M.b2diff, nb)]),
        ("xe", "y28", [(_RX_GAUCHE_L, M.w2g, nv), (_RX_DROIT_L, M.w2d, nv), (_RX_EFF, M.eff2, nv)]),
        # ovalisations (seulement si une valeur existe dans le fichier .F)
        ("x2", "y2c", [(_RX_DASH, oval(F, "0432"), nv)]),
        ("xb", "y32", [(_RX_DASH, oval(F, "0433"), nv)]),
        ("x2", "y30", [(_RX_DASH, oval(F, "0440"), nv)]),
        ("xb", "y36", [(_RX_DASH, oval(F, "0441"), nv)]),
        ("x2", "y2e", [(_RX_DASH, oval(F, "0463"), nv)]),
        ("xb", "y34", [(_RX_DASH, oval(F, "0464"), nv)]),
        # matricule
        ("x4", "yd", [(r"\d+", M.mat, nv)]),
        # efficacites et poids total
        ("x2", "y37", [(r"(?<=FS: )\d+", M.eff_fs, nb)]),
        ("x2", "y38", [(r"(?<=FP: )\d+", M.eff_fp, nb)]),
        ("x2", "y39", [(r"(?<=Total: )\d+", M.wtot, nv)]),
    ]
    for x, y, edits in ops1:
        p1 = _edit_div(p1, x, y, edits, log)

    ops2 = [
        ("x2", "y3b", [(_RX_DATE, date_s, nv), (_RX_TIME, time_s, nv)]),
        ("x2", "y3c", [(_RX_DATE, date_s, nv)]),
        ("x4", "yd", [(r"\d+", M.mat, nv)]),
        # emissions (G) : HC=0500  Temp huile=0501  CO=0509  CO2=0510  CO corr=0511
        ("x10", "y40", [(r"\d+,\d+", dec(G, "0509"), nv)]),
        ("x2", "y41", [(r"\d+,\d+", dec(G, "0510"), nv)]),
        ("x2", "y42", [(r"(?<=: )\d+", int_of(G, "0500"), nv)]),
        ("x2", "y45", [(r"(?<=: )\d+", int_of(G, "0501"), nv)]),
        ("x2", "y48", [(r"\d+,\d+", dec(G, "0511"), nv)]),
    ]
    for x, y, edits in ops2:
        p2 = _edit_div(p2, x, y, edits, log)

    css = (
        '<style type="text/css">.nv{font-family:ffc,ff3,ff1,ff19,Arial,sans-serif}'
        ".nb{font-family:Arial,Helvetica,sans-serif;font-weight:bold}"
        "@page{size:210mm 297mm;margin:0}"
        "@media print{html{zoom:0.75}#page-container{left:-8.4mm !important}}</style>"
    )
    head = head.replace("</head>", css + "</head>")
    write_text(out_path, head + p1 + p2)
    log("Rapport genere : " + out_path)


# ---------------------------------------------------------------------------
# Rapport GAZOLE (update_report_go_O.ps1)
# ---------------------------------------------------------------------------
_SPAN_RX = re.compile(
    r'<span class="([^"]*)" style="left:([0-9.]+)pt;top:([0-9.]+)pt;'
    r'font-size:([0-9.]+)pt;line-height:([0-9.]+)pt;([^"]*)">([^<]*)</span>'
)


class _Item:
    __slots__ = ("idx", "end", "cls", "left", "top", "size", "line", "rest", "dead", "new_text", "new_top")


def _seg(name, top, l1, l2, text, rest="", left=None):
    return {"name": name, "top": top, "l1": l1, "l2": l2, "text": text, "rest": rest, "left": left}


def _txt(fmt: str, *vals) -> Optional[str]:
    for v in vals:
        if v is None or v == "":
            return None
    return fmt.format(*vals)


def _diff_left(v: Optional[str]) -> Optional[float]:
    if v is None or v == "":
        return None
    return 320.5 - (len(v) - 1) * 5.56


def _edit_page(page: str, segs, log: Log) -> str:
    items: List[_Item] = []
    for m in _SPAN_RX.finditer(page):
        it = _Item()
        it.idx, it.end = m.start(), m.end()
        it.cls = m.group(1)
        it.left, it.top = float(m.group(2)), float(m.group(3))
        it.size, it.line, it.rest = m.group(4), m.group(5), m.group(6)
        it.dead, it.new_text, it.new_top = False, None, 0.0
        items.append(it)
    for s in segs:
        if s["text"] is None or s["text"] == "":
            continue
        cand = [it for it in items
                if not it.dead and abs(it.top - s["top"]) <= 2.0 and s["l1"] <= it.left < s["l2"]]
        if not cand:
            log("  ATTENTION : zone introuvable : " + s["name"])
            continue
        first = cand[0]
        for c in cand:
            if c.left < first.left:
                first = c
        for c in cand:
            if c is not first:
                c.dead = True
        first.new_text = str(s["text"])
        first.new_top = s["top"]
        if s["rest"] != "":
            first.rest = s["rest"]
        if s["left"] is not None:
            first.left = float(s["left"])
    out: List[str] = []
    pos = 0
    for it in items:
        out.append(page[pos:it.idx])
        pos = it.end
        if it.dead:
            continue
        if it.new_text is not None:
            t = it.new_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            out.append(
                '<span class="%s" style="left:%.2fpt;top:%.2fpt;font-size:%spt;line-height:%spt;%s">%s</span>'
                % (it.cls, it.left, it.new_top, it.size, it.line, it.rest, t)
            )
        else:
            out.append(page[it.idx:it.end])
    out.append(page[pos:])
    return "".join(out)


def build_report_gazole(folder: str, stamp: str, template: str, out_path: str, log: Log) -> None:
    M = Measures(folder)
    date_s, time_s = M.date_time(stamp)
    F, R, S, O = M.F, M.R, M.S, M.O

    if not os.path.isfile(template):
        raise ReportError("modele introuvable : " + template)
    html = read_template(template)
    first_page = html.find('<div class="page"')
    if first_page < 0:
        raise ReportError("page 1 introuvable dans le modele")
    cut = html.find('<div class="page"', first_page + 10)
    if cut < 0:
        raise ReportError("page 2 introuvable dans le modele")
    p1, p2 = html[:cut], html[cut:]

    rip1, rip2 = rip_comma(R, "0401"), rip_comma(R, "0402")
    s1g, s1d, s1diff = int_of(S, "0410"), int_of(S, "0411"), int_of(S, "0412")
    s2g, s2d, s2diff = int_of(S, "0413"), int_of(S, "0414"), int_of(S, "0415")
    o1g, o1d = oval(F, "0432"), oval(F, "0433")
    o2g, o2d = oval(F, "0440"), oval(F, "0441")
    opg, opd = oval(F, "0463"), oval(F, "0464")

    pw = "Poids gauche: {0} daN Poids droit: {1} daN"
    pwe = pw + " Eff.: {2} %"
    g = [
        _seg("date", 92.41, 99, 150, date_s),
        _seg("heure", 92.41, 231, 290, time_s),
        _seg("dateimp", 107.85, 132, 190, date_s),
        _seg("matric", 247.17, 418, 520, M.mat),
        _seg("rip1", 394.65, 147, 200, _txt("{0} m/km", rip1)),
        _seg("rip2", 409.53, 147, 200, _txt("{0} m/km", rip2)),
        _seg("s1g", 450.21, 168, 190, _txt("{0} %", s1g)),
        _seg("s1d", 449.81, 249, 270, _txt("{0} %", s1d)),
        _seg("s1diff", 450.35, 329, 345, _txt("{0} %", s1diff)),
        _seg("s1w", 449.35, 357, 600, _txt(pw, M.w1g, M.w1d)),
        _seg("s2g", 463.25, 168, 190, _txt("{0} %", s2g)),
        _seg("s2d", 463.25, 249, 270, _txt("{0} %", s2d)),
        _seg("s2diff", 463.79, 326, 345, _txt("{0} %", s2diff)),
        _seg("s2w", 462.79, 360, 600, _txt(pw, M.w2g, M.w2d)),
        _seg("b1g", 503.71, 165, 200, _txt("{0} daN", M.b1g)),
        _seg("b1d", 503.09, 246, 290, _txt("{0} daN", M.b1d)),
        _seg("b1diff", 504.90, 320, 364, _txt("Diff.: {0} %", M.b1diff), "", _diff_left(M.b1diff)),
        _seg("b1w", 503.90, 365, 600, _txt(pwe, M.w1g, M.w1d, M.eff1), "", 368.5),
        _seg("o1g", 517.44, 167, 190, _txt("{0} %", o1g)),
        _seg("o1d", 516.53, 242, 270, _txt("{0} %", o1d)),
        _seg("pg", 530.14, 165, 200, _txt("{0} daN", M.pg)),
        _seg("pd", 529.41, 246, 290, _txt("{0} daN", M.pd)),
        _seg("pdiff", 530.97, 348, 365, _txt("{0} %", M.pdiff)),
        _seg("opg", 543.36, 168, 190, _txt("{0} %", opg)),
        _seg("opd", 543.41, 242, 270, _txt("{0} %", opd)),
        _seg("b2g", 556.57, 165, 200, _txt("{0} daN", M.b2g)),
        _seg("b2d", 556.29, 246, 290, _txt("{0} daN", M.b2d)),
        _seg("b2diff", 558.45, 320, 364, _txt("Diff.: {0} %", M.b2diff), "", _diff_left(M.b2diff)),
        _seg("b2w", 557.45, 365, 600, _txt(pwe, M.w2g, M.w2d, M.eff2), "", 368.5),
        _seg("o2g", 570.30, 168, 190, _txt("{0} %", o2g)),
        _seg("o2d", 570.29, 242, 270, _txt("{0} %", o2d)),
        _seg("effFS", 593.13, 138, 170, _txt("{0} %", M.eff_fs)),
        _seg("effFP", 607.66, 138, 170, _txt("{0} %", M.eff_fp)),
        _seg("wtot", 621.86, 120, 170, _txt("{0} daN", M.wtot)),
    ]
    # opacimetre (.O) : 0533/0534 = mesures K, 0538 = moyenne K, 0531 = temperature huile, 0532 = RPM
    op_mean = raw_value(O, "0538", "--,--")
    oil_temp = raw_value(O, "0531", "----")
    k11, k12 = raw_value(O, "0533", "--,--"), raw_value(O, "0534", "--,--")
    t11, t12 = raw_value(O, "0535", "----"), raw_value(O, "0536", "----")
    rpm = raw_value(O, "0532", "----")
    g += [
        _seg("moy1", 662.73, 176, 260, ": " + op_mean + " (1/m)", "color:rgb(255,0,0);"),
        _seg("th1", 676.61, 181, 200, oil_temp),
        _seg("k11", 676.13, 358, 410, k11),
        _seg("t11", 676.13, 476, 520, t11),
        _seg("k12", 692.93, 358, 410, k12),
        _seg("t12", 692.93, 476, 520, t12),
        _seg("rpm1", 690.05, 181, 220, rpm),
    ]
    p1 = _edit_page(p1, g, log)

    g2 = [
        _seg("matric2", 73.89, 107, 200, M.mat),
        _seg("date2", 73.70, 438, 500, date_s),
        _seg("heure2", 73.70, 534, 600, time_s),
    ]
    p2 = _edit_page(p2, g2, log)

    css = ('<style type="text/css">@media print{.page{width:595pt !important;height:841pt !important;'
           "overflow:hidden;transform:translateX(-3%) !important;transform-origin:top left !important}"
           ".page:last-of-type{page-break-after:auto !important}}</style>")
    write_text(out_path, (p1 + p2).replace("</head>", css + "</head>"))
    log("Rapport genere : " + out_path)
    if M.o_path:
        log("Opacimetre lu depuis : " + M.o_path)
    else:
        log("ATTENTION : fichier .O introuvable ; les champs opacimetre manquants seront des tirets.")


# ---------------------------------------------------------------------------
# Plan d'execution
# ---------------------------------------------------------------------------
def make_plan(opt: JobOptions, folder: str, stamp: str, log: Log) -> Plan:
    if not find_files(folder, "F"):
        raise JobError("Aucun fichier de mesures .F dans le dossier :\n%s\n"
                       "Choisissez le dossier qui contient les fichiers de la voiture." % folder)
    mode = {"essence": MODE_ESSENCE, "gazole": MODE_GAZOLE}.get(opt.mode.lower()) or detect_mode(folder)
    if mode == MODE_GAZOLE:
        name, builder, exts = opt.tpl_gazole, build_report_gazole, ("F", "G", "R", "S", "O")
    else:
        name, builder, exts = opt.tpl_essence, build_report_essence, ("F", "G", "R", "S")

    def update(lg: Log) -> int:
        n = update_measure_files(folder, stamp, lg)
        if n == 0:
            lg("ATTENTION : aucun fichier de mesures (.F .O .G .R .S) dans le dossier.")
        return n

    def build(template: str, out: str) -> None:
        builder(folder, stamp, template, out, log)

    def paths() -> List[str]:
        return [p for e in exts for p in find_files(folder, e)]

    return Plan(label=mode, template_name=name, template_required=False, report_name=REPORT_NAME,
                pdf_name=PDF_NAME, update=update, build=build, move_paths=paths,
                conflict_default="overwrite", chrome_virtual_time=True, chrome_as_uri=False)
