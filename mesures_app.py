# -*- coding: utf-8 -*-
"""
Point d'entree.

    MesuresApp.exe                                   -> fenetre
    MesuresApp.exe --auto                            -> traitement sans fenetre (comme les anciens .bat)
    MesuresApp.exe --auto --type bus --folder D:\\mesures --no-print
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

from mesures import __version__
from mesures.common import FileLog
from mesures.config import app_dir, load_config, options_from_config
from mesures.job import run_job
from mesures.options import VEHICLE_BUS, VEHICLE_CAMION, VEHICLE_VOITURE


def run_auto(args: argparse.Namespace) -> int:
    cfg = load_config()
    opt = options_from_config(cfg, args.folder or os.getcwd())
    if args.type:
        opt.vehicle = args.type
    if args.mode:
        opt.mode = args.mode
    if args.no_print:
        opt.do_print = False
    if args.no_pdf:
        opt.make_pdf = False
        opt.do_print = False
    if args.no_move:
        opt.move_files = False
    journal = FileLog(os.path.join(app_dir(), "mesures_log.txt"))
    journal("---- Mode automatique v%s (%s) ----" % (__version__, opt.vehicle))

    def log(msg: str) -> None:
        journal(msg)
        try:
            print(msg)
        except Exception:  # noqa: BLE001 - pas de console en mode fenetre
            pass

    return 0 if run_job(opt, log) else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mesures - controle technique")
    p.add_argument("--auto", action="store_true", help="traitement sans fenetre")
    p.add_argument("--folder", help="dossier des fichiers de mesures (defaut : dossier courant)")
    p.add_argument("--type", choices=(VEHICLE_VOITURE, VEHICLE_BUS, VEHICLE_CAMION),
                   help="type de vehicule (defaut : dernier choix enregistre)")
    p.add_argument("--mode", choices=("auto", "essence", "gazole"), help="voiture : essence ou gazole")
    p.add_argument("--no-print", action="store_true", help="ne pas imprimer")
    p.add_argument("--no-pdf", action="store_true", help="ne pas creer le PDF (ni imprimer)")
    p.add_argument("--no-move", action="store_true", help="ne pas deplacer les fichiers")
    p.add_argument("--version", action="version", version="Mesures " + __version__)
    args = p.parse_args(argv)
    if args.auto:
        return run_auto(args)
    try:
        from mesures.gui import run_gui
        return run_gui()
    except Exception:  # noqa: BLE001
        try:
            with open(os.path.join(app_dir(), "mesures_crash.txt"), "w", encoding="utf-8") as fh:
                fh.write(traceback.format_exc())
        except OSError:
            pass
        raise


if __name__ == "__main__":
    sys.exit(main())
