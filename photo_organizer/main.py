"""Jendela utama aplikasi Photo Organizer."""

from __future__ import annotations

import os
import shutil
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QAction, QIcon, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSlider, QSplitter, QStatusBar, QToolBar, QToolButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QInputDialog,
)

from . import APP_NAME, __version__
from .db import Database
from .duplicates import find_duplicate_groups
from .imaging import THUMB_SIZE, get_thumbnail, cached_thumbnail
from .locations import cluster_locations, build_map_html
from .organizer import (organize_by_date, bulk_rename, export_to_folder,
                        safe_folder_name)
from .sources import label as source_label
from .faces import models_available
from .theme import apply_theme, DEFAULT_ACCENT, DEFAULT_MODE
from .widgets import (AboutDialog, FolderManagerDialog, HelpDialog,
                      OrganizeDialog, RenameDialog, SettingsDialog, StarRating)
from .resources import asset_path, default_data_dir, portable_settings
from .workers import (ScanWorker, ThumbnailWorker, FaceWorker, GeocodeWorker,
                      QualityWorker)

try:
    from send2trash import send2trash as _send2trash
except Exception:  # noqa: BLE001
    _send2trash = None

ICON_SIZE = QSize(180, 180)
PHOTO_ROLE = Qt.UserRole + 1


def _placeholder_icon() -> QIcon:
    pix = QPixmap(THUMB_SIZE[0], THUMB_SIZE[1])
    pix.fill(Qt.lightGray)
    return QIcon(pix)


class DuplicatesDialog(QDialog):
    """Tampilkan grup foto duplikat dan biarkan pengguna menghapus pilihannya."""

    def __init__(self, groups: list[list[dict]], cache_dir: Path, parent=None):
        super().__init__(parent)
        self.groups = groups
        self.cache_dir = cache_dir
        self.deleted_ids: list[int] = []
        self.setWindowTitle("Foto Duplikat / Mirip")
        self.resize(1000, 620)
        layout = QVBoxLayout(self)

        total = sum(len(g) for g in groups)
        info = QLabel(
            f"Ditemukan <b>{len(groups)} grup</b> ({total} foto). "
            "Klik sebuah foto untuk melihat pratinjau di kanan. "
            "File terbesar di tiap grup tidak dicentang (kandidat 'asli'). "
            "Centang yang ingin dihapus."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        split = QSplitter(Qt.Horizontal)
        layout.addWidget(split, 1)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Ukuran", "Dimensi", "Lokasi"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 90)
        self.tree.setIconSize(QSize(72, 72))
        self.tree.currentItemChanged.connect(self._on_current_changed)
        split.addWidget(self.tree)

        # Panel pratinjau di kanan agar pengguna bisa membandingkan visual.
        prev_panel = QWidget()
        pv = QVBoxLayout(prev_panel)
        self.preview = QLabel("Klik sebuah foto untuk pratinjau")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumWidth(300)
        self.preview.setStyleSheet(
            "background:#16171b; color:#9aa0aa; border:1px solid #2c2d34;"
            "border-radius:10px; padding:6px;")
        pv.addWidget(self.preview, 1)
        self.preview_info = QLabel("")
        self.preview_info.setWordWrap(True)
        self.preview_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pv.addWidget(self.preview_info)
        split.addWidget(prev_panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        for gi, group in enumerate(groups, 1):
            top = QTreeWidgetItem([f"Grup {gi} — {len(group)} foto"])
            top.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(top)
            for idx, photo in enumerate(group):
                size_kb = (photo.get("size") or 0) / 1024
                dim = (f"{photo.get('width')}×{photo.get('height')}"
                       if photo.get("width") else "—")
                child = QTreeWidgetItem([
                    photo["filename"], f"{size_kb:,.0f} KB", dim,
                    str(Path(photo["path"]).parent),
                ])
                child.setData(0, Qt.UserRole, photo)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                # Biarkan file terbesar (idx 0) tidak dicentang.
                child.setCheckState(0, Qt.Unchecked if idx == 0 else Qt.Unchecked)
                thumb = get_thumbnail(Path(photo["path"]), self.cache_dir)
                if thumb:
                    child.setIcon(0, QIcon(str(thumb)))
                top.addChild(child)
            top.setExpanded(True)

        btns = QHBoxLayout()
        select_extra = QPushButton("Centang semua kecuali yang terbesar")
        select_extra.clicked.connect(self._check_extras)
        delete_btn = QPushButton("Hapus yang dicentang")
        delete_btn.setObjectName("Danger")
        delete_btn.clicked.connect(self._delete_checked)
        close_btn = QPushButton("Tutup")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(select_extra)
        btns.addStretch()
        btns.addWidget(delete_btn)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _on_current_changed(self, current, _previous):
        if current is None:
            return
        photo = current.data(0, Qt.UserRole)
        if not photo:  # baris header grup
            self.preview.setPixmap(QPixmap())
            self.preview.setText("(grup)")
            self.preview_info.setText("")
            return
        pix = QPixmap(photo["path"])
        if pix.isNull():
            self.preview.setText("(pratinjau tidak tersedia)")
        else:
            self.preview.setPixmap(pix.scaled(
                max(self.preview.width(), 100), max(self.preview.height(), 100),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        size_kb = (photo.get("size") or 0) / 1024
        dim = (f"{photo.get('width')}×{photo.get('height')} px"
               if photo.get("width") else "—")
        self.preview_info.setText(
            f"<b>{photo['filename']}</b><br>{dim} • {size_kb:,.0f} KB<br>"
            f"<span style='color:#888'>{photo['path']}</span>")

    def _check_extras(self):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                child.setCheckState(0, Qt.Checked if j > 0 else Qt.Unchecked)

    def _collect_checked(self) -> list[dict]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.checkState(0) == Qt.Checked:
                    out.append(child.data(0, Qt.UserRole))
        return out

    def _delete_checked(self):
        targets = self._collect_checked()
        if not targets:
            QMessageBox.information(self, APP_NAME, "Tidak ada foto yang dicentang.")
            return
        ans = QMessageBox.warning(
            self, "Konfirmasi Hapus",
            f"Hapus permanen {len(targets)} file dari disk?\n"
            "Tindakan ini tidak bisa dibatalkan.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        failed = 0
        for photo in targets:
            try:
                os.remove(photo["path"])
                self.deleted_ids.append(photo["id"])
            except OSError:
                failed += 1
        msg = f"{len(targets) - failed} file dihapus."
        if failed:
            msg += f" {failed} gagal dihapus."
        QMessageBox.information(self, APP_NAME, msg)
        self.accept()


class JunkDialog(QDialog):
    """Tampilkan foto yang terdeteksi 'tidak penting' untuk dipindah ke Dihapus."""

    def __init__(self, results: list[dict], cache_dir: Path, parent=None):
        super().__init__(parent)
        self.cache_dir = cache_dir
        self.chosen_ids: list[int] = []
        self.setWindowTitle("Deteksi Gambar Tidak Penting")
        self.resize(1000, 640)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            f"Ditemukan <b>{len(results)}</b> gambar berpotensi tidak penting "
            "(buram/gelap/terang/datar). Centang yang ingin dipindah ke "
            "<b>🗑️ Dihapus</b>, lalu tinjau di sana sebelum benar-benar dihapus."))

        split = QSplitter(Qt.Horizontal)
        layout.addWidget(split, 1)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Alasan"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setIconSize(QSize(72, 72))
        self.tree.currentItemChanged.connect(self._on_current)
        split.addWidget(self.tree)

        prev = QWidget()
        pv = QVBoxLayout(prev)
        self.preview = QLabel("Klik sebuah gambar untuk pratinjau")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumWidth(300)
        self.preview.setStyleSheet(
            "background:#16171b; color:#9aa0aa; border:1px solid #2c2d34;"
            "border-radius:10px; padding:6px;")
        pv.addWidget(self.preview, 1)
        self.preview_info = QLabel("")
        self.preview_info.setWordWrap(True)
        pv.addWidget(self.preview_info)
        split.addWidget(prev)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        for r in results:
            item = QTreeWidgetItem([r["filename"], ", ".join(r["reasons"])])
            item.setData(0, Qt.UserRole, r)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)      # default tercentang
            thumb = get_thumbnail(Path(r["path"]), self.cache_dir)
            if thumb:
                item.setIcon(0, QIcon(str(thumb)))
            self.tree.addTopLevelItem(item)

        btns = QHBoxLayout()
        check_all = QPushButton("Centang semua")
        check_all.clicked.connect(lambda: self._set_all(True))
        uncheck_all = QPushButton("Hapus centang")
        uncheck_all.clicked.connect(lambda: self._set_all(False))
        move_btn = QPushButton("➡️ Pindahkan dicentang ke Dihapus")
        move_btn.setObjectName("Primary")
        move_btn.clicked.connect(self._move)
        close_btn = QPushButton("Tutup")
        close_btn.clicked.connect(self.reject)
        btns.addWidget(check_all)
        btns.addWidget(uncheck_all)
        btns.addStretch()
        btns.addWidget(move_btn)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _on_current(self, current, _prev):
        if not current:
            return
        r = current.data(0, Qt.UserRole)
        pix = QPixmap(r["path"])
        if pix.isNull():
            thumb = get_thumbnail(Path(r["path"]), self.cache_dir)
            pix = QPixmap(str(thumb)) if thumb else QPixmap()
        if not pix.isNull():
            self.preview.setPixmap(pix.scaled(
                max(self.preview.width(), 100), max(self.preview.height(), 100),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.preview.setText("(pratinjau tidak tersedia)")
        self.preview_info.setText(
            f"<b>{r['filename']}</b><br>Alasan: {', '.join(r['reasons'])}<br>"
            f"<span style='color:#888'>{r['path']}</span>")

    def _set_all(self, checked: bool):
        st = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, st)

    def _move(self):
        ids = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                ids.append(it.data(0, Qt.UserRole)["id"])
        if not ids:
            QMessageBox.information(self, APP_NAME, "Tidak ada yang dicentang.")
            return
        self.chosen_ids = ids
        self.accept()


class MapDialog(QDialog):
    """Peta interaktif yang tertanam langsung di dalam aplikasi (QtWebEngine)."""

    def __init__(self, html_path: Path, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineSettings

        self.setWindowTitle("🗺️ Peta Foto")
        self.resize(1040, 740)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Bilah atas: tombol layar penuh & tutup.
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        bar.addWidget(QLabel("🗺️ <b>Peta Foto</b>"))
        bar.addStretch()
        self.fs_btn = QPushButton("⛶ Layar Penuh")
        self.fs_btn.setToolTip("Layar penuh (F11)")
        self.fs_btn.clicked.connect(self._toggle_fullscreen)
        close_btn = QPushButton("✕ Tutup")
        close_btn.clicked.connect(self.accept)
        bar.addWidget(self.fs_btn)
        bar.addWidget(close_btn)
        bar_w = QWidget()
        bar_w.setObjectName("FilterBar")
        bar_w.setLayout(bar)
        lay.addWidget(bar_w)

        self.view = QWebEngineView()
        st = self.view.settings()
        # Halaman lokal (file://) perlu izin mengakses file lokal (thumbnail)
        # dan sumber remote (tile OSM + Leaflet CDN).
        st.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        st.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.view.load(QUrl.fromLocalFile(str(Path(html_path).resolve())))
        lay.addWidget(self.view, 1)

        QShortcut(QKeySequence(Qt.Key_F11), self, self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.fs_btn.setText("⛶ Layar Penuh")
        else:
            self.showFullScreen()
            self.fs_btn.setText("🗗 Keluar Layar Penuh")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.setWindowIcon(QIcon(str(asset_path("icon.png"))))
        self.resize(1180, 760)

        self.settings = portable_settings()
        # Lokasi penyimpanan data (portable): default = folder aplikasi/data.
        configured = self.settings.value("storage/db_dir", None)
        self.data_dir = Path(configured) if configured else default_data_dir()
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.data_dir = default_data_dir()
        db_file = self.data_dir / "library.db"
        # Tidak ada migrasi otomatis: aplikasi portable selalu mulai dengan
        # data di folder ini. Untuk memuat katalog lama, pakai
        # Pengaturan ▸ Import Database.
        self.db = Database(db_file)
        self.cache_dir = self.data_dir / "thumbnails"
        self.placeholder = _placeholder_icon()
        self.scan_worker: ScanWorker | None = None
        self.thumb_worker: ThumbnailWorker | None = None
        self.face_worker: FaceWorker | None = None
        self.geo_worker: GeocodeWorker | None = None
        self.quality_worker: QualityWorker | None = None
        self._geo_attempted: set = set()
        self.current_photo: dict | None = None
        # Filter aktif dari sidebar: {"kind": ...}
        self.current_filter: dict = {"kind": "all"}
        # Tampungan Hapus (persisten di DB): id media yang akan diproses.
        self.staged: set = self.db.staged_ids()
        # Ukuran thumbnail galeri (tersimpan antar sesi).
        self.icon_px: int = int(self.settings.value("gallery/icon_px", 180))

        self._build_ui()
        self.refresh_sidebar()
        self.refresh_gallery()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self._build_toolbar()
        self._build_filter_bar()

        splitter = QSplitter(Qt.Horizontal)

        # Sidebar navigasi kiri.
        splitter.addWidget(self._build_sidebar())

        # Tengah: filter bar + galeri.
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.addWidget(self.filter_bar)
        cv.addWidget(self._build_staging_bar())

        self.gallery = QListWidget()
        self.gallery.setObjectName("Gallery")
        self.gallery.setViewMode(QListWidget.IconMode)
        self.gallery.setIconSize(QSize(self.icon_px, self.icon_px))
        self.gallery.setResizeMode(QListWidget.Adjust)
        self.gallery.setMovement(QListWidget.Static)
        self.gallery.setSpacing(8)
        self.gallery.setUniformItemSizes(True)
        self.gallery.setSelectionMode(QListWidget.ExtendedSelection)
        self.gallery.itemSelectionChanged.connect(self._on_selection_changed)
        self.gallery.itemDoubleClicked.connect(self._open_external)
        self.gallery.setContextMenuPolicy(Qt.CustomContextMenu)
        self.gallery.customContextMenuRequested.connect(self._gallery_menu)
        cv.addWidget(self.gallery)

        # Shortcut hapus (hanya aktif saat galeri fokus).
        #   Delete       -> masukkan ke Tampungan Hapus
        #   Shift+Delete -> langsung ke Recycle Bin
        #   Ctrl+Delete  -> langsung hapus permanen
        sc_del = QShortcut(QKeySequence(Qt.Key_Delete), self.gallery)
        sc_del.setContext(Qt.WidgetShortcut)
        sc_del.activated.connect(self.stage_selected)
        sc_trash = QShortcut(QKeySequence("Shift+Delete"), self.gallery)
        sc_trash.setContext(Qt.WidgetShortcut)
        sc_trash.activated.connect(lambda: self.delete_selected("trash"))
        sc_perm = QShortcut(QKeySequence("Ctrl+Delete"), self.gallery)
        sc_perm.setContext(Qt.WidgetShortcut)
        sc_perm.activated.connect(lambda: self.delete_selected("permanent"))
        splitter.addWidget(center)

        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([220, 700, 280])

        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(splitter)
        self.setCentralWidget(central)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        self.status.addPermanentWidget(self.progress)

    def _menu_button(self, tb, text: str, menu: QMenu):
        """Tombol toolbar dengan menu dropdown (mengelompokkan beberapa aksi)."""
        btn = QToolButton()
        btn.setText(text)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addWidget(btn)
        return btn

    def _build_toolbar(self):
        tb = QToolBar("Utama")
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        # 📁 Folder (tambah / pindai / kelola)
        m_folder = QMenu(self)
        m_folder.addAction("➕ Tambah Folder", self.add_folder)
        m_folder.addAction("🔄 Pindai Ulang", self.rescan)
        m_folder.addAction("🗂️ Kelola Folder…", self.manage_folders)
        self._menu_button(tb, "📁 Folder", m_folder)

        # 🧰 Alat (susun / rename / duplikat / wajah)
        m_tools = QMenu(self)
        m_tools.addAction("📅 Susun per Tanggal…", self.organize_dialog)
        m_tools.addAction("✏️ Ganti Nama Massal…", self.rename_dialog)
        m_tools.addAction("🔍 Cari Duplikat…", self.find_duplicates)
        m_tools.addAction("🧹 Deteksi Gambar Tidak Penting…", self.detect_junk)
        self.act_faces = m_tools.addAction("🙂 Pindai Wajah", self.scan_faces)
        if not models_available():
            self.act_faces.setEnabled(False)
            self.act_faces.setToolTip("Model wajah tidak ditemukan di folder models/")
        self._menu_button(tb, "🧰 Alat", m_tools)

        # Aksi yang sering dipakai tetap satu-klik.
        tb.addAction("📚 Album Baru", self.new_album)
        tb.addAction("🗺️ Peta", self.open_map)

        # Dorong Bantuan & Pengaturan ke ujung kanan agar selalu terlihat.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        m_help = QMenu(self)
        m_help.addAction("📖 Cara Pemakaian", self.show_help)
        m_help.addAction("ℹ️ Tentang", self.show_about)
        self._menu_button(tb, "❓ Bantuan", m_help)

        tb.addAction("⚙️ Pengaturan", self.open_settings)

    def _build_sidebar(self) -> QWidget:
        self.sidebar = QTreeWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setMinimumWidth(190)
        self.sidebar.setMaximumWidth(320)
        self.sidebar.setIconSize(QSize(40, 40))
        self.sidebar.itemClicked.connect(self._on_sidebar_clicked)
        self.sidebar.itemDoubleClicked.connect(self._on_sidebar_double)
        return self.sidebar

    def refresh_sidebar(self):
        """Bangun ulang isi sidebar dari database."""
        self.sidebar.blockSignals(True)
        self.sidebar.clear()

        def add(parent, text, spec, icon: QIcon | None = None):
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.UserRole, spec)
            if icon:
                item.setIcon(0, icon)
            (parent.addChild if isinstance(parent, QTreeWidgetItem)
             else self.sidebar.addTopLevelItem)(item)
            return item

        mc = self.db.media_counts()
        n_photo = mc.get("photo", 0)
        n_video = mc.get("video", 0)
        add(self.sidebar, f"🗂️ Semua ({n_photo + n_video})", {"kind": "all"})
        add(self.sidebar, f"🖼️ Foto ({n_photo})", {"media_type": "photo"})
        add(self.sidebar, f"🎬 Video ({n_video})", {"media_type": "video"})
        if self.staged:
            add(self.sidebar, f"🗑️ Dihapus ({len(self.staged)})",
                {"kind": "staged"})

        # Sumber
        src_top = add(self.sidebar, "Sumber", {"kind": "header"})
        src_top.setFlags(Qt.ItemIsEnabled)
        for key, count in self.db.source_counts():
            add(src_top, f"{source_label(key)} ({count})", {"source": key})
        src_top.setExpanded(True)

        # Folder asal
        folders = self._folders()
        if folders:
            fld_top = add(self.sidebar, "Folder", {"kind": "header"})
            fld_top.setFlags(Qt.ItemIsEnabled)
            counts = self.db.counts_by_folder(folders)
            for fpath in sorted(folders):
                name = Path(fpath).name or fpath
                it = add(fld_top, f"📁 {name} ({counts.get(fpath, 0)})",
                         {"kind": "folder", "folder": fpath})
                it.setToolTip(0, fpath)
            fld_top.setExpanded(True)

        # Album
        self.album_top = add(self.sidebar, "Album", {"kind": "header"})
        self.album_top.setFlags(Qt.ItemIsEnabled)
        for aid, name, count in self.db.albums_with_counts():
            add(self.album_top, f"📚 {name} ({count})", {"album_id": aid,
                                                          "album_name": name})
        self.album_top.setExpanded(True)

        # Orang
        ppl_top = add(self.sidebar, "Orang", {"kind": "header"})
        ppl_top.setFlags(Qt.ItemIsEnabled)
        for pid, name, count in self.db.persons_with_counts():
            label_txt = name if name else "❓ Belum dinamai"
            it = add(ppl_top, f"🙂 {label_txt} ({count})",
                     {"person_id": pid, "person_name": name})
            cover = self.db.person_cover_face(pid)
            if cover:
                icon = self._face_icon(cover)
                if icon:
                    it.setIcon(0, icon)
        ppl_top.setExpanded(True)

        # Lokasi
        gps_rows = self.db.photos_with_gps()
        loc_top = add(self.sidebar, "Lokasi", {"kind": "header"})
        loc_top.setFlags(Qt.ItemIsEnabled)
        geo_targets = []
        if gps_rows:
            add(loc_top, f"📍 Semua berlokasi ({len(gps_rows)})",
                {"kind": "location", "ids": [r["id"] for r in gps_rows]})
            for c in cluster_locations(gps_rows)[:60]:
                cached = self.db.geocache_get(c["key"])
                name = cached or c["label"]
                if not cached and c["key"] not in self._geo_attempted:
                    geo_targets.append((c["key"], c["lat"], c["lon"]))
                add(loc_top, f"📌 {name} ({c['count']})",
                    {"kind": "location", "ids": c["ids"], "label": name})
        loc_top.setExpanded(True)

        self.sidebar.blockSignals(False)

        # Mulai penamaan tempat (reverse-geocode) di latar belakang.
        if geo_targets:
            self._start_geocode(geo_targets)

    def _face_icon(self, face_row) -> QIcon | None:
        """Potong wilayah wajah dari foto sebagai ikon kecil."""
        pix = QPixmap(face_row["path"])
        if pix.isNull():
            return None
        x, y, w, h = (face_row["x"], face_row["y"],
                      face_row["w"], face_row["h"])
        x = max(0, x); y = max(0, y)
        crop = pix.copy(x, y, w, h)
        if crop.isNull():
            return QIcon(pix)
        return QIcon(crop.scaled(40, 40, Qt.KeepAspectRatioByExpanding,
                                 Qt.SmoothTransformation))

    def _on_sidebar_clicked(self, item: QTreeWidgetItem, _col: int):
        spec = item.data(0, Qt.UserRole) or {}
        if spec.get("kind") == "header":
            return
        self.current_filter = spec
        self.refresh_gallery()

    def _on_sidebar_double(self, item: QTreeWidgetItem, _col: int):
        spec = item.data(0, Qt.UserRole) or {}
        if "album_id" in spec:
            self._album_context(spec)
        elif "person_id" in spec:
            self._person_context(spec)
        elif spec.get("kind") == "location" and spec.get("ids"):
            self._location_context(spec)

    def _build_filter_bar(self):
        self.filter_bar = QWidget()
        self.filter_bar.setObjectName("FilterBar")
        h = QHBoxLayout(self.filter_bar)
        h.setContentsMargins(12, 9, 12, 9)
        h.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Cari nama file atau tanggal…")
        self.search_edit.textChanged.connect(self.refresh_gallery)
        h.addWidget(QLabel("Cari:"))
        h.addWidget(self.search_edit, 2)

        self.rating_filter = QComboBox()
        self.rating_filter.addItem("Semua", -1)          # semua rating
        for n in range(1, 6):
            self.rating_filter.addItem("★" * n, n)       # ikon bintang saja
        self.rating_filter.setToolTip("Saring berdasarkan jumlah bintang")
        self.rating_filter.currentIndexChanged.connect(self.refresh_gallery)
        h.addWidget(QLabel("Rating:"))
        h.addWidget(self.rating_filter)

        self.tag_filter = QComboBox()
        self.tag_filter.currentIndexChanged.connect(self.refresh_gallery)
        h.addWidget(QLabel("Tag:"))
        h.addWidget(self.tag_filter)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("📅 Terbaru", "date_taken DESC")
        self.sort_combo.addItem("📅 Terlama", "date_taken ASC")
        self.sort_combo.addItem("🔤 Nama A→Z", "filename ASC")
        self.sort_combo.addItem("🔤 Nama Z→A", "filename DESC")
        self.sort_combo.currentIndexChanged.connect(self.refresh_gallery)
        h.addWidget(QLabel("Urutkan:"))
        h.addWidget(self.sort_combo)

        # Slider ukuran thumbnail (ringkas; kolom Cari yang melebar mengisi sisa).
        h.addWidget(QLabel("Ukuran:"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(90, 420)
        self.zoom_slider.setFixedWidth(90)
        self.zoom_slider.setValue(self.icon_px)
        self.zoom_slider.setToolTip("Perbesar/perkecil thumbnail")
        self.zoom_slider.valueChanged.connect(self._on_zoom)
        h.addWidget(self.zoom_slider)

    def _on_zoom(self, value: int):
        """Ubah ukuran thumbnail galeri secara langsung (tanpa reload)."""
        self.icon_px = value
        self.settings.setValue("gallery/icon_px", value)
        self.gallery.setIconSize(QSize(value, value))
        for i in range(self.gallery.count()):
            self.gallery.item(i).setSizeHint(QSize(value + 20, value + 40))

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("DetailPanel")
        v = QVBoxLayout(panel)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        self.preview_label = QLabel("Pilih foto untuk melihat detail")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(240)
        self.preview_label.setStyleSheet(
            "background:#16171b; color:#9aa0aa; border:1px solid #2c2d34;"
            "border-radius:10px; padding:6px;")
        v.addWidget(self.preview_label)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.info_label)

        v.addWidget(QLabel("<b>Rating:</b>"))
        self.star_widget = StarRating()
        self.star_widget.rating_changed.connect(self._on_rating_changed)
        v.addWidget(self.star_widget)

        v.addWidget(QLabel("<b>Tag:</b>"))
        self.tags_label = QLabel("—")
        self.tags_label.setWordWrap(True)
        v.addWidget(self.tags_label)

        tag_row = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Tambah tag lalu Enter")
        self.tag_input.returnPressed.connect(self._add_tag)
        add_tag_btn = QPushButton("Tambah")
        add_tag_btn.setObjectName("Primary")
        add_tag_btn.clicked.connect(self._add_tag)
        tag_row.addWidget(self.tag_input)
        tag_row.addWidget(add_tag_btn)
        v.addLayout(tag_row)

        remove_tag_btn = QPushButton("Hapus tag…")
        remove_tag_btn.clicked.connect(self._remove_tag)
        v.addWidget(remove_tag_btn)

        v.addStretch()
        panel.setMinimumWidth(280)
        return panel

    # -------------------------------------------------------------- scanning
    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih folder berisi foto")
        if not d:
            return
        folders = set(self.settings.value("folders", [], type=list))
        folders.add(d)
        self.settings.setValue("folders", list(folders))
        self._start_scan([d])

    def rescan(self):
        folders = self._folders()
        if not folders:
            QMessageBox.information(
                self, APP_NAME,
                "Belum ada folder. Klik 'Tambah Folder' dulu.")
            return
        self._start_scan(folders)

    def _folders(self) -> list[str]:
        return list(self.settings.value("folders", [], type=list))

    def rescan_folders(self, folders: list[str]):
        if folders:
            self._start_scan(folders)

    def remove_folder(self, folder: str, purge_index: bool = True):
        """Lepas folder dari daftar pantauan; opsional bersihkan indeksnya."""
        folders = [f for f in self._folders() if f != folder]
        self.settings.setValue("folders", folders)
        if purge_index:
            removed = self.db.delete_under_path(folder)
            self.status.showMessage(
                f"Folder dilepas. {removed} media dikeluarkan dari indeks.", 5000)
        else:
            self.status.showMessage("Folder dilepas dari daftar.", 5000)
        # Bila filter aktif menunjuk media yang baru dihapus, kembali ke Semua.
        self.current_filter = {"kind": "all"}
        self.refresh_sidebar()
        self.refresh_gallery()

    def manage_folders(self):
        FolderManagerDialog(self, self).exec()

    # ----------------------------------------------------------- lokasi/peta
    def open_map(self):
        rows = self.db.photos_with_gps()
        if not rows:
            QMessageBox.information(
                self, APP_NAME,
                "Belum ada foto dengan data lokasi (GPS) di EXIF.\n"
                "Foto dari kamera HP biasanya punya GPS bila layanan lokasi aktif.")
            return
        rows = rows[:3000]                  # batasi agar HTML tetap ringan
        thumb_cap = 1500                    # batas pembuatan thumbnail baru
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.status.showMessage("Menyiapkan thumbnail peta…")
        QApplication.processEvents()
        points = []
        try:
            for i, r in enumerate(rows):
                # Buat thumbnail bila belum ada (agar pin tampil sebagai foto).
                if i < thumb_cap:
                    thumb = get_thumbnail(Path(r["path"]), self.cache_dir)
                else:
                    thumb = cached_thumbnail(Path(r["path"]), self.cache_dir)
                place = self.db.geocache_get(
                    f"{round(r['lat'], 2)},{round(r['lon'], 2)}")
                points.append({
                    "lat": r["lat"], "lon": r["lon"], "name": r["filename"],
                    "date": r["date_taken"], "place": place,
                    "thumb": str(thumb) if thumb else None,
                    "full": r["path"],          # foto asli untuk popup
                })
        finally:
            QApplication.restoreOverrideCursor()
        out = build_map_html(points, "Peta Foto")
        try:
            MapDialog(out, self).exec()
            self.status.showMessage(
                f"Peta ditampilkan ({len(points)} titik lokasi).", 6000)
        except Exception as exc:            # noqa: BLE001
            # Cadangan: buka di browser bila QtWebEngine bermasalah.
            webbrowser.open(out.as_uri())
            self.status.showMessage(
                f"Peta dibuka di browser (QtWebEngine gagal: {exc}).", 8000)

    def _start_geocode(self, targets: list[tuple]):
        if self.geo_worker and self.geo_worker.isRunning():
            return
        # Tandai sudah dicoba agar tidak diulang terus (mis. saat offline).
        for key, _lat, _lon in targets:
            self._geo_attempted.add(key)
        self.geo_worker = GeocodeWorker(self.db, targets)
        self.geo_worker.finished_geo.connect(self._on_geocode_done)
        self.geo_worker.start()

    def _on_geocode_done(self, found: int):
        if found:
            self.refresh_sidebar()      # tampilkan nama tempat yang baru didapat

    def _start_scan(self, folders: list[str]):
        if self.scan_worker and self.scan_worker.isRunning():
            return
        self.progress.show()
        self.progress.setRange(0, 0)
        self.status.showMessage("Memindai…")
        self.scan_worker = ScanWorker(self.db, folders, self.cache_dir)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished_scan.connect(self._on_scan_done)
        self.scan_worker.start()

    def _on_scan_progress(self, cur: int, total: int, name: str):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(cur)
        self.status.showMessage(f"Memindai {cur}/{total}: {name}")

    def _on_scan_done(self, total: int):
        self.progress.hide()
        self.status.showMessage(f"Selesai. {total} media terindeks.", 5000)
        self.refresh_sidebar()
        self.refresh_gallery()

    # --------------------------------------------------------------- gallery
    def refresh_gallery(self):
        self._reload_tag_filter()
        text = self.search_edit.text().strip()
        rv = self.rating_filter.currentData()
        rating_exact = rv if (rv is not None and rv >= 0) else None
        tag = self.tag_filter.currentData() or ""
        f = self.current_filter

        is_staged = f.get("kind") == "staged"
        ids_param = list(self.staged) if is_staged else f.get("ids")
        # Tampilkan/atur bilah aksi "Dihapus".
        self.staging_bar.setVisible(is_staged)
        if is_staged:
            self.staging_label.setText(
                f"🗑️ <b>Dihapus</b> — {len(self.staged)} item")

        rows = self.db.query_photos(
            text=text, rating_exact=rating_exact, tag=tag,
            source=f.get("source", ""),
            media_type=f.get("media_type", ""),
            album_id=f.get("album_id", 0),
            person_id=f.get("person_id", 0),
            has_gps=f.get("has_gps", False),
            ids=ids_param,
            folder=f.get("folder", ""),
            exclude_staged=not is_staged,   # tampilkan item Dihapus hanya di bin
            order_by=self.sort_combo.currentData() or "date_taken DESC",
        )
        self.gallery.clear()

        thumb_jobs: list[tuple[int, str]] = []
        for idx, row in enumerate(rows):
            photo = dict(row)
            item = QListWidgetItem(self.placeholder, photo["filename"])
            item.setData(PHOTO_ROLE, photo)
            item.setSizeHint(QSize(self.icon_px + 20, self.icon_px + 40))
            item.setToolTip(f"{photo['filename']}\n{photo.get('date_taken','')}")
            self.gallery.addItem(item)
            thumb_jobs.append((idx, photo["path"]))

        self.status.showMessage(f"{len(rows)} media ditampilkan.")
        self._start_thumbnails(thumb_jobs)

    def _start_thumbnails(self, jobs: list[tuple[int, str]]):
        if self.thumb_worker and self.thumb_worker.isRunning():
            self.thumb_worker.stop()
            self.thumb_worker.wait(2000)
        if not jobs:
            return
        self.thumb_worker = ThumbnailWorker(jobs, self.cache_dir)
        self.thumb_worker.thumb_ready.connect(self._on_thumb_ready)
        self.thumb_worker.start()

    def _on_thumb_ready(self, row: int, thumb_path: str):
        item = self.gallery.item(row)
        if item:
            item.setIcon(QIcon(thumb_path))

    def _reload_tag_filter(self):
        current = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("Semua tag", "")
        for name in self.db.all_tags():
            self.tag_filter.addItem(name, name)
        # Pulihkan pilihan sebelumnya bila masih ada.
        if current:
            i = self.tag_filter.findData(current)
            if i >= 0:
                self.tag_filter.setCurrentIndex(i)
        self.tag_filter.blockSignals(False)

    # ------------------------------------------------------------- detail
    def _selected_photos(self) -> list[dict]:
        return [it.data(PHOTO_ROLE) for it in self.gallery.selectedItems()]

    def _on_selection_changed(self):
        photos = self._selected_photos()
        if not photos:
            self.current_photo = None
            self.preview_label.setText("Pilih foto untuk melihat detail")
            self.preview_label.setPixmap(QPixmap())
            self.info_label.setText("")
            self.star_widget.set_rating(0)
            self.tags_label.setText("—")
            return
        photo = photos[-1]
        self.current_photo = photo
        is_vid = photo.get("media_type") == "video"

        if is_vid:
            thumb = get_thumbnail(Path(photo["path"]), self.cache_dir)
            pix = QPixmap(str(thumb)) if thumb else QPixmap()
        else:
            pix = QPixmap(photo["path"])
        if not pix.isNull():
            self.preview_label.setPixmap(pix.scaled(
                self.preview_label.width(), 320,
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.preview_label.setText("(pratinjau tidak tersedia)")

        size_kb = (photo.get("size") or 0) / 1024
        dim = (f"{photo.get('width')}×{photo.get('height')} px"
               if photo.get("width") else "—")
        src = "EXIF" if photo.get("date_source") == "exif" else "tanggal file"
        lines = [
            f"<b>{photo['filename']}</b>",
            "🎬 Video" if is_vid else "🖼️ Foto",
            f"Tanggal: {photo.get('date_taken','—')} <i>({src})</i>",
            f"Dimensi: {dim}",
            f"Ukuran: {size_kb:,.0f} KB",
        ]
        if is_vid and photo.get("duration"):
            secs = int(photo["duration"])
            lines.insert(2, f"Durasi: {secs // 60}m {secs % 60}d")
        if photo.get("source"):
            lines.append(f"Sumber: {source_label(photo['source'])}")
        # Orang yang terdeteksi pada foto ini.
        faces = self.db.faces_for_photo(photo["id"])
        if faces:
            names = [f["person_name"] or "?" for f in faces]
            lines.append(f"Orang: {', '.join(names)}")
        lines.append(f"<span style='color:#888'>{photo['path']}</span>")
        self.info_label.setText("<br>".join(lines))
        self.star_widget.set_rating(photo.get("rating", 0))
        self._refresh_tags_label()

    def _refresh_tags_label(self):
        if not self.current_photo:
            return
        tags = self.db.tags_for(self.current_photo["id"])
        self.tags_label.setText(", ".join(tags) if tags else "—")

    def _on_rating_changed(self, value: int):
        # Tulis balik ke data item agar rating tetap saat foto dipilih ulang
        # (data item bisa berupa salinan, jadi harus di-setData lagi).
        for it in self.gallery.selectedItems():
            photo = it.data(PHOTO_ROLE)
            photo["rating"] = value
            it.setData(PHOTO_ROLE, photo)
            self.db.set_rating(photo["id"], value)
        if self.current_photo is not None:
            self.current_photo["rating"] = value

    def _add_tag(self):
        if not self.current_photo:
            return
        name = self.tag_input.text().strip()
        if not name:
            return
        for photo in self._selected_photos():
            self.db.add_tag(photo["id"], name)
        self.tag_input.clear()
        self._refresh_tags_label()
        self._reload_tag_filter()

    def _remove_tag(self):
        if not self.current_photo:
            return
        tags = self.db.tags_for(self.current_photo["id"])
        if not tags:
            return
        name, ok = QInputDialog.getItem(
            self, "Hapus Tag", "Pilih tag untuk dihapus:", tags, 0, False)
        if ok and name:
            for photo in self._selected_photos():
                self.db.remove_tag(photo["id"], name)
            self._refresh_tags_label()
            self._reload_tag_filter()

    def _open_external(self, item: QListWidgetItem):
        photo = item.data(PHOTO_ROLE)
        try:
            os.startfile(photo["path"])  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            pass

    # --------------------------------------------------------- operations
    def _targets_for_operation(self) -> list[dict]:
        """Foto yang dipilih, atau semua yang tampil bila tak ada seleksi."""
        selected = self._selected_photos()
        if selected:
            return selected
        return [self.gallery.item(i).data(PHOTO_ROLE)
                for i in range(self.gallery.count())]

    def organize_dialog(self):
        targets = self._targets_for_operation()
        if not targets:
            QMessageBox.information(self, APP_NAME, "Tidak ada foto untuk disusun.")
            return
        dlg = OrganizeDialog(len(targets), self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        if not vals["target"]:
            QMessageBox.warning(self, APP_NAME, "Folder tujuan belum dipilih.")
            return
        moved = organize_by_date(
            targets, Path(vals["target"]), vals["pattern"], vals["move"])
        if vals["move"]:
            for pid, _old, new in moved:
                self.db.update_path(pid, new)
            self.db.commit()
        self.refresh_gallery()
        QMessageBox.information(
            self, APP_NAME,
            f"{len(moved)} foto berhasil "
            f"{'dipindahkan' if vals['move'] else 'disalin'}.")

    def rename_dialog(self):
        targets = self._targets_for_operation()
        if not targets:
            QMessageBox.information(self, APP_NAME, "Tidak ada foto untuk diganti nama.")
            return
        dlg = RenameDialog(targets[0], len(targets), self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        renamed = bulk_rename(targets, vals["template"], vals["start"])
        for pid, _old, new in renamed:
            self.db.update_path(pid, new)
        self.db.commit()
        self.refresh_gallery()
        QMessageBox.information(
            self, APP_NAME, f"{len(renamed)} foto berhasil diganti namanya.")

    def find_duplicates(self):
        rows = self.db.all_with_phash()
        if not rows:
            QMessageBox.information(
                self, APP_NAME, "Belum ada foto terindeks. Tambah folder dulu.")
            return
        self.status.showMessage("Menganalisis duplikat…")
        QApplication.processEvents()
        groups = find_duplicate_groups(rows, threshold=5)
        self.status.clearMessage()
        if not groups:
            QMessageBox.information(
                self, APP_NAME, "Tidak ditemukan foto duplikat/mirip. 🎉")
            return
        dlg = DuplicatesDialog(groups, self.cache_dir, self)
        dlg.exec()
        if dlg.deleted_ids:
            for pid in dlg.deleted_ids:
                self.db.delete_photo(pid)
            self.refresh_sidebar()
            self.refresh_gallery()

    # --------------------------------------------------- gambar tidak penting
    def detect_junk(self):
        if self.quality_worker and self.quality_worker.isRunning():
            return
        total = len(self.db.query_photos(media_type="photo"))
        if total == 0:
            QMessageBox.information(
                self, APP_NAME, "Belum ada foto untuk dianalisis.")
            return
        self.progress.show()
        self.progress.setRange(0, total)
        self.status.showMessage("Menganalisis kualitas gambar…")
        self.quality_worker = QualityWorker(self.db)
        self.quality_worker.progress.connect(self._on_quality_progress)
        self.quality_worker.finished_quality.connect(self._on_quality_done)
        self.quality_worker.start()

    def _on_quality_progress(self, cur: int, total: int, name: str):
        self.progress.setRange(0, total)
        self.progress.setValue(cur)
        self.status.showMessage(f"Menganalisis {cur}/{total}: {name}")

    def _on_quality_done(self, results: list):
        self.progress.hide()
        self.status.showMessage(
            f"Selesai. {len(results)} gambar berpotensi tidak penting.", 6000)
        if not results:
            QMessageBox.information(
                self, APP_NAME,
                "Tidak ada gambar 'tidak penting' yang terdeteksi. 🎉")
            return
        dlg = JunkDialog(results, self.cache_dir, self)
        if dlg.exec() == QDialog.Accepted and dlg.chosen_ids:
            self.staged.update(dlg.chosen_ids)
            self.db.set_staged(dlg.chosen_ids, True)
            self.refresh_sidebar()
            self.refresh_gallery()
            self.status.showMessage(
                f"{len(dlg.chosen_ids)} gambar dipindahkan ke 'Dihapus'.", 6000)

    # ----------------------------------------------------------- albums
    def new_album(self):
        name, ok = QInputDialog.getText(self, "Album Baru", "Nama album:")
        if not (ok and name.strip()):
            return
        aid = self.db.create_album(name.strip())
        targets = self._selected_photos()
        if targets:
            self.db.add_to_album(aid, [p["id"] for p in targets])
            QMessageBox.information(
                self, APP_NAME,
                f"Album '{name}' dibuat dengan {len(targets)} media.")
        else:
            QMessageBox.information(self, APP_NAME, f"Album '{name}' dibuat.")
        self.refresh_sidebar()

    def _album_context(self, spec: dict):
        """Klik ganda album: opsi export / ganti nama / hapus."""
        menu = QMenu(self)
        act_export = menu.addAction("📤 Export album…")
        menu.addSeparator()
        act_ren = menu.addAction("✏️ Ganti nama album…")
        act_del = menu.addAction("🗑️ Hapus album")
        act = menu.exec(self.cursor().pos())
        if act == act_export:
            self.export_album(spec["album_id"], spec.get("album_name", "Album"))
        elif act == act_ren:
            name, ok = QInputDialog.getText(
                self, "Ganti Nama Album", "Nama baru:",
                text=spec.get("album_name", ""))
            if ok and name.strip():
                self.db.rename_album(spec["album_id"], name.strip())
                self.refresh_sidebar()
        elif act == act_del:
            self.db.delete_album(spec["album_id"])
            if self.current_filter.get("album_id") == spec["album_id"]:
                self.current_filter = {"kind": "all"}
                self.refresh_gallery()
            self.refresh_sidebar()

    def _export_media(self, media, default_name: str):
        """Salin/pindahkan kumpulan media ke folder bernama `default_name`.

        Dipakai bersama oleh export album, orang, dan lokasi.
        """
        media = [dict(m) for m in media]
        if not media:
            QMessageBox.information(
                self, APP_NAME, f"'{default_name}' tidak punya media untuk diekspor.")
            return

        folder = safe_folder_name(default_name)
        box = QMessageBox(self)
        box.setWindowTitle("Export")
        box.setIcon(QMessageBox.Question)
        box.setText(f"Export {len(media)} media ('{default_name}')?")
        box.setInformativeText(
            f"File akan diletakkan di sub-folder '{folder}' di lokasi tujuan.\n"
            "• Salin: file asli tetap ada.\n"
            "• Pindahkan: file asli dipindah (indeks diperbarui otomatis).")
        copy_btn = box.addButton("Salin", QMessageBox.AcceptRole)
        move_btn = box.addButton("Pindahkan", QMessageBox.DestructiveRole)
        box.addButton("Batal", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == copy_btn:
            move = False
        elif clicked == move_btn:
            move = True
        else:
            return

        parent_dir = QFileDialog.getExistingDirectory(
            self, "Pilih folder tujuan export")
        if not parent_dir:
            return
        target = Path(parent_dir) / folder

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.status.showMessage(f"Mengekspor '{default_name}'…")
        try:
            results = export_to_folder(
                media, target, move=move,
                progress=lambda c, t, n: (
                    self.status.showMessage(f"Export {c}/{t}: {n}"),
                    QApplication.processEvents()),
            )
        finally:
            QApplication.restoreOverrideCursor()

        if move and results:
            for pid, _old, new in results:
                self.db.update_path(pid, new)
            self.db.commit()
            self.refresh_sidebar()
            self.refresh_gallery()

        verb = "dipindahkan" if move else "disalin"
        self.status.showMessage(f"{len(results)} media {verb} ke {target}", 8000)
        ans = QMessageBox.information(
            self, APP_NAME,
            f"'{default_name}': {len(results)} media {verb} ke:\n{target}\n\n"
            "Buka folder hasil export?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ans == QMessageBox.Yes:
            try:
                os.startfile(str(target))  # type: ignore[attr-defined]
            except (OSError, AttributeError):
                pass

    def export_album(self, album_id: int, album_name: str):
        self._export_media(self.db.query_photos(album_id=album_id), album_name)

    def _gallery_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        targets = self._selected_photos()
        if not targets:
            return
        menu = QMenu(self)
        add_menu = menu.addMenu(f"➕ Tambahkan {len(targets)} ke album")
        albums = self.db.albums_with_counts()
        if albums:
            for aid, name, _c in albums:
                act = add_menu.addAction(name)
                act.setData(("add", aid))
        else:
            add_menu.addAction("(belum ada album)").setEnabled(False)
        add_menu.addSeparator()
        new_act = add_menu.addAction("📚 Album baru…")
        new_act.setData(("new", 0))

        cur_album = self.current_filter.get("album_id", 0)
        remove_act = None
        if cur_album:
            remove_act = menu.addAction("➖ Keluarkan dari album ini")
        menu.addSeparator()
        open_act = menu.addAction("📂 Buka file")
        menu.addSeparator()
        n = len(targets)
        stage_act = menu.addAction(
            f"🗑️ Hapus dari indeks → 'Dihapus' ({n})\tDel")
        del_trash_act = None
        if _send2trash:
            del_trash_act = menu.addAction(
                f"♻️ Pindahkan ke Recycle Bin ({n})\tShift+Del")
        del_perm_act = menu.addAction(
            f"❌ Hapus permanen dari disk ({n})\tCtrl+Del")

        chosen = menu.exec(self.gallery.mapToGlobal(pos))
        if not chosen:
            return
        ids = [p["id"] for p in targets]
        data = chosen.data()
        if data and data[0] == "add":
            self.db.add_to_album(data[1], ids)
            self.refresh_sidebar()
            self.status.showMessage(f"{len(ids)} media ditambahkan ke album.", 4000)
        elif data and data[0] == "new":
            self.new_album()
        elif chosen == remove_act:
            self.db.remove_from_album(cur_album, ids)
            self.refresh_sidebar()
            self.refresh_gallery()
        elif chosen == open_act:
            self._open_external(self.gallery.selectedItems()[0])
        elif chosen == stage_act:
            self.stage_selected()
        elif del_trash_act is not None and chosen == del_trash_act:
            self.delete_selected("trash")
        elif chosen == del_perm_act:
            self.delete_selected("permanent")

    # -------------------------------------------------- hapus & tampungan
    def _build_staging_bar(self) -> QWidget:
        """Bilah aksi yang tampil saat membuka Tampungan Hapus."""
        self.staging_bar = QWidget()
        self.staging_bar.setObjectName("FilterBar")
        h = QHBoxLayout(self.staging_bar)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(8)
        self.staging_label = QLabel("")
        self.staging_label.setToolTip(
            "Aksi berlaku ke item yang dipilih, atau semua isi 'Dihapus' "
            "bila tak ada yang dipilih.")
        h.addWidget(self.staging_label)
        h.addStretch(1)

        b_idx = QPushButton("🗑️ Hapus dari indeks")
        b_idx.clicked.connect(lambda: self._staging_delete("index"))
        b_trash = QPushButton("♻️ Recycle Bin")
        b_trash.clicked.connect(lambda: self._staging_delete("trash"))
        if not _send2trash:
            b_trash.setEnabled(False)
        b_perm = QPushButton("❌ Permanen")
        b_perm.setObjectName("Danger")
        b_perm.clicked.connect(lambda: self._staging_delete("permanent"))
        b_out = QPushButton("↩️ Keluarkan")
        b_out.clicked.connect(self._staging_unstage)
        b_clear = QPushButton("Kosongkan")
        b_clear.clicked.connect(self._staging_clear)
        for b in (b_idx, b_trash, b_perm, b_out, b_clear):
            h.addWidget(b)
        self.staging_bar.hide()
        return self.staging_bar

    def stage_selected(self):
        """Tombol Delete: masukkan media terpilih ke Tampungan Hapus."""
        photos = self._selected_photos()
        if not photos:
            return
        ids = [p["id"] for p in photos]
        self.staged.update(ids)
        self.db.set_staged(ids, True)
        self.current_photo = None
        self.refresh_sidebar()
        self.refresh_gallery()   # item langsung hilang dari tampilan saat ini
        self.status.showMessage(
            f"{len(photos)} media dipindahkan ke 'Dihapus' (total {len(self.staged)}). "
            "Buka '🗑️ Dihapus' di sidebar untuk memprosesnya.", 7000)

    def delete_selected(self, mode: str = "index"):
        """Hapus media terpilih langsung (shortcut Shift/Ctrl + menu klik-kanan)."""
        self._delete_photos(self._selected_photos(), mode)

    def _delete_photos(self, photos, mode: str) -> int:
        """Inti operasi hapus untuk sekumpulan media.

        mode: 'index' (indeks saja) | 'trash' (Recycle Bin) | 'permanent'.
        Mengembalikan jumlah yang berhasil diproses.
        """
        photos = [dict(p) for p in photos]
        if not photos:
            return 0
        n = len(photos)

        if mode == "trash" and not _send2trash:
            QMessageBox.warning(
                self, APP_NAME,
                "Paket 'send2trash' tidak terpasang. Jalankan: pip install send2trash")
            return 0
        if mode == "permanent":
            ans = QMessageBox.warning(
                self, "Konfirmasi Hapus Permanen",
                f"Hapus PERMANEN {n} file dari disk?\n"
                "Tindakan ini tidak bisa dibatalkan.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return 0

        failed = 0
        for p in photos:
            if mode == "permanent":
                try:
                    os.remove(p["path"])
                except FileNotFoundError:
                    pass               # file sudah tidak ada, tetap bersihkan indeks
                except OSError:
                    failed += 1
                    continue
            elif mode == "trash":
                try:
                    _send2trash(os.path.abspath(p["path"]))
                except FileNotFoundError:
                    pass
                except Exception:      # noqa: BLE001
                    failed += 1
                    continue
            self.db.delete_photo(p["id"])
            self.staged.discard(p["id"])

        self.current_photo = None
        self.refresh_sidebar()
        self.refresh_gallery()
        if mode == "permanent":
            msg = f"{n - failed} file dihapus permanen."
        elif mode == "trash":
            msg = f"{n - failed} file dipindahkan ke Recycle Bin."
        else:
            msg = f"{n - failed} media dihapus dari indeks (file asli tetap)."
        if failed:
            msg += f" {failed} gagal."
        self.status.showMessage(msg, 6000)
        return n - failed

    def _staged_photos(self) -> list:
        if not self.staged:
            return []
        return self.db.query_photos(ids=list(self.staged), exclude_staged=False)

    def _staging_targets(self) -> list:
        """Item terpilih di galeri, atau seluruh isi tampungan bila tak ada."""
        sel = self._selected_photos()
        return sel if sel else self._staged_photos()

    def _staging_delete(self, mode: str):
        self._delete_photos(self._staging_targets(), mode)

    def _staging_unstage(self):
        targets = self._staging_targets()
        if not targets:
            return
        ids = [p["id"] for p in targets]
        for i in ids:
            self.staged.discard(i)
        self.db.set_staged(ids, False)
        self.refresh_sidebar()
        self.refresh_gallery()
        self.status.showMessage(
            f"{len(targets)} media dikeluarkan dari tampungan.", 4000)

    def _staging_clear(self):
        if not self.staged:
            return
        self.staged.clear()
        self.db.clear_staged()
        if self.current_filter.get("kind") == "staged":
            self.current_filter = {"kind": "all"}
        self.refresh_sidebar()
        self.refresh_gallery()
        self.status.showMessage("Tampungan dikosongkan.", 4000)

    # ----------------------------------------------------------- faces
    def scan_faces(self):
        if not models_available():
            QMessageBox.warning(
                self, APP_NAME,
                "Model wajah tidak ditemukan. Pastikan folder 'models' berisi "
                "file YuNet & SFace.")
            return
        if self.face_worker and self.face_worker.isRunning():
            return
        pending = len(self.db.needs_face_scan())
        if pending == 0:
            QMessageBox.information(
                self, APP_NAME,
                "Semua foto sudah dipindai wajah. Kelompok orang ada di sidebar.")
            return
        self.progress.show()
        self.progress.setRange(0, pending)
        self.status.showMessage("Memindai wajah…")
        self.act_faces.setEnabled(False)
        self.face_worker = FaceWorker(self.db)
        self.face_worker.progress.connect(self._on_face_progress)
        self.face_worker.finished_faces.connect(self._on_faces_done)
        self.face_worker.start()

    def _on_face_progress(self, cur: int, total: int, phase: str):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(cur)
        self.status.showMessage(f"{phase} ({cur}/{total})")

    def _on_faces_done(self, num_faces: int, num_persons: int):
        self.progress.hide()
        self.act_faces.setEnabled(True)
        self.status.showMessage(
            f"Selesai. {num_faces} wajah, {num_persons} orang terdeteksi.", 6000)
        self.refresh_sidebar()

    # ----------------------------------------------------------- bantuan
    def show_help(self):
        HelpDialog(self).exec()

    def show_about(self):
        AboutDialog(self).exec()

    # ----------------------------------------------------------- penyimpanan
    def _stop_workers(self):
        for w in (self.thumb_worker, self.scan_worker, self.face_worker,
                  self.geo_worker, self.quality_worker):
            if w and w.isRunning():
                w.stop()
                w.wait(3000)

    @property
    def _db_file(self) -> Path:
        return self.data_dir / "library.db"

    def change_storage_dir(self):
        """Pindahkan lokasi penyimpanan database (untuk portabilitas)."""
        d = QFileDialog.getExistingDirectory(
            self, "Pilih folder penyimpanan data")
        if not d:
            return None
        new = Path(d)
        if new.resolve() == self.data_dir.resolve():
            return str(self.data_dir)
        new.mkdir(parents=True, exist_ok=True)
        target_db = new / "library.db"
        use_existing = False
        if target_db.exists():
            ans = QMessageBox.question(
                self, APP_NAME,
                "Folder ini sudah berisi database Photo Organizer.\n"
                "Gunakan database yang sudah ada di sana?\n"
                "(No = batal)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ans != QMessageBox.Yes:
                return None
            use_existing = True

        self._stop_workers()
        old_db = self._db_file
        old_thumb = self.cache_dir
        self.db.close()
        try:
            if not use_existing:
                shutil.move(str(old_db), str(target_db))
                if old_thumb.exists() and not (new / "thumbnails").exists():
                    shutil.move(str(old_thumb), str(new / "thumbnails"))
        except (OSError, shutil.Error) as exc:
            QMessageBox.warning(self, APP_NAME, f"Gagal memindahkan data: {exc}")

        self.data_dir = new
        self.cache_dir = new / "thumbnails"
        self.db = Database(target_db)
        self.settings.setValue("storage/db_dir", str(new))
        self.staged = self.db.staged_ids()
        self.current_filter = {"kind": "all"}
        self.current_photo = None
        self.refresh_sidebar()
        self.refresh_gallery()
        QMessageBox.information(
            self, APP_NAME, f"Penyimpanan data sekarang di:\n{new}")
        return str(new)

    def export_database(self):
        """Salin database saat ini ke berkas pilihan pengguna."""
        self.db.commit()
        fn, _ = QFileDialog.getSaveFileName(
            self, "Export Database", "photo_organizer_backup.db",
            "Database SQLite (*.db)")
        if not fn:
            return
        try:
            shutil.copy2(str(self._db_file), fn)
            QMessageBox.information(self, APP_NAME, f"Database diekspor ke:\n{fn}")
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Gagal export: {exc}")

    def import_database(self):
        """Ganti database saat ini dengan berkas pilihan (dengan cadangan)."""
        fn, _ = QFileDialog.getOpenFileName(
            self, "Import Database", "", "Database SQLite (*.db)")
        if not fn:
            return
        ans = QMessageBox.warning(
            self, APP_NAME,
            "Impor akan MENGGANTI database saat ini dengan berkas terpilih.\n"
            "Database sekarang dicadangkan ke 'library.db.bak'. Lanjutkan?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        self._stop_workers()
        self.db.close()
        db_file = self._db_file
        try:
            if db_file.exists():
                shutil.copy2(str(db_file), str(db_file) + ".bak")
            shutil.copy2(fn, str(db_file))
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Gagal import: {exc}")
        self.db = Database(db_file)
        self.clear_thumbnail_cache()         # thumbnail lama mungkin tak relevan
        self.staged = self.db.staged_ids()
        self.current_filter = {"kind": "all"}
        self.current_photo = None
        self.refresh_sidebar()
        self.refresh_gallery()
        QMessageBox.information(
            self, APP_NAME,
            "Database diimpor. Klik '🔄 Pindai Ulang' bila lokasi file berbeda.")

    # ----------------------------------------------------------- settings
    def open_settings(self):
        mode = self.settings.value("theme/mode", DEFAULT_MODE, type=str)
        accent = self.settings.value("theme/accent", DEFAULT_ACCENT, type=str)
        dlg = SettingsDialog(
            mode, accent,
            on_reset_index=self.reset_index,
            on_clear_cache=self.clear_thumbnail_cache,
            storage_dir=str(self.data_dir),
            on_change_storage=self.change_storage_dir,
            on_export_db=self.export_database,
            on_import_db=self.import_database,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.values()
            self.settings.setValue("theme/mode", vals["mode"])
            self.settings.setValue("theme/accent", vals["accent"])
            apply_theme(QApplication.instance(), vals["mode"], vals["accent"])
            self.status.showMessage("Tema diperbarui.", 4000)

    def clear_thumbnail_cache(self) -> int:
        """Hapus semua thumbnail di cache. Kembalikan jumlah berkas dihapus."""
        n = 0
        if self.cache_dir.exists():
            for f in self.cache_dir.glob("*.jpg"):
                try:
                    f.unlink()
                    n += 1
                except OSError:
                    pass
        return n

    def reset_index(self):
        """Hentikan worker, kosongkan indeks DB, dan bersihkan cache thumbnail."""
        for w in (self.thumb_worker, self.scan_worker, self.face_worker,
                  self.geo_worker, self.quality_worker):
            if w and w.isRunning():
                w.stop()
                w.wait(3000)
        self.db.reset_index()
        self.clear_thumbnail_cache()
        self.staged.clear()
        self.current_filter = {"kind": "all"}
        self.current_photo = None
        self.refresh_sidebar()
        self.refresh_gallery()

    def _rename_person(self, spec: dict):
        name, ok = QInputDialog.getText(
            self, "Beri Nama Orang", "Nama orang ini:",
            text=spec.get("person_name") or "")
        if ok and name.strip():
            self.db.rename_person(spec["person_id"], name.strip())
            self.refresh_sidebar()

    def _person_context(self, spec: dict):
        """Klik ganda orang: opsi export / beri nama."""
        menu = QMenu(self)
        act_export = menu.addAction("📤 Export foto orang ini…")
        menu.addSeparator()
        act_ren = menu.addAction("✏️ Beri / ganti nama…")
        act = menu.exec(self.cursor().pos())
        if act == act_export:
            name = spec.get("person_name") or f"Orang_{spec['person_id']}"
            self._export_media(
                self.db.query_photos(person_id=spec["person_id"]), name)
        elif act == act_ren:
            self._rename_person(spec)

    def _location_context(self, spec: dict):
        """Klik ganda lokasi: export foto di tempat itu."""
        menu = QMenu(self)
        act_export = menu.addAction("📤 Export foto lokasi ini…")
        act = menu.exec(self.cursor().pos())
        if act == act_export:
            name = spec.get("label") or "Lokasi"
            self._export_media(self.db.query_photos(ids=spec.get("ids")), name)

    def closeEvent(self, event):
        for w in (self.thumb_worker, self.scan_worker, self.face_worker,
                  self.geo_worker, self.quality_worker):
            if w and w.isRunning():
                w.stop()
                w.wait(3000)
        self.db.close()
        super().closeEvent(event)


def main():
    # Disarankan untuk QtWebEngine (peta tertanam) — harus sebelum QApplication.
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(asset_path("icon.png"))))
    s = portable_settings()
    mode = s.value("theme/mode", DEFAULT_MODE, type=str)
    accent = s.value("theme/accent", DEFAULT_ACCENT, type=str)
    apply_theme(app, mode, accent)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
