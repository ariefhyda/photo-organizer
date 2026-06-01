"""Resolusi path aset, folder aplikasi, dan pengaturan portable."""

from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    """Path ke berkas di folder assets/, baik saat dev maupun saat jadi exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets" / name
    return Path(__file__).resolve().parent.parent / "assets" / name


def app_dir() -> Path:
    """Folder tempat aplikasi berada (di samping .exe saat dibekukan)."""
    if getattr(sys, "frozen", False):           # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    """Lokasi data default (portable): subfolder 'data' di folder aplikasi."""
    d = app_dir() / "data"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Folder aplikasi tak bisa ditulis (mis. Program Files) -> pakai home.
        d = Path.home() / ".photo_organizer"
        d.mkdir(parents=True, exist_ok=True)
    return d


def portable_settings():
    """QSettings berbasis berkas .ini di folder aplikasi (ikut portabel)."""
    from PySide6.QtCore import QSettings
    return QSettings(str(app_dir() / "photo_organizer.ini"),
                     QSettings.IniFormat)
