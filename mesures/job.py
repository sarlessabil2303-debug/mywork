# -*- coding: utf-8 -*-
"""Deroulement commun : controles -> mise a jour -> rapport -> PDF -> impression -> deplacement."""
from __future__ import annotations

import os
import traceback

from . import bus, car, truck
from .common import (JobError, Log, Plan, find_chrome, find_sumatra, make_pdf, move_files, newest_file,
                     print_pdf, read_mesures, now_stamp, resolve_template)
from .options import JobOptions, VEHICLE_BUS, VEHICLE_CAMION, VEHICLE_VOITURE

MAKERS = {
    VEHICLE_VOITURE: car.make_plan,
    VEHICLE_BUS: bus.make_plan,
    VEHICLE_CAMION: truck.make_plan,
}


def guess_family(folder: str) -> str:
    """'voiture' (champ 0427), 'bus_camion' (champ 1106) ou '' si indetermine."""
    f = newest_file(folder, "F")
    if not f:
        return ""
    keys = read_mesures(f)
    if "1106" in keys:
        return "bus_camion"
    if "0427" in keys:
        return "voiture"
    return ""


def run_job(opt: JobOptions, log: Log) -> bool:
    folder = os.path.abspath(opt.folder)
    if not os.path.isdir(folder):
        log("ERREUR : dossier introuvable : " + folder)
        return False
    updated = False
    try:
        maker = MAKERS.get(opt.vehicle)
        if maker is None:
            raise JobError("Type de vehicule inconnu : %r" % opt.vehicle)
        stamp = now_stamp()
        plan: Plan = maker(opt, folder, stamp, log)       # controles : rien n'est encore modifie
        log("Type : %s" % plan.label)

        template = resolve_template(plan.template_name, folder, opt.app_dir)
        if template is None and plan.template_required:
            raise JobError("Modele HTML introuvable : %s\n(dossier des mesures ou dossier du programme)"
                           % plan.template_name)

        count = plan.update(log)
        updated = True
        if count:
            log("%d champ(s) date/CRC mis a jour." % count)

        if template is None:
            log("Modele HTML \"%s\" introuvable - rapport ignore." % plan.template_name)
        else:
            report = os.path.join(folder, plan.report_name)
            pdf = os.path.join(folder, plan.pdf_name)
            if os.path.exists(report):
                os.remove(report)
            plan.build(template, report)
            if not os.path.isfile(report):
                raise JobError("Le rapport HTML n'a pas ete cree : " + report)
            if opt.make_pdf or opt.do_print:
                log("Creation du PDF...")
                if not make_pdf(report, pdf, find_chrome(opt.chrome), log,
                                as_uri=plan.chrome_as_uri, virtual_time=plan.chrome_virtual_time):
                    raise JobError("Le PDF n'a pas ete genere (ou semble vide). "
                                   "Les fichiers de mesures ne sont pas deplaces.")
                log("PDF cree : " + pdf)
                if opt.do_print:
                    print_pdf(pdf, max(1, int(opt.copies)), find_sumatra(opt.sumatra, opt.app_dir, folder), log)

        if opt.move_files:
            conflict = plan.conflict_default if opt.conflict == "auto" else opt.conflict
            log("Deplacement des fichiers de mesures vers " + opt.dest)
            move_files(plan.move_paths(), opt.dest, conflict, log)

        log("Termine - %s - %s" % (plan.label, stamp))
        return True
    except JobError as exc:
        log("ERREUR : %s" % exc)
        if updated:
            log("Les fichiers de mesures ont deja recu la nouvelle date ; on peut relancer sans risque.")
        return False
    except Exception:  # noqa: BLE001 - tout est journalise
        log("ERREUR inattendue :\n" + traceback.format_exc())
        return False
