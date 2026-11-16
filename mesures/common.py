# -*- coding: utf-8 -*-
"""Outils partages : fichiers de mesures, CRC, PDF, impression, deplacement, journal."""
from __future__ import annotations

import html as html_lib
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

Log = Callable[[str], None]


class JobError(Exception):
    """Erreur qui arrete le traitement (message affiche a l'utilisateur)."""


class ReportError(JobError):
    """Erreur pendant la generation du rapport HTML."""


@dataclass
class Plan:
    """Ce qu'un type de vehicule sait faire ; le deroulement est commun (voir job.py)."""
    label: str                                  # ESSENCE, GAZOLE, BUS, CAMION LOURD
    template_name: str
    template_required: bool
    report_name: str
    pdf_name: str
    update: Callable[[Log], int]                # met a jour date + CRC, renvoie le nombre de champs
    build: Callable[[str, str], None]           # (chemin du modele, chemin du rapport)
    move_paths: Callable[[], List[str]]         # fichiers a deplacer a la fin
    conflict_default: str = "overwrite"         # comportement d'origine si le fichier existe dans res
    chrome_virtual_time: bool = False
    chrome_as_uri: bool = False


# ---------------------------------------------------------------------------
# Date et CRC
# ---------------------------------------------------------------------------
def now_stamp(now: Optional[datetime] = None) -> str:
    """ddMMyyyyHHmmss (heure de l'ordinateur)."""
    return (now or datetime.now()).strftime("%d%m%Y%H%M%S")


def split_stamp(stamp: str) -> Tuple[str, str]:
    if len(stamp) != 14 or not stamp.isdigit():
        raise ReportError("date invalide : " + repr(stamp))
    return ("%s/%s/%s" % (stamp[0:2], stamp[2:4], stamp[4:8]),
            "%s:%s:%s" % (stamp[8:10], stamp[10:12], stamp[12:14]))


def checksum(value: str, scheme: str = "cyclic") -> int:
    """Somme des codes caracteres ponderes par la position.

    cyclic : poids 1,2,3,4,5,1,2,...   (voitures et bus, ancien .bat)
    linear : poids 1,2,3,4,5,6,7,...   (camions lourds, ancien trucks_process.ps1)
    """
    total = 0
    for i, ch in enumerate(value):
        weight = (i % 5) + 1 if scheme == "cyclic" else i + 1
        total += ord(ch) * weight
    return total


# ---------------------------------------------------------------------------
# Fichiers de mesures
# ---------------------------------------------------------------------------
_NEWLINE = re.compile(r"\r\n|\r|\n")


def find_files(folder: str, ext: str) -> List[str]:
    """Fichiers (pas les dossiers) d'extension ext, sans tenir compte de la casse."""
    want = "." + ext.lower()
    result = []
    try:
        names = os.listdir(folder)
    except OSError:
        return result
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isfile(path) and os.path.splitext(name)[1].lower() == want:
            result.append(path)
    return sorted(result)


def newest_file(folder: str, ext: str) -> Optional[str]:
    files = find_files(folder, ext)
    return max(files, key=lambda p: os.path.getmtime(p)) if files else None


def sibling_file(folder: str, stem: str, ext: str) -> Optional[str]:
    """Fichier <stem>.<ext> du dossier (casse ignoree)."""
    for path in find_files(folder, ext):
        if os.path.splitext(os.path.basename(path))[0].lower() == stem.lower():
            return path
    return None


def read_lines(path: str) -> List[str]:
    """Lignes du fichier en latin-1 (chaque octet est conserve tel quel)."""
    with open(path, "rb") as fh:
        lines = _NEWLINE.split(fh.read().decode("latin-1"))
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def write_lines(path: str, lines: Sequence[str]) -> None:
    with open(path, "wb") as fh:
        fh.write(("\r\n".join(lines) + "\r\n").encode("latin-1"))


def read_mesures(path: Optional[str]) -> Dict[str, str]:
    """Valeurs de la section [MESURES] : {'0420': '361', ...}."""
    result: Dict[str, str] = {}
    if not path:
        return result
    inside = False
    for line in read_lines(path):
        s = line.strip()
        if s == "[MESURES]":
            inside = True
            continue
        if s.startswith("["):
            inside = False
            continue
        if inside:
            m = re.match(r"^(\d{4})=(.*)$", s)
            if m:
                result[m.group(1)] = m.group(2).strip()
    return result


def apply_date_crc(lines: Sequence[str], keys: Sequence[str], stamp: str, crc: int,
                   reset_on_other: bool = False) -> Tuple[List[str], Set[str], Set[str]]:
    """Remplace la date dans [MESURES] et le CRC dans [CRC] pour les cles donnees.

    Renvoie (nouvelles lignes, cles trouvees dans [MESURES], cles trouvees dans [CRC]).
    reset_on_other : une autre section ([XXX]) arrete la mise a jour (camions lourds) ;
    sinon seules [MESURES] et [CRC] changent la section courante (voitures, bus).
    """
    out = list(lines)
    found_m: Set[str] = set()
    found_c: Set[str] = set()
    section = None
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if line == "[MESURES]":
            section = "M"
            continue
        if line == "[CRC]":
            section = "C"
            continue
        if reset_on_other and line.startswith("["):
            section = None
            continue
        if section is None:
            continue
        m = re.match(r"^(\d{4})=", line)
        if m and m.group(1) in keys:
            key = m.group(1)
            if section == "M":
                out[i] = key + "=" + stamp
                found_m.add(key)
            else:
                out[i] = key + "=" + str(crc)
                found_c.add(key)
    return out, found_m, found_c


def _section_values(lines: Sequence[str], reset_on_other: bool) -> Tuple[Dict[str, str], Dict[str, str]]:
    meas: Dict[str, str] = {}
    crcs: Dict[str, str] = {}
    section = None
    for raw in lines:
        line = raw.rstrip()
        if line == "[MESURES]":
            section = "M"
            continue
        if line == "[CRC]":
            section = "C"
            continue
        if reset_on_other and line.startswith("["):
            section = None
            continue
        m = re.match(r"^(\d{4})=(.*)$", line)
        if section and m:
            (meas if section == "M" else crcs)[m.group(1)] = m.group(2).strip()
    return meas, crcs


def detect_crc_scheme(all_lines: Sequence[Sequence[str]], keys_per_file: Sequence[Sequence[str]],
                      default: str, reset_on_other: bool = False) -> Tuple[str, str]:
    """Deduit le calcul du CRC a partir des champs date deja presents (avant modification).

    Pour chaque champ, le CRC stocke doit valoir checksum(valeur du champ). Renvoie
    (schema, commentaire). Si les fichiers ne permettent pas de trancher : schema par defaut.
    """
    votes = {"cyclic": 0, "linear": 0}
    for lines, keys in zip(all_lines, keys_per_file):
        meas, crcs = _section_values(lines, reset_on_other)
        for key in keys:
            if key in meas and key in crcs and meas[key] and re.match(r"^\d+$", crcs[key]):
                for scheme in votes:
                    if checksum(meas[key], scheme) == int(crcs[key]):
                        votes[scheme] += 1
    if votes["cyclic"] > votes["linear"]:
        return "cyclic", "CRC : calcul cyclique confirme par les fichiers"
    if votes["linear"] > votes["cyclic"]:
        return "linear", "CRC : calcul lineaire confirme par les fichiers"
    return default, "CRC : calcul par defaut (%s), les fichiers ne permettent pas de verifier" % default


def update_files(specs: Sequence[Tuple[str, Sequence[str]]], stamp: str, default_scheme: str,
                 log: Log, reset_on_other: bool = False, strict: bool = False,
                 always_write: bool = False, warn_missing: bool = True) -> int:
    """Met a jour date + CRC dans plusieurs fichiers.

    specs : [(chemin, cles), ...].  strict : si un champ manque dans un fichier, rien n'est ecrit.
    Les fichiers ne sont ecrits qu'apres traitement complet de tous les fichiers.
    """
    loaded = [(path, keys, read_lines(path)) for path, keys in specs]
    scheme, comment = detect_crc_scheme([l for _, _, l in loaded], [k for _, k, _ in loaded],
                                        default_scheme, reset_on_other)
    crc = checksum(stamp, scheme)
    log("Date/heure : %s   CRC : %d" % (stamp, crc))
    log(comment)
    results = []
    total = 0
    missing: List[str] = []
    for path, keys, lines in loaded:
        out, fm, fc = apply_date_crc(lines, keys, stamp, crc, reset_on_other)
        name = os.path.basename(path)
        for key in keys:
            if key not in fm:
                missing.append("%s : champ %s absent de [MESURES]" % (name, key))
            if key not in fc:
                missing.append("%s : CRC du champ %s absent de [CRC]" % (name, key))
        total += len(fm) + len(fc)
        results.append((path, out, bool(fm or fc)))
    if missing:
        if strict:
            raise JobError("Mise a jour impossible, aucun fichier modifie :\n  " + "\n  ".join(missing))
        for m in missing if warn_missing else []:
            log("ATTENTION : " + m)
    for path, out, changed in results:
        if (changed or always_write) and out:
            write_lines(path, out)
            log("  mis a jour : " + os.path.basename(path))
    return total


# ---------------------------------------------------------------------------
# Valeurs et HTML
# ---------------------------------------------------------------------------
def val(h: Dict[str, str], key: str, fallback: str = "----") -> str:
    v = h.get(key)
    if v is None or v.strip() == "":
        return fallback
    return v.strip()


def int_text(h: Dict[str, str], key: str, fallback: str = "----") -> str:
    v = val(h, key, "")
    return str(int(v)) if re.match(r"^\d+$", v) else fallback


def sum_text(h: Dict[str, str], keys: Sequence[str], fallback: str) -> str:
    total, found = 0, False
    for k in keys:
        v = val(h, k, "")
        if re.match(r"^\d+$", v):
            total += int(v)
            found = True
    return str(total) if found else fallback


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def read_template(path: str) -> str:
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8-sig")


def write_text(path: str, text: str) -> None:
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))


def template_candidates(name: str) -> List[str]:
    out: List[str] = []
    for n in (name, name.replace(" ", "_"), name.replace("_", " ")):
        if n and n not in out:
            out.append(n)
    return out


def resolve_template(name: str, folder: str, app_dir: str) -> Optional[str]:
    for base in (folder, app_dir):
        if not base:
            continue
        for n in template_candidates(name):
            p = os.path.join(base, n)
            if os.path.isfile(p):
                return p
    return None


# ---------------------------------------------------------------------------
# PDF et impression
# ---------------------------------------------------------------------------
def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _first_file(paths) -> Optional[str]:
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def find_chrome(custom: str = "") -> Optional[str]:
    cands = [custom]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LocalAppData"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    base = os.environ.get("ProgramFiles")
    if base:
        cands.append(os.path.join(base, "Chromium", "Application", "chrome.exe"))
    cands.append(shutil.which("chrome.exe") or "")
    return _first_file(cands)


def find_sumatra(custom: str, app_dir: str, folder: str) -> Optional[str]:
    cands = [custom, os.path.join(app_dir, "SumatraPDF.exe") if app_dir else "",
             os.path.join(folder, "SumatraPDF.exe")]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LocalAppData"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "SumatraPDF", "SumatraPDF.exe"))
    return _first_file(cands)


def make_pdf(report: str, pdf: str, chrome: Optional[str], log: Log,
             as_uri: bool = False, virtual_time: bool = False, timeout: int = 180) -> bool:
    if os.path.exists(pdf):
        os.remove(pdf)
    if not chrome:
        log("Chrome introuvable - impossible de creer le PDF.")
        return False
    profile = tempfile.mkdtemp(prefix="chrome_pdf_")
    source = Path(report).resolve().as_uri() if as_uri else os.path.abspath(report)
    cmd = [chrome, "--headless", "--disable-gpu", "--user-data-dir=" + profile,
           "--no-first-run", "--no-pdf-header-footer", "--print-to-pdf-no-header"]
    if virtual_time:
        cmd.append("--virtual-time-budget=5000")
    cmd += ["--print-to-pdf=" + os.path.abspath(pdf), source]
    try:
        subprocess.run(cmd, timeout=timeout, creationflags=_no_window(), stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        log("Chrome n'a pas termine dans le delai prevu.")
    finally:
        pass
    ok = False
    for _ in range(20):          # le fichier peut apparaitre un peu apres la fin du processus
        if os.path.isfile(pdf) and os.path.getsize(pdf) >= 1000:
            ok = True
            break
        time.sleep(0.5)
    shutil.rmtree(profile, ignore_errors=True)
    return ok


def print_pdf(pdf: str, copies: int, sumatra: Optional[str], log: Log) -> None:
    pdf = os.path.abspath(pdf)
    if sumatra:
        log("Impression avec SumatraPDF (%d exemplaire(s))" % copies)
        subprocess.run(
            [sumatra, "-print-to-default", "-print-settings", "noscale,paper=A4,%dx" % copies,
             "-silent", "-exit-when-done", pdf],
            creationflags=_no_window(), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        log("Impression impossible : systeme non Windows.")
        return
    log("ATTENTION : SumatraPDF introuvable, impression par le lecteur PDF par defaut.")
    try:
        for _ in range(copies):
            startfile(pdf, "print")
            time.sleep(5)
    except OSError:
        log("Impression automatique impossible : ouverture du PDF.")
        try:
            startfile(pdf)
        except OSError as exc:
            log("Impossible d'ouvrir le PDF : %s" % exc)


# ---------------------------------------------------------------------------
# Deplacement vers res
# ---------------------------------------------------------------------------
def move_files(paths: Sequence[str], dest: str, conflict: str, log: Log) -> None:
    """Copie, verifie la taille, puis supprime la source. conflict : overwrite | rename."""
    os.makedirs(dest, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for path in paths:
        name = os.path.basename(path)
        target = os.path.join(dest, name)
        if os.path.exists(target):
            if conflict == "rename":
                base, ext = os.path.splitext(name)
                target = os.path.join(dest, "%s_%s%s" % (base, stamp, ext))
            else:
                os.remove(target)
        shutil.copy2(path, target)
        if os.path.getsize(target) != os.path.getsize(path):
            raise JobError("Copie incomplete vers " + target)
        os.remove(path)
        log("  deplace : %s -> %s" % (name, target))


# ---------------------------------------------------------------------------
# Journal dans un fichier
# ---------------------------------------------------------------------------
class FileLog:
    """Ajoute les messages a un fichier journal (rotation simple a 512 Ko)."""

    def __init__(self, path: str, max_bytes: int = 512 * 1024):
        self.path = path
        try:
            if os.path.isfile(path) and os.path.getsize(path) > max_bytes:
                os.replace(path, path + ".old")
        except OSError:
            pass

    def __call__(self, msg: str) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                for line in str(msg).splitlines() or [""]:
                    fh.write("%s  %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), line))
        except OSError:
            pass
