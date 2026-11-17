# -*- coding: utf-8 -*-
"""Interface graphique (tkinter) - compatible Python 3.7 / Windows 7."""
from __future__ import annotations

import os
import queue
import threading
import traceback
from datetime import datetime
from typing import Dict

from . import __version__, car
from .common import FileLog, JobError, find_files, resolve_template
from .config import app_dir, defaults, load_config, options_from_config, save_config
from .job import guess_family, run_job
from .vehicle_check import VehicleNotRegistered, check_vehicle
from .options import VEHICLE_BUS, VEHICLE_CAMION, VEHICLE_LABELS, VEHICLE_VOITURE

APP_TITLE = "Mesures - controle technique"

CONFLICT_LABELS = {
    "auto": "Selon le type (voiture/camion : ecraser, bus : renommer)",
    "overwrite": "Toujours ecraser",
    "rename": "Toujours renommer (date et heure)",
}
MODE_LABELS = {"auto": "Automatique (.O sans .G = gazole)", "essence": "Essence", "gazole": "Gazole"}


def has_measure_files(folder: str) -> bool:
    return any(find_files(folder, e) for e in "FOGRS")


def default_folder(cfg: Dict[str, object]) -> str:
    """Dossier courant (le logiciel de mesure lance l'exe depuis le dossier des fichiers)."""
    return os.getcwd()


def run_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    cfg = load_config()
    journal = FileLog(os.path.join(app_dir(), "mesures_log.txt"))

    class App(tk.Tk):
        def __init__(self) -> None:
            super().__init__()
            self.title("%s  v%s" % (APP_TITLE, __version__))
            self.minsize(820, 680)
            self.q: "queue.Queue" = queue.Queue()
            self.running = False

            S, B, I, D = tk.StringVar, tk.BooleanVar, tk.IntVar, tk.DoubleVar
            self.v_folder = S(value=default_folder(cfg))
            self.v_vehicle = S(value=str(cfg["vehicle"]))
            self.v_mode = S(value=MODE_LABELS.get(str(cfg["mode"]), MODE_LABELS["auto"]))
            self.v_dest = S(value=str(cfg["dest"]))
            self.v_pdf, self.v_print, self.v_move = B(value=bool(cfg["make_pdf"])), B(value=bool(cfg["do_print"])), \
                B(value=bool(cfg["move_files"]))
            self.v_copies = I(value=int(cfg["copies"]))
            self.v_delrep = B(value=bool(cfg["delete_report"]))
            self.v_check, self.v_cg = B(value=bool(cfg["check_cg"])), S(value=str(cfg["cg_dir"]))
            self.v_conflict = S(value=CONFLICT_LABELS.get(str(cfg["conflict"]), CONFLICT_LABELS["auto"]))
            self.v_tpl = {k: S(value=str(cfg[k])) for k in ("tpl_essence", "tpl_gazole", "tpl_bus", "tpl_camion")}
            self.v_chrome, self.v_sumatra = S(value=str(cfg["chrome"])), S(value=str(cfg["sumatra"]))
            self.v_bus_scale = I(value=int(cfg["bus_scale"]))
            self.v_bus_shift, self.v_camion_shift = D(value=float(cfg["bus_shift"])), \
                D(value=float(cfg["camion_shift"]))
            self.v_info, self.v_warn = S(), S()

            nb = ttk.Notebook(self)
            nb.pack(fill="both", expand=True, padx=8, pady=8)
            main = ttk.Frame(nb, padding=10)
            setup = ttk.Frame(nb, padding=10)
            nb.add(main, text="Traitement")
            nb.add(setup, text="Reglages")
            self._build_main(main)
            self._build_setup(setup)

            for v in [self.v_folder, self.v_vehicle, self.v_mode, *self.v_tpl.values()]:
                v.trace_add("write", lambda *_: self.refresh_info())
            self.v_print.trace_add("write", lambda *_: self.v_print.get() and self.v_pdf.set(True))
            self.refresh_info()
            self.protocol("WM_DELETE_WINDOW", self.on_close)

        # -- construction ---------------------------------------------------
        def _build_main(self, root: "ttk.Frame") -> None:
            pad = {"padx": 6, "pady": 3}
            root.columnconfigure(0, weight=1)
            root.rowconfigure(5, weight=1)

            f1 = ttk.LabelFrame(root, text="1. Dossier des fichiers de mesures", padding=8)
            f1.grid(row=0, column=0, sticky="ew", pady=(0, 6))
            f1.columnconfigure(0, weight=1)
            ttk.Entry(f1, textvariable=self.v_folder).grid(row=0, column=0, sticky="ew", **pad)
            ttk.Button(f1, text="Parcourir...", command=self.pick_folder).grid(row=0, column=1, **pad)
            ttk.Button(f1, text="Actualiser", command=self.refresh_info).grid(row=0, column=2, **pad)
            ttk.Label(f1, textvariable=self.v_info, justify="left").grid(row=1, column=0, columnspan=3,
                                                                         sticky="w", **pad)
            ttk.Label(f1, textvariable=self.v_warn, foreground="#b00000", justify="left").grid(
                row=2, column=0, columnspan=3, sticky="w", **pad)

            f2 = ttk.LabelFrame(root, text="2. Type de vehicule", padding=8)
            f2.grid(row=1, column=0, sticky="ew", pady=(0, 6))
            for i, key in enumerate((VEHICLE_VOITURE, VEHICLE_BUS, VEHICLE_CAMION)):
                ttk.Radiobutton(f2, text=VEHICLE_LABELS[key], value=key, variable=self.v_vehicle).grid(
                    row=0, column=i, sticky="w", **pad)
            ttk.Label(f2, text="Voiture - controle :").grid(row=1, column=0, sticky="e", **pad)
            ttk.Combobox(f2, textvariable=self.v_mode, state="readonly", width=34,
                         values=list(MODE_LABELS.values())).grid(row=1, column=1, columnspan=2, sticky="w", **pad)

            f3 = ttk.LabelFrame(root, text="3. Actions", padding=8)
            f3.grid(row=2, column=0, sticky="ew", pady=(0, 6))
            f3.columnconfigure(4, weight=1)
            ttk.Checkbutton(f3, text="Creer le PDF", variable=self.v_pdf).grid(row=0, column=0, sticky="w", **pad)
            ttk.Checkbutton(f3, text="Imprimer", variable=self.v_print).grid(row=0, column=1, sticky="w", **pad)
            ttk.Label(f3, text="Exemplaires :").grid(row=0, column=2, sticky="e", **pad)
            ttk.Spinbox(f3, from_=1, to=10, width=4, textvariable=self.v_copies).grid(row=0, column=3, sticky="w", **pad)
            ttk.Checkbutton(f3, text="Deplacer les fichiers de mesures vers :", variable=self.v_move).grid(
                row=1, column=0, columnspan=3, sticky="w", **pad)
            ttk.Entry(f3, textvariable=self.v_dest).grid(row=1, column=3, columnspan=2, sticky="ew", **pad)

            ttk.Checkbutton(f3, text="Supprimer le rapport (HTML et PDF) une fois les fichiers deplaces",
                            variable=self.v_delrep).grid(row=2, column=0, columnspan=5, sticky="w", **pad)

            f4 = ttk.Frame(root)
            f4.grid(row=3, column=0, sticky="ew", pady=(0, 6))
            self.btn_run = ttk.Button(f4, text="Lancer le traitement", command=self.start)
            self.btn_run.pack(side="left", **pad)
            ttk.Button(f4, text="Ouvrir le rapport", command=self.open_report).pack(side="left", **pad)
            ttk.Button(f4, text="Ouvrir le dossier", command=self.open_folder).pack(side="left", **pad)
            ttk.Button(f4, text="Quitter", command=self.on_close).pack(side="right", **pad)
            self.pb = ttk.Progressbar(f4, mode="indeterminate", length=120)
            self.pb.pack(side="right", **pad)

            ttk.Label(root, text="Journal").grid(row=4, column=0, sticky="w")
            self.log_box = scrolledtext.ScrolledText(root, height=12, state="disabled", font=("Consolas", 9))
            self.log_box.grid(row=5, column=0, sticky="nsew")

        def _build_setup(self, root: "ttk.Frame") -> None:
            pad = {"padx": 6, "pady": 3}
            root.columnconfigure(1, weight=1)
            r = 0
            rows = (("Modele voiture essence :", self.v_tpl["tpl_essence"], None),
                    ("Modele voiture gazole :", self.v_tpl["tpl_gazole"], None),
                    ("Modele bus :", self.v_tpl["tpl_bus"], None),
                    ("Modele camion lourd :", self.v_tpl["tpl_camion"], None),
                    ("Chrome (vide = auto) :", self.v_chrome, "exe"),
                    ("SumatraPDF (vide = auto) :", self.v_sumatra, "exe"))
            for label, var, kind in rows:
                ttk.Label(root, text=label).grid(row=r, column=0, sticky="w", **pad)
                ttk.Entry(root, textvariable=var).grid(row=r, column=1, sticky="ew", **pad)
                if kind:
                    ttk.Button(root, text="...", width=3, command=lambda v=var: self.pick_exe(v)).grid(
                        row=r, column=2, **pad)
                r += 1
            ttk.Checkbutton(root, text="Verifier le vehicule avant traitement (fichier .cg)",
                            variable=self.v_check).grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(root, textvariable=self.v_cg).grid(row=r, column=1, sticky="ew", **pad)
            ttk.Button(root, text="...", width=3, command=self.pick_cg).grid(row=r, column=2, **pad)
            r += 1
            ttk.Label(root, text="Fichier deja present dans la destination :").grid(row=r, column=0, sticky="w", **pad)
            ttk.Combobox(root, textvariable=self.v_conflict, state="readonly",
                         values=list(CONFLICT_LABELS.values())).grid(row=r, column=1, sticky="ew", **pad)
            r += 1
            cal = ttk.LabelFrame(root, text="Calage de l'impression", padding=8)
            cal.grid(row=r, column=0, columnspan=3, sticky="ew", pady=8)
            ttk.Label(cal, text="Bus - taille de la page (%) :").grid(row=0, column=0, sticky="w", **pad)
            ttk.Spinbox(cal, from_=50, to=120, width=6, textvariable=self.v_bus_scale).grid(row=0, column=1, **pad)
            ttk.Label(cal, text="Bus - decalage horizontal (%) :").grid(row=1, column=0, sticky="w", **pad)
            ttk.Spinbox(cal, from_=-20, to=20, increment=0.5, width=6, textvariable=self.v_bus_shift).grid(
                row=1, column=1, **pad)
            ttk.Label(cal, text="Camion lourd - decalage horizontal (%) :").grid(row=2, column=0, sticky="w", **pad)
            ttk.Spinbox(cal, from_=-20, to=20, increment=0.5, width=6, textvariable=self.v_camion_shift).grid(
                row=2, column=1, **pad)
            ttk.Label(cal, text="Negatif = vers la gauche. Les modeles HTML sont cherches dans le dossier "
                                "des mesures, puis a cote du programme.", wraplength=620).grid(
                row=3, column=0, columnspan=2, sticky="w", **pad)
            ttk.Button(root, text="Valeurs par defaut", command=self.reset_defaults).grid(row=r + 1, column=0, sticky="w", **pad)

        # -- utilitaires ----------------------------------------------------
        @staticmethod
        def _key(labels: Dict[str, str], text: str, fallback: str) -> str:
            for k, v in labels.items():
                if v == text:
                    return k
            return fallback

        def pick_folder(self) -> None:
            d = filedialog.askdirectory(initialdir=self.v_folder.get() or os.getcwd(),
                                        title="Dossier des fichiers de mesures")
            if d:
                self.v_folder.set(os.path.normpath(d))

        def pick_cg(self) -> None:
            d = filedialog.askdirectory(initialdir=self.v_cg.get() or os.getcwd(), title="Dossier cg")
            if d:
                self.v_cg.set(os.path.normpath(d))

        def pick_exe(self, var: "tk.StringVar") -> None:
            p = filedialog.askopenfilename(title="Choisir le programme",
                                           filetypes=[("Programme", "*.exe"), ("Tous", "*.*")])
            if p:
                var.set(os.path.normpath(p))

        def reset_defaults(self) -> None:
            d = defaults()
            for k, v in self.v_tpl.items():
                v.set(str(d[k]))
            self.v_chrome.set("")
            self.v_sumatra.set("")
            self.v_check.set(True)
            self.v_cg.set(str(d["cg_dir"]))
            self.v_conflict.set(CONFLICT_LABELS["auto"])
            self.v_bus_scale.set(int(d["bus_scale"]))
            self.v_bus_shift.set(float(d["bus_shift"]))
            self.v_camion_shift.set(float(d["camion_shift"]))

        def refresh_info(self) -> None:
            folder = self.v_folder.get().strip()
            self.v_warn.set("")
            if not os.path.isdir(folder):
                self.v_info.set("Dossier introuvable.")
                return
            parts = ["%s x%d" % (e, len(find_files(folder, e))) for e in "FOGRS" if find_files(folder, e)]
            vehicle = self.v_vehicle.get()
            if vehicle == VEHICLE_VOITURE:
                mode = self._key(MODE_LABELS, self.v_mode.get(), "auto")
                label = car.detect_mode(folder) if mode == "auto" else mode.upper()
                name = self.v_tpl["tpl_gazole" if label == car.MODE_GAZOLE else "tpl_essence"].get()
            elif vehicle == VEHICLE_BUS:
                label, name = "BUS", self.v_tpl["tpl_bus"].get()
            else:
                label, name = "CAMION LOURD", self.v_tpl["tpl_camion"].get()
            tpl = resolve_template(name, folder, app_dir())
            self.v_info.set("Fichiers : %s   |   Traitement : %s   |   Modele : %s" % (
                ", ".join(parts) if parts else "aucun fichier de mesures", label,
                "trouve" if tpl else "INTROUVABLE"))
            family = guess_family(folder)
            if family == "bus_camion" and vehicle == VEHICLE_VOITURE:
                self.v_warn.set("ATTENTION : les fichiers ressemblent a un bus / camion lourd, pas a une voiture.")
            elif family == "voiture" and vehicle != VEHICLE_VOITURE:
                self.v_warn.set("ATTENTION : les fichiers ressemblent a une voiture, pas a un bus / camion lourd.")

        def log(self, msg: str) -> None:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", "%s  %s\n" % (datetime.now().strftime("%H:%M:%S"), msg))
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        def current_config(self) -> Dict[str, object]:
            def num(var, default, cast):
                try:
                    return cast(var.get())
                except (tk.TclError, ValueError):
                    return default
            copies = max(1, min(10, num(self.v_copies, 2, int)))
            c: Dict[str, object] = {
                "vehicle": self.v_vehicle.get(),
                "mode": self._key(MODE_LABELS, self.v_mode.get(), "auto"),
                "dest": self.v_dest.get().strip() or str(defaults()["dest"]),
                "make_pdf": self.v_pdf.get(), "do_print": self.v_print.get(), "copies": copies,
                "move_files": self.v_move.get(),
                "delete_report": self.v_delrep.get(),
                "check_cg": self.v_check.get(),
                "cg_dir": self.v_cg.get().strip() or str(defaults()["cg_dir"]),
                "conflict": self._key(CONFLICT_LABELS, self.v_conflict.get(), "auto"),
                "chrome": self.v_chrome.get().strip(), "sumatra": self.v_sumatra.get().strip(),
                "bus_scale": num(self.v_bus_scale, 88, int),
                "bus_shift": num(self.v_bus_shift, -3.0, float),
                "camion_shift": num(self.v_camion_shift, -4.0, float),
            }
            for k, v in self.v_tpl.items():
                c[k] = v.get().strip() or str(defaults()[k])
            return c

        def open_path(self, path: str) -> None:
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                messagebox.showinfo(APP_TITLE, path)
                return
            try:
                startfile(path)
            except OSError as exc:
                messagebox.showerror(APP_TITLE, "Impossible d'ouvrir :\n%s\n\n%s" % (path, exc))

        def open_report(self) -> None:
            folder = self.v_folder.get().strip()
            name = "rapport_camion.html" if self.v_vehicle.get() == VEHICLE_CAMION else "rapport_a_imprimer.html"
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                self.open_path(p)
            else:
                messagebox.showinfo(APP_TITLE, "Aucun rapport dans ce dossier (supprime apres le deplacement, "
                                    "ou pas encore genere).")

        def open_folder(self) -> None:
            self.open_path(self.v_folder.get().strip())

        # -- execution ------------------------------------------------------
        def start(self) -> None:
            if self.running:
                return
            folder = self.v_folder.get().strip()
            if not os.path.isdir(folder):
                messagebox.showerror(APP_TITLE, "Le dossier n'existe pas :\n" + folder)
                return
            if self.v_check.get():
                # Le fichier .cg peut etre ajoute a tout moment : on relit le dossier a chaque essai.
                cg_dir = self.v_cg.get().strip() or str(defaults()["cg_dir"])
                while True:
                    try:
                        check_vehicle(folder, cg_dir, lambda m: None)
                        break
                    except VehicleNotRegistered as exc:
                        if not messagebox.askretrycancel(
                                APP_TITLE, "%s\n\nEnregistrez le vehicule, puis cliquez sur Reessayer." % exc):
                            return
                    except JobError as exc:
                        messagebox.showerror(APP_TITLE, str(exc))
                        return
            if self.v_warn.get() and not messagebox.askyesno(APP_TITLE, self.v_warn.get() + "\n\nContinuer quand meme ?"):
                return
            if not has_measure_files(folder):
                messagebox.showerror(APP_TITLE, "Aucun fichier de mesures (.F .O .G .R .S) dans ce dossier :\n%s\n\n"
                                     "Choisissez le dossier qui contient les fichiers du vehicule." % folder)
                return
            if self.v_move.get() and not messagebox.askyesno(
                    APP_TITLE, "Les fichiers de mesures seront deplaces vers :\n%s\n\nContinuer ?" % self.v_dest.get()):
                return
            new_cfg = self.current_config()
            cfg.update(new_cfg)
            save_config(cfg)
            opt = options_from_config(new_cfg, folder)
            self.running = True
            self.btn_run.configure(state="disabled")
            self.pb.start(12)
            self.log("---- Demarrage ----")
            journal("---- Demarrage (%s) ----" % VEHICLE_LABELS.get(opt.vehicle, opt.vehicle))
            threading.Thread(target=self._worker, args=(opt,), daemon=True).start()
            self.after(100, self._poll)

        def _worker(self, opt) -> None:
            def emit(m: str) -> None:
                journal(m)
                self.q.put(("log", m))
            ok = False
            try:
                ok = run_job(opt, emit)
            except Exception:  # noqa: BLE001
                emit("ERREUR inattendue :\n" + traceback.format_exc())
            self.q.put(("done", ok))

        def _poll(self) -> None:
            finished = None
            try:
                while True:
                    kind, payload = self.q.get_nowait()
                    if kind == "log":
                        self.log(str(payload))
                    else:
                        finished = bool(payload)
            except queue.Empty:
                pass
            if finished is None:
                self.after(100, self._poll)
                return
            self.pb.stop()
            self.btn_run.configure(state="normal")
            self.running = False
            self.refresh_info()
            if finished:
                messagebox.showinfo(APP_TITLE, "Traitement termine.")
            else:
                messagebox.showerror(APP_TITLE, "Le traitement a echoue. Voir le journal.")

        def on_close(self) -> None:
            cfg.update(self.current_config())
            save_config(cfg)
            self.destroy()

    App().mainloop()
    return 0
