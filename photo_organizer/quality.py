"""Heuristik deteksi gambar 'tidak penting' (buram/gelap/terang/datar).

Memakai PIL + NumPy (bukan OpenCV) agar tahan terhadap berbagai format
(termasuk WebP animasi, JPEG/PNG dengan profil bermasalah) tanpa memunculkan
spam peringatan dekoder native.

Metrik cepat pada gambar grayscale yang diperkecil ~480px:
- Ketajaman : varians Laplacian (rendah = buram)
- Kecerahan : rata-rata (sangat rendah/tinggi = gelap/terang)
- Detail    : standar deviasi (rendah = datar/kosong)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

# Gambar beresolusi sangat besar tidak digagalkan (panorama dsb.).
Image.MAX_IMAGE_PIXELS = None

# Ambang default (bisa disesuaikan).
BLUR_VAR = 60.0      # < ini -> buram
DARK_MEAN = 35.0     # < ini -> terlalu gelap
BRIGHT_MEAN = 225.0  # > ini -> terlalu terang
FLAT_STD = 14.0      # < ini -> datar/kosong

REASONS = ("Buram", "Terlalu gelap", "Terlalu terang", "Datar/kosong")


def _read_gray_array(path: str):
    """Baca gambar -> array grayscale (diperkecil). None bila gagal."""
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("L")
            w, h = im.size
            m = max(w, h)
            if m > 480:
                s = 480.0 / m
                im = im.resize((max(1, int(w * s)), max(1, int(h * s))))
            return np.asarray(im, dtype=np.float64)
    except Exception:        # noqa: BLE001 - file rusak/format aneh
        return None


def analyze_image(
    path: str,
    blur_var: float = BLUR_VAR,
    dark_mean: float = DARK_MEAN,
    bright_mean: float = BRIGHT_MEAN,
    flat_std: float = FLAT_STD,
) -> list[str]:
    """Kembalikan daftar alasan gambar dianggap 'tidak penting' (kosong = normal)."""
    g = _read_gray_array(path)
    if g is None or g.size == 0 or min(g.shape) < 3:
        return []
    mean = float(g.mean())
    std = float(g.std())
    # Laplacian diskret 3x3 pada piksel interior: [[0,1,0],[1,-4,1],[0,1,0]]
    lap = (-4.0 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1]
           + g[1:-1, :-2] + g[1:-1, 2:])
    lap_var = float(lap.var())

    reasons: list[str] = []
    if lap_var < blur_var:
        reasons.append("Buram")
    if mean < dark_mean:
        reasons.append("Terlalu gelap")
    elif mean > bright_mean:
        reasons.append("Terlalu terang")
    if std < flat_std:
        reasons.append("Datar/kosong")
    return reasons
