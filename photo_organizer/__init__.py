"""Photo Organizer - aplikasi desktop untuk mengorganisir foto."""

import os as _os

# Diamkan log native OpenCV (harus diset sebelum cv2 di-import).
_os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")

__version__ = "1.0.0"
APP_NAME = "Photo Organizer"
