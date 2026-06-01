"""Worker thread untuk operasi berat agar UI tetap responsif."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .db import Database
from .imaging import (is_media, is_video, extract_metadata,
                      extract_video_metadata, get_thumbnail)
from .sources import classify


class ScanWorker(QThread):
    """Pindai folder secara rekursif lalu simpan metadata foto ke database."""

    progress = Signal(int, int, str)   # current, total, filename
    finished_scan = Signal(int)        # jumlah foto terindeks

    def __init__(self, db: Database, folders: list[str], cache_dir: Path):
        super().__init__()
        self.db = db
        self.folders = folders
        self.cache_dir = cache_dir
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # Kumpulkan semua file gambar lebih dulu agar bisa menghitung total.
        files: list[Path] = []
        for folder in self.folders:
            for root, _dirs, names in os.walk(folder):
                for name in names:
                    p = Path(root) / name
                    if is_media(p):
                        files.append(p)

        total = len(files)
        seen_paths: set[str] = set()
        for i, path in enumerate(files, 1):
            if self._stop:
                break
            sp = str(path)
            seen_paths.add(sp)
            try:
                mtime = path.stat().st_mtime
                size = path.stat().st_size
            except OSError:
                continue

            if self.db.get_photo_mtime(sp) != mtime:
                if is_video(path):
                    meta = extract_video_metadata(path)
                    media_type = "video"
                else:
                    meta = extract_metadata(path)
                    media_type = "photo"
                meta.setdefault("duration", None)
                self.db.upsert_photo({
                    "path": sp,
                    "filename": path.name,
                    "size": size,
                    "mtime": mtime,
                    "media_type": media_type,
                    "source": classify(sp),
                    **meta,
                })
            else:
                # Backfill ringan untuk record lama tanpa kolom sumber.
                self.db.ensure_source(
                    sp, classify(sp),
                    "video" if is_video(path) else "photo")
            self.progress.emit(i, total, path.name)

        self.db.commit()
        self.finished_scan.emit(total)


class ThumbnailWorker(QThread):
    """Hasilkan thumbnail untuk daftar item dan kirim saat masing-masing siap."""

    thumb_ready = Signal(int, str)   # row_index, thumb_path

    def __init__(self, items: list[tuple[int, str]], cache_dir: Path):
        super().__init__()
        self.items = items          # (row_index, image_path)
        self.cache_dir = cache_dir
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        for row_index, image_path in self.items:
            if self._stop:
                return
            thumb = get_thumbnail(Path(image_path), self.cache_dir)
            if thumb:
                self.thumb_ready.emit(row_index, str(thumb))


class FaceWorker(QThread):
    """Deteksi wajah pada foto baru lalu kelompokkan menjadi orang."""

    progress = Signal(int, int, str)        # current, total, fase
    finished_faces = Signal(int, int)       # jumlah wajah, jumlah orang

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from collections import defaultdict
        from .faces import FaceAnalyzer, cluster_faces

        pending = self.db.needs_face_scan()
        total = len(pending)
        new_faces = 0
        try:
            analyzer = FaceAnalyzer()
        except Exception:
            self.finished_faces.emit(0, 0)
            return

        # --- Tahap 1: deteksi & embedding ---
        for i, row in enumerate(pending, 1):
            if self._stop:
                break
            results = analyzer.analyze(row["path"])
            for r in results:
                self.db.add_face(row["id"], r["box"], r["embedding"])
                new_faces += 1
            self.db.mark_faces_done(row["id"])
            if i % 20 == 0:
                self.db.commit()
            self.progress.emit(i, total, f"Deteksi wajah: {Path(row['path']).name}")
        self.db.commit()

        # --- Tahap 2: pengelompokan global ---
        self.progress.emit(total, total, "Mengelompokkan orang…")
        faces = self.db.all_faces()
        clusters = cluster_faces(faces)
        id_to_row = {f["id"]: f for f in faces}
        by_label: dict[int, list] = defaultdict(list)
        for fid, lbl in clusters.items():
            by_label[lbl].append(id_to_row[fid])

        for members in by_label.values():
            # Pertahankan orang yang sudah dinamai bila ada di klaster ini.
            existing = [m["person_id"] for m in members if m["person_id"]]
            named = None
            for pid in existing:
                r = self.db.conn.execute(
                    "SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()
                if r and r["name"]:
                    named = pid
                    break
            person_id = named or (existing[0] if existing else
                                  self.db.create_person())
            for m in members:
                if m["person_id"] != person_id:
                    self.db.assign_face_person(m["id"], person_id)

        # Hapus orang yang tidak lagi punya wajah.
        self.db.conn.execute(
            "DELETE FROM persons WHERE id NOT IN "
            "(SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)")
        self.db.commit()

        num_persons = len(self.db.persons_with_counts())
        self.finished_faces.emit(new_faces, num_persons)


class QualityWorker(QThread):
    """Pindai foto dan tandai yang kemungkinan 'tidak penting'."""

    progress = Signal(int, int, str)     # current, total, filename
    finished_quality = Signal(list)      # list dict {id,path,filename,reasons}

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from .quality import analyze_image
        rows = self.db.query_photos(media_type="photo")
        total = len(rows)
        out = []
        for i, r in enumerate(rows, 1):
            if self._stop:
                break
            reasons = analyze_image(r["path"])
            if reasons:
                out.append({"id": r["id"], "path": r["path"],
                            "filename": r["filename"], "reasons": reasons})
            self.progress.emit(i, total, r["filename"])
        self.finished_quality.emit(out)


class GeocodeWorker(QThread):
    """Isi nama tempat (reverse-geocode) untuk klaster lokasi, di latar belakang.

    Mematuhi kebijakan Nominatim (maks. 1 permintaan/detik) dan menyimpan hasil
    ke cache database.
    """

    progress = Signal(int, int)     # current, total
    finished_geo = Signal(int)      # jumlah nama baru

    def __init__(self, db: Database, targets: list[tuple]):
        super().__init__()
        self.db = db
        self.targets = targets      # list (key, lat, lon) yang belum ada namanya
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        import time
        from .locations import reverse_geocode
        total = len(self.targets)
        found = 0
        for i, (key, lat, lon) in enumerate(self.targets, 1):
            if self._stop:
                break
            name = reverse_geocode(lat, lon)
            if name:
                self.db.geocache_set(key, name)
                found += 1
            self.progress.emit(i, total)
            if i < total:
                time.sleep(1.1)     # patuhi batas 1 req/detik
        self.finished_geo.emit(found)
