# -*- coding: utf-8 -*-
"""Controle du numero de vehicule avant tout traitement.

1. tous les fichiers de mesures du dossier portent le meme numero que le fichier .F le plus recent ;
2. un fichier <numero>.cg existe dans le dossier cg (vehicule enregistre depuis l'ordinateur externe).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from .common import JobError, Log, find_files, newest_file


class VehicleNotRegistered(JobError):
    """Aucun fichier <numero>.cg : le vehicule doit d'abord etre enregistre (peut etre ajoute a tout moment)."""


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def distance(a: str, b: str) -> int:
    """Distance de Levenshtein (nombre de chiffres a changer / ajouter / retirer)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def similar_numbers(plate: str, candidates: Dict[str, str], max_distance: int = 2, limit: int = 5) -> List[str]:
    """Numeros proches de plate : memes chiffres a des zeros ppres, ou a 1-2 chiffres d'ecart."""
    found = []
    core = plate.lstrip("0")
    for key, filename in candidates.items():
        d = distance(plate, key)
        same_value = core != "" and key.lstrip("0") == core
        if same_value or d <= max_distance:
            found.append((0 if same_value else d, filename))
    found.sort()
    return [name for _, name in found[:limit]]


def check_vehicle(folder: str, cg_dir: str, log: Log) -> Optional[str]:
    """Leve JobError si le numero est incoherent ou absent du dossier cg. Renvoie le numero controle."""
    f_path = newest_file(folder, "F")
    if not f_path:
        log("ATTENTION : aucun fichier .F, numero du vehicule non controle.")
        return None
    plate = _stem(f_path)

    others = []
    for ext in "FOGRS":
        for path in find_files(folder, ext):
            if _stem(path).lower() != plate.lower():
                others.append(os.path.basename(path))
    if others:
        raise JobError("Erreur de numerotation : les fichiers de mesures ne portent pas tous le numero %s :\n  %s\n"
                       "Retirez les fichiers d'un autre vehicule ou corrigez leur nom."
                       % (plate, "\n  ".join(sorted(others))))

    if not os.path.isdir(cg_dir):
        raise JobError("Dossier cg introuvable : %s\nImpossible de verifier que le vehicule %s est enregistre."
                       % (cg_dir, plate))
    cg_files = {_stem(p).lower(): os.path.basename(p) for p in find_files(cg_dir, "cg")}
    if plate.lower() in cg_files:
        log("Vehicule %s : fichier %s present dans %s" % (plate, cg_files[plate.lower()], cg_dir))
        return plate

    hints = similar_numbers(plate.lower(), cg_files)
    msg = ("Le vehicule %s doit d'abord etre enregistre :\naucun fichier %s.cg dans %s."
           % (plate, plate, cg_dir))
    if hints:
        msg += "\nErreur de numerotation possible ? Fichiers proches : " + ", ".join(hints)
    raise VehicleNotRegistered(msg)
