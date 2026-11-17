# -*- coding: utf-8 -*-
"""Options d'un traitement et valeurs par defaut."""
from __future__ import annotations

from dataclasses import dataclass

VEHICLE_VOITURE = "voiture"
VEHICLE_BUS = "bus"
VEHICLE_CAMION = "camion"

VEHICLE_LABELS = {
    VEHICLE_VOITURE: "Voiture (essence / gazole)",
    VEHICLE_BUS: "Bus",
    VEHICLE_CAMION: "Camion lourd",
}


@dataclass
class JobOptions:
    folder: str
    vehicle: str = VEHICLE_VOITURE
    mode: str = "auto"              # voiture seulement : auto | essence | gazole
    plate: str = ""                 # matricule saisi (vide = garder le nom des fichiers) ; jamais enregistre
    dest: str = r"C:\GIEGLAN\res"
    make_pdf: bool = True
    do_print: bool = True
    copies: int = 2
    move_files: bool = True
    delete_report: bool = True      # supprimer le rapport (html + pdf) une fois les fichiers deplaces
    check_cg: bool = True           # verifier le numero du vehicule (fichier .cg + coherence des fichiers)
    cg_dir: str = r"C:\GIEGLAN\cg"
    conflict: str = "auto"          # fichier deja present dans res : auto | overwrite | rename
    tpl_essence: str = "es7_essence test_merged.html"
    tpl_gazole: str = "go1.html"
    tpl_bus: str = "bus_go.html"
    tpl_camion: str = "camion_lourd.html"
    bus_scale: int = 88             # % de la page a l'impression (bus)
    bus_shift: float = -3.0         # decalage horizontal en % (bus), negatif = vers la gauche
    camion_shift: float = -4.0      # decalage horizontal en % (camion lourd)
    chrome: str = ""                # vide = detection automatique
    sumatra: str = ""               # vide = detection automatique
    app_dir: str = ""               # dossier de l'application (modeles, SumatraPDF)


# Cles sauvegardees dans le fichier de configuration (tout sauf folder / app_dir)
CONFIG_KEYS = (
    "vehicle", "mode", "dest", "make_pdf", "do_print", "copies", "move_files", "delete_report", "check_cg", "cg_dir", "conflict",
    "tpl_essence", "tpl_gazole", "tpl_bus", "tpl_camion",
    "bus_scale", "bus_shift", "camion_shift", "chrome", "sumatra",
)
