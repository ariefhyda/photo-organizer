"""Deteksi foto duplikat / mirip berdasarkan perceptual hash."""

from __future__ import annotations

from .imaging import hamming_distance


def find_duplicate_groups(rows: list, threshold: int = 5) -> list[list[dict]]:
    """Kelompokkan foto yang mirip berdasarkan jarak perceptual hash.

    `rows` adalah daftar record (punya 'id', 'path', 'phash', 'size', dst).
    `threshold` = jarak Hamming maksimum agar dianggap duplikat
                  (0 = identik, makin besar makin longgar).
    Mengembalikan daftar grup; tiap grup berisi >= 2 foto mirip,
    diurutkan dengan file terbesar di depan (kandidat "asli").
    """
    items = [dict(r) for r in rows if r["phash"]]
    n = len(items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Bandingkan pasangan. Rows sudah diurutkan berdasarkan phash sehingga
    # foto mirip cenderung berdekatan; kita pakai jendela geser untuk efisiensi
    # plus perbandingan penuh saat dataset kecil.
    if n <= 1500:
        for i in range(n):
            for j in range(i + 1, n):
                if hamming_distance(items[i]["phash"], items[j]["phash"]) <= threshold:
                    union(i, j)
    else:
        window = 40
        for i in range(n):
            for j in range(i + 1, min(i + 1 + window, n)):
                if hamming_distance(items[i]["phash"], items[j]["phash"]) <= threshold:
                    union(i, j)

    groups: dict[int, list[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i])

    result = []
    for members in groups.values():
        if len(members) >= 2:
            members.sort(key=lambda m: (m.get("size") or 0), reverse=True)
            result.append(members)
    result.sort(key=len, reverse=True)
    return result
