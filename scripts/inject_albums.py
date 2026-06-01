"""Inject ALBUM + ISINYA (foto anggota) langsung ke library.db.

Default target : E:\\photo-organizer\\data\\library.db
Sumber album   : E:\\_ORGANIZE_LOG\\organize_manifest.csv  (From -> To)

Album diambil dari nama folder LAMA bermakna terdekat (melompati folder
generik, folder bertanggal, cache, WhatsApp, aset ikon/app, backup-dump).
Foto dicocokkan ke tabel `photos` lewat kolom `path` (harus sudah terindeks).

Pakai:
  python inject_albums.py                 # backup -> reset album -> inject
  python inject_albums.py --dry           # pratinjau saja (tidak menulis)
  python inject_albums.py --keep          # jangan hapus album lama (tambah saja)
  python inject_albums.py --min 6         # hanya album berisi >= 6 foto
  python inject_albums.py --db "<path>"   # target DB lain
"""
from __future__ import annotations
import argparse, csv, os, re, shutil, sqlite3, sys
from datetime import datetime

MANIFEST = r"E:\_ORGANIZE_LOG\organize_manifest.csv"
DEFAULT_DB = r"E:\photo-organizer\data\library.db"

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
DATE_RE = re.compile(r"^\d{1,4}([-_./ ]\d{1,4}){0,2}$")
SOURCE_ROOTS = {"aa", "backup-14-07-25", "backup-22-01-26", "me", "media", "yona", "dcim"}
NAME_CONTAINS = ("whatsapp", "thumbnail", "sticker", "cache", "appicon",
                 "appiconset", "drawable", "mipmap", ".xcassets", "yowhatsapp",
                 "gbwhatsapp", "telegram", "backup", "crop", "status",
                 "screenrecord", "camscanner", "shareit", "xrecorder")
PATH_CONTAINS = (".appiconset", ".xcassets", "\\assets\\", "appicon",
                 "drawable", "mipmap", "node_modules", "\\help\\", "\\res\\",
                 "tema ppt", "\\icons\\", "\\icon\\", "ta yona")


def album_from_old(old_path: str):
    low_path = old_path.lower()
    if any(tok in low_path for tok in PATH_CONTAINS):
        return None
    folders = old_path.split("\\")[1:-1]   # drop drive & filename
    for name in reversed(folders):
        low = name.strip().lower()
        if (not low or low in GENERIC or low in SOURCE_ROOTS
                or DATE_RE.match(low) or len(low) <= 2 or low.isdigit()
                or any(tok in low for tok in NAME_CONTAINS)):
            continue
        return name.strip()
    return None


def load_albums(min_count):
    by_album = {}
    with open(MANIFEST, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            old = row.get("From") or row.get("OriginalPath")
            new = row.get("To") or row.get("MovedTo")
            if not old or not new:
                continue
            alb = album_from_old(old)
            if alb:
                by_album.setdefault(alb, set()).add(os.path.normcase(new))
    return {a: s for a, s in by_album.items() if len(s) >= min_count}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--min", type=int, default=4)
    ap.add_argument("--dry", action="store_true", help="pratinjau saja")
    ap.add_argument("--keep", action="store_true", help="jangan reset album lama")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print("DB tidak ditemukan:", args.db); sys.exit(1)
    if not os.path.exists(MANIFEST):
        print("Manifest tidak ditemukan:", MANIFEST); sys.exit(1)

    by_album = load_albums(args.min)
    total_paths = sum(len(s) for s in by_album.values())
    print(f"Album unik   : {len(by_album)} (min {args.min} foto)")
    print(f"Foto ber-album: {total_paths}")

    con = sqlite3.connect(args.db, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    con.row_factory = sqlite3.Row
    idx = {os.path.normcase(r["path"]): r["id"]
           for r in con.execute("SELECT id, path FROM photos")}
    print(f"DB photos    : {len(idx)} di {args.db}")

    plan = []   # (album, [photo_id,...])
    for alb, paths in sorted(by_album.items(), key=lambda kv: -len(kv[1])):
        ids = [idx[p] for p in paths if p in idx]
        if ids:
            plan.append((alb, ids))
    matched = sum(len(ids) for _, ids in plan)
    print(f"Album akan dibuat: {len(plan)} | keanggotaan: {matched}")
    print("\n--- 20 album terbesar ---")
    for alb, ids in plan[:20]:
        print(f"  {alb[:45]:<45} {len(ids):>5}")

    if args.dry:
        print("\n(DRY — tidak menulis apa pun.)")
        con.close(); return

    # backup DB
    bak = args.db + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(args.db, bak)
    print(f"\nBackup DB -> {bak}")

    if not args.keep:
        con.execute("DELETE FROM album_items")
        con.execute("DELETE FROM albums")
        print("Album lama dihapus (reset).")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created = added = 0
    for alb, ids in plan:
        con.execute("INSERT OR IGNORE INTO albums (name, created) VALUES (?, ?)", (alb, now))
        aid = con.execute("SELECT id FROM albums WHERE name = ?", (alb,)).fetchone()["id"]
        before = con.total_changes
        con.executemany(
            "INSERT OR IGNORE INTO album_items (album_id, photo_id) VALUES (?, ?)",
            [(aid, pid) for pid in ids])
        added += con.total_changes - before
        created += 1
    con.commit()

    n_alb = con.execute("SELECT COUNT(*) c FROM albums").fetchone()["c"]
    n_item = con.execute("SELECT COUNT(*) c FROM album_items").fetchone()["c"]
    con.close()
    print(f"\nSELESAI. Album: {created} dibuat | keanggotaan ditambah: {added}")
    print(f"DB sekarang: {n_alb} album, {n_item} keanggotaan album.")


if __name__ == "__main__":
    main()
