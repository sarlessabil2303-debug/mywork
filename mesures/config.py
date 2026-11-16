# -*- coding: utf-8 -*-
"""Configuration persistante (JSON a cote de l'exe)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from typing import Dict

from .options import CONFIG_KEYS, JobOptions


def app_dir() -> str:
    """Dossier de l'exe (PyInstaller) ou du projet."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path() -> str:
    return os.path.join(app_dir(), "mesures_config.json")


def defaults() -> Dict[str, object]:
    base = asdict(JobOptions(folder=""))
    return {k: base[k] for k in CONFIG_KEYS}


def load_config() -> Dict[str, object]:
    cfg = defaults()
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            for k in CONFIG_KEYS:
                if k not in data:
                    continue
                v, d = data[k], cfg[k]
                if isinstance(d, bool):
                    ok = isinstance(v, bool)
                elif isinstance(d, float):
                    ok = isinstance(v, (int, float)) and not isinstance(v, bool)
                elif isinstance(d, int):
                    ok = isinstance(v, int) and not isinstance(v, bool)
                else:
                    ok = isinstance(v, str)
                if ok:
                    cfg[k] = float(v) if isinstance(d, float) else v
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: Dict[str, object]) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump({k: cfg[k] for k in CONFIG_KEYS if k in cfg}, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def options_from_config(cfg: Dict[str, object], folder: str) -> JobOptions:
    opt = JobOptions(folder=folder)
    for k in CONFIG_KEYS:
        if k in cfg:
            setattr(opt, k, cfg[k])
    opt.bus_shift = float(opt.bus_shift)
    opt.camion_shift = float(opt.camion_shift)
    opt.app_dir = app_dir()
    return opt
