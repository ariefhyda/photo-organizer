"""Hasilkan ikon aplikasi (assets/icon.png & assets/icon.ico).

Jalankan: python scripts/make_icon.py
Menggambar motif 'foto' (matahari + gunung) di atas kartu putih dengan latar
gradien aksen, lalu menyimpan PNG 256px dan ICO multi-ukuran.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = (108, 140, 255)      # #6c8cff
ACCENT2 = (138, 162, 255)     # gradien lebih terang
SUN = (255, 194, 75)          # #ffc24b
MTN = (60, 84, 170)           # gunung


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0], size[1]], radius, fill=255)
    return m


def make(px: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    # Latar gradien vertikal aksen.
    grad = Image.new("RGB", (1, px))
    for y in range(px):
        t = y / px
        grad.putpixel((0, y), tuple(
            int(ACCENT[i] + (ACCENT2[i] - ACCENT[i]) * t) for i in range(3)))
    grad = grad.resize((px, px))
    img.paste(grad, (0, 0), rounded_mask((px, px), int(px * 0.22)))

    d = ImageDraw.Draw(img)
    # Kartu foto putih.
    pad = int(px * 0.17)
    card = [pad, int(px * 0.22), px - pad, px - int(px * 0.22)]
    d.rounded_rectangle(card, int(px * 0.05), fill=(255, 255, 255, 255))

    cx0, cy0, cx1, cy1 = card
    cw, ch = cx1 - cx0, cy1 - cy0
    # Matahari.
    r = int(cw * 0.12)
    sx, sy = cx0 + int(cw * 0.26), cy0 + int(ch * 0.30)
    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=SUN)
    # Gunung (dua segitiga) menutup bagian bawah kartu.
    base = cy1 - int(ch * 0.04)
    d.polygon([(cx0 + int(cw * 0.10), base),
               (cx0 + int(cw * 0.42), cy0 + int(ch * 0.45)),
               (cx0 + int(cw * 0.66), base)], fill=MTN)
    d.polygon([(cx0 + int(cw * 0.40), base),
               (cx0 + int(cw * 0.70), cy0 + int(ch * 0.55)),
               (cx1 - int(cw * 0.06), base)], fill=ACCENT)
    return img


def main():
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(parents=True, exist_ok=True)
    big = make(1024)
    icon256 = big.resize((256, 256), Image.LANCZOS)
    icon256.save(out / "icon.png")
    icon256.save(out / "icon.ico",
                 sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                        (128, 128), (256, 256)])
    print("Ikon disimpan:", out / "icon.png", "&", out / "icon.ico")


if __name__ == "__main__":
    main()
