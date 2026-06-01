# Photo Organizer

Aplikasi desktop (Windows) untuk mengorganisir koleksi foto. Dibuat dengan
Python + PySide6 (Qt) dan SQLite.

## Fitur

- **Foto & video** — galeri menampilkan foto *dan* video (MP4, MOV, MKV, dll.)
  dengan thumbnail frame video (berlabel ikon ▶). Durasi & dimensi video
  terbaca otomatis.
- **Sidebar navigasi** — jelajahi koleksi per kategori: Semua / Foto / Video,
  per **Sumber**, per **Album**, dan per **Orang**.
- **Pemisahan sumber otomatis** — media dikelompokkan jadi 📷 Kamera,
  💬 WhatsApp, 🖼️ Screenshot, ✈️ Telegram, ⬇️ Download, dll. berdasarkan pola
  folder & nama file.
- **Album** — buat album, masukkan foto/video (klik kanan → Tambahkan ke
  album), ganti nama / hapus album (klik dua kali album di sidebar).
- **Pengenalan wajah otomatis** — deteksi wajah (YuNet) lalu kelompokkan orang
  yang sama (SFace). Klik dua kali sebuah orang di sidebar untuk memberi nama;
  setelah itu cari semua foto orang tersebut dengan satu klik.
- **Susun berdasarkan tanggal/EXIF** — salin atau pindahkan media ke folder
  rapi berdasarkan tanggal (EXIF, fallback tanggal file), mis. `2024/2024-06`.
- **Deteksi & hapus duplikat** — perceptual hash menemukan foto identik/mirip,
  dengan **panel pratinjau** untuk membandingkan sebelum menghapus.
- **Tag, rating & pencarian** — bintang (0–5), tag, dan filter teks/rating/tag.
- **Ganti nama massal** — template seperti `Foto_{date}_{n:03}`.

## Menjalankan

```bat
REM Pertama kali: pasang dependensi
pip install -r requirements.txt

REM Jalankan
run.bat
```

Atau:

```bat
python -m photo_organizer
```

## Cara pakai singkat

1. Klik **➕ Tambah Folder** dan pilih folder berisi foto. Aplikasi memindai
   isinya (rekursif), membaca metadata, dan membuat thumbnail.
2. Galeri akan terisi. Klik foto untuk melihat detail, beri **rating** dengan
   bintang, dan tambah **tag** di panel kanan.
3. Gunakan kotak **Cari**, filter **Rating**, dan filter **Tag** untuk
   menyaring.
3. **Sidebar kiri** — klik kategori untuk menyaring galeri: Semua / Foto /
   Video, per Sumber (Kamera/WhatsApp/Screenshot/…), per Album, atau per Orang.
4. Tombol toolbar:
   - **📅 Susun per Tanggal** — menyusun media terpilih (atau semua yang tampil
     bila tidak ada yang dipilih) ke folder tujuan.
   - **🔍 Cari Duplikat** — menampilkan grup foto mirip + pratinjau.
   - **✏️ Ganti Nama Massal** — mengganti nama media terpilih dengan template.
   - **📚 Album Baru** — membuat album (media terpilih langsung dimasukkan).
   - **🙂 Pindai Wajah** — mendeteksi & mengelompokkan wajah. Setelah selesai,
     grup orang muncul di sidebar.
5. **Album**: pilih beberapa media → klik kanan → *Tambahkan ke album*. Klik
   dua kali album di sidebar untuk ganti nama / hapus.
6. **Orang**: jalankan *Pindai Wajah*, lalu klik dua kali grup orang di sidebar
   untuk memberi nama. Klik grup untuk melihat semua foto orang itu.

> Tip: bila tidak ada media yang diseleksi, operasi "Susun" dan "Ganti Nama"
> berlaku untuk **semua media yang sedang tampil** di galeri (sesuai filter).

### Pengenalan wajah — catatan

Fitur wajah memakai model OpenCV di folder **`models/`**
(`face_detection_yunet_*.onnx` dan `face_recognition_sface_*.onnx`). Folder ini
ikut dibundel saat build `.exe`. Pemindaian dilakukan lokal di perangkat —
tidak ada data yang dikirim ke internet. Pengelompokan otomatis tidak sempurna;
satu orang kadang terpecah jadi beberapa grup atau tercampur — penamaan manual
membantu memperbaikinya pada pindai berikutnya.

## Membuat build portable (.exe) untuk laptop lain

Jalankan:

```bat
build_exe.bat
```

Hasilnya **folder portable** di `dist\PhotoOrganizer\`. Untuk memakai di laptop
lain (Windows 64-bit, tanpa instal Python):

1. Salin seluruh folder `dist\PhotoOrganizer\` ke laptop tujuan.
2. Jalankan `PhotoOrganizer.exe` di dalamnya.

Data (database, thumbnail, pengaturan) disimpan **di dalam folder itu**
(`data\` + `photo_organizer.ini`), jadi aplikasi benar-benar portable —
pindahkan foldernya dan datamu ikut.

> Catatan: peta tertanam memakai **QtWebEngine** sehingga ukuran folder besar
> (~400–700MB) dan butuh internet untuk memuat peta. Build berformat `--onedir`
> (folder) karena paling andal untuk QtWebEngine.

## (Lama) Membuat file .exe (distribusi ke laptop lain)

Untuk menjalankan di laptop lain **tanpa instal Python**, build menjadi satu
file `.exe`:

```bat
build_exe.bat
```

Hasilnya: **`dist\PhotoOrganizer.exe`** — cukup salin file ini ke laptop lain
dan jalankan dengan klik dua kali.

Catatan:
- `.exe` ini untuk **Windows 64-bit**. Untuk macOS/Linux perlu build terpisah
  di OS tersebut.
- File berukuran besar (~80–200 MB) karena memuat Python + Qt di dalamnya.
- Saat pertama dibuka, exe `--onefile` butuh beberapa detik untuk
  mengekstrak diri. Bila ingin start lebih cepat, ganti `--onefile` menjadi
  `--onedir` di `build_exe.bat` (hasilnya satu folder, bukan satu file).
- Antivirus/SmartScreen kadang memperingatkan exe hasil PyInstaller yang belum
  ditandatangani — ini wajar; pilih "Run anyway" / "tetap jalankan".

## Penyimpanan data

Database dan cache thumbnail disimpan di `~/.photo_organizer/`
(mis. `C:\Users\<nama>\.photo_organizer\`). Menghapus folder ini akan mereset
indeks (file foto asli tidak terpengaruh).

## Catatan

- Penghapusan duplikat menghapus file **permanen** dari disk (bukan ke Recycle
  Bin). Periksa centang sebelum mengonfirmasi.
- Format didukung: JPG, PNG, GIF, BMP, TIFF, WebP, dan (bila pustaka tersedia)
  HEIC/HEIF.
