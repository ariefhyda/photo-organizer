"""Widget & dialog kustom untuk antarmuka."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QSpinBox,
    QTextBrowser, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from .organizer import build_new_name
from .resources import asset_path
from .theme import ACCENTS

GITHUB_URL = "https://github.com/ariefhyda"
DEVELOPER = "Arief Hyda"


class StarRating(QWidget):
    """Lima bintang yang bisa diklik untuk memberi rating 0-5."""

    rating_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rating = 0
        self._buttons: list[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for i in range(1, 6):
            btn = QPushButton("☆")  # bintang kosong
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(34, 34)
            btn.clicked.connect(lambda _=False, v=i: self._on_click(v))
            self._buttons.append(btn)
            layout.addWidget(btn)
        layout.addStretch()
        self.set_rating(0)

    # Gaya dasar tombol bintang (override padding/min-width dari tema global).
    _BTN_CSS = ("font-size: 24px; border: none; background: transparent;"
                "padding: 0; margin: 0; min-width: 0; color: %s;")

    def _on_click(self, value: int):
        # Klik bintang yang sama -> nol-kan.
        self.set_rating(0 if value == self._rating else value)
        self.rating_changed.emit(self._rating)

    def set_rating(self, value: int):
        self._rating = max(0, min(5, value))
        for i, btn in enumerate(self._buttons, 1):
            btn.setText("★" if i <= self._rating else "☆")  # penuh/kosong
            btn.setStyleSheet(
                self._BTN_CSS % ("#ffc24b" if i <= self._rating else "#8a8f98"))

    def rating(self) -> int:
        return self._rating


class OrganizeDialog(QDialog):
    """Dialog untuk menyusun foto ke folder berdasarkan tanggal."""

    PATTERNS = {
        "Tahun / Tahun-Bulan  (2024/2024-06)": "%Y/%Y-%m",
        "Tahun / Bulan        (2024/06)": "%Y/%m",
        "Tahun-Bulan-Hari     (2024-06-01)": "%Y-%m-%d",
        "Tahun saja           (2024)": "%Y",
    }

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Susun Berdasarkan Tanggal")
        self.setMinimumWidth(480)
        form = QFormLayout(self)

        form.addRow(QLabel(f"<b>{count} foto</b> akan disusun ke folder tujuan."))

        self.target_edit = QLineEdit()
        browse = QPushButton("Pilih…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.target_edit)
        row.addWidget(browse)
        roww = QWidget(); roww.setLayout(row)
        form.addRow("Folder tujuan:", roww)

        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems(self.PATTERNS.keys())
        form.addRow("Struktur folder:", self.pattern_combo)

        self.copy_radio = QRadioButton("Salin (file asli tetap ada)")
        self.move_radio = QRadioButton("Pindahkan (hapus dari lokasi asal)")
        self.copy_radio.setChecked(True)
        mode = QHBoxLayout()
        mode.addWidget(self.copy_radio)
        mode.addWidget(self.move_radio)
        modew = QWidget(); modew.setLayout(mode)
        form.addRow("Mode:", modew)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih folder tujuan")
        if d:
            self.target_edit.setText(d)

    def values(self) -> dict:
        return {
            "target": self.target_edit.text().strip(),
            "pattern": self.PATTERNS[self.pattern_combo.currentText()],
            "move": self.move_radio.isChecked(),
        }


class RenameDialog(QDialog):
    """Dialog untuk mengganti nama banyak file sekaligus."""

    def __init__(self, sample: dict, count: int, parent=None):
        super().__init__(parent)
        self.sample = sample
        self.setWindowTitle("Ganti Nama Massal")
        self.setMinimumWidth(520)
        form = QFormLayout(self)

        form.addRow(QLabel(f"<b>{count} foto</b> akan diganti namanya."))

        self.template_edit = QLineEdit("Foto_{date}_{n:03}")
        self.template_edit.textChanged.connect(self._update_preview)
        form.addRow("Template:", self.template_edit)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 999999)
        self.start_spin.setValue(1)
        self.start_spin.valueChanged.connect(self._update_preview)
        form.addRow("Mulai nomor dari:", self.start_spin)

        help_text = QLabel(
            "Placeholder: <code>{n}</code> nomor urut, "
            "<code>{n:03}</code> dengan nol di depan, "
            "<code>{name}</code> nama asli, <code>{ext}</code> ekstensi, "
            "<code>{date}</code> tanggal, <code>{time}</code> waktu."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #666;")
        form.addRow(help_text)

        self.preview = QLabel()
        self.preview.setStyleSheet("color: #0a7; font-family: monospace;")
        form.addRow("Contoh hasil:", self.preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._update_preview()

    def _update_preview(self):
        try:
            name = build_new_name(
                self.template_edit.text(),
                self.start_spin.value(),
                Path(self.sample["path"]),
                self.sample.get("date_taken"),
            )
            self.preview.setText(name)
        except Exception as exc:  # noqa: BLE001
            self.preview.setText(f"(template tidak valid: {exc})")

    def values(self) -> dict:
        return {
            "template": self.template_edit.text(),
            "start": self.start_spin.value(),
        }


class SettingsDialog(QDialog):
    """Pengaturan: tema (mode + warna aksen) dan pemeliharaan indeks."""

    def __init__(self, current_mode: str, current_accent: str,
                 on_reset_index, on_clear_cache, storage_dir: str = "",
                 on_change_storage=None, on_export_db=None, on_import_db=None,
                 parent=None):
        super().__init__(parent)
        self._on_reset_index = on_reset_index
        self._on_clear_cache = on_clear_cache
        self._on_change_storage = on_change_storage
        self._on_export_db = on_export_db
        self._on_import_db = on_import_db
        self._mode = current_mode
        self._accent = current_accent
        self._swatches: list[QPushButton] = []

        self.setWindowTitle("Pengaturan")
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        root.setSpacing(14)

        # ----- Tampilan -----
        root.addWidget(self._section("Tampilan"))

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("🌙 Gelap", "dark")
        self.mode_combo.addItem("☀️ Terang", "light")
        i = self.mode_combo.findData(current_mode)
        self.mode_combo.setCurrentIndex(i if i >= 0 else 0)
        mode_row.addWidget(self.mode_combo, 1)
        root.addLayout(mode_row)

        root.addWidget(QLabel("Warna aksen:"))
        sw_row = QHBoxLayout()
        sw_row.setSpacing(8)
        for name, hexv in ACCENTS.items():
            btn = QPushButton()
            btn.setToolTip(name)
            btn.setFixedSize(30, 30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("accent_hex", hexv)
            btn.clicked.connect(lambda _=False, h=hexv: self._pick_accent(h))
            self._swatches.append(btn)
            sw_row.addWidget(btn)
        custom = QPushButton("➕")
        custom.setFixedSize(30, 30)
        custom.setToolTip("Warna kustom…")
        custom.clicked.connect(self._pick_custom)
        sw_row.addWidget(custom)
        sw_row.addStretch()
        root.addLayout(sw_row)
        self._render_swatches()

        # ----- Pemeliharaan -----
        root.addWidget(self._section("Pemeliharaan Indeks"))
        hint = QLabel(
            "Reset indexing menghapus seluruh data indeks (foto, tag, album, "
            "orang, wajah) dari aplikasi. <b>File foto/video di disk tidak "
            "dihapus.</b> Folder yang dipantau tetap, jadi kamu bisa pindai ulang."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9aa0aa;")
        root.addWidget(hint)

        maint = QHBoxLayout()
        clear_btn = QPushButton("🧹 Hapus Cache Thumbnail")
        clear_btn.clicked.connect(self._clear_cache)
        reset_btn = QPushButton("♻️ Reset Indexing")
        reset_btn.setObjectName("Danger")
        reset_btn.clicked.connect(self._reset_index)
        maint.addWidget(clear_btn)
        maint.addStretch()
        maint.addWidget(reset_btn)
        root.addLayout(maint)

        # ----- Penyimpanan (portable) -----
        if self._on_change_storage or self._on_export_db:
            root.addWidget(self._section("Penyimpanan Database"))
            sinfo = QLabel(
                "Database & cache disimpan di folder ini (default: folder "
                "aplikasi, agar portable). Kamu bisa memindahkannya, atau "
                "export/import database sebagai cadangan.")
            sinfo.setWordWrap(True)
            sinfo.setStyleSheet("color:#9aa0aa;")
            root.addWidget(sinfo)

            self.storage_label = QLabel(self._fmt_path(storage_dir))
            self.storage_label.setWordWrap(True)
            self.storage_label.setStyleSheet(
                "font-family:monospace; padding:6px; border-radius:6px;")
            root.addWidget(self.storage_label)

            srow = QHBoxLayout()
            change_btn = QPushButton("📁 Ubah Folder…")
            change_btn.clicked.connect(self._change_storage)
            exp_btn = QPushButton("⬆️ Export DB…")
            exp_btn.clicked.connect(lambda: self._on_export_db and self._on_export_db())
            imp_btn = QPushButton("⬇️ Import DB…")
            imp_btn.clicked.connect(lambda: self._on_import_db and self._on_import_db())
            srow.addWidget(change_btn)
            srow.addStretch()
            srow.addWidget(exp_btn)
            srow.addWidget(imp_btn)
            root.addLayout(srow)

        # ----- OK / Cancel -----
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Terapkan")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(f"<b>{text}</b>")
        lbl.setStyleSheet("margin-top:4px;")
        return lbl

    def _pick_accent(self, hexv: str):
        self._accent = hexv
        self._render_swatches()

    def _pick_custom(self):
        col = QColorDialog.getColor(parent=self, title="Pilih warna aksen")
        if col.isValid():
            self._accent = col.name()
            self._render_swatches()

    def _render_swatches(self):
        for btn in self._swatches:
            hexv = btn.property("accent_hex")
            selected = hexv.lower() == self._accent.lower()
            border = "#ffffff" if selected else "rgba(0,0,0,0.25)"
            width = 3 if selected else 1
            btn.setStyleSheet(
                f"background:{hexv}; border:{width}px solid {border};"
                "border-radius:8px;")

    def _fmt_path(self, p: str) -> str:
        return f"📂 {p}" if p else "—"

    def _change_storage(self):
        if not self._on_change_storage:
            return
        newp = self._on_change_storage()
        if newp:
            self.storage_label.setText(self._fmt_path(newp))

    def _clear_cache(self):
        n = self._on_clear_cache()
        QMessageBox.information(
            self, "Pengaturan", f"{n} berkas thumbnail dihapus dari cache.")

    def _reset_index(self):
        ans = QMessageBox.warning(
            self, "Reset Indexing",
            "Hapus semua data indeks (foto, tag, album, orang, wajah)?\n\n"
            "File asli di disk TIDAK akan dihapus. Setelah ini kamu bisa "
            "memindai ulang folder.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans == QMessageBox.Yes:
            self._on_reset_index()
            QMessageBox.information(
                self, "Pengaturan",
                "Indeks direset. Klik '🔄 Pindai Ulang' untuk mengindeks "
                "kembali folder kamu.")

    def values(self) -> dict:
        return {
            "mode": self.mode_combo.currentData(),
            "accent": self._accent,
        }


class FolderManagerDialog(QDialog):
    """Kelola daftar folder yang dipantau: tambah, pindai ulang, hapus."""

    FOLDER_ROLE = Qt.UserRole + 1

    def __init__(self, mw, parent=None):
        super().__init__(parent or mw)
        self._mw = mw                       # referensi ke MainWindow
        self.setWindowTitle("Kelola Folder")
        self.resize(620, 420)
        root = QVBoxLayout(self)

        root.addWidget(QLabel(
            "Folder yang dipantau aplikasi. Pindai ulang untuk memperbarui "
            "media baru, atau hapus dari daftar bila tidak ingin dipantau."))

        self.list = QListWidget()
        self.list.setAlternatingRowColors(False)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        root.addWidget(self.list, 1)

        btns = QHBoxLayout()
        self.add_btn = QPushButton("➕ Tambah Folder")
        self.add_btn.setObjectName("Primary")
        self.add_btn.clicked.connect(self._add)
        self.rescan_btn = QPushButton("🔄 Pindai Ulang")
        self.rescan_btn.clicked.connect(self._rescan_selected)
        self.rescan_all_btn = QPushButton("🔄 Pindai Semua")
        self.rescan_all_btn.clicked.connect(self._rescan_all)
        self.remove_btn = QPushButton("🗑️ Hapus dari Daftar")
        self.remove_btn.setObjectName("Danger")
        self.remove_btn.clicked.connect(self._remove)
        close_btn = QPushButton("Tutup")
        close_btn.clicked.connect(self.accept)

        btns.addWidget(self.add_btn)
        btns.addWidget(self.rescan_btn)
        btns.addWidget(self.rescan_all_btn)
        btns.addStretch()
        btns.addWidget(self.remove_btn)
        btns.addWidget(close_btn)
        root.addLayout(btns)

        self._reload()

    def _reload(self):
        self.list.clear()
        folders = self._mw._folders()
        counts = self._mw.db.counts_by_folder(folders) if folders else {}
        for f in sorted(folders):
            n = counts.get(f, 0)
            item = QListWidgetItem(f"📁  {f}\n      {n} media terindeks")
            item.setData(self.FOLDER_ROLE, f)
            self.list.addItem(item)
        if not folders:
            ph = QListWidgetItem("(belum ada folder — klik 'Tambah Folder')")
            ph.setFlags(Qt.NoItemFlags)
            self.list.addItem(ph)
        self._update_buttons()

    def _update_buttons(self):
        has_sel = self._selected() is not None
        self.rescan_btn.setEnabled(has_sel)
        self.remove_btn.setEnabled(has_sel)
        self.rescan_all_btn.setEnabled(bool(self._mw._folders()))

    def _selected(self):
        items = self.list.selectedItems()
        if not items:
            return None
        return items[0].data(self.FOLDER_ROLE)

    def _add(self):
        self._mw.add_folder()
        self._reload()

    def _rescan_selected(self):
        folder = self._selected()
        if folder:
            self._mw.rescan_folders([folder])
            self.accept()

    def _rescan_all(self):
        self._mw.rescan()
        self.accept()

    def _remove(self):
        folder = self._selected()
        if not folder:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Hapus Folder")
        box.setIcon(QMessageBox.Question)
        box.setText(f"Hapus folder dari daftar pantauan?\n\n{folder}")
        box.setInformativeText(
            "File asli di disk tidak akan dihapus. Pilih apakah indeks "
            "(thumbnail/tag/album/wajah) media folder ini juga dihapus.")
        purge_btn = box.addButton("Hapus + bersihkan indeks",
                                  QMessageBox.AcceptRole)
        keep_btn = box.addButton("Hapus dari daftar saja",
                                 QMessageBox.ActionRole)
        box.addButton("Batal", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == purge_btn:
            self._mw.remove_folder(folder, purge_index=True)
            self._reload()
        elif clicked == keep_btn:
            self._mw.remove_folder(folder, purge_index=False)
            self._reload()


_HELP_HTML = f"""
<h2>📖 Panduan {APP_NAME}</h2>
<p>Aplikasi untuk mengelola foto &amp; video: galeri, album, pengenalan wajah,
peta lokasi, deteksi duplikat, dan lainnya.</p>

<h3>1. Menambah media</h3>
<ul>
<li><b>📁 Folder ▸ Tambah Folder</b> — pilih folder; aplikasi memindai
foto/video (rekursif), membuat thumbnail, membaca tanggal/EXIF, sumber, &amp; GPS.</li>
<li><b>📁 Folder ▸ Pindai Ulang</b> — perbarui semua folder (cari media baru).</li>
<li><b>📁 Folder ▸ Kelola Folder</b> — lihat daftar folder + jumlah media,
pindai ulang, atau lepas folder dari pantauan.</li>
</ul>

<h3>2. Menjelajah (sidebar kiri)</h3>
<ul>
<li><b>🗂️ Semua / 🖼️ Foto / 🎬 Video</b> — saring berdasarkan jenis.</li>
<li><b>Sumber</b> — Kamera, WhatsApp, Screenshot, dll. (dideteksi otomatis).</li>
<li><b>Album</b> — koleksi buatanmu. <i>Klik dua kali</i> album untuk Export /
ganti nama / hapus.</li>
<li><b>Orang</b> — hasil pengelompokan wajah. <i>Klik dua kali</i> untuk Export /
beri nama.</li>
<li><b>Lokasi</b> — tempat (dari GPS). <i>Klik dua kali</i> untuk Export.</li>
</ul>
<p>Kotak <b>Cari</b>, filter <b>Rating</b>, dan <b>Tag</b> di atas galeri
mempersempit hasil. Pilih foto untuk melihat detail, beri ⭐ rating, dan tag di
panel kanan. <i>Klik dua kali</i> media untuk membukanya.</p>

<h3>3. Alat (🧰)</h3>
<ul>
<li><b>📅 Susun per Tanggal</b> — salin/pindahkan ke folder berdasarkan tanggal.</li>
<li><b>✏️ Ganti Nama Massal</b> — rename banyak file dengan pola template.</li>
<li><b>🔍 Cari Duplikat</b> — temukan foto mirip (perceptual hash), pratinjau,
lalu hapus yang tak perlu.</li>
<li><b>🙂 Pindai Wajah</b> — deteksi &amp; kelompokkan wajah jadi "Orang".</li>
</ul>

<h3>4. Album &amp; Export</h3>
<ul>
<li>Pilih beberapa media ▸ klik kanan ▸ <b>Tambahkan ke album</b>, atau
<b>📚 Album Baru</b> di toolbar.</li>
<li><b>Export</b> (album/orang/lokasi, via klik dua kali di sidebar) —
salin/pindahkan file asli ke folder bernama item tersebut.</li>
</ul>

<h3>5. Peta (🗺️)</h3>
<p>Menampilkan foto ber-GPS di peta interaktif; pin berupa thumbnail, klik untuk
melihat foto &amp; detail. Tersedia tombol <b>Layar Penuh (F11)</b>.</p>

<h3>6. Menghapus &amp; "Dihapus"</h3>
<ul>
<li><b>Delete</b> — pindahkan ke <b>🗑️ Dihapus</b> (hilang dari index, file
masih aman). Dari sana baru bisa: hapus dari indeks / Recycle Bin / permanen,
atau <b>↩️ Keluarkan</b> untuk membatalkan.</li>
<li><b>Shift+Delete</b> — langsung ke Recycle Bin. <b>Ctrl+Delete</b> — hapus
permanen.</li>
</ul>

<h3>7. Pengaturan (⚙️)</h3>
<p>Mode gelap/terang, warna aksen, reset indexing, dan bersihkan cache thumbnail.</p>
<p style="color:#888"><i>Data indeks &amp; thumbnail disimpan di
folder <code>.photo_organizer</code> pada direktori pengguna. File foto/video
asli tidak pernah diubah kecuali kamu memilih Pindahkan/Hapus permanen.</i></p>
"""


class HelpDialog(QDialog):
    """Panduan cara pemakaian aplikasi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Bantuan — {APP_NAME}")
        self.resize(640, 620)
        lay = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(_HELP_HTML)
        lay.addWidget(browser)
        btn = QPushButton("Tutup")
        btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        lay.addLayout(row)


class AboutDialog(QDialog):
    """Info aplikasi & developer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Tentang {APP_NAME}")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        pix = QPixmap(str(asset_path("icon.png")))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio,
                                      Qt.SmoothTransformation))
        lay.addWidget(logo)

        info = QLabel(
            f"<div align='center'>"
            f"<h2 style='margin:2px'>{APP_NAME}</h2>"
            f"<p style='color:#888;margin:2px'>Versi {__version__}</p>"
            f"<p style='margin:8px 0'>Pengelola foto &amp; video: galeri, album, "
            f"wajah, peta, duplikat.</p>"
            f"<p style='margin:2px'>Dibuat oleh <b>{DEVELOPER}</b></p>"
            f"<p style='margin:2px'>"
            f"<a href='{GITHUB_URL}'>{GITHUB_URL}</a></p>"
            f"</div>")
        info.setOpenExternalLinks(True)
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        lay.addWidget(info)

        btn = QPushButton("Tutup")
        btn.setObjectName("Primary")
        btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        lay.addLayout(row)
