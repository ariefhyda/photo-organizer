"""Tema modern (QSS) yang bisa dikonfigurasi: mode gelap/terang + warna aksen."""

from __future__ import annotations

# Pilihan warna aksen preset (nama -> hex).
ACCENTS = {
    "Biru":   "#6c8cff",
    "Hijau":  "#3ecf8e",
    "Ungu":   "#a974ff",
    "Oranye": "#ff9f43",
    "Merah":  "#ff6b6b",
    "Tosca":  "#21c7c7",
}
DEFAULT_ACCENT = "#6c8cff"
DEFAULT_MODE = "dark"

# Palet per mode.
PALETTES = {
    "dark": {
        "BG": "#16171b", "PANEL": "#202127", "ELEV": "#2a2b33",
        "ELEV_HOVER": "#34353d", "ELEV_PRESS": "#3f404a", "BORDER": "#2c2d34",
        "TEXT": "#e7e8ea", "TEXT_DIM": "#9aa0aa", "ITEM_HOVER": "#21222a",
        "SCROLL": "#34353d", "SCROLL_HOVER": "#4b4c58",
        "DISABLED_TEXT": "#6b6e76", "DISABLED_BG": "#24252b",
        "STAGE_BG": "#16171b", "DANGER": "#ff6b6b",
    },
    "light": {
        "BG": "#f3f4f6", "PANEL": "#ffffff", "ELEV": "#eceef2",
        "ELEV_HOVER": "#e2e5ea", "ELEV_PRESS": "#d6dae1", "BORDER": "#d7dae0",
        "TEXT": "#1f2128", "TEXT_DIM": "#6b7280", "ITEM_HOVER": "#eef1f6",
        "SCROLL": "#cfd3da", "SCROLL_HOVER": "#b8bdc6",
        "DISABLED_TEXT": "#aab0bb", "DISABLED_BG": "#eceef2",
        "STAGE_BG": "#1b1c20", "DANGER": "#e03131",
    },
}


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lighten(hex_color: str, amount: float = 0.18) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _accent_soft(hex_color: str, mode: str) -> str:
    """Warna latar lembut dari aksen untuk seleksi item galeri."""
    r, g, b = _hex_to_rgb(hex_color)
    if mode == "dark":
        # campur ke arah panel gelap
        return f"#{int(r*0.35+20):02x}{int(g*0.35+22):02x}{int(b*0.35+30):02x}"
    return _lighten(hex_color, 0.78)


def build_stylesheet(mode: str = DEFAULT_MODE,
                     accent: str = DEFAULT_ACCENT) -> str:
    p = dict(PALETTES.get(mode, PALETTES["dark"]))
    p["ACCENT"] = accent
    p["ACCENT_HOVER"] = _lighten(accent, 0.16)
    p["ACCENT_SOFT"] = _accent_soft(accent, mode)
    return _TEMPLATE.format(**p)


_TEMPLATE = """
* {{
    font-family: "Segoe UI", "Inter", "Roboto", sans-serif;
    font-size: 10.5pt;
}}
QWidget {{ background: {BG}; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QLabel {{ background: transparent; }}

/* ---------- Toolbar ---------- */
QToolBar#MainToolbar {{
    background: {PANEL}; border: none; padding: 8px 10px; spacing: 4px;
}}
QToolBar#MainToolbar QToolButton {{
    background: transparent; color: {TEXT};
    padding: 8px 13px; border-radius: 9px; font-weight: 500;
}}
QToolBar#MainToolbar QToolButton:hover {{ background: {ELEV}; }}
QToolBar#MainToolbar QToolButton:pressed {{ background: {ELEV_HOVER}; }}
QToolBar#MainToolbar QToolButton:disabled {{ color: {DISABLED_TEXT}; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; margin: 6px 8px; }}

/* ---------- Sidebar ---------- */
#Sidebar {{ background: {PANEL}; border: none; outline: 0; padding: 6px 4px; }}
#Sidebar::item {{
    padding: 8px 8px; border-radius: 9px; margin: 1px 4px; color: {TEXT_DIM};
}}
#Sidebar::item:hover {{ background: {ELEV}; color: {TEXT}; }}
#Sidebar::item:selected {{ background: {ACCENT}; color: white; }}

/* ---------- Galeri ---------- */
#Gallery {{ background: {BG}; border: none; outline: 0; padding: 8px; }}
#Gallery::item {{ color: {TEXT_DIM}; border-radius: 12px; padding: 8px; }}
#Gallery::item:hover {{ background: {ITEM_HOVER}; }}
#Gallery::item:selected {{
    background: {ACCENT_SOFT}; border: 1px solid {ACCENT}; color: {TEXT};
}}

/* ---------- Filter bar & panel detail ---------- */
#FilterBar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
#DetailPanel {{ background: {PANEL}; border-left: 1px solid {BORDER}; }}

/* ---------- Input ---------- */
QLineEdit, QComboBox, QSpinBox {{
    background: {ELEV}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 7px 10px; color: {TEXT};
    selection-background-color: {ACCENT}; selection-color: white;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
    selection-background-color: {ACCENT}; outline: 0; padding: 4px;
}}

/* ---------- Tombol ---------- */
QPushButton {{
    background: {ELEV}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 8px 15px; color: {TEXT}; font-weight: 500;
}}
QPushButton:hover {{ background: {ELEV_HOVER}; }}
QPushButton:pressed {{ background: {ELEV_PRESS}; }}
QPushButton:disabled {{ color: {DISABLED_TEXT}; background: {DISABLED_BG}; }}
QPushButton#Primary {{ background: {ACCENT}; border: none; color: white; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Danger {{ color: {DANGER}; font-weight: 600; }}

/* ---------- Tree ---------- */
QTreeWidget {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; outline: 0;
}}
QTreeWidget::item {{ padding: 6px 4px; border-radius: 6px; }}
QTreeWidget::item:selected {{ background: {ACCENT}; color: white; }}
QHeaderView::section {{
    background: {PANEL}; color: {TEXT_DIM}; padding: 7px;
    border: none; border-right: 1px solid {BORDER};
}}

/* ---------- Scrollbar ---------- */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 3px; }}
QScrollBar::handle:vertical {{ background: {SCROLL}; border-radius: 5px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {SCROLL_HOVER}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 3px; }}
QScrollBar::handle:horizontal {{ background: {SCROLL}; border-radius: 5px; min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- Status & progress ---------- */
QStatusBar {{ background: {PANEL}; color: {TEXT_DIM}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
QProgressBar {{
    background: {ELEV}; border: none; border-radius: 7px;
    text-align: center; color: {TEXT}; height: 16px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 7px; }}

/* ---------- Menu ---------- */
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 7px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 6px 10px; }}

/* ---------- Lain-lain ---------- */
QToolTip {{
    background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 6px 8px; border-radius: 7px;
}}
QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QRadioButton, QCheckBox {{ background: transparent; spacing: 8px; }}
"""

# Latar "panggung" untuk pratinjau foto (selalu gelap, seperti viewer foto).
def stage_style(mode: str = DEFAULT_MODE) -> str:
    p = PALETTES.get(mode, PALETTES["dark"])
    return (f"background:{p['STAGE_BG']}; color:#9aa0aa;"
            f"border:1px solid {p['BORDER']}; border-radius:10px; padding:6px;")


def apply_theme(app, mode: str = DEFAULT_MODE, accent: str = DEFAULT_ACCENT):
    """Terapkan style Fusion + QSS sesuai mode & aksen."""
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet(mode, accent))
