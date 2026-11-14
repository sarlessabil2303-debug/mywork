# -*- coding: utf-8 -*-
"""
mesures_app.py - interface graphique (tkinter) pour mesures_core.

    MesuresApp.exe                      -> ouvre la fenetre
    MesuresApp.exe --auto               -> lance le traitement sans fenetre (comme l'ancien .bat)
    MesuresApp.exe --auto --folder D:\\mesures --no-print

Compatible Python 3.8 / Windows 7.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import traceback
from datetime import datetime
from typing import Dict

import mesures_core as core

APP_TITLE = "Mesures - date, CRC et rapport"

DEFAULTS: Dict[str, object] = {
    "folder": "",
    "dest": r"C:\GIEGLAN\res",
    "mode": "auto",
    "make_pdf": True,
    "do_print": True,
    "copies": 2,
    "move_files": True,
    "tpl_essence": "es7_essence test_merged.html",
    "tpl_gazole": "go1.html",
    "chrome": "",
    "sumatra": "",
}


def app_dir() -> str:
    """Dossier de l'exe (PyInstaller) ou du script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def config_path() -> str:
    return os.path.join(app_dir(), "mesures_config.json")


def load_config() -> Dict[str, object]:
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: Dict[str, object]) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def has_measure_files(folder: str) -> bool:
    return any(core.find_files(folder, e) for e in core.EXT_KEYS)


def default_folder(cfg: Dict[str, object]) -> str:
    cwd = os.getcwd()
    if has_measure_files(cwd):
        return cwd
    saved = str(cfg.get("folder") or "")
    if saved and os.path.isdir(saved):
        return saved
    return cwd


def options_from_config(cfg: Dict[str, object], folder: str) -> core.JobOptions:
    return core.JobOptions(
        folder=folder,
        dest=str(cfg["dest"]),
        mode=str(cfg["mode"]),
        make_pdf=bool(cfg["make_pdf"]),
        do_print=bool(cfg["do_print"]),
        copies=int(cfg["copies"]),
        move_files=bool(cfg["move_files"]),
        tpl_essence=str(cfg["tpl_essence"]),
        tpl_gazole=str(cfg["tpl_gazole"]),
        chrome=str(cfg["chrome"]),
        sumatra=str(cfg["sumatra"]),
        app_dir=app_dir(),
    )


# ---------------------------------------------------------------------------
# Mode sans fenetre
# ---------------------------------------------------------------------------
def run_auto(args: argparse.Namespace) -> int:
    cfg = load_config()
    folder = args.folder or default_folder(cfg)
    opt = options_from_config(cfg, folder)
    if args.no_print:
        opt.do_print = False
    if args.no_pdf:
        opt.make_pdf = False
        opt.do_print = False
    if args.no_move:
        opt.move_files = False
    if args.mode:
        opt.mode = args.mode
    log_file = os.path.join(app_dir(), "mesures_log.txt")
    try:
        lf = open(log_file, "w", encoding="utf-8")
    except OSError:
        lf = None

    def log(msg: str) -> None:
        if lf:
            lf.write("%s  %s\n" % (datetime.now().strftime("%H:%M:%S"), msg))
            lf.flush()
        try:
            print(msg)
        except Exception:  # noqa: BLE001 - pas de console en mode fenetre
            pass

    try:
        return 0 if core.run_job(opt, log) else 1
    finally:
        if lf:
            lf.close()


# ---------------------------------------------------------------------------
# Interface graphique
# ---------------------------------------------------------------------------
def run_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    cfg = load_config()

    class App(tk.Tk):
        def __init__(self) -> None:
            super().__init__()
            self.title(APP_TITLE)
            self.minsize(780, 640)
            self.q: "queue.Queue" = queue.Queue()
            self.running = False

            self.v_folder = tk.StringVar(value=default_folder(cfg))
            self.v_dest = tk.StringVar(value=str(cfg["dest"]))
            self.v_mode = tk.StringVar(value=str(cfg["mode"]))
            self.v_pdf = tk.BooleanVar(value=bool(cfg["make_pdf"]))
            self.v_print = tk.BooleanVar(value=bool(cfg["do_print"]))
            self.v_move = tk.BooleanVar(value=bool(cfg["move_files"]))
            self.v_copies = tk.IntVar(value=int(cfg["copies"]))
            self.v_tpl_es = tk.StringVar(value=str(cfg["tpl_essence"]))
            self.v_tpl_go = tk.StringVar(value=str(cfg["tpl_gazole"]))
            self.v_chrome = tk.StringVar(value=str(cfg["chrome"]))
            self.v_sumatra = tk.StringVar(value=str(cfg["sumatra"]))
            self.v_info = tk.StringVar()

            self._build()
            for v in (self.v_folder, self.v_mode, self.v_tpl_es, self.v_tpl_go):
                v.trace_add("write", lambda *_: self.refresh_info())
            self.v_print.trace_add("write", lambda *_: self._sync_print())
            self.refresh_info()
            self.protocol("WM_DELETE_WINDOW", self.on_close)

        # -- construction ---------------------------------------------------
        def _build(self) -> None:
            pad = {"padx": 6, "pady": 3}
            root = ttk.Frame(self, padding=10)
            root.pack(fill="both", expand=True)
            root.columnconfigure(0, weight=1)

            f1 = ttk.LabelFrame(root, text="Dossier des fichiers de mesures", padding=8)
            f1.grid(row=0, column=0, sticky="ew", pady=(0, 6))
            f1.columnconfigure(0, weight=1)
            ttk.Entry(f1, textvariable=self.v_folder).grid(row=0, column=0, sticky="ew", **pad)
            ttk.Button(f1, text="Parcourir...", command=self.pick_folder).grid(row=0, column=1, **pad)
            ttk.Button(f1, text="Actualiser", command=self.refresh_info).grid(row=0, column=2, **pad)
            ttk.Label(f1, textvariable=self.v_info, justify="left").grid(
                row=1, column=0, columnspan=3, sticky="w", **pad)

            f2 = ttk.LabelFrame(root, text="Traitement", padding=8)
            f2.grid(row=1, column=0, sticky="ew", pady=(0, 6))
            f2.columnconfigure(3, weight=1)
            ttk.Label(f2, text="Type de controle :").grid(row=0, column=0, sticky="w", **pad)
            ttk.Combobox(f2, textvariable=self.v_mode, state="readonly", width=12,
                         values=("auto", "essence", "gazole")).grid(row=0, column=1, sticky="w", **pad)
            ttk.Label(f2, text="(auto : .O sans .G = gazole)").grid(row=0, column=2, columnspan=2, sticky="w", **pad)
            ttk.Checkbutton(f2, text="Creer le PDF", variable=self.v_pdf).grid(row=1, column=0, sticky="w", **pad)
            ttk.Checkbutton(f2, text="Imprimer", variable=self.v_print).grid(row=1, column=1, sticky="w", **pad)
            ttk.Label(f2, text="Exemplaires :").grid(row=1, column=2, sticky="e", **pad)
            ttk.Spinbox(f2, from_=1, to=10, width=4, textvariable=self.v_copies).grid(row=1, column=3, sticky="w", **pad)
            ttk.Checkbutton(f2, text="Deplacer les fichiers de mesures vers :", variable=self.v_move).grid(
                row=2, column=0, columnspan=2, sticky="w", **pad)
            ttk.Entry(f2, textvariable=self.v_dest).grid(row=2, column=2, columnspan=2, sticky="ew", **pad)

            f3 = ttk.LabelFrame(root, text="Options avancees", padding=8)
            f3.grid(row=2, column=0, sticky="ew", pady=(0, 6))
            f3.columnconfigure(1, weight=1)
            rows = (
                ("Modele essence :", self.v_tpl_es, None),
                ("Modele gazole :", self.v_tpl_go, None),
                ("Chrome (vide = auto) :", self.v_chrome, "exe"),
                ("SumatraPDF (vide = auto) :", self.v_sumatra, "exe"),
            )
            for i, (label, var, kind) in enumerate(rows):
                ttk.Label(f3, text=label).grid(row=i, column=0, sticky="w", **pad)
                ttk.Entry(f3, textvariable=var).grid(row=i, column=1, sticky="ew", **pad)
                if kind:
                    ttk.Button(f3, text="...", width=3,
                               command=lambda v=var: self.pick_exe(v)).grid(row=i, column=2, **pad)

            f4 = ttk.Frame(root)
            f4.grid(row=3, column=0, sticky="ew", pady=(0, 6))
            self.btn_run = ttk.Button(f4, text="Lancer le traitement", command=self.start)
            self.btn_run.pack(side="left", **pad)
            ttk.Button(f4, text="Ouvrir le rapport", command=self.open_report).pack(side="left", **pad)
            ttk.Button(f4, text="Ouvrir le dossier", command=self.open_folder).pack(side="left", **pad)
            ttk.Button(f4, text="Quitter", command=self.on_close).pack(side="right", **pad)
            self.pb = ttk.Progressbar(f4, mode="indeterminate", length=120)
            self.pb.pack(side="right", **pad)

            root.rowconfigure(4, weight=1)
            self.log_box = scrolledtext.ScrolledText(root, height=12, state="disabled", font=("Consolas", 9))
            self.log_box.grid(row=4, column=0, sticky="nsew")

        # -- utilitaires ----------------------------------------------------
        def _sync_print(self) -> None:
            if self.v_print.get():
                self.v_pdf.set(True)

        def pick_folder(self) -> None:
            d = filedialog.askdirectory(initialdir=self.v_folder.get() or os.getcwd(),
                                        title="Dossier des fichiers de mesures")
            if d:
                self.v_folder.set(os.path.normpath(d))

        def pick_exe(self, var: "tk.StringVar") -> None:
            p = filedialog.askopenfilename(title="Choisir le programme",
                                           filetypes=[("Programme", "*.exe"), ("Tous", "*.*")])
            if p:
                var.set(os.path.normpath(p))

        def refresh_info(self) -> None:
            folder = self.v_folder.get().strip()
            if not os.path.isdir(folder):
                self.v_info.set("Dossier introuvable.")
                return
            parts = []
            for ext in core.EXT_KEYS:
                n = len(core.find_files(folder, ext))
                if n:
                    parts.append("%s x%d" % (ext, n))
            files = ", ".join(parts) if parts else "aucun fichier de mesures"
            mode = self.v_mode.get()
            detected = core.detect_mode(folder) if mode == "auto" else mode.upper()
            name = self.v_tpl_go.get() if detected == core.MODE_GAZOLE else self.v_tpl_es.get()
            tpl = core.resolve_template(name, folder, app_dir())
            self.v_info.set("Fichiers : %s   |   Mode : %s   |   Modele : %s" % (
                files, detected, "trouve" if tpl else "INTROUVABLE"))

        def log(self, msg: str) -> None:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", "%s  %s\n" % (datetime.now().strftime("%H:%M:%S"), msg))
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        def current_config(self) -> Dict[str, object]:
            try:
                copies = max(1, min(10, int(self.v_copies.get())))
            except (tk.TclError, ValueError):
                copies = 2
            return {
                "folder": self.v_folder.get().strip(),
                "dest": self.v_dest.get().strip() or str(DEFAULTS["dest"]),
                "mode": self.v_mode.get(),
                "make_pdf": self.v_pdf.get(),
                "do_print": self.v_print.get(),
                "copies": copies,
                "move_files": self.v_move.get(),
                "tpl_essence": self.v_tpl_es.get().strip() or str(DEFAULTS["tpl_essence"]),
                "tpl_gazole": self.v_tpl_go.get().strip() or str(DEFAULTS["tpl_gazole"]),
                "chrome": self.v_chrome.get().strip(),
                "sumatra": self.v_sumatra.get().strip(),
            }

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
            p = os.path.join(self.v_folder.get().strip(), core.REPORT_NAME)
            if os.path.isfile(p):
                self.open_path(p)
            else:
                messagebox.showinfo(APP_TITLE, "Aucun rapport genere dans ce dossier.")

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
            if not has_measure_files(folder):
                if not messagebox.askyesno(APP_TITLE, "Aucun fichier de mesures (.F .O .G .R .S) dans ce dossier.\n"
                                           "Continuer quand meme ?"):
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
            threading.Thread(target=self._worker, args=(opt,), daemon=True).start()
            self.after(100, self._poll)

        def _worker(self, opt: core.JobOptions) -> None:
            ok = False
            try:
                ok = core.run_job(opt, lambda m: self.q.put(("log", m)))
            except Exception:  # noqa: BLE001
                self.q.put(("log", "ERREUR inattendue :\n" + traceback.format_exc()))
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=APP_TITLE)
    p.add_argument("--auto", action="store_true", help="traitement sans fenetre")
    p.add_argument("--folder", help="dossier des fichiers de mesures (defaut : dossier courant)")
    p.add_argument("--mode", choices=("auto", "essence", "gazole"))
    p.add_argument("--no-print", action="store_true", help="ne pas imprimer")
    p.add_argument("--no-pdf", action="store_true", help="ne pas creer le PDF (ni imprimer)")
    p.add_argument("--no-move", action="store_true", help="ne pas deplacer les fichiers")
    args = p.parse_args(argv)
    if args.auto:
        return run_auto(args)
    try:
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
