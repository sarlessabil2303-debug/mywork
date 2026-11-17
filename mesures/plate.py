# -*- coding: utf-8 -*-
"""Matricule (numero d'immatriculation) : verification et correction du nom des fichiers de mesures.

Le matricule imprime sur le rapport est le nom des fichiers (sans extension). Si le nom est faux,
on saisit le bon matricule : les fichiers .F .O .G .R .S portant l'ancien nom sont renommes.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

from .common import JobError, Log, find_files, newest_file

MEASURE_EXTS = ("F", "O", "G", "R", "S")
_VALID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def validate_plate(text: str) -> str:
    plate = (text or "").strip()
    if not _VALID.match(plate):
        raise JobError("Matricule invalide : %r (lettres, chiffres, - et _ seulement)" % plate)
    return plate


def current_plate(folder: str) -> Optional[str]:
    """Nom (sans extension) du fichier .F le plus recent, ou None."""
    f = newest_file(folder, "F")
    return os.path.splitext(os.path.basename(f))[0] if f else None


def group_files(folder: str, stem: str) -> List[str]:
    """Fichiers de mesures (.F .O .G .R .S) portant ce nom (casse ignoree)."""
    found = []
    for ext in MEASURE_EXTS:
        for path in find_files(folder, ext):
            if os.path.splitext(os.path.basename(path))[0].lower() == stem.lower():
                found.append(path)
    return found


def compare(folder: str, typed: str) -> Tuple[str, Optional[str]]:
    """Etat pour l'affichage : ('empty'|'invalid'|'nofile'|'same'|'different', nom actuel)."""
    cur = current_plate(folder)
    if not (typed or "").strip():
        return "empty", cur
    if not _VALID.match(typed.strip()):
        return "invalid", cur
    if cur is None:
        return "nofile", cur
    return ("same" if typed.strip() == cur else "different"), cur


def rename_plate(folder: str, typed: str, log: Log) -> List[Tuple[str, str]]:
    """Renomme les fichiers pour qu'ils portent le matricule saisi.

    Renvoie la liste (ancien, nouveau) pour pouvoir annuler. Rien n'est renomme si une cible existe deja.
    """
    plate = validate_plate(typed)
    cur = current_plate(folder)
    if cur is None:
        raise JobError("Aucun fichier .F dans le dossier : impossible de verifier le matricule.")
    if plate == cur:
        log("Matricule %s : identique au nom des fichiers, rien a renommer." % plate)
        return []
    files = group_files(folder, cur)
    pairs = []
    for old in files:
        ext = os.path.splitext(old)[1]
        pairs.append((old, os.path.join(folder, plate + ext)))
    for old, new in pairs:
        same_file = os.path.normcase(old) == os.path.normcase(new)
        if os.path.exists(new) and not same_file and not (
                os.path.exists(old) and os.path.samefile(old, new)):
            raise JobError("Impossible de renommer : %s existe deja." % os.path.basename(new))
    done: List[Tuple[str, str]] = []
    try:
        for old, new in pairs:
            os.rename(old, new)
            done.append((old, new))
    except OSError as exc:
        undo_rename(done, log)
        raise JobError("Renommage impossible (%s). Aucun fichier modifie." % exc)
    log("Matricule : nom de fichier incorrect (%s) -> renomme en %s :" % (cur, plate))
    for old, new in done:
        log("  %s -> %s" % (os.path.basename(old), os.path.basename(new)))
    return done


def undo_rename(done: List[Tuple[str, str]], log: Log) -> None:
    for old, new in reversed(done):
        try:
            os.rename(new, old)
        except OSError as exc:
            log("ATTENTION : retour au nom d'origine impossible pour %s (%s)" % (os.path.basename(new), exc))
