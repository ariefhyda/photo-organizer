"""Buat album di library.db berdasarkan struktur folder LAMA.

Sumber pemetaan: E:\\_ORGANIZE_LOG\\organize_manifest.csv  (From -> To)
  - From = lokasi lama foto (mis. E:\\MEDIA\\ALBUM\\G. Pundak\\VID.mp4)
  - To   = lokasi baru di E:\\FOTO\\YYYY\\YYYY-MM\\...

Album = nama folder LAMA bermakna terdekat (melompati folder generik &
folder bertanggal), mis. 'G. Pundak', 'Family', 'Peter kocheng'.

Pakai:
  python import_albums.py                 # DRY RUN (lihat daftar album)
  python import_albums.py --apply         # tulis album ke DB
  python import_albums.py --apply --db "C:\\path\\library.db"
"""
from __future__ import annotations
import argparse, csv, os, re, sqlite3, sys
from datetime import datetime

MANIFEST = r"E:\_ORGANIZE_LOG\organize_manifest.csv"
DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".photo_organizer", "library.db")

# Folder yang BUKAN nama album (generik / wadah / sumber root) -> dilewati.
GENERIC = {
    "camera", "dcim", "100andro", "100media", "101andro", "files", "file",
    "foto", "fotos", "photo", "photos", "images", "image", "img", "pics",
    "internal", "hp", "phone", "gallery", "galeri", "pictures", "picture",
    "download", "downloads", "unduhan", "whatsapp", "wa", "telegram", "tele",
    "screenshot", "screenshots", "tangkapan layar", "video", "videos",
    "recover", "recovery", "restored", "new folder", "untitled", "album",
    "albums", "edisi foto", "aa", "me", "media", "yona", "dcim",
    "backup-14-07-25", "backup-22-01-26", "sd", "card", "storage", "emulated",
    "0", "movies", "music", "documents", "saved", "sent", "received",
    "grid", "dan lain-lain", "lain-lain", "belum di tata", "crop-3x4",
    "instagram", "facebook", "fb", "messenger", "bbm", "line", "pin",
    "original file", "data", "moment", "canva", "rahasia", "private",
}
# pola folder bertanggal apa pun -> dilewati
# (2018, 2021-03, 2018-08-26, 20180826, 23-8-2019, 26-08-24, 8_2019, dst.)
DATE_RE = re.compile(r"^\d{1,4}([-_./ ]\d{1,4}){0,2}$")
SOURCE_ROOTS = {"aa", "backup-14-07-25", "backup-22-01-26", "me", "media", "yona", "dcim"}
# bila NAMA folder mengandung salah satu token ini -> bukan album
NAME_CONTAINS = ("whatsapp", "thumbnail", "sticker", "cache", "appicon",
                 "appiconset", "drawable", "mipmap", ".xcassets", "yowhatsapp",
                 "gbwhatsapp", "telegram", "backup", "crop", "status",
                 "screenrecord", "camscanner", "shareit", "xrecorder")
# bila JALUR LAMA mengandung salah satu token ini -> aset proyek/app, bukan foto
PATH_CONTAINS = (".appiconset", ".xcassets", "\\assets\\", "appicon",
                 "drawable", "mipmap", "node_modules", "\\help\\", "\\res\\",
                 "tema ppt", "\\icons\\", "\\icon\\", "ta yona")


def album_from_old(old_path: str) -> str | None:
    low_path = old_path.lower()
    if any(tok in low_path for tok in PATH_CONTAINS):
        return None
    parts = old_path.split("\\")
    folders = parts[1:-1]  # drop drive 'E:' dan filename
    for name in reversed(folders):
        low = name.strip().lower()
        if (not low or low in GENERIC or low in SOURCE_ROOTS
                or DATE_RE.match(low) or len(low) <= 2 or low.isdigit()
                or any(tok in low for tok in NAME_CONTAINS)):
            continue
        return name.strip()
    return None


def load_mapping():
    """Kembalikan list (new_path, album_name) dari manifest."""
    out = []
    with open(MANIFEST, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            old = row.get("From") or row.get("OriginalPath")
            new = row.get("To") or row.get("MovedTo")
            if not old or not new:
                continue
            alb = album_from_old(old)
            if alb:
                out.append((new, alb))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="tulis ke DB (default: dry run)")
    ap.add_argument("--reset", action="store_true",
                    help="hapus semua album lama dulu, lalu bangun ulang bersih")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--min", type=int, default=2, help="album minimal sekian foto (default 2)")
    args = ap.parse_args()

    mapping = load_mapping()
    # album -> set(new_path)
    by_album: dict[str, set] = {}
    for new, alb in mapping:
        by_album.setdefault(alb, set()).add(os.path.normcase(new))

    # buang album terlalu kecil
    by_album = {a: s for a, s in by_album.items() if len(s) >= args.min}
    print(f"Manifest    : {len(mapping)} foto punya album")
    print(f"Album unik  : {len(by_album)} (min {args.min} foto/album)")

    if not os.path.exists(args.db):
        print("DB tidak ditemukan:", args.db); sys.exit(1)
    con = sqlite3.connect(args.db, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.row_factory = sqlite3.Row
    # path(normcase) -> id
    idx = {os.path.normcase(r["path"]): r["id"]
           for r in con.execute("SELECT id, path FROM photos")}
    print(f"DB photos   : {len(idx)} terindeks di {args.db}")

    # hitung kecocokan
    rows_preview = []
    matched_total = 0
    for alb, paths in sorted(by_album.items(), key=lambda kv: -len(kv[1])):
        ids = [idx[p] for p in paths if p in idx]
        matched_total += len(ids)
        rows_preview.append((alb, len(paths), len(ids)))

    print(f"\nTotal foto ber-album di manifest : {sum(len(s) for s in by_album.values())}")
    print(f"Yang sudah ada di DB (cocok)     : {matched_total}")
    print("\n--- 30 album terbesar (album | foto di manifest | sudah di DB) ---")
    for alb, ntot, nmatch in rows_preview[:30]:
        print(f"  {alb[:40]:<40} {ntot:>6} {nmatch:>6}")

    # simpan daftar album ke CSV
    out_csv = r"E:\_ORGANIZE_LOG\album_mapping.csv"
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["Album", "FotoDiManifest", "SudahDiDB"])
        for alb, ntot, nmatch in rows_preview:
            w.writerow([alb, ntot, nmatch])
    print(f"\nDaftar lengkap album -> {out_csv}")

    if not args.apply:
        print("\n(DRY RUN — belum menulis apa pun. Tambah --apply untuk eksekusi.)")
        con.close(); return

    # APPLY
    if args.reset:
        con.execute("DELETE FROM album_items")
        con.execute("DELETE FROM albums")
        con.commit()
        print("\n(reset: album lama dihapus)")
    created = 0; added = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for alb, paths in by_album.items():
        ids = [idx[p] for p in paths if p in idx]
        if not ids:
            continue
        con.execute("INSERT OR IGNORE INTO albums (name, created) VALUES (?, ?)", (alb, now))
        aid = con.execute("SELECT id FROM albums WHERE name = ?", (alb,)).fetchone()["id"]
        before = con.total_changes
        con.executemany(
            "INSERT OR IGNORE INTO album_items (album_id, photo_id) VALUES (?, ?)",
            [(aid, pid) for pid in ids])
        added += con.total_changes - before
        created += 1
    con.commit(); con.close()
    print(f"\nAPPLIED. Album dibuat/dipakai: {created} | keanggotaan ditambah: {added}")


if __name__ == "__main__":
    main()
