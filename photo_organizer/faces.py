"""Deteksi & pengenalan wajah memakai model OpenCV (YuNet + SFace).

- YuNet  : deteksi wajah + 5 titik landmark.
- SFace  : ekstraksi embedding 128-dimensi untuk membandingkan identitas.

Embedding disimpan sebagai bytes float32. Pengelompokan (orang yang sama)
dilakukan dengan union-find berbasis kemiripan kosinus.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np

DET_MODEL = "face_detection_yunet_2023mar.onnx"
REC_MODEL = "face_recognition_sface_2021dec.onnx"

# Ambang kemiripan kosinus SFace: >= 0.363 dianggap orang yang sama.
SAME_PERSON_COSINE = 0.363
# Hanya proses wajah dengan skor deteksi & ukuran memadai.
MIN_DET_SCORE = 0.7
MIN_FACE_PX = 40


def models_dir() -> Path:
    """Lokasi folder model, mendukung mode PyInstaller (sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "models"
    return Path(__file__).resolve().parent.parent / "models"


def models_available() -> bool:
    d = models_dir()
    return (d / DET_MODEL).exists() and (d / REC_MODEL).exists()


def _imread_unicode(path: str):
    """cv2.imread yang aman untuk path berkarakter non-ASCII (Windows)."""
    import cv2
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


class FaceAnalyzer:
    """Pembungkus detektor + pengenal wajah OpenCV (dimuat sekali)."""

    def __init__(self):
        import cv2
        d = models_dir()
        self.detector = cv2.FaceDetectorYN.create(
            str(d / DET_MODEL), "", (320, 320),
            score_threshold=MIN_DET_SCORE)
        self.recognizer = cv2.FaceRecognizerSF.create(
            str(d / REC_MODEL), "")

    def analyze(self, image_path: str) -> list[dict]:
        """Deteksi wajah pada sebuah gambar.

        Mengembalikan list dict: {box: (x,y,w,h), embedding: bytes}.
        """
        img = _imread_unicode(image_path)
        if img is None:
            return []
        h, w = img.shape[:2]
        # Batasi sisi terpanjang agar deteksi cepat & stabil.
        scale = 1.0
        max_side = 1024
        if max(h, w) > max_side:
            scale = max_side / max(h, w)
            import cv2
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            h, w = img.shape[:2]

        self.detector.setInputSize((w, h))
        try:
            _n, faces = self.detector.detect(img)
        except Exception:
            return []
        if faces is None:
            return []

        out = []
        for face in faces:
            x, y, fw, fh = face[0:4]
            if fw < MIN_FACE_PX or fh < MIN_FACE_PX:
                continue
            try:
                aligned = self.recognizer.alignCrop(img, face)
                feat = self.recognizer.feature(aligned)  # shape (1,128)
            except Exception:
                continue
            emb = np.asarray(feat, dtype=np.float32).reshape(-1)
            # Simpan box dalam koordinat gambar asli.
            inv = 1.0 / scale
            box = (x * inv, y * inv, fw * inv, fh * inv)
            out.append({"box": box, "embedding": emb.tobytes()})
        return out


def _normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def cluster_faces(face_rows: list, threshold: float = SAME_PERSON_COSINE
                  ) -> dict[int, int]:
    """Kelompokkan wajah menjadi orang.

    `face_rows` : list record berisi minimal 'id' dan 'embedding' (bytes).
    Mengembalikan dict {face_id: cluster_index}.
    """
    ids = []
    vecs = []
    for r in face_rows:
        emb = r["embedding"]
        if not emb:
            continue
        v = np.frombuffer(emb, dtype=np.float32)
        if v.size == 0:
            continue
        ids.append(r["id"])
        vecs.append(v)
    n = len(ids)
    if n == 0:
        return {}

    mat = _normalize(np.vstack(vecs))
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Matriks kemiripan kosinus penuh (vektor sudah dinormalkan -> dot product).
    sim = mat @ mat.T
    for i in range(n):
        # Bandingkan hanya ke indeks setelahnya untuk efisiensi.
        js = np.where(sim[i, i + 1:] >= threshold)[0]
        for j in js:
            union(i, i + 1 + int(j))

    clusters: dict[int, int] = {}
    label_map: dict[int, int] = {}
    next_label = 0
    for i in range(n):
        root = find(i)
        if root not in label_map:
            label_map[root] = next_label
            next_label += 1
        clusters[ids[i]] = label_map[root]
    return clusters
