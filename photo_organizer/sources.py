"""Klasifikasi sumber media (kamera, WhatsApp, screenshot, dll.).

Deteksi berbasis heuristik dari jalur folder dan pola nama file. Tidak 100%
akurat, tapi menutup mayoritas kasus umum di perangkat Android/Windows.
"""

from __future__ import annotations

import re
from pathlib import Path

# Label tampilan untuk tiap kunci sumber.
SOURCE_LABELS = {
    "camera": "📷 Kamera",
    "whatsapp": "💬 WhatsApp",
    "screenshot": "🖼️ Screenshot",
    "telegram": "✈️ Telegram",
    "instagram": "📸 Instagram",
    "facebook": "👍 Facebook",
    "download": "⬇️ Download",
    "lainnya": "📁 Lainnya",
}

# Pola nama file khas.
_RE_WHATSAPP = re.compile(r"^(IMG|VID|AUD|PTT)-\d{8}-WA\d+", re.I)
_RE_SCREENSHOT = re.compile(r"^(screenshot|screen[ _-]?shot|scr_)", re.I)
_RE_CAMERA = re.compile(
    r"^(IMG_?\d{6,}|DSC[_F]?\d+|DSCN\d+|P\d{6,}|PXL_\d{8}|"
    r"\d{8}_\d{6}|VID_?\d{6,}|MVIMG)", re.I)


def classify(path: str) -> str:
    """Kembalikan kunci sumber untuk sebuah file media."""
    p = Path(path)
    name = p.name
    # Gabungkan komponen folder (lowercase) untuk pencocokan jalur.
    parts = [s.lower() for s in p.parts]
    joined = "/".join(parts)

    def in_path(*keys: str) -> bool:
        return any(k in joined for k in keys)

    # Urutan penting: yang paling spesifik dulu.
    if in_path("whatsapp") or _RE_WHATSAPP.match(name):
        return "whatsapp"
    if in_path("screenshot", "screenshots") or _RE_SCREENSHOT.match(name):
        return "screenshot"
    if in_path("telegram"):
        return "telegram"
    if in_path("instagram"):
        return "instagram"
    if in_path("facebook", "/fb/"):
        return "facebook"
    if in_path("/download", "downloads", "unduhan"):
        return "download"
    if in_path("dcim", "camera", "kamera") or _RE_CAMERA.match(name):
        return "camera"
    return "lainnya"


def label(key: str) -> str:
    return SOURCE_LABELS.get(key, key)
