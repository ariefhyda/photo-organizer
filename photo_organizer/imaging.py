"""Utilitas pemrosesan gambar: EXIF, thumbnail, dan perceptual hash."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

import imagehash
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.ExifTags import TAGS

# Jangan gagalkan gambar beresolusi sangat besar (mis. panorama) dengan
# DecompressionBombError; aplikasi lokal jadi izinkan ukuran besar.
Image.MAX_IMAGE_PIXELS = None

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
                 ".webp", ".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".3gp",
             ".webm", ".mpg", ".mpeg", ".flv"}

THUMB_SIZE = (220, 220)


def is_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXT


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXT


def is_media(path: Path) -> bool:
    return is_image(path) or is_video(path)


def _exif_dict(img: Image.Image) -> dict:
    try:
        raw = img.getexif()
    except Exception:
        return {}
    out = {}
    for tag_id, value in raw.items():
        out[TAGS.get(tag_id, tag_id)] = value
    return out


def _extract_gps(img: Image.Image) -> tuple:
    """Ambil (lat, lon) desimal dari EXIF GPSInfo, atau (None, None)."""
    try:
        gps = img.getexif().get_ifd(0x8825)   # 0x8825 = GPSInfo
    except Exception:
        return None, None
    if not gps:
        return None, None

    def to_deg(coord, ref) -> Optional[float]:
        try:
            d, m, s = (float(coord[0]), float(coord[1]), float(coord[2]))
        except (TypeError, ValueError, IndexError):
            return None
        val = d + m / 60.0 + s / 3600.0
        ref = (ref.decode() if isinstance(ref, bytes) else str(ref)).strip().upper()
        if ref in ("S", "W"):
            val = -val
        return val

    lat = to_deg(gps.get(2), gps.get(1))
    lon = to_deg(gps.get(4), gps.get(3))
    if lat is None or lon is None:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None, None
    return round(lat, 6), round(lon, 6)


def extract_metadata(path: Path) -> dict:
    """Ambil metadata sebuah gambar.

    Mengembalikan dict berisi date_taken, date_source, width, height, phash.
    Tidak melempar error untuk file yang gagal dibaca (mengembalikan fallback).
    """
    result = {
        "date_taken": None,
        "date_source": "mtime",
        "width": None,
        "height": None,
        "phash": None,
        "lat": None,
        "lon": None,
    }
    try:
        with Image.open(path) as img:
            # GPS dibaca dari gambar asli (sebelum transpose).
            result["lat"], result["lon"] = _extract_gps(img)
            img = ImageOps.exif_transpose(img)
            result["width"], result["height"] = img.size

            exif = _exif_dict(img)
            dt_str = (exif.get("DateTimeOriginal")
                      or exif.get("DateTimeDigitized")
                      or exif.get("DateTime"))
            if dt_str:
                try:
                    dt = datetime.strptime(str(dt_str), "%Y:%m:%d %H:%M:%S")
                    result["date_taken"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                    result["date_source"] = "exif"
                except ValueError:
                    pass

            try:
                small = img.convert("RGB")
                result["phash"] = str(imagehash.phash(small))
            except Exception:
                pass
    except Exception:        # noqa: BLE001 - file rusak/format aneh: pakai fallback
        pass

    if not result["date_taken"]:
        try:
            mtime = path.stat().st_mtime
            result["date_taken"] = datetime.fromtimestamp(mtime).strftime(
                "%Y-%m-%d %H:%M:%S")
        except OSError:
            pass
    return result


def _thumb_key(path: Path, mtime: float) -> str:
    h = hashlib.sha1(f"{path}:{mtime}".encode("utf-8")).hexdigest()
    return h + ".jpg"


def extract_video_metadata(path: Path) -> dict:
    """Ambil dimensi & durasi video memakai OpenCV."""
    result = {"date_taken": None, "date_source": "mtime",
              "width": None, "height": None, "phash": None, "duration": None}
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            result["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
            result["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if fps > 0 and frames > 0:
                result["duration"] = round(frames / fps, 1)
        cap.release()
    except Exception:
        pass
    from datetime import datetime
    try:
        mtime = path.stat().st_mtime
        result["date_taken"] = datetime.fromtimestamp(mtime).strftime(
            "%Y-%m-%d %H:%M:%S")
    except OSError:
        pass
    return result


def _make_video_thumb(path: Path, thumb_path: Path) -> bool:
    """Ambil satu frame video sebagai thumbnail. True bila berhasil."""
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            cap.release()
            return False
        # Ambil frame di sekitar 1 detik / awal video.
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        target = min(15, int(frames) - 1) if frames > 1 else 0
        if target > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return False
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        # Tambah segitiga "play" agar mudah dikenali sebagai video.
        _draw_play_badge(img)
        img.save(thumb_path, "JPEG", quality=82)
        return True
    except Exception:
        return False


def _draw_play_badge(img: Image.Image):
    from PIL import ImageDraw
    w, h = img.size
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy, r = w // 2, h // 2, max(14, min(w, h) // 7)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 130))
    s = r // 2
    d.polygon([(cx - s // 2, cy - s), (cx - s // 2, cy + s), (cx + s, cy)],
              fill=(255, 255, 255, 230))


def cached_thumbnail(path: Path, cache_dir: Path) -> Optional[Path]:
    """Kembalikan path thumbnail HANYA bila sudah ada di cache (tanpa generate)."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    thumb_path = cache_dir / _thumb_key(path, mtime)
    return thumb_path if thumb_path.exists() else None


def get_thumbnail(path: Path, cache_dir: Path) -> Optional[Path]:
    """Hasilkan (atau ambil dari cache) thumbnail JPEG. Kembalikan path-nya."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = cache_dir / _thumb_key(path, mtime)
    if thumb_path.exists():
        return thumb_path
    if is_video(path):
        return thumb_path if _make_video_thumb(path, thumb_path) else None
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=82)
        return thumb_path
    except Exception:        # noqa: BLE001
        return None


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Jarak Hamming antara dua perceptual hash (string hex)."""
    try:
        return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
    except Exception:
        return 999
