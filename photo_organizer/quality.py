"""Heuristik deteksi gambar 'tidak penting' (buram/gelap/terang/datar).

Memakai OpenCV. Tidak ada AI berat — hanya metrik cepat:
- Ketajaman  : varians Laplacian (rendah = buram)
- Kecerahan  : rata-rata abu-abu (sangat rendah/tinggi = gelap/terang)
- Detail     : standar deviasi abu-abu (rendah = datar/kosong)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Ambang default (bisa disesuaikan). Dihitung pada gambar yang diperkecil ~480px.
BLUR_VAR = 60.0      # < ini -> buram
DARK_MEAN = 35.0     # < ini -> terlalu gelap
BRIGHT_MEAN = 225.0  # > ini -> terlalu terang
FLAT_STD = 14.0      # < ini -> datar/kosong (mis. tutup lensa, layar polos)

REASONS = ("Buram", "Terlalu gelap", "Terlalu terang", "Datar/kosong")


def _read_gray(path: str):
    """Baca gambar sebagai grayscale (tahan path non-ASCII di Windows)."""
    import cv2
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None
    if img is None:
        return None
    h, w = img.shape[:2]
    m = max(h, w)
    if m > 480:
        s = 480.0 / m
        img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))))
    return img


def analyze_image(
    path: str,
    blur_var: float = BLUR_VAR,
    dark_mean: float = DARK_MEAN,
    bright_mean: float = BRIGHT_MEAN,
    flat_std: float = FLAT_STD,
) -> list[str]:
    """Kembalikan daftar alasan mengapa gambar dianggap 'tidak penting'.

    Kosong = gambar tampak normal/penting.
    """
    import cv2
    img = _read_gray(path)
    if img is None:
        return []
    mean = float(img.mean())
    std = float(img.std())
    lap = float(cv2.Laplacian(img, cv2.CV_64F).var())

    reasons: list[str] = []
    if lap < blur_var:
        reasons.append("Buram")
    if mean < dark_mean:
        reasons.append("Terlalu gelap")
    elif mean > bright_mean:
        reasons.append("Terlalu terang")
    if std < flat_std:
        reasons.append("Datar/kosong")
    return reasons
