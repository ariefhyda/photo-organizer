"""Lapisan database SQLite untuk menyimpan metadata foto, tag, dan rating."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional


def default_data_dir() -> Path:
    """Direktori penyimpanan database & cache thumbnail (per-user)."""
    d = Path.home() / ".photo_organizer"
    d.mkdir(parents=True, exist_ok=True)
    return d


SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    filename    TEXT NOT NULL,
    size        INTEGER,
    date_taken  TEXT,            -- ISO 'YYYY-MM-DD HH:MM:SS'
    date_source TEXT,            -- 'exif' atau 'mtime'
    width       INTEGER,
    height      INTEGER,
    phash       TEXT,            -- perceptual hash (deteksi duplikat)
    rating      INTEGER NOT NULL DEFAULT 0,
    mtime       REAL,            -- mtime file untuk deteksi perubahan
    media_type  TEXT NOT NULL DEFAULT 'photo',  -- 'photo' atau 'video'
    duration    REAL,            -- durasi video (detik)
    source      TEXT,            -- kategori sumber: camera/whatsapp/...
    faces_done  INTEGER NOT NULL DEFAULT 0,     -- 1 bila sudah dipindai wajah
    lat         REAL,            -- lintang GPS (EXIF)
    lon         REAL             -- bujur GPS (EXIF)
);
CREATE INDEX IF NOT EXISTS idx_photos_date   ON photos(date_taken);
CREATE INDEX IF NOT EXISTS idx_photos_phash  ON photos(phash);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS photo_tags (
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (photo_id, tag_id)
);

CREATE TABLE IF NOT EXISTS albums (
    id      INTEGER PRIMARY KEY,
    name    TEXT UNIQUE NOT NULL COLLATE NOCASE,
    created TEXT
);

CREATE TABLE IF NOT EXISTS album_items (
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    PRIMARY KEY (album_id, photo_id)
);

CREATE TABLE IF NOT EXISTS persons (
    id   INTEGER PRIMARY KEY,
    name TEXT                       -- NULL = belum dinamai
);

CREATE TABLE IF NOT EXISTS faces (
    id        INTEGER PRIMARY KEY,
    photo_id  INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    x INTEGER, y INTEGER, w INTEGER, h INTEGER,
    embedding BLOB                  -- vektor float32 (SFace, 128-d)
);
CREATE INDEX IF NOT EXISTS idx_faces_photo  ON faces(photo_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);

CREATE TABLE IF NOT EXISTS geocache (
    key  TEXT PRIMARY KEY,   -- 'lat,lon' dibulatkan
    name TEXT
);

CREATE TABLE IF NOT EXISTS staged_items (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE
);
"""

# Cuplikan SQL: kecualikan media yang ada di "Dihapus" (staged_items).
_NS = "NOT IN (SELECT photo_id FROM staged_items)"

# Kolom yang ditambahkan pada versi lebih baru (untuk migrasi DB lama).
_PHOTO_MIGRATIONS = {
    "media_type": "TEXT NOT NULL DEFAULT 'photo'",
    "duration": "REAL",
    "source": "TEXT",
    "faces_done": "INTEGER NOT NULL DEFAULT 0",
    "lat": "REAL",
    "lon": "REAL",
}


class Database:
    """Pembungkus tipis di atas SQLite. Thread-safe dipanggil dari satu thread."""

    def __init__(self, db_path: Optional[Path] = None):
        self.path = db_path or (default_data_dir() / "library.db")
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """Tambah kolom baru pada database lama bila belum ada."""
        cols = {r["name"] for r in
                self.conn.execute("PRAGMA table_info(photos)").fetchall()}
        for name, decl in _PHOTO_MIGRATIONS.items():
            if name not in cols:
                self.conn.execute(
                    f"ALTER TABLE photos ADD COLUMN {name} {decl}")
        # Index pada kolom yang mungkin baru ditambahkan (setelah migrasi).
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photos_source ON photos(source)")

    def close(self):
        self.conn.close()

    # ---- tampungan hapus (persisten) ---------------------------------
    def staged_ids(self) -> set:
        return {r["photo_id"] for r in
                self.conn.execute("SELECT photo_id FROM staged_items").fetchall()}

    def set_staged(self, ids, staged: bool):
        rows = [(int(i),) for i in ids]
        if not rows:
            return
        if staged:
            self.conn.executemany(
                "INSERT OR IGNORE INTO staged_items (photo_id) VALUES (?)", rows)
        else:
            self.conn.executemany(
                "DELETE FROM staged_items WHERE photo_id = ?", rows)
        self.conn.commit()

    def clear_staged(self):
        self.conn.execute("DELETE FROM staged_items")
        self.conn.commit()

    def reset_index(self):
        """Kosongkan seluruh data indeks (foto, tag, album, orang, wajah).

        File foto/video di disk TIDAK terpengaruh — hanya indeks aplikasi
        yang dihapus. Folder yang dipantau (disimpan di QSettings) tetap.
        """
        for table in ("album_items", "photo_tags", "faces", "staged_items",
                      "albums", "tags", "persons", "photos"):
            self.conn.execute(f"DELETE FROM {table}")
        # Reset penghitung AUTOINCREMENT bila ada.
        try:
            self.conn.execute("DELETE FROM sqlite_sequence")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()
        self.conn.execute("VACUUM")

    def _under(self, path: str, base_norm: str) -> bool:
        import os
        p = os.path.normcase(os.path.abspath(path))
        return p == base_norm or p.startswith(base_norm + os.sep)

    def counts_by_folder(self, folders: list[str]) -> dict[str, int]:
        """Jumlah media terindeks di bawah tiap folder (satu kali baca)."""
        import os
        bases = {f: os.path.normcase(os.path.abspath(f)) for f in folders}
        counts = {f: 0 for f in folders}
        for r in self.conn.execute("SELECT path FROM photos").fetchall():
            for f, base in bases.items():
                if self._under(r["path"], base):
                    counts[f] += 1
                    break
        return counts

    def delete_under_path(self, folder: str) -> int:
        """Hapus record media yang berada di bawah folder tertentu.

        File di disk tidak dihapus — hanya indeksnya. FK ON DELETE CASCADE
        otomatis membersihkan tag/album/wajah terkait.
        """
        import os
        base = os.path.normcase(os.path.abspath(folder))
        ids = [r["id"] for r in
               self.conn.execute("SELECT id, path FROM photos").fetchall()
               if self._under(r["path"], base)]
        for pid in ids:
            self.conn.execute("DELETE FROM photos WHERE id = ?", (pid,))
        # Bersihkan orang tanpa wajah tersisa.
        self.conn.execute(
            "DELETE FROM persons WHERE id NOT IN "
            "(SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)")
        self.conn.commit()
        return len(ids)

    # ---- photos -------------------------------------------------------
    def get_photo_mtime(self, path: str) -> Optional[float]:
        row = self.conn.execute(
            "SELECT mtime FROM photos WHERE path = ?", (path,)
        ).fetchone()
        return row["mtime"] if row else None

    def upsert_photo(self, data: dict) -> int:
        """Sisipkan atau perbarui satu foto berdasarkan path. Kembalikan id."""
        data = {**data}
        data.setdefault("media_type", "photo")  # kolom NOT NULL
        cols = ("path", "filename", "size", "date_taken", "date_source",
                "width", "height", "phash", "mtime", "media_type",
                "duration", "source", "lat", "lon")
        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "path")
        cur = self.conn.execute(
            f"INSERT INTO photos ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT(path) DO UPDATE SET {updates}",
            tuple(data.get(c) for c in cols),
        )
        if cur.lastrowid:
            row = self.conn.execute(
                "SELECT id FROM photos WHERE path = ?", (data["path"],)
            ).fetchone()
            return row["id"]
        return cur.lastrowid

    def ensure_source(self, path: str, source: str, media_type: str):
        """Isi source/media_type untuk record lama yang belum punya (cepat)."""
        self.conn.execute(
            "UPDATE photos SET source = ?, media_type = ? "
            "WHERE path = ? AND (source IS NULL OR source = '')",
            (source, media_type, path),
        )

    def update_path(self, photo_id: int, new_path: str):
        self.conn.execute(
            "UPDATE photos SET path = ?, filename = ? WHERE id = ?",
            (new_path, Path(new_path).name, photo_id),
        )

    def remove_missing(self, existing_paths: set[str]) -> int:
        """Hapus record foto yang file-nya tidak ada di set path tertentu."""
        rows = self.conn.execute("SELECT id, path FROM photos").fetchall()
        gone = [r["id"] for r in rows if r["path"] not in existing_paths]
        for pid in gone:
            self.conn.execute("DELETE FROM photos WHERE id = ?", (pid,))
        return len(gone)

    def set_rating(self, photo_id: int, rating: int):
        self.conn.execute(
            "UPDATE photos SET rating = ? WHERE id = ?", (rating, photo_id)
        )
        self.conn.commit()

    def delete_photo(self, photo_id: int):
        self.conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        self.conn.commit()

    def query_photos(
        self,
        text: str = "",
        min_rating: int = 0,
        rating_exact: Optional[int] = None,
        tag: str = "",
        source: str = "",
        media_type: str = "",
        album_id: int = 0,
        person_id: int = 0,
        has_gps: bool = False,
        ids: Optional[list] = None,
        folder: str = "",
        exclude_staged: bool = True,
        order_by: str = "date_taken DESC",
    ) -> list[sqlite3.Row]:
        sql = "SELECT DISTINCT p.* FROM photos p"
        params: list = []
        where = []
        if exclude_staged:
            where.append(f"p.id {_NS}")
        if has_gps:
            where.append("p.lat IS NOT NULL AND p.lon IS NOT NULL")
        if ids is not None:
            if not ids:
                return []
            where.append("p.id IN (%s)" % ",".join("?" for _ in ids))
            params += list(ids)
        if tag:
            sql += (" JOIN photo_tags pt ON pt.photo_id = p.id"
                    " JOIN tags t ON t.id = pt.tag_id")
            where.append("t.name = ?")
            params.append(tag)
        if album_id:
            sql += " JOIN album_items ai ON ai.photo_id = p.id"
            where.append("ai.album_id = ?")
            params.append(album_id)
        if person_id:
            sql += " JOIN faces f ON f.photo_id = p.id"
            where.append("f.person_id = ?")
            params.append(person_id)
        if text:
            where.append("(p.filename LIKE ? OR p.date_taken LIKE ?)")
            params += [f"%{text}%", f"%{text}%"]
        if min_rating > 0:
            where.append("p.rating >= ?")
            params.append(min_rating)
        if rating_exact is not None:
            where.append("p.rating = ?")
            params.append(rating_exact)
        if source:
            where.append("p.source = ?")
            params.append(source)
        if media_type:
            where.append("p.media_type = ?")
            params.append(media_type)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order_by}"
        rows = self.conn.execute(sql, params).fetchall()
        if folder:
            import os
            base = os.path.normcase(os.path.abspath(folder))
            rows = [r for r in rows if self._under(r["path"], base)]
        return rows

    # ---- lokasi / GPS ------------------------------------------------
    def gps_count(self) -> int:
        r = self.conn.execute(
            f"SELECT COUNT(*) c FROM photos WHERE lat IS NOT NULL AND id {_NS}"
        ).fetchone()
        return r["c"]

    def photos_with_gps(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, path, filename, lat, lon, date_taken "
            f"FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL AND id {_NS}"
        ).fetchall()

    def geocache_get(self, key: str) -> Optional[str]:
        r = self.conn.execute(
            "SELECT name FROM geocache WHERE key = ?", (key,)).fetchone()
        return r["name"] if r else None

    def geocache_set(self, key: str, name: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO geocache (key, name) VALUES (?, ?)",
            (key, name))
        self.conn.commit()

    def source_counts(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT COALESCE(source, 'lainnya') AS s, COUNT(*) AS c "
            f"FROM photos WHERE id {_NS} GROUP BY s ORDER BY c DESC"
        ).fetchall()
        return [(r["s"], r["c"]) for r in rows]

    def media_counts(self) -> dict:
        rows = self.conn.execute(
            "SELECT media_type AS t, COUNT(*) AS c FROM photos "
            f"WHERE id {_NS} GROUP BY t"
        ).fetchall()
        return {r["t"]: r["c"] for r in rows}

    def all_with_phash(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, path, filename, size, phash, width, height "
            f"FROM photos WHERE phash IS NOT NULL AND id {_NS} ORDER BY phash"
        ).fetchall()

    # ---- tags ---------------------------------------------------------
    def add_tag(self, photo_id: int, name: str):
        name = name.strip()
        if not name:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,)
        )
        tag = self.conn.execute(
            "SELECT id FROM tags WHERE name = ?", (name,)
        ).fetchone()
        self.conn.execute(
            "INSERT OR IGNORE INTO photo_tags (photo_id, tag_id) VALUES (?, ?)",
            (photo_id, tag["id"]),
        )
        self.conn.commit()

    def remove_tag(self, photo_id: int, name: str):
        tag = self.conn.execute(
            "SELECT id FROM tags WHERE name = ?", (name,)
        ).fetchone()
        if tag:
            self.conn.execute(
                "DELETE FROM photo_tags WHERE photo_id = ? AND tag_id = ?",
                (photo_id, tag["id"]),
            )
            self.conn.commit()

    def tags_for(self, photo_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT t.name FROM tags t JOIN photo_tags pt ON pt.tag_id = t.id "
            "WHERE pt.photo_id = ? ORDER BY t.name",
            (photo_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def all_tags(self) -> list[str]:
        rows = self.conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    # ---- albums -------------------------------------------------------
    def create_album(self, name: str) -> int:
        from datetime import datetime
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO albums (name, created) VALUES (?, ?)",
            (name.strip(), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM albums WHERE name = ?", (name.strip(),)
        ).fetchone()
        return row["id"] if row else cur.lastrowid

    def rename_album(self, album_id: int, new_name: str):
        self.conn.execute(
            "UPDATE albums SET name = ? WHERE id = ?", (new_name.strip(), album_id))
        self.conn.commit()

    def delete_album(self, album_id: int):
        self.conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
        self.conn.commit()

    def add_to_album(self, album_id: int, photo_ids: Iterable[int]):
        self.conn.executemany(
            "INSERT OR IGNORE INTO album_items (album_id, photo_id) VALUES (?, ?)",
            [(album_id, pid) for pid in photo_ids],
        )
        self.conn.commit()

    def remove_from_album(self, album_id: int, photo_ids: Iterable[int]):
        self.conn.executemany(
            "DELETE FROM album_items WHERE album_id = ? AND photo_id = ?",
            [(album_id, pid) for pid in photo_ids],
        )
        self.conn.commit()

    def albums_with_counts(self) -> list[tuple[int, str, int]]:
        rows = self.conn.execute(
            "SELECT a.id, a.name, COUNT(ai.photo_id) AS c FROM albums a "
            "LEFT JOIN album_items ai ON ai.album_id = a.id "
            f"AND ai.photo_id {_NS} "
            "GROUP BY a.id ORDER BY a.name"
        ).fetchall()
        return [(r["id"], r["name"], r["c"]) for r in rows]

    # ---- faces & persons ---------------------------------------------
    def needs_face_scan(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, path FROM photos "
            f"WHERE faces_done = 0 AND media_type = 'photo' AND id {_NS}"
        ).fetchall()

    def add_face(self, photo_id: int, box: tuple, embedding: bytes,
                 person_id: Optional[int] = None) -> int:
        x, y, w, h = box
        cur = self.conn.execute(
            "INSERT INTO faces (photo_id, person_id, x, y, w, h, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (photo_id, person_id, int(x), int(y), int(w), int(h), embedding),
        )
        return cur.lastrowid

    def mark_faces_done(self, photo_id: int):
        self.conn.execute(
            "UPDATE photos SET faces_done = 1 WHERE id = ?", (photo_id,))

    def create_person(self, name: Optional[str] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO persons (name) VALUES (?)", (name,))
        self.conn.commit()
        return cur.lastrowid

    def rename_person(self, person_id: int, name: str):
        self.conn.execute(
            "UPDATE persons SET name = ? WHERE id = ?", (name.strip(), person_id))
        self.conn.commit()

    def assign_face_person(self, face_id: int, person_id: int):
        self.conn.execute(
            "UPDATE faces SET person_id = ? WHERE id = ?", (person_id, face_id))
        self.conn.commit()

    def all_faces(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, photo_id, person_id, x, y, w, h, embedding FROM faces"
        ).fetchall()

    def unassigned_faces(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, photo_id, x, y, w, h, embedding FROM faces "
            "WHERE person_id IS NULL"
        ).fetchall()

    def persons_with_counts(self) -> list[tuple[int, Optional[str], int]]:
        rows = self.conn.execute(
            "SELECT pe.id, pe.name, COUNT(f.id) AS c FROM persons pe "
            f"JOIN faces f ON f.person_id = pe.id AND f.photo_id {_NS} "
            "GROUP BY pe.id HAVING c > 0 ORDER BY (pe.name IS NULL), c DESC"
        ).fetchall()
        return [(r["id"], r["name"], r["c"]) for r in rows]

    def person_cover_face(self, person_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT f.*, p.path FROM faces f JOIN photos p ON p.id = f.photo_id "
            "WHERE f.person_id = ? LIMIT 1", (person_id,)
        ).fetchone()

    def faces_for_photo(self, photo_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT f.*, pe.name AS person_name FROM faces f "
            "LEFT JOIN persons pe ON pe.id = f.person_id "
            "WHERE f.photo_id = ?", (photo_id,)
        ).fetchall()

    def clear_faces(self):
        """Hapus semua data wajah & orang (untuk pindai ulang)."""
        self.conn.execute("DELETE FROM faces")
        self.conn.execute("DELETE FROM persons")
        self.conn.execute("UPDATE photos SET faces_done = 0")
        self.conn.commit()

    def commit(self):
        self.conn.commit()
