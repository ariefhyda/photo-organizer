"""Operasi pengorganisasian file: susun berdasarkan tanggal & ganti nama massal."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


def safe_folder_name(name: str) -> str:
    """Buang karakter yang tidak valid untuk nama folder (Windows)."""
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name)
    cleaned = re.sub(r"_+", "_", cleaned)          # gabungkan _ beruntun
    cleaned = cleaned.strip().strip("._ ").strip()  # buang . _ spasi di ujung
    return cleaned or "Album"


def export_to_folder(
    photos: list[dict],
    target_dir: Path,
    move: bool = False,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> list[tuple[int, str, str]]:
    """Salin/pindahkan media ke satu folder tujuan.

    Mengembalikan list (photo_id, old_path, new_path) yang berhasil.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[int, str, str]] = []
    total = len(photos)
    for i, p in enumerate(photos, 1):
        src = Path(p["path"])
        if not src.exists():
            continue
        dest = _unique_destination(target_dir / src.name)
        try:
            if move:
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(str(src), str(dest))
            results.append((p["id"], str(src), str(dest)))
        except (OSError, shutil.Error):
            pass
        if progress:
            progress(i, total, src.name)
    return results


def _unique_destination(dest: Path) -> Path:
    """Hindari menimpa file: tambahkan _1, _2, ... bila perlu."""
    if not dest.exists():
        return dest
    stem, suffix, parent = dest.stem, dest.suffix, dest.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def organize_by_date(
    photos: list[dict],
    target_root: Path,
    pattern: str = "%Y/%Y-%m",
    move: bool = False,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> list[tuple[int, str, str]]:
    """Salin/pindah foto ke subfolder berdasarkan tanggal pengambilan.

    `photos` adalah list dict berisi minimal 'id', 'path', 'date_taken'.
    `pattern` memakai format strftime untuk struktur folder.
    Mengembalikan list (photo_id, old_path, new_path) yang berhasil dipindah.
    """
    target_root = Path(target_root)
    results: list[tuple[int, str, str]] = []
    total = len(photos)
    for i, p in enumerate(photos, 1):
        src = Path(p["path"])
        if not src.exists():
            continue
        date_str = p.get("date_taken")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            dt = datetime.fromtimestamp(src.stat().st_mtime)
        subdir = target_root / dt.strftime(pattern)
        subdir.mkdir(parents=True, exist_ok=True)
        dest = _unique_destination(subdir / src.name)
        try:
            if move:
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(str(src), str(dest))
            results.append((p["id"], str(src), str(dest)))
        except (OSError, shutil.Error):
            pass
        if progress:
            progress(i, total, src.name)
    return results


def build_new_name(
    template: str,
    index: int,
    original: Path,
    date_taken: Optional[str],
) -> str:
    """Bangun nama file baru dari template.

    Placeholder yang didukung:
      {n}     -> nomor urut (1-based)
      {n:03}  -> nomor urut dengan padding (mis. 001)
      {name}  -> nama file asli tanpa ekstensi
      {ext}   -> ekstensi (tanpa titik)
      {date}  -> tanggal YYYY-MM-DD
      {time}  -> waktu HHMMSS
    """
    try:
        dt = datetime.strptime(date_taken, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        dt = datetime.fromtimestamp(original.stat().st_mtime)

    ext = original.suffix.lstrip(".")
    fields = {
        "n": index,
        "name": original.stem,
        "ext": ext,
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H%M%S"),
    }
    try:
        new_stem = template.format(**fields)
    except (KeyError, ValueError):
        new_stem = template
    # Pastikan ekstensi ada bila template tidak menyertakannya.
    if not Path(new_stem).suffix and ext:
        new_stem = f"{new_stem}.{ext}"
    return new_stem


def bulk_rename(
    photos: list[dict],
    template: str,
    start: int = 1,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> list[tuple[int, str, str]]:
    """Ganti nama banyak file sekaligus mengikuti template.

    Mengembalikan list (photo_id, old_path, new_path) yang berhasil di-rename.
    """
    results: list[tuple[int, str, str]] = []
    total = len(photos)
    for i, p in enumerate(photos):
        src = Path(p["path"])
        if not src.exists():
            continue
        new_name = build_new_name(template, start + i, src, p.get("date_taken"))
        dest = _unique_destination(src.with_name(new_name))
        try:
            src.rename(dest)
            results.append((p["id"], str(src), str(dest)))
        except OSError:
            pass
        if progress:
            progress(i + 1, total, new_name)
    return results
