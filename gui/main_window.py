import os
import shutil
import json
from collections import deque
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QLabel, QComboBox, QPushButton, QCheckBox,
    QFileDialog, QMessageBox, QListWidgetItem,
    QToolButton, QMenu, QWidgetAction, QGroupBox, QDialog, QDialogButtonBox,
    QFormLayout, QSlider, QSizePolicy, QButtonGroup, QStyle,
    QApplication, QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPoint, QPointF, QEvent, QSize
from PyQt6.QtGui import (QAction, QKeySequence, QShortcut, QColor,
                          QIcon, QPixmap, QImage, QTransform, QCursor, QPainter)

from core.config_io import DatasetConfig
from core.annotation_io import load_annotations, save_annotations, get_images, get_label_path
from core.models import IMAGE_EXTENSIONS
from core.image_ops import (recalc_annotations_crop, recalc_annotations_rotate,
                            recalc_annotations_mosaic)
from core.folder_detect import detect_folder, execute_normalization
from gui.editor.viewer import ImageViewer
from gui.editor.items import BBoxItem, SegmentItem, class_color, set_label_px
from gui.editor.image_list_widget import ImageListWidget
from gui.style import SPLIT_COLORS, TEXT, TEXT_DIM, DANGER, PANEL3
from gui.dialogs.folder_import_dialog import FolderImportDialog

# ─── SVG icon helpers ─────────────────────────────────────────────────────────

try:
    from PyQt6.QtSvg import QSvgRenderer as _QSvgRenderer
    _SVG_OK = True
except ImportError:
    _SVG_OK = False

_ICON_PATHS = {
    "folder": ("M3 6.5A1.5 1.5 0 0 1 4.5 5H8l1.5 1.8H19.5A1.5 1.5 0 0 1 21 8.3"
               "v9.2A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"),
    "save":   "M5 4h11l3 3v13H5zM9 4v5h6V4M8 14h8v6H8z",
    "undo":   "M9 7L4 12l5 5M4 12h11a5 5 0 0 1 0 10h-2",
    "redo":   "M15 7l5 5-5 5M20 12H9a5 5 0 0 0 0 10h2",
    "gear":   ("M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2l1.5 2.5 2.8-.6.6 2.8"
               "L20 9l-1.6 2.4L20 14l-3.1 1.3-.6 2.8-2.8-.6L12 20l-1.5-2.1"
               "-2.8.6-.6-2.8L4 14l1.6-2L4 9l3.1-1.3.6-2.8 2.8.6z"),
    "trash":  "M3 6h18M8 6V4h8v2M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M10 11v6M14 11v6",
    "copy":   "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1M11 9h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2z",
}


def _svg_icon(name: str, size: int = 16, color: str = "#c2c4c9") -> "QIcon | None":
    """Create a QIcon from a design-spec SVG path (returns None if QtSvg unavailable)."""
    if not _SVG_OK:
        return None
    from PyQt6.QtCore import QByteArray
    from PyQt6.QtGui import QPainter
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{_ICON_PATHS.get(name, "")}"/></svg>'
    )
    renderer = _QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)


def _png_icon(path: Path, size: int = 16, color: str = "#c2c4c9") -> "QIcon | None":
    """Load PNG, make white background transparent, tint to color."""
    img = QImage(str(path))
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    h = color.lstrip("#")
    tr, tg, tb = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())
    buf = bytearray(bytes(ptr))
    for i in range(0, len(buf), 4):           # BGRA on little-endian
        b, g, r = buf[i], buf[i + 1], buf[i + 2]
        brightness = (r + g + b) // 3
        alpha = max(0, 255 - brightness)       # white→transparent, dark→opaque
        buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = tb, tg, tr, alpha
    buf_bytes = bytes(buf)
    colored = QImage(buf_bytes, img.width(), img.height(),
                     img.bytesPerLine(), QImage.Format.Format_ARGB32).copy()
    pix = QPixmap.fromImage(colored).scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.drawPixmap((size - pix.width()) // 2, (size - pix.height()) // 2, pix)
    painter.end()
    return QIcon(out)


_ICONS_DIR = Path(__file__).parent / "icons"

HISTORY_FILE   = Path.home() / '.yololabel_history.json'
HISTORY_LIMIT  = 10
SETTINGS_FILE  = Path.home() / '.yololabel_settings.json'
PROGRESS_FILE  = Path.home() / '.yololabel_progress.json'


class ImgStatus(Enum):
    UNVIEWED = "unviewed"
    VIEWED   = "viewed"
    SAVED    = "saved"


class SettingsDialog(QDialog):
    def __init__(self, current: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.setFixedSize(320, 265)
        layout = QVBoxLayout(self)

        mouse_group = QGroupBox("Кнопки мыши")
        mg = QFormLayout(mouse_group)
        self._pan_combo = QComboBox()
        self._pan_combo.addItems(["Правая кнопка", "Средняя кнопка"])
        self._pan_combo.setCurrentIndex(0 if current.get("pan_button","right") == "right" else 1)
        self._pan_combo.setToolTip("Перемещение изображения в области просмотра")
        mg.addRow("Перемещать:", self._pan_combo)
        self._fit_combo = QComboBox()
        self._fit_combo.addItems(["Средняя кнопка", "Правая кнопка"])
        self._fit_combo.setCurrentIndex(0 if current.get("fit_button","middle") == "middle" else 1)
        self._fit_combo.setToolTip("Выровнять изображение в области просмотра")
        mg.addRow("Выровнять:", self._fit_combo)
        layout.addWidget(mouse_group)

        edit_group = QGroupBox("Редактирование")
        eg = QFormLayout(edit_group)
        self._confirm_del_cb = QCheckBox()
        self._confirm_del_cb.setChecked(current.get("confirm_delete", True))
        self._confirm_del_cb.setToolTip("Подтверждать удаление файла")
        eg.addRow("Подтверждать удаление:", self._confirm_del_cb)

        self._mosaic_step_spin = QSpinBox()
        self._mosaic_step_spin.setRange(1, 100)
        self._mosaic_step_spin.setValue(current.get("mosaic_step", 20))
        self._mosaic_step_spin.setSuffix(" %")
        self._mosaic_step_spin.setToolTip(
            "Разница масштаба между минимальным и максимальным размером объекта")
        eg.addRow("Шаг мозаики:", self._mosaic_step_spin)
        layout.addWidget(edit_group)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_settings(self) -> dict:
        return {
            "pan_button": "right" if self._pan_combo.currentIndex() == 0 else "middle",
            "fit_button": "middle" if self._fit_combo.currentIndex() == 0 else "right",
            "confirm_delete": self._confirm_del_cb.isChecked(),
            "mosaic_step": self._mosaic_step_spin.value(),
        }


def _color_icon(color: QColor, size: int = 14) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(color)
    return QIcon(pix)


_MAX_PATH_CHARS = 60
_MAX_NAME_CHARS = 40


def _truncate_middle(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    keep = max_len - 1  # 1 char for ellipsis
    front = keep * 2 // 3
    return text[:front] + "…" + text[-(keep - front):]


class _HistoryItem(QLabel):
    """Label for a history entry inside QWidgetAction."""

    def __init__(self, text: str, missing: bool, action, menu):
        super().__init__(text)
        self._action = action
        self._menu = menu
        self._missing = missing
        self.setContentsMargins(20, 4, 20, 4)
        self._set_active(False)

    def _set_active(self, active: bool):
        bg = PANEL3 if active else "transparent"
        color = DANGER if self._missing else TEXT
        self.setStyleSheet(
            f"color: {color}; background: {bg}; font-size: 13px;")

    def enterEvent(self, event):
        # Trigger hovered signal so _on_history_hovered updates all labels
        self._menu.setActiveAction(self._action)
        super().enterEvent(event)


# ─── File conflict dialog ─────────────────────────────────────────────────────

class _FileConflictDialog(QDialog):
    REPLACE = 0
    RENAME  = 1
    SKIP    = 2

    def __init__(self, existing_path: Path, new_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Файл уже существует")
        self.setModal(True)
        self.setMinimumWidth(440)
        self._result = self.SKIP

        layout = QVBoxLayout(self)

        def _fmt_info(p: Path) -> str:
            try:
                stat = p.stat()
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M")
                if size >= 1_048_576:
                    sz = f"{size / 1_048_576:.1f} МБ"
                elif size >= 1024:
                    sz = f"{size / 1024:.0f} КБ"
                else:
                    sz = f"{size} Б"
            except Exception:
                sz, mtime = "?", "?"
            return sz, mtime

        def _fmt_dims(p: Path) -> str:
            try:
                from PyQt6.QtGui import QImageReader
                r = QImageReader(str(p))
                s = r.size()
                if s.isValid():
                    return f"{s.width()}×{s.height()} px"
            except Exception:
                pass
            return ""

        ex_sz, ex_mt = _fmt_info(existing_path)
        nw_sz, nw_mt = _fmt_info(new_path)
        nw_dims = _fmt_dims(new_path)

        ex_group = QGroupBox("Существующий файл")
        ex_form = QFormLayout(ex_group)
        ex_form.addRow("Имя:",      QLabel(existing_path.name))
        ex_form.addRow("Размер:",   QLabel(ex_sz))
        ex_form.addRow("Изменён:",  QLabel(ex_mt))
        layout.addWidget(ex_group)

        nw_group = QGroupBox("Новый файл")
        nw_form = QFormLayout(nw_group)
        nw_form.addRow("Имя:",      QLabel(new_path.name))
        nw_form.addRow("Размер:",   QLabel(nw_sz))
        nw_form.addRow("Изменён:",  QLabel(nw_mt))
        if nw_dims:
            nw_form.addRow("Разрешение:", QLabel(nw_dims))
        layout.addWidget(nw_group)

        layout.addSpacing(8)
        btn_row = QHBoxLayout()
        btn_replace = QPushButton("Заменить")
        btn_rename  = QPushButton("Переименовать")
        btn_skip    = QPushButton("Пропустить")
        btn_replace.clicked.connect(lambda: self._finish(self.REPLACE))
        btn_rename.clicked.connect(lambda: self._finish(self.RENAME))
        btn_skip.clicked.connect(lambda: self._finish(self.SKIP))
        btn_row.addWidget(btn_replace)
        btn_row.addWidget(btn_rename)
        btn_row.addWidget(btn_skip)
        layout.addLayout(btn_row)

    def _finish(self, result: int):
        self._result = result
        self.accept()

    def chosen(self) -> int:
        return self._result


# ─── Main window ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    UNDO_LIMIT = 60

    def __init__(self):
        super().__init__()
        self._config: DatasetConfig | None = None
        self._images: List[Path] = []
        self._current_idx = -1
        self._dirty = False
        self._navigating = False
        self._updating_ui = False
        self._ann_items: List = []

        self._pending_image: QImage | None = None
        self._pre_mosaic_image: QImage | None = None
        self._pre_mosaic_anns: list | None = None
        self._pre_mosaic_dirty: bool = False
        self._pre_mosaic_had_pending: bool = False
        self._pre_mosaic_nn_preview: bool = False
        self._mosaic_save_anns: list | None = None
        self._mosaic_grid_size: int = 0
        self._current_browse_split = ""
        self._confirm_delete = True
        self._mosaic_step: int = 20
        self._nn_size = 640
        self._nn_preview = False

        self._undo_stack: deque = deque(maxlen=self.UNDO_LIMIT)
        self._redo_stack: deque = deque(maxlen=self.UNDO_LIMIT)
        self._pre_edit_state: list | None = None
        self._in_undo = False
        self._split_undo_stack: list[dict] = []
        self._split_redo_stack: list[dict] = []

        self._img_status: dict[str, ImgStatus] = {}
        self._load_progress()

        self._esc_pending = False
        self._esc_timer = QTimer(self)
        self._esc_timer.setSingleShot(True)
        self._esc_timer.setInterval(400)
        self._esc_timer.timeout.connect(lambda: setattr(self, '_esc_pending', False))

        self._load_settings()
        self._setup_ui()
        self._setup_shortcuts()
        self._apply_mouse_settings()
        self.setWindowTitle("YOLO Annotator")
        self.resize(1440, 920)
        self._restore_window_geometry()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._make_left_panel())
        splitter.addWidget(self._build_center_widget())
        splitter.addWidget(self._make_right_panel())
        splitter.setSizes([262, 900, 290])
        splitter.setStretchFactor(1, 1)

        container = QWidget()
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)
        vlay.addWidget(self._build_toolbar_widget())
        vlay.addWidget(splitter, 1)
        self.setCentralWidget(container)

        self._status_lbl = QLabel("Откройте папку датасета для начала работы")
        self.statusBar().addWidget(self._status_lbl)

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar_widget(self) -> QWidget:
        app_style = QApplication.instance().style()
        # Resolve icons: SVG from design spec, fall back to Qt standard
        ic_folder = (_svg_icon("folder") or
                     app_style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        ic_undo   = _svg_icon("undo")
        ic_redo   = _svg_icon("redo")
        ic_gear   = (_png_icon(_ICONS_DIR / "settings.png", size=16)
                     or _svg_icon("gear"))

        tb = QWidget()
        tb.setObjectName("toolbar")
        tb.setFixedHeight(34)
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(0)

        # ── Zone 1: Mode tabs ─────────────────────────────────────────────────
        mode_bg = QWidget()
        mode_bg.setObjectName("modetabs-bg")
        mode_bg.setFixedHeight(26)
        mode_lay = QHBoxLayout(mode_bg)
        mode_lay.setContentsMargins(2, 2, 2, 2)
        mode_lay.setSpacing(2)

        self._mode_annotate = QPushButton("Разметка")
        self._mode_annotate.setObjectName("modetab")
        self._mode_annotate.setCheckable(True)
        self._mode_annotate.setChecked(True)
        self._mode_annotate.setFixedHeight(22)
        self._mode_annotate.setToolTip("Режим разметки изображений")

        self._mode_dataset = QPushButton("Датасет")
        self._mode_dataset.setObjectName("modetab")
        self._mode_dataset.setCheckable(True)
        self._mode_dataset.setFixedHeight(22)
        self._mode_dataset.setToolTip("Анализ датасета (будет добавлено)")

        mode_group = QButtonGroup(tb)
        mode_group.setExclusive(True)
        mode_group.addButton(self._mode_annotate)
        mode_group.addButton(self._mode_dataset)

        mode_lay.addWidget(self._mode_annotate)
        mode_lay.addWidget(self._mode_dataset)

        lay.addWidget(mode_bg, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._make_sep())

        # ── Zone 2: File actions ───────────────────────────────────────────────
        z2 = QWidget()
        z2.setObjectName("tzone")
        z2l = QHBoxLayout(z2)
        z2l.setContentsMargins(8, 0, 8, 0)
        z2l.setSpacing(4)

        self._open_btn = QToolButton(self)
        self._open_btn.setIcon(ic_folder)
        self._open_btn.setIconSize(QSize(16, 16))
        self._open_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._open_btn.setObjectName("tbtn")
        # Width = left-pad(8) + icon(16) + gap(6) + menu-indicator(14) = 44px
        # Override right padding so the icon doesn't bleed into the arrow area
        self._open_btn.setFixedSize(44, 24)
        self._open_btn.setStyleSheet(
            "QToolButton#tbtn { padding: 0 14px 0 5px; }"
        )
        self._open_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._open_btn.setToolTip(
            "Открыть папку датасета\n▾ — история / открыть YAML")
        self._open_menu = QMenu(self)
        self._open_menu.installEventFilter(self)
        self._open_menu.hovered.connect(self._on_history_hovered)
        self._open_btn.setMenu(self._open_menu)
        self._open_btn.clicked.connect(self._open_folder)
        self._populate_open_menu()

        self._undo_btn = QToolButton(self)
        if ic_undo:
            self._undo_btn.setIcon(ic_undo)
            self._undo_btn.setIconSize(QSize(16, 16))
            self._undo_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        else:
            self._undo_btn.setText("↩")
        self._undo_btn.setObjectName("tbtn")
        self._undo_btn.setFixedSize(26, 24)
        self._undo_btn.setToolTip("Отменить последнее действие (Ctrl+Z)")
        self._undo_btn.clicked.connect(self._undo)
        self._undo_btn.setEnabled(False)

        self._redo_btn = QToolButton(self)
        if ic_redo:
            self._redo_btn.setIcon(ic_redo)
            self._redo_btn.setIconSize(QSize(16, 16))
            self._redo_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        else:
            self._redo_btn.setText("↪")
        self._redo_btn.setObjectName("tbtn")
        self._redo_btn.setFixedSize(26, 24)
        self._redo_btn.setToolTip("Повторить отменённое действие (Ctrl+Y)")
        self._redo_btn.clicked.connect(self._redo)
        self._redo_btn.setEnabled(False)

        z2l.addWidget(self._open_btn)
        z2l.addWidget(self._undo_btn)
        z2l.addWidget(self._redo_btn)

        lay.addWidget(z2, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addSpacing(12)
        self._dataset_path_lbl = QLabel("")
        self._dataset_path_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 12px; background: transparent;")
        lay.addWidget(self._dataset_path_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addStretch()
        lay.addWidget(self._make_sep())

        # ── Zone 3: Status ─────────────────────────────────────────────────────
        z3 = QWidget()
        z3.setObjectName("tzone")
        z3l = QHBoxLayout(z3)
        z3l.setContentsMargins(8, 0, 12, 0)
        z3l.setSpacing(10)

        self._autosave_cb = QCheckBox("Автосохранение")
        self._autosave_cb.setFixedHeight(22)
        self._autosave_cb.setToolTip(
            "Автоматически сохранять при переходе между изображениями")

        self._settings_btn = QToolButton(self)
        if ic_gear:
            self._settings_btn.setIcon(ic_gear)
            self._settings_btn.setIconSize(QSize(16, 16))
            self._settings_btn.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly)
        else:
            self._settings_btn.setText("⚙")
        self._settings_btn.setObjectName("tbtn")
        self._settings_btn.setFixedSize(26, 24)
        self._settings_btn.setToolTip("Настройки (кнопки мыши и пр.)")
        self._settings_btn.clicked.connect(self._open_settings)

        z3l.addWidget(self._autosave_cb)
        z3l.addWidget(self._settings_btn)

        lay.addWidget(z3, 0, Qt.AlignmentFlag.AlignVCenter)

        return tb

    def _make_sep(self) -> QWidget:
        sep = QWidget()
        sep.setObjectName("zone-sep")
        sep.setFixedWidth(1)
        sep.setFixedHeight(18)
        return sep

    # ── Center widget ─────────────────────────────────────────────────────────

    def _build_center_widget(self) -> QWidget:
        center = QWidget()
        vlay = QVBoxLayout(center)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        vlay.addWidget(self._build_canvas_nav_bar())
        vlay.addWidget(self._build_assign_row())

        self._viewer = ImageViewer()
        self._viewer.viewport().installEventFilter(self)
        self._viewer.annotation_changed.connect(self._on_annotation_changed)
        self._viewer.annotation_added.connect(self._on_annotation_added)
        self._viewer.pre_edit_started.connect(self._on_pre_edit_started)
        self._viewer.label_size_changed.connect(self._on_label_size_changed)
        self._viewer.crop_confirmed.connect(self._on_crop_confirmed)
        self._viewer.crop_cancelled.connect(self._on_crop_cancelled)
        self._viewer.segment_convert_requested.connect(self._on_segment_double_click)
        self._viewer.scene().selectionChanged.connect(self._on_scene_selection_changed)
        self._viewer.files_dropped.connect(self._on_files_dropped)

        vlay.addWidget(self._viewer, 1)
        return center

    def _build_canvas_nav_bar(self) -> QWidget:
        nav = QWidget()
        nav.setObjectName("canvas-nav")
        nav.setFixedHeight(30)
        lay = QHBoxLayout(nav)
        lay.setContentsMargins(12, 2, 12, 2)
        lay.setSpacing(6)

        self._nav_prev = QPushButton("‹")
        self._nav_prev.setObjectName("nav-btn")
        self._nav_prev.setFixedSize(28, 24)
        self._nav_prev.setToolTip("Предыдущее изображение (←)")
        self._nav_prev.clicked.connect(self._prev_image)

        self._nav_counter = QLabel("–")
        self._nav_counter.setObjectName("nav-counter")
        self._nav_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._nav_counter.setMinimumWidth(52)

        self._nav_next = QPushButton("›")
        self._nav_next.setObjectName("nav-btn")
        self._nav_next.setFixedSize(28, 24)
        self._nav_next.setToolTip("Следующее изображение (→)")
        self._nav_next.clicked.connect(self._next_image)

        lay.addWidget(self._nav_prev, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._nav_counter, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._nav_next, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch()

        self._nn_size_spin = QSpinBox()
        self._nn_size_spin.setObjectName("nn-size-spin")
        self._nn_size_spin.setRange(32, 4096)
        self._nn_size_spin.setSingleStep(32)
        self._nn_size_spin.setValue(self._nn_size)
        self._nn_size_spin.setSuffix(" px")
        self._nn_size_spin.setFixedWidth(76)
        self._nn_size_spin.setFixedHeight(22)
        self._nn_size_spin.setToolTip("Размер входа нейронной сети")
        self._nn_size_spin.valueChanged.connect(self._on_nn_size_changed)

        self._nn_preview_cb = QCheckBox("Размер нейросети")
        self._nn_preview_cb.setObjectName("nn-preview-cb")
        self._nn_preview_cb.setToolTip(
            "Показать изображение в масштабе нейронной сети (только предпросмотр, не сохраняется)")
        self._nn_preview_cb.toggled.connect(self._on_nn_preview_toggled)

        lay.addWidget(self._nn_size_spin, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._nn_preview_cb, 0, Qt.AlignmentFlag.AlignVCenter)

        return nav

    def _build_assign_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("assign-row")
        row.setFixedHeight(32)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(4)

        seg_bg = QWidget()
        seg_bg.setObjectName("seg-bg")
        seg_lay = QHBoxLayout(seg_bg)
        seg_lay.setContentsMargins(0, 0, 0, 0)
        seg_lay.setSpacing(2)

        self._split_btns: dict[str, QPushButton] = {}
        _split_tips = {
            "train": "Переместить изображение в сплит Train [1]",
            "val":   "Переместить изображение в сплит Val [2]",
            "test":  "Переместить изображение в сплит Test [3]",
        }
        for name, hotkey in [("Train", "1"), ("Val", "2"), ("Test", "3")]:
            btn = QPushButton(f"● {name}  {hotkey}")
            btn.setObjectName("split-btn")
            btn.setProperty("split", name.lower())
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setFixedWidth(80)
            btn.setToolTip(_split_tips[name.lower()])
            btn.clicked.connect(
                lambda _checked, s=name.lower(): self._on_assign_split(s))
            seg_lay.addWidget(btn)
            self._split_btns[name.lower()] = btn

        lay.addWidget(seg_bg)

        self._defer_btn = QPushButton("⚡ Отложить  4")
        self._defer_btn.setObjectName("split-btn")
        self._defer_btn.setProperty("split", "review")
        self._defer_btn.setCheckable(True)
        self._defer_btn.setFixedHeight(24)
        self._defer_btn.setToolTip(
            "Отложить изображение в Review-папку [4]\n"
            "Папка review/ создаётся автоматически при первом использовании")
        self._split_btns["review"] = self._defer_btn
        lay.addWidget(self._defer_btn)

        self._move_enabled_cb = QCheckBox("Перенос")
        self._move_enabled_cb.setObjectName("move-enabled-cb")
        self._move_enabled_cb.setChecked(True)
        self._move_enabled_cb.setToolTip(
            "Переносить файл при нажатии 1/2/3/4\n"
            "Снимите для навигации без перемещения файлов")
        lay.addWidget(self._move_enabled_cb)

        lay.addStretch()

        cur_lbl = QLabel("текущий:")
        cur_lbl.setObjectName("cur-lbl")

        # Badge — clickable, opens browse-split popup menu
        self._split_badge_btn = QToolButton()
        self._split_badge_btn.setObjectName("split-badge-btn")
        self._split_badge_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        self._split_badge_btn.setToolTip(
            "Текущий просматриваемый сплит\nНажмите для переключения")
        self._split_badge_btn.setFixedHeight(22)
        self._split_badge_menu = QMenu(self)
        self._split_badge_menu.aboutToShow.connect(self._rebuild_badge_menu)
        self._split_badge_btn.setMenu(self._split_badge_menu)

        cur_block = QWidget()
        cur_block.setObjectName("cur-block")
        cur_block.setFixedWidth(130)
        cbl = QHBoxLayout(cur_block)
        cbl.setContentsMargins(0, 0, 0, 0)
        cbl.setSpacing(4)
        cbl.addWidget(cur_lbl)
        cbl.addWidget(self._split_badge_btn, 1)
        lay.addWidget(cur_block)

        return row

    # ── Left / right panels ───────────────────────────────────────────────────

    def _make_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel-left")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header_row = QWidget()
        header_row.setObjectName("panel-header-row")
        hr_lay = QHBoxLayout(header_row)
        hr_lay.setContentsMargins(12, 6, 4, 6)
        hr_lay.setSpacing(4)

        header = QLabel("ИЗОБРАЖЕНИЯ")
        header.setObjectName("phead")
        hr_lay.addWidget(header)
        hr_lay.addStretch()

        _app_style = QApplication.instance().style()
        _ic_save  = (_svg_icon("save") or
                     _app_style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        _ic_copy  = _svg_icon("copy")
        _ic_trash = _svg_icon("trash")

        self._save_btn = QToolButton(self)
        self._save_btn.setIcon(_ic_save)
        self._save_btn.setIconSize(QSize(16, 16))
        self._save_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._save_btn.setObjectName("panel-head-btn")
        self._save_btn.setFixedSize(24, 22)
        self._save_btn.setToolTip("Сохранить изменения (Ctrl+S)")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)

        self._dup_btn = QToolButton(self)
        if _ic_copy:
            self._dup_btn.setIcon(_ic_copy)
            self._dup_btn.setIconSize(QSize(16, 16))
            self._dup_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        else:
            self._dup_btn.setText("⧉")
        self._dup_btn.setObjectName("panel-head-btn")
        self._dup_btn.setFixedSize(24, 22)
        self._dup_btn.setToolTip("Дублировать изображение [C]")
        self._dup_btn.clicked.connect(self._duplicate_current_image)
        self._dup_btn.setEnabled(False)

        self._del_file_btn = QToolButton(self)
        if _ic_trash:
            self._del_file_btn.setIcon(_ic_trash)
            self._del_file_btn.setIconSize(QSize(16, 16))
            self._del_file_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        else:
            self._del_file_btn.setText("🗑")
        self._del_file_btn.setObjectName("panel-head-btn-danger")
        self._del_file_btn.setFixedSize(24, 22)
        self._del_file_btn.setToolTip("Удалить текущий файл [D]")
        self._del_file_btn.clicked.connect(self._delete_current_file)
        self._del_file_btn.setEnabled(False)

        hr_lay.addWidget(self._save_btn)
        hr_lay.addWidget(self._dup_btn)
        hr_lay.addWidget(self._del_file_btn)
        lay.addWidget(header_row)

        self._image_list = ImageListWidget()
        self._image_list.currentRowChanged.connect(self._on_image_list_row_changed)
        self._image_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._image_list.customContextMenuRequested.connect(
            self._on_image_list_context_menu)
        self._image_list.files_dropped.connect(self._on_files_dropped)
        lay.addWidget(self._image_list)

        panel.setMinimumWidth(170)
        panel.setMaximumWidth(320)
        return panel

    def _make_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel-right")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        ann_group = QGroupBox("Аннотации")
        ag = QVBoxLayout(ann_group)
        ag.setContentsMargins(4, 6, 4, 4)
        ag.setSpacing(4)

        self._draw_btn = QPushButton("✏ Рамка  [Пробел]")
        self._draw_btn.setCheckable(True)
        self._draw_btn.setToolTip("Нарисовать bounding box [Пробел]")
        self._draw_btn.toggled.connect(self._on_draw_mode_toggled)
        self._draw_btn.setEnabled(False)
        ag.addWidget(self._draw_btn)

        self._ann_list = QListWidget()
        self._ann_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._ann_list.itemSelectionChanged.connect(self._on_ann_list_selection_changed)
        self._ann_list.itemDoubleClicked.connect(self._on_ann_list_double_click)
        ag.addWidget(self._ann_list)

        ag.addWidget(QLabel("Класс:"))
        self._class_combo = QComboBox()
        self._class_combo.currentIndexChanged.connect(self._on_class_combo_changed)
        self._class_combo.setEnabled(False)
        ag.addWidget(self._class_combo)

        self._convert_btn = QPushButton("→ BBox")
        self._convert_btn.setToolTip("Конвертировать выбранные сегментации в bbox")
        self._convert_btn.clicked.connect(self._on_convert_to_bbox)
        self._convert_btn.setEnabled(False)
        ag.addWidget(self._convert_btn)

        self._delete_btn = QPushButton("Удалить рамку  [Del]")
        self._delete_btn.setObjectName("danger-btn")
        self._delete_btn.setToolTip("Удалить выбранные рамки / сегментации [Del]")
        self._delete_btn.clicked.connect(self._on_delete)
        self._delete_btn.setEnabled(False)
        ag.addWidget(self._delete_btn)

        lay.addWidget(ann_group, 1)

        img_group = QGroupBox("Изображение")
        ig = QVBoxLayout(img_group)
        ig.setContentsMargins(4, 6, 4, 4)
        ig.setSpacing(4)

        crop_mosaic_row = QWidget()
        cm_lay = QHBoxLayout(crop_mosaic_row)
        cm_lay.setContentsMargins(0, 0, 0, 0)
        cm_lay.setSpacing(4)

        self._crop_btn = QPushButton("✂ Обрезать")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setToolTip("Обрезать [X]")
        self._crop_btn.toggled.connect(self._on_crop_btn)
        self._crop_btn.setEnabled(False)

        self._mosaic_btn = QPushButton("⊞ Мозаика  [M]")
        self._mosaic_btn.setToolTip("Мозаика 2×2 из текущего изображения [M]")
        self._mosaic_btn.clicked.connect(self._apply_mosaic)
        self._mosaic_btn.setEnabled(False)

        cm_lay.addWidget(self._crop_btn)
        cm_lay.addWidget(self._mosaic_btn)
        ig.addWidget(crop_mosaic_row)

        rot_row = QWidget()
        rot_lay = QHBoxLayout(rot_row)
        rot_lay.setContentsMargins(0, 0, 0, 0)
        rot_lay.setSpacing(4)
        self._rotate_cw_btn = QPushButton("↻ CW  [R]")
        self._rotate_cw_btn.setToolTip("Повернуть по часовой стрелке [R]")
        self._rotate_cw_btn.clicked.connect(lambda: self._rotate_image(clockwise=True))
        self._rotate_cw_btn.setEnabled(False)
        self._rotate_ccw_btn = QPushButton("↺ CCW  [⇧R]")
        self._rotate_ccw_btn.setToolTip("Повернуть против часовой стрелки [Shift+R]")
        self._rotate_ccw_btn.clicked.connect(lambda: self._rotate_image(clockwise=False))
        self._rotate_ccw_btn.setEnabled(False)
        rot_lay.addWidget(self._rotate_cw_btn)
        rot_lay.addWidget(self._rotate_ccw_btn)
        ig.addWidget(rot_row)

        def _slider_row(label: str) -> tuple:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            lbl = QLabel(label)
            lbl.setFixedWidth(14)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(-100, 100)
            sl.setValue(0)
            sl.setTickInterval(50)
            sl.setEnabled(False)
            val_lbl = QLabel("0")
            val_lbl.setFixedWidth(28)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rl.addWidget(lbl)
            rl.addWidget(sl)
            rl.addWidget(val_lbl)
            return row, sl, val_lbl

        bright_row, self._bright_sl, self._bright_val = _slider_row("Я")
        contr_row,  self._contr_sl,  self._contr_val  = _slider_row("К")
        self._bright_sl.valueChanged.connect(self._on_bc_changed)
        self._contr_sl.valueChanged.connect(self._on_bc_changed)
        self._bright_sl.valueChanged.connect(
            lambda v: self._bright_val.setText(str(v)))
        self._contr_sl.valueChanged.connect(
            lambda v: self._contr_val.setText(str(v)))

        def _add_snap(sl: QSlider):
            def _snap():
                if 0 < abs(sl.value()) <= 2:
                    sl.setValue(0)
            sl.sliderReleased.connect(_snap)
        _add_snap(self._bright_sl)
        _add_snap(self._contr_sl)

        ig.addWidget(bright_row)
        ig.addWidget(contr_row)

        lay.addWidget(img_group, 0)

        panel.setMinimumWidth(170)
        panel.setMaximumWidth(320)
        return panel

    # ── Shortcuts ─────────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence.StandardKey.Save,  self, self._on_save)
        QShortcut(QKeySequence.StandardKey.Undo,  self, self._undo)
        QShortcut(QKeySequence.StandardKey.Redo,  self, self._redo)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._on_delete)
        QShortcut(QKeySequence(Qt.Key.Key_Space),  self, self._toggle_draw_mode)
        QShortcut(QKeySequence(Qt.Key.Key_D),      self, self._delete_current_file)
        QShortcut(QKeySequence(Qt.Key.Key_C),      self, self._duplicate_current_image)
        QShortcut(QKeySequence("X"),               self, self._toggle_crop_mode)
        QShortcut(QKeySequence("M"),               self, self._apply_mosaic)
        QShortcut(QKeySequence("R"),               self, lambda: self._rotate_image(clockwise=True))
        QShortcut(QKeySequence("Shift+R"),         self, lambda: self._rotate_image(clockwise=False))
        QShortcut(QKeySequence("Ctrl+A"),          self, self._select_all_annotations)
        QShortcut(QKeySequence("1"), self, lambda: self._on_assign_split("train"))
        QShortcut(QKeySequence("2"), self, lambda: self._on_assign_split("val"))
        QShortcut(QKeySequence("3"), self, lambda: self._on_assign_split("test"))
        QShortcut(QKeySequence("4"), self, lambda: self._on_assign_split("review"))

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key.Key_Escape:
            if self._pre_mosaic_image is not None:
                self._revert_mosaic()
                return
            if self._esc_pending:
                self._esc_timer.stop()
                self._esc_pending = False
                self._on_double_esc()
            else:
                self._esc_pending = True
                self._esc_timer.start()
            super().keyPressEvent(event)
            return

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            selected = [i for i in self._viewer.scene().selectedItems()
                        if isinstance(i, (BBoxItem, SegmentItem))]
            if selected:
                step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
                dx = step if key == Qt.Key.Key_Right else (-step if key == Qt.Key.Key_Left else 0)
                dy = step if key == Qt.Key.Key_Down  else (-step if key == Qt.Key.Key_Up   else 0)
                self._move_selected_items(dx, dy)
                return
            else:
                if key == Qt.Key.Key_Right:
                    self._next_image()
                elif key == Qt.Key.Key_Left:
                    self._prev_image()
                return

        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        open_menu = getattr(self, '_open_menu', None)
        if open_menu is not None and obj is open_menu \
                and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Delete:
                pos = open_menu.mapFromGlobal(QCursor.pos())
                act = open_menu.actionAt(pos) or open_menu.activeAction()
                if act is not None and act.data():
                    self._delete_history_entry(str(act.data()))
                    return True
        if obj is self._viewer.viewport() and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                       Qt.Key.Key_Up, Qt.Key.Key_Down):
                selected = [i for i in self._viewer.scene().selectedItems()
                            if isinstance(i, (BBoxItem, SegmentItem))]
                if selected:
                    step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
                    dx = step if key == Qt.Key.Key_Right else (-step if key == Qt.Key.Key_Left else 0)
                    dy = step if key == Qt.Key.Key_Down  else (-step if key == Qt.Key.Key_Up   else 0)
                    self._move_selected_items(dx, dy)
                    return True
        return super().eventFilter(obj, event)

    def _move_selected_items(self, dx: int, dy: int):
        selected = [i for i in self._viewer.scene().selectedItems()
                    if isinstance(i, (BBoxItem, SegmentItem))]
        if not selected:
            return
        self._capture_for_undo()
        for item in selected:
            if isinstance(item, BBoxItem):
                r = item.rect()
                bw, bh = float(item._bnd_w), float(item._bnd_h)
                x1 = max(0.0, min(bw - r.width(),  r.left() + dx)) if bw else r.left() + dx
                y1 = max(0.0, min(bh - r.height(), r.top()  + dy)) if bh else r.top()  + dy
                item.set_rect(QRectF(x1, y1, r.width(), r.height()))
            elif isinstance(item, SegmentItem):
                bw, bh = float(item._bnd_w), float(item._bnd_h)
                pts = item.points()
                new_pts = []
                for p in pts:
                    nx = max(0.0, min(bw, p.x() + dx)) if bw else p.x() + dx
                    ny = max(0.0, min(bh, p.y() + dy)) if bh else p.y() + dy
                    new_pts.append(QPointF(nx, ny))
                item._pts = new_pts
                item.prepareGeometryChange()
                for i, h in enumerate(item._vhandles):
                    h.setPos(new_pts[i])
                item.update()
        self._viewer.annotation_changed.emit()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_settings(self):
        try:
            d = json.loads(SETTINGS_FILE.read_text())
            set_label_px(d.get('label_px', 12))
            self._confirm_delete = d.get("confirm_delete", True)
            self._mosaic_step = d.get("mosaic_step", 20)
            self._nn_size = d.get("nn_size", 640)
            self._mouse_settings = {
                "pan_button": d.get("pan_button", "right"),
                "fit_button": d.get("fit_button", "middle"),
            }
        except Exception:
            self._mouse_settings = {"pan_button": "right", "fit_button": "middle"}

    def _apply_mouse_settings(self):
        self._viewer.set_mouse_buttons(
            self._mouse_settings["pan_button"],
            self._mouse_settings["fit_button"])

    def _open_settings(self):
        current = {**self._mouse_settings,
                   "confirm_delete": self._confirm_delete,
                   "mosaic_step": self._mosaic_step}
        dlg = SettingsDialog(current, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = dlg.get_settings()
            self._confirm_delete = new.pop("confirm_delete", True)
            self._mosaic_step = new.pop("mosaic_step", 20)
            self._mouse_settings.update(new)
            self._apply_mouse_settings()
            self._save_settings()

    def _save_settings(self):
        try:
            try:
                d = json.loads(SETTINGS_FILE.read_text())
            except Exception:
                d = {}
            d.update(self._mouse_settings)
            d["confirm_delete"] = self._confirm_delete
            d["mosaic_step"] = self._mosaic_step
            d["nn_size"] = self._nn_size
            SETTINGS_FILE.write_text(json.dumps(d))
        except Exception:
            pass

    def _on_label_size_changed(self, px: int):
        try:
            try:
                d = json.loads(SETTINGS_FILE.read_text())
            except Exception:
                d = {}
            d['label_px'] = px
            SETTINGS_FILE.write_text(json.dumps(d))
        except Exception:
            pass

    def _make_letterbox(self, pix: QPixmap, size: int):
        """Scale pix to fit size×size with black padding. Returns (pixmap, sw, sh, pad_x, pad_y)."""
        from PyQt6.QtGui import QPainter
        scaled = pix.scaled(size, size,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        sw, sh = scaled.width(), scaled.height()
        pad_x = (size - sw) // 2
        pad_y = (size - sh) // 2
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.black)
        painter = QPainter(result)
        painter.drawPixmap(pad_x, pad_y, scaled)
        painter.end()
        return result, sw, sh, pad_x, pad_y

    def _remap_anns_letterbox(self, anns, sw, sh, pad_x, pad_y, size):
        """Remap normalized annotation coords from original image space to letterboxed canvas space."""
        from core.models import Annotation, AnnType
        result = []
        for ann in anns:
            if ann.ann_type == AnnType.BBOX:
                cx, cy, w, h = ann.data
                new_cx = (cx * sw + pad_x) / size
                new_cy = (cy * sh + pad_y) / size
                new_w  = w * sw / size
                new_h  = h * sh / size
                result.append(Annotation(ann.class_id, AnnType.BBOX,
                                         [new_cx, new_cy, new_w, new_h]))
            else:
                new_data = []
                for i in range(0, len(ann.data), 2):
                    new_data.append((ann.data[i]     * sw + pad_x) / size)
                    new_data.append((ann.data[i + 1] * sh + pad_y) / size)
                result.append(Annotation(ann.class_id, AnnType.SEGMENT, new_data))
        return result

    def _unmap_anns_letterbox(self, anns, sw, sh, pad_x, pad_y, size):
        """Inverse of _remap_anns_letterbox: letterboxed canvas coords → original image coords."""
        from core.models import Annotation, AnnType
        result = []
        for ann in anns:
            if ann.ann_type == AnnType.BBOX:
                cx, cy, w, h = ann.data
                result.append(Annotation(ann.class_id, AnnType.BBOX, [
                    (cx * size - pad_x) / sw,
                    (cy * size - pad_y) / sh,
                    w * size / sw,
                    h * size / sh,
                ]))
            else:
                new_data = []
                for i in range(0, len(ann.data), 2):
                    new_data.append((ann.data[i]     * size - pad_x) / sw)
                    new_data.append((ann.data[i + 1] * size - pad_y) / sh)
                result.append(Annotation(ann.class_id, AnnType.SEGMENT, new_data))
        return result

    def _on_nn_size_changed(self, value: int):
        self._nn_size = value
        self._save_settings()
        if self._nn_preview:
            self._load_current_image()

    def _on_nn_preview_toggled(self, checked: bool):
        self._nn_preview = checked
        if self._pre_mosaic_image is not None and self._pending_image is not None:
            self._refresh_mosaic_nn_display()
        else:
            self._load_current_image()

    def _refresh_mosaic_nn_display(self):
        """Switch letterbox on/off for the current mosaic without discarding it."""
        classes = self._config.names if self._config else []
        # Proportional annotations: use stored ones, or capture from viewer on first NN-ON toggle.
        if self._mosaic_save_anns is not None:
            prop_anns = self._mosaic_save_anns
        else:
            prop_anns = list(self._viewer.get_annotations())
            if self._nn_preview:
                self._mosaic_save_anns = prop_anns
        if self._nn_preview:
            lb_pix, sw, sh, pad_x, pad_y = self._make_letterbox(
                QPixmap.fromImage(self._pending_image), self._nn_size)
            lb_anns = self._remap_anns_letterbox(prop_anns, sw, sh, pad_x, pad_y, self._nn_size)
            self._viewer.reload_with_pixmap(lb_pix, lb_anns, classes)
        else:
            self._viewer.reload_with_pixmap(
                QPixmap.fromImage(self._pending_image), prop_anns, classes)
        self._rebuild_ann_list()
        self._update_status()

    # ── Config history ────────────────────────────────────────────────────────

    def _load_history(self) -> list:
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []

    def _save_history(self, path_str: str):
        hist = [p for p in self._load_history() if p != path_str]
        hist.insert(0, path_str)
        try:
            HISTORY_FILE.write_text(json.dumps(hist[:HISTORY_LIMIT]))
        except Exception:
            pass
        self._populate_open_menu()

    def _delete_history_entry(self, path_str: str):
        hist = [p for p in self._load_history() if p != path_str]
        try:
            HISTORY_FILE.write_text(json.dumps(hist))
        except Exception:
            pass
        # Remove just the matching action from the open menu so it stays visible
        for act in self._open_menu.actions():
            if isinstance(act, QWidgetAction) and act.data() == path_str:
                self._open_menu.removeAction(act)
                break
        # Remove separator if no history items remain
        remaining = [a for a in self._open_menu.actions()
                     if isinstance(a, QWidgetAction)]
        if not remaining:
            for act in self._open_menu.actions():
                if act.isSeparator():
                    self._open_menu.removeAction(act)
                    break

    def _on_history_hovered(self, action):
        for act in self._open_menu.actions():
            if isinstance(act, QWidgetAction):
                w = act.defaultWidget()
                if isinstance(w, _HistoryItem):
                    w._set_active(act is action)

    def _populate_open_menu(self):
        self._open_menu.clear()
        self._history_widgets: list = []  # keep Python refs so GC won't drop wrappers
        act_folder = QAction("Открыть папку...", self)
        act_folder.triggered.connect(self._open_folder)
        self._open_menu.addAction(act_folder)
        act_yaml = QAction("Открыть YAML конфиг...", self)
        act_yaml.triggered.connect(self._open_new_config)
        self._open_menu.addAction(act_yaml)
        hist = self._load_history()
        if hist:
            self._open_menu.addSeparator()
            for p in hist:
                missing = not Path(p).exists()
                wa = QWidgetAction(self._open_menu)
                wa.setData(p)
                lbl = _HistoryItem(p, missing, wa, self._open_menu)
                wa.setDefaultWidget(lbl)
                wa.triggered.connect(
                    lambda checked, _p=p: self._load_config_from_path(_p))
                self._open_menu.addAction(wa)
                self._history_widgets.append(lbl)

    def _open_folder(self):
        start_dir = ""
        hist = self._load_history()
        if hist:
            parent = Path(hist[0]).parent
            if parent.exists():
                start_dir = str(parent)
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку датасета", start_dir)
        if not folder:
            return
        try:
            result = detect_folder(Path(folder))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось проанализировать папку:\n{e}")
            return

        if result.yaml_path:
            self._load_config_from_path(str(result.yaml_path))
            return

        dlg = FolderImportDialog(result, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        accepted = dlg.accepted_keys()
        class_names = dlg.class_names()
        try:
            yaml_path = execute_normalization(result, accepted, class_names)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось выполнить преобразование:\n{e}")
            return
        self._load_config_from_path(str(yaml_path))

    def _open_new_config(self):
        start_dir = ""
        hist = self._load_history()
        if hist:
            parent = Path(hist[0]).parent
            if parent.exists():
                start_dir = str(parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open YAML Config", start_dir,
            "YAML files (*.yaml *.yml);;All files (*)")
        if path:
            self._load_config_from_path(path)

    def _load_config_from_path(self, path: str):
        try:
            self._config = DatasetConfig(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to parse config:\n{e}")
            return
        self._save_history(path)
        self._update_dataset_path_display()

        self._class_combo.clear()
        for cid, name in enumerate(self._config.names):
            self._class_combo.addItem(_color_icon(class_color(cid)), name)

        if self._config.splits:
            first = next(iter(self._config.splits))
            self._current_browse_split = first
            self._load_split(first)
        else:
            QMessageBox.warning(self, "Warning",
                                "No valid split folders found next to the config.")

    # ── Split browsing ────────────────────────────────────────────────────────

    def _switch_browse_split(self, split: str):
        if not self._config or split not in self._config.splits:
            return
        if self._dirty:
            if not self._maybe_save():
                return
        self._current_browse_split = split
        self._load_split(split)

    def _rebuild_badge_menu(self):
        self._split_badge_menu.clear()
        if not self._config:
            return
        _order = ["train", "val", "test", "review"]
        shown = set(_order)
        for split in _order:
            split_dir = self._config.splits.get(split)
            if split_dir is not None:
                try:
                    imgs = get_images(split_dir) if split_dir.exists() else []
                    count = len(imgs)
                except Exception:
                    count = 0
                act = QAction(f"{split}  ({count} фото)", self)
                act.triggered.connect(
                    lambda _, s=split: self._switch_browse_split(s))
            else:
                act = QAction(f"{split}  (–)", self)
                act.setEnabled(False)
            self._split_badge_menu.addAction(act)
        for split, split_dir in self._config.splits.items():
            if split not in shown:
                try:
                    imgs = get_images(split_dir) if split_dir.exists() else []
                    count = len(imgs)
                except Exception:
                    count = 0
                act = QAction(f"{split}  ({count} фото)", self)
                act.triggered.connect(
                    lambda _, s=split: self._switch_browse_split(s))
                self._split_badge_menu.addAction(act)

    def _load_split(self, split: str):
        if not self._config or split not in self._config.splits:
            return
        self._images = get_images(self._config.splits[split])
        self._current_idx = -1
        self._dirty = False
        self._clear_undo()

        self._image_list.blockSignals(True)
        self._image_list.clear()
        for img in self._images:
            self._image_list.addItem(img.name)
        self._image_list.blockSignals(False)
        self._image_list.set_paths(self._images)
        for i in range(len(self._images)):
            self._apply_status_color(i)

        self._clear_scene()
        self._save_btn.setEnabled(False)
        self._dup_btn.setEnabled(False)
        self._del_file_btn.setEnabled(False)
        self._set_image_controls_enabled(False)
        self._update_status()
        self._update_assign_row()

        if self._images:
            self._navigate_to(0)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _next_image(self):
        self._navigate_to(self._current_idx + 1)

    def _prev_image(self):
        self._navigate_to(self._current_idx - 1)

    def _on_image_list_row_changed(self, row: int):
        if self._navigating or row < 0 or row == self._current_idx:
            return
        self._navigate_to(row)

    def _navigate_to(self, idx: int):
        if not self._images:
            return
        idx = max(0, min(len(self._images) - 1, idx))
        if idx == self._current_idx:
            return

        if self._dirty:
            if self._autosave_cb.isChecked():
                self._save_current()
            elif not self._maybe_save():
                self._navigating = True
                self._image_list.setCurrentRow(self._current_idx)
                self._navigating = False
                return

        self._current_idx = idx
        self._navigating = True
        self._image_list.setCurrentRow(idx)
        self._navigating = False
        self._load_current_image()

    def _load_current_image(self):
        if self._current_idx < 0 or not self._images:
            return
        self._pending_image = None
        self._pre_mosaic_image = None
        self._pre_mosaic_anns = None
        self._pre_mosaic_dirty = False
        self._pre_mosaic_had_pending = False
        self._pre_mosaic_nn_preview = False
        self._mosaic_save_anns = None
        self._mosaic_grid_size = 0
        self._mosaic_btn.setToolTip("Мозаика 2×2 [M]")
        self._set_image_controls_enabled(True)
        self._viewer.stop_crop_mode()
        self._crop_btn.setChecked(False)
        path = self._images[self._current_idx]
        anns = load_annotations(path)
        classes = self._config.names if self._config else []
        if self._nn_preview:
            pix = QPixmap(str(path))
            if not pix.isNull():
                lb_pix, sw, sh, pad_x, pad_y = self._make_letterbox(pix, self._nn_size)
                lb_anns = self._remap_anns_letterbox(anns, sw, sh, pad_x, pad_y, self._nn_size)
                self._viewer.reload_with_pixmap(lb_pix, lb_anns, classes)
            else:
                self._viewer.load_image(path, anns, classes)
        else:
            self._viewer.load_image(path, anns, classes)
        self._bright_sl.setValue(0)
        self._contr_sl.setValue(0)
        self._dirty = False
        self._save_btn.setEnabled(True)
        self._dup_btn.setEnabled(True)
        self._del_file_btn.setEnabled(True)
        self._mosaic_btn.setEnabled(True)
        self._clear_undo()
        self._rebuild_ann_list()
        self._update_status()
        self._update_assign_row()
        if self._class_combo.count():
            self._sync_viewer_class(self._class_combo.currentIndex())
        if self._get_img_status(path) == ImgStatus.UNVIEWED:
            self._set_img_status(path, ImgStatus.VIEWED)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save(self):
        self._save_current()

    def _save_current(self):
        if self._current_idx < 0 or not self._images:
            return
        path = self._images[self._current_idx]
        had_pending = self._pending_image is not None
        if self._pending_image is not None:
            self._pending_image.save(str(path))
            self._pending_image = None
        self._pre_mosaic_image = None
        self._pre_mosaic_anns = None
        if self._mosaic_save_anns is not None:
            anns_to_save = self._mosaic_save_anns
            self._mosaic_save_anns = None
        elif self._nn_preview and not had_pending:
            # Viewer holds letterboxed coords; unmap to original image space before saving.
            pix = QPixmap(str(path))
            if not pix.isNull():
                _, sw, sh, pad_x, pad_y = self._make_letterbox(pix, self._nn_size)
                anns_to_save = self._unmap_anns_letterbox(
                    self._viewer.get_annotations(), sw, sh, pad_x, pad_y, self._nn_size)
            else:
                anns_to_save = self._viewer.get_annotations()
        else:
            anns_to_save = self._viewer.get_annotations()
        save_annotations(path, anns_to_save)
        self._dirty = False
        self._viewer.scene().clearSelection()
        self._set_img_status(path, ImgStatus.SAVED)
        self._update_status()

    def _maybe_save(self) -> bool:
        reply = QMessageBox.question(
            self, "Unsaved Changes", "Save changes to the current image?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Yes:
            self._save_current()
        else:
            self._dirty = False
            self._pending_image = None
        return True

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def _clear_undo(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._pre_edit_state = None
        self._undo_btn.setEnabled(bool(self._split_undo_stack))
        self._redo_btn.setEnabled(bool(self._split_redo_stack))

    def _on_pre_edit_started(self):
        if not self._in_undo:
            self._pre_edit_state = {"image": self._pending_image,
                                    "anns": self._viewer.get_annotations()}

    def _push_undo(self, state):
        self._undo_stack.append(state)
        self._redo_stack.clear()
        self._undo_btn.setEnabled(True)
        self._redo_btn.setEnabled(False)

    def _current_full_state(self):
        return {"image": self._pending_image, "anns": self._viewer.get_annotations()}

    def _undo(self):
        if self._pre_mosaic_image is not None:
            self._revert_mosaic()
            return
        if self._undo_stack:
            self._redo_stack.append(self._current_full_state())
            state = self._undo_stack.pop()
            self._restore(state)
            self._undo_btn.setEnabled(bool(self._undo_stack) or bool(self._split_undo_stack))
            self._redo_btn.setEnabled(True)
        elif self._split_undo_stack:
            self._undo_split_move()

    def _redo(self):
        if self._redo_stack:
            self._undo_stack.append(self._current_full_state())
            state = self._redo_stack.pop()
            self._restore(state)
            self._undo_btn.setEnabled(True)
            self._redo_btn.setEnabled(bool(self._redo_stack) or bool(self._split_redo_stack))
        elif self._split_redo_stack:
            self._redo_split_move()

    def _restore(self, state):
        self._in_undo = True
        classes = self._config.names if self._config else []
        if isinstance(state, dict):
            saved_image = state["image"]
            anns = state["anns"]
        else:
            saved_image = self._pending_image  # legacy list — treat as annotation-only
            anns = state
        if saved_image is not self._pending_image:
            self._pending_image = saved_image
            if saved_image is not None:
                pix = QPixmap.fromImage(saved_image)
            elif self._nn_preview:
                disk_pix = QPixmap(str(self._images[self._current_idx]))
                pix, *_ = self._make_letterbox(disk_pix, self._nn_size) \
                    if not disk_pix.isNull() else (disk_pix,)
            else:
                pix = QPixmap(str(self._images[self._current_idx]))
            self._viewer.reload_with_pixmap(pix, anns, classes)
        else:
            self._viewer.restore_annotations(anns, classes)
        self._in_undo = False
        self._rebuild_ann_list()
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._update_status()

    # ── Split move undo/redo ──────────────────────────────────────────────────

    def _undo_split_move(self):
        entry = self._split_undo_stack.pop()
        try:
            shutil.move(str(entry["dst_path"]), str(entry["src_path"]))
            if entry["dst_label"].exists():
                shutil.move(str(entry["dst_label"]), str(entry["src_label"]))
        except Exception as e:
            QMessageBox.critical(self, "Undo failed", f"Не удалось вернуть файл:\n{e}")
            self._split_undo_stack.append(entry)
            return
        idx = min(entry["list_idx"], len(self._images))
        self._images.insert(idx, entry["src_path"])
        self._image_list.insertItem(idx, QListWidgetItem(entry["src_path"].name))
        self._image_list.insert_path(idx, entry["src_path"])
        self._split_redo_stack.append(entry)
        self._current_idx = -1
        self._navigate_to(idx)
        self._undo_btn.setEnabled(bool(self._split_undo_stack))
        self._redo_btn.setEnabled(True)

    def _redo_split_move(self):
        entry = self._split_redo_stack.pop()
        src_path = entry["src_path"]
        try:
            entry["dst_path"].parent.mkdir(parents=True, exist_ok=True)
            entry["dst_label"].parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(entry["dst_path"]))
            if entry["src_label"].exists():
                shutil.move(str(entry["src_label"]), str(entry["dst_label"]))
        except Exception as e:
            QMessageBox.critical(self, "Redo failed", f"Не удалось переместить файл:\n{e}")
            self._split_redo_stack.append(entry)
            return
        if src_path in self._images:
            actual_idx = self._images.index(src_path)
            self._image_list.takeItem(actual_idx)
            self._image_list.remove_path(actual_idx)
            self._images.pop(actual_idx)
        else:
            actual_idx = entry["list_idx"]
        self._split_undo_stack.append(entry)
        self._dirty = False
        self._clear_undo()
        if self._images:
            self._current_idx = -1
            self._navigate_to(min(actual_idx, len(self._images) - 1))
        else:
            self._current_idx = -1
            self._clear_scene()
            self._save_btn.setEnabled(False)
            self._dup_btn.setEnabled(False)
            self._del_file_btn.setEnabled(False)
            self._update_status()
            self._update_assign_row()
        self._undo_btn.setEnabled(True)
        self._redo_btn.setEnabled(bool(self._split_redo_stack))

    # ── Annotation list ───────────────────────────────────────────────────────

    def _rebuild_ann_list(self, _=None):
        self._updating_ui = True
        self._ann_list.clear()
        self._ann_items = []
        seq = 1
        for item in self._viewer.scene().items():
            if not isinstance(item, (BBoxItem, SegmentItem)):
                continue
            kind = "BBox" if isinstance(item, BBoxItem) else "Seg"
            lw = QListWidgetItem(_color_icon(item.color),
                                 f"{seq}. {kind}: {item.class_name}")
            self._ann_list.addItem(lw)
            self._ann_items.append(item)
            seq += 1
        self._updating_ui = False

    def _on_ann_list_selection_changed(self):
        if self._updating_ui:
            return
        selected_rows = sorted(self._ann_list.row(i)
                               for i in self._ann_list.selectedItems())
        self._updating_ui = True
        self._viewer.scene().clearSelection()
        first_item = None
        for row in selected_rows:
            if row < len(self._ann_items):
                self._ann_items[row].setSelected(True)
                if first_item is None:
                    first_item = self._ann_items[row]
        self._updating_ui = False
        if first_item is not None:
            self._viewer.scroll_to_item(first_item)

    def _clear_scene(self):
        self._viewer._safe_clear_scene()
        self._ann_items = []
        self._ann_list.clear()

    def _on_scene_selection_changed(self):
        if self._updating_ui:
            return
        selected = [i for i in self._viewer.scene().selectedItems()
                    if isinstance(i, (BBoxItem, SegmentItem))]
        has_sel = bool(selected)
        has_seg = any(isinstance(i, SegmentItem) for i in selected)
        self._delete_btn.setEnabled(has_sel)
        self._convert_btn.setEnabled(has_seg)
        self._class_combo.setEnabled(has_sel)

        self._updating_ui = True
        self._ann_list.clearSelection()
        for item in selected:
            if item in self._ann_items:
                row = self._ann_items.index(item)
                self._ann_list.item(row).setSelected(True)
        if selected:
            self._class_combo.setCurrentIndex(selected[0].class_id)
        self._updating_ui = False

    # ── Draw mode ─────────────────────────────────────────────────────────────

    def _on_draw_mode_toggled(self, checked: bool):
        self._viewer.set_draw_mode(checked)
        self._draw_btn.setText("✏ Рисую…" if checked else "✏ Рамка  [Пробел]")

    def _toggle_draw_mode(self):
        self._draw_btn.setChecked(not self._draw_btn.isChecked())

    # ── Crop mode ─────────────────────────────────────────────────────────────

    def _toggle_crop_mode(self):
        if not self._images or self._current_idx < 0:
            return
        self._crop_btn.setChecked(not self._crop_btn.isChecked())

    def _on_crop_btn(self, checked: bool):
        if checked:
            self._draw_btn.setChecked(False)
            self._viewer.start_crop_mode()
        else:
            self._viewer.stop_crop_mode()

    def _on_crop_confirmed(self, rect: QRectF):
        self._crop_btn.setChecked(False)
        self._apply_crop(rect)

    def _on_crop_cancelled(self):
        self._crop_btn.setChecked(False)

    def _apply_crop(self, crop_rect: QRectF):
        if self._current_idx < 0 or not self._images:
            return
        cx, cy = crop_rect.x(), crop_rect.y()
        cw, ch = crop_rect.width(), crop_rect.height()

        if self._nn_preview and self._pending_image is None:
            # Viewer shows a letterboxed canvas. Map crop rect and annotations back
            # to original image coordinates before cropping.
            orig_pix = QPixmap(str(self._images[self._current_idx]))
            if orig_pix.isNull():
                return
            _, sw, sh, pad_x, pad_y = self._make_letterbox(orig_pix, self._nn_size)
            orig_w, orig_h = orig_pix.width(), orig_pix.height()
            ox = max(0, int(round((cx - pad_x) * orig_w / sw)))
            oy = max(0, int(round((cy - pad_y) * orig_h / sh)))
            ow = min(int(round(cw * orig_w / sw)), orig_w - ox)
            oh = min(int(round(ch * orig_h / sh)), orig_h - oy)
            if ow <= 0 or oh <= 0:
                return
            orig_anns = self._unmap_anns_letterbox(
                list(self._viewer.get_annotations()), sw, sh, pad_x, pad_y, self._nn_size)
            new_anns = recalc_annotations_crop(orig_anns, orig_w, orig_h, ox, oy, ow, oh)
            cropped = orig_pix.toImage().copy(ox, oy, ow, oh)
        else:
            src = self._pending_image if self._pending_image is not None else \
                  QImage(str(self._images[self._current_idx]))
            if src.isNull():
                return
            img_w, img_h = self._viewer.image_size
            cropped = src.copy(int(round(cx)), int(round(cy)),
                               int(round(cw)), int(round(ch)))
            new_anns = recalc_annotations_crop(
                list(self._viewer.get_annotations()), img_w, img_h, cx, cy, cw, ch)

        pre_crop_state = {"image": self._pending_image,
                          "anns": list(self._viewer.get_annotations())}
        self._pending_image = cropped
        classes = self._config.names if self._config else []
        self._viewer.reload_with_pixmap(QPixmap.fromImage(cropped), new_anns, classes)
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._push_undo(pre_crop_state)
        self._rebuild_ann_list()
        self._update_status()

    # ── Rotate ────────────────────────────────────────────────────────────────

    def _rotate_image(self, clockwise: bool):
        if self._current_idx < 0 or not self._images:
            return
        src = self._pending_image if self._pending_image is not None else \
              QImage(str(self._images[self._current_idx]))
        if src.isNull():
            return
        angle = 90 if clockwise else -90
        rotated = src.transformed(QTransform().rotate(angle))
        current_anns = self._viewer.get_annotations()
        pre_rotate_state = {"image": self._pending_image, "anns": list(current_anns)}
        new_anns = recalc_annotations_rotate(current_anns, clockwise)
        classes = self._config.names if self._config else []
        self._pending_image = rotated
        self._viewer.reload_with_pixmap(
            QPixmap.fromImage(rotated), new_anns, classes)
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._push_undo(pre_rotate_state)
        self._rebuild_ann_list()
        self._update_status()

    # ── Mosaic ────────────────────────────────────────────────────────────────

    def _apply_mosaic(self):
        if self._current_idx < 0 or not self._images:
            return

        from PyQt6.QtGui import QPainter
        from core.models import AnnType

        path = self._images[self._current_idx]

        if self._pre_mosaic_image is not None:
            # Subsequent click: increment grid, rebuild from original (pre-mosaic) image.
            next_N = self._mosaic_grid_size + 1
            if next_N > 8:
                return
            self._mosaic_grid_size = next_N
            src = self._pre_mosaic_image
            current_anns = self._pre_mosaic_anns
            use_nn = self._pre_mosaic_nn_preview
        else:
            # First click: load source and save pre-mosaic state.
            use_nn = self._nn_preview_cb.isChecked()
            if use_nn:
                src = QImage(str(path))
                if src.isNull():
                    return
                current_anns = load_annotations(path)
            else:
                src = self._pending_image if self._pending_image is not None else \
                      QImage(str(path))
                if src.isNull():
                    return
                current_anns = self._viewer.get_annotations()
            self._mosaic_grid_size = 2
            self._pre_mosaic_had_pending = self._pending_image is not None
            self._pre_mosaic_image = src.copy()
            self._pre_mosaic_anns = list(current_anns)
            self._pre_mosaic_dirty = self._dirty
            self._pre_mosaic_nn_preview = use_nn

        N = self._mosaic_grid_size
        n_tiles = N * N

        src_w = src.width()
        src_h = src.height()
        if use_nn:
            # Scale factors are expressed relative to the original src so that tiles are
            # produced in a single resize step.  Multiplying base/step by nn_factor maps
            # src coordinates to the proportional nn_size canvas without an intermediate
            # pre-scale of the source image.
            max_side = max(src_w, src_h)
            nn_factor = self._nn_size / max_side
            out_w = int(round(src_w * nn_factor))
            out_h = int(round(src_h * nn_factor))
            base_scale = nn_factor / N
            step = self._mosaic_step / 100.0 / n_tiles * nn_factor
        else:
            out_w, out_h = src_w, src_h
            base_scale = 1.0 / N
            # mosaic_step = total spread between smallest and largest tile (in % of src size)
            # step per tile = spread / n_tiles  (per user spec: e.g. 20% / 4 tiles = 5%)
            step = self._mosaic_step / 100.0 / n_tiles

        cell_w = out_w // N
        cell_h = out_h // N

        def _optimal_crop(overflow, anns, scale, src_dim, cell_dim, coord_idx):
            """Crop offset that centers annotation union bbox in cell."""
            if overflow <= 0 or not anns:
                return 0.0
            scaled_dim = src_dim * scale
            lo, hi = float('inf'), float('-inf')
            for ann in anns:
                if ann.ann_type == AnnType.BBOX:
                    ncx, ncy, nw, nh = ann.data
                    if coord_idx == 0:
                        a = (ncx - nw / 2) * scaled_dim
                        b = (ncx + nw / 2) * scaled_dim
                    else:
                        a = (ncy - nh / 2) * scaled_dim
                        b = (ncy + nh / 2) * scaled_dim
                else:
                    vals = [ann.data[i] * scaled_dim
                            for i in range(coord_idx, len(ann.data), 2)]
                    if not vals:
                        continue
                    a, b = min(vals), max(vals)
                lo = min(lo, a)
                hi = max(hi, b)
            if lo == float('inf'):
                return 0.0
            ideal = (lo + hi) / 2.0 - cell_dim / 2.0
            return max(0.0, min(float(overflow), ideal))

        output = QImage(out_w, out_h, QImage.Format.Format_RGB32)
        output.fill(Qt.GlobalColor.black)
        painter = QPainter(output)

        all_anns = []

        for row in range(N):
            for col in range(N):
                # Scale index: 0 = BL (smallest), increases left→right, bottom→top
                scale_idx = (N - 1 - row) * N + col
                scale = base_scale + scale_idx * step
                cell_x = col * cell_w
                cell_y = row * cell_h
                scaled_w = int(round(scale * src_w))
                scaled_h = int(round(scale * src_h))
                overflow_x = max(0, scaled_w - cell_w)
                overflow_y = max(0, scaled_h - cell_h)

                crop_x = _optimal_crop(overflow_x, current_anns, scale, src_w, cell_w, 0)
                crop_y = _optimal_crop(overflow_y, current_anns, scale, src_h, cell_h, 1)

                scaled_img = src.scaled(scaled_w, scaled_h,
                                        Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
                painter.drawImage(cell_x, cell_y, scaled_img,
                                  int(crop_x), int(crop_y), cell_w, cell_h)

                tile_anns = recalc_annotations_mosaic(
                    current_anns, src_w, src_h, scale,
                    crop_x, crop_y, cell_x, cell_y, cell_w, cell_h, out_w, out_h)
                all_anns.extend(tile_anns)

        painter.end()

        self._pending_image = output
        classes = self._config.names if self._config else []
        if use_nn:
            # Save proportional mosaic; display with letterbox for visual consistency.
            self._mosaic_save_anns = list(all_anns)
            lb_pix, sw, sh, pad_x, pad_y = self._make_letterbox(
                QPixmap.fromImage(output), self._nn_size)
            lb_anns = self._remap_anns_letterbox(all_anns, sw, sh, pad_x, pad_y, self._nn_size)
            self._viewer.reload_with_pixmap(lb_pix, lb_anns, classes)
        else:
            self._mosaic_save_anns = None
            self._viewer.reload_with_pixmap(QPixmap.fromImage(output), all_anns, classes)
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._rebuild_ann_list()
        self._update_status()

        next_N = N + 1
        if next_N <= 8:
            self._mosaic_btn.setToolTip(
                f"Мозаика {N}×{N} применена. Нажмите для {next_N}×{next_N} [M]")
        else:
            self._mosaic_btn.setToolTip(f"Мозаика {N}×{N} (максимум). Esc/Ctrl+Z — отмена [M]")

    def _revert_mosaic(self):
        if self._pre_mosaic_image is None:
            return
        classes = self._config.names if self._config else []
        pre_img = self._pre_mosaic_image
        pre_anns = self._pre_mosaic_anns
        had_pending = self._pre_mosaic_had_pending
        was_dirty = self._pre_mosaic_dirty
        was_nn_preview = self._pre_mosaic_nn_preview
        self._pre_mosaic_image = None
        self._pre_mosaic_anns = None
        self._pre_mosaic_dirty = False
        self._pre_mosaic_had_pending = False
        self._pre_mosaic_nn_preview = False
        self._mosaic_grid_size = 0
        self._mosaic_save_anns = None
        self._mosaic_btn.setToolTip("Мозаика 2×2 [M]")
        if was_nn_preview:
            # Restore letterbox display: re-apply letterbox transform to original annotations.
            path = self._images[self._current_idx]
            pix = QPixmap(str(path))
            self._pending_image = None
            if not pix.isNull():
                lb_pix, sw, sh, pad_x, pad_y = self._make_letterbox(pix, self._nn_size)
                lb_anns = self._remap_anns_letterbox(pre_anns, sw, sh, pad_x, pad_y, self._nn_size)
                self._viewer.reload_with_pixmap(lb_pix, lb_anns, classes)
        else:
            self._pending_image = pre_img if had_pending else None
            self._viewer.reload_with_pixmap(QPixmap.fromImage(pre_img), pre_anns, classes)
        self._dirty = was_dirty
        self._save_btn.setEnabled(was_dirty)
        self._rebuild_ann_list()
        self._update_status()

    # ── Delete current image file ─────────────────────────────────────────────

    def _delete_current_file(self):
        if self._current_idx < 0 or not self._images:
            return
        path = self._images[self._current_idx]
        if self._confirm_delete:
            reply = QMessageBox.question(
                self, "Delete File",
                f"Delete '{path.name}' from disk?\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        label = get_label_path(path)
        if label.exists():
            try:
                label.unlink()
            except Exception:
                pass
        idx = self._current_idx
        self._image_list.takeItem(idx)
        self._image_list.remove_path(idx)
        self._images.pop(idx)
        self._dirty = False
        self._clear_undo()
        if self._images:
            self._current_idx = -1
            self._navigate_to(min(idx, len(self._images) - 1))
        else:
            self._current_idx = -1
            self._clear_scene()
            self._save_btn.setEnabled(False)
            self._dup_btn.setEnabled(False)
            self._del_file_btn.setEnabled(False)
            self._set_image_controls_enabled(False)
            self._update_status()
            self._update_assign_row()

    # ── Duplicate current image ───────────────────────────────────────────────

    def _duplicate_current_image(self):
        if self._current_idx < 0 or not self._images:
            return
        src_path = self._images[self._current_idx]
        parent = src_path.parent
        stem = src_path.stem
        suffix = src_path.suffix
        dst_path = parent / f"{stem}_copy{suffix}"
        n = 2
        while dst_path.exists():
            dst_path = parent / f"{stem}_copy_{n}{suffix}"
            n += 1
        shutil.copy2(src_path, dst_path)
        src_label = get_label_path(src_path)
        if src_label.exists():
            shutil.copy2(src_label, get_label_path(dst_path))
        new_idx = self._current_idx + 1
        self._images.insert(new_idx, dst_path)
        self._image_list.blockSignals(True)
        self._image_list.insertItem(new_idx, dst_path.name)
        self._image_list.blockSignals(False)
        self._image_list.insert_path(new_idx, dst_path)
        self._apply_status_color(new_idx)
        self._navigate_to(new_idx)

    # ── Class combo ───────────────────────────────────────────────────────────

    def _on_class_combo_changed(self, idx: int):
        if self._updating_ui or not self._config or idx < 0:
            return
        cname = self._config.names[idx]
        color = class_color(idx)
        self._sync_viewer_class(idx)

        selected = [i for i in self._viewer.scene().selectedItems()
                    if isinstance(i, (BBoxItem, SegmentItem))]
        if selected:
            self._capture_for_undo()
            for item in selected:
                item.set_class(idx, cname, color)
            self._rebuild_ann_list()
            self._on_annotation_changed()

    def _sync_viewer_class(self, idx: int):
        if not self._config or idx < 0 or idx >= len(self._config.names):
            return
        self._viewer.set_current_class(
            idx, self._config.names[idx], class_color(idx))

    # ── Annotation actions ────────────────────────────────────────────────────

    def _capture_for_undo(self):
        self._pre_edit_state = {"image": self._pending_image,
                                "anns": self._viewer.get_annotations()}

    def _on_annotation_changed(self):
        if self._in_undo:
            return
        if self._pre_edit_state is not None:
            self._push_undo(self._pre_edit_state)
            self._pre_edit_state = None
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._update_status()

    def _on_annotation_added(self, _=None):
        self._rebuild_ann_list()

    def _select_all_annotations(self):
        for item in self._viewer.scene().items():
            if isinstance(item, (BBoxItem, SegmentItem)):
                item.setSelected(True)

    def _on_delete(self):
        if not self._viewer.scene().selectedItems():
            return
        self._capture_for_undo()
        self._viewer.delete_selected()
        self._rebuild_ann_list()

    def _on_convert_to_bbox(self):
        self._capture_for_undo()
        self._viewer.convert_selected_to_bbox()
        self._rebuild_ann_list()

    # ── Status ────────────────────────────────────────────────────────────────

    def _update_status(self):
        if not self._images or self._current_idx < 0:
            self._status_lbl.setText("Изображения не загружены")
            self._nav_counter.setText("–")
            return
        n = len(self._images)
        i = self._current_idx + 1
        self._nav_counter.setText(f"{i} / {n}")
        path = self._images[self._current_idx]
        name = path.name
        marker = " *" if self._dirty else ""
        img_w, img_h = self._viewer.image_size
        px_info = f"{img_w}×{img_h}px"
        try:
            nbytes = os.path.getsize(path)
            if nbytes >= 1_048_576:
                sz = f"{nbytes/1_048_576:.1f} MB"
            elif nbytes >= 1024:
                sz = f"{nbytes/1024:.0f} KB"
            else:
                sz = f"{nbytes} B"
        except OSError:
            sz = "?"
        undo_info = f"  ↩{len(self._undo_stack)}" if self._undo_stack else ""
        name_display = _truncate_middle(name, _MAX_NAME_CHARS)
        self._status_lbl.setText(
            f"{i}/{n}  {name_display}{marker}  {px_info}  {sz}{undo_info}")
        self._status_lbl.setToolTip(str(path) if name_display != name else "")

    def _update_dataset_path_display(self):
        if not self._config:
            return
        folder = str(self._config.config_path.parent)
        display = _truncate_middle(folder, _MAX_PATH_CHARS)
        self._dataset_path_lbl.setText(display)
        self._dataset_path_lbl.setToolTip(folder if display != folder else "")
        self.setWindowTitle(
            f"YOLO Annotator — {self._config.config_path.parent.name}")

    # ── Brightness / contrast ─────────────────────────────────────────────────

    def _on_bc_changed(self):
        self._viewer.set_bc_adjustment(
            self._bright_sl.value(), self._contr_sl.value())

    # ── Segment double-click → convert ────────────────────────────────────────

    def _on_segment_double_click(self, seg_item):
        self._capture_for_undo()
        self._viewer.scene().clearSelection()
        seg_item.setSelected(True)
        self._viewer.convert_selected_to_bbox()
        self._rebuild_ann_list()

    # ── Annotation list double-click → class change ───────────────────────────

    def _on_ann_list_double_click(self, list_item):
        if not self._config or len(self._config.names) <= 1:
            return
        row = self._ann_list.row(list_item)
        if row < 0 or row >= len(self._ann_items):
            return
        ann_item = self._ann_items[row]
        menu = QMenu(self)
        for cid, name in enumerate(self._config.names):
            act = QAction(_color_icon(class_color(cid)), name, self)
            act.triggered.connect(
                lambda checked, c=cid, it=ann_item: self._change_item_class(it, c))
            menu.addAction(act)
        menu.exec(QCursor.pos())

    def _change_item_class(self, ann_item, class_id: int):
        if not self._config or class_id >= len(self._config.names):
            return
        cname = self._config.names[class_id]
        color = class_color(class_id)
        self._capture_for_undo()
        ann_item.set_class(class_id, cname, color)
        self._rebuild_ann_list()
        self._on_annotation_changed()

    # ── Image status ──────────────────────────────────────────────────────────

    def _load_progress(self):
        try:
            d = json.loads(PROGRESS_FILE.read_text())
            for k, v in d.items():
                try:
                    self._img_status[k] = ImgStatus(v)
                except ValueError:
                    pass
        except Exception:
            pass

    def _save_progress(self):
        try:
            d = {k: v.value for k, v in self._img_status.items()}
            PROGRESS_FILE.write_text(json.dumps(d))
        except Exception:
            pass

    def _get_img_status(self, path: Path) -> ImgStatus:
        return self._img_status.get(str(path), ImgStatus.UNVIEWED)

    def _set_img_status(self, path: Path, status: ImgStatus):
        self._img_status[str(path)] = status
        self._save_progress()
        if path in self._images:
            self._apply_status_color(self._images.index(path))

    def _apply_status_color(self, idx: int):
        if idx < 0 or idx >= self._image_list.count() or idx >= len(self._images):
            return
        item = self._image_list.item(idx)
        if item is None:
            return
        status = self._get_img_status(self._images[idx])
        if status == ImgStatus.UNVIEWED:
            item.setForeground(QColor(110, 110, 110))
            item.setBackground(QColor(0, 0, 0, 0))
        elif status == ImgStatus.VIEWED:
            item.setForeground(QColor(220, 220, 220))
            item.setBackground(QColor(0, 0, 0, 0))
        else:  # SAVED
            item.setForeground(QColor(160, 230, 160))
            item.setBackground(QColor(15, 45, 15))

    def _set_image_controls_enabled(self, enabled: bool):
        self._draw_btn.setEnabled(enabled)
        if not enabled and self._draw_btn.isChecked():
            self._draw_btn.setChecked(False)
        self._crop_btn.setEnabled(enabled)
        if not enabled and self._crop_btn.isChecked():
            self._crop_btn.setChecked(False)
        self._mosaic_btn.setEnabled(enabled)
        self._rotate_cw_btn.setEnabled(enabled)
        self._rotate_ccw_btn.setEnabled(enabled)
        self._bright_sl.setEnabled(enabled)
        self._contr_sl.setEnabled(enabled)

    def _on_files_dropped(self, paths: list):
        if not self._config or not self._current_browse_split:
            return
        split_dir = self._config.splits.get(self._current_browse_split)
        if not split_dir:
            return

        from PyQt6.QtGui import QImageReader
        last_added_idx = None

        for src_path in paths:
            src_path = Path(src_path)
            if src_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            reader = QImageReader(str(src_path))
            if not reader.canRead():
                QMessageBox.warning(
                    self, "Ошибка открытия",
                    f"Не удалось открыть файл как изображение:\n{src_path.name}")
                continue

            dst_path = split_dir / src_path.name
            replacing_existing = dst_path in self._images

            if dst_path.exists():
                dlg = _FileConflictDialog(dst_path, src_path, self)
                dlg.exec()
                choice = dlg.chosen()
                if choice == _FileConflictDialog.SKIP:
                    continue
                elif choice == _FileConflictDialog.RENAME:
                    stem, suffix = src_path.stem, src_path.suffix
                    n = 1
                    while True:
                        dst_path = split_dir / f"{stem}_{n}{suffix}"
                        if not dst_path.exists():
                            break
                        n += 1
                    replacing_existing = False

            try:
                split_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_path), str(dst_path))
            except Exception as e:
                QMessageBox.critical(
                    self, "Ошибка копирования",
                    f"Не удалось скопировать файл:\n{e}")
                continue

            if replacing_existing:
                # File already in list — just navigate to it
                idx = self._images.index(dst_path)
                self._set_img_status(dst_path, ImgStatus.UNVIEWED)
                last_added_idx = idx
            else:
                # Insert at sorted position
                new_idx = len(self._images)
                for i, p in enumerate(self._images):
                    if dst_path.name < p.name:
                        new_idx = i
                        break
                self._images.insert(new_idx, dst_path)
                self._image_list.blockSignals(True)
                self._image_list.insertItem(new_idx, dst_path.name)
                self._image_list.blockSignals(False)
                self._image_list.insert_path(new_idx, dst_path)
                self._apply_status_color(new_idx)
                last_added_idx = new_idx

        if last_added_idx is not None:
            self._navigate_to(last_added_idx)

    def _on_image_list_context_menu(self, pos: QPoint):
        item = self._image_list.itemAt(pos)
        if item is None:
            return
        row = self._image_list.row(item)
        if row < 0 or row >= len(self._images):
            return
        path = self._images[row]
        menu = QMenu(self)
        act_viewed  = QAction("✓ Проверено",  self)
        act_saved   = QAction("● Отработано", self)
        act_revisit = QAction("○ Отработать", self)
        act_viewed.triggered.connect(
            lambda: self._set_img_status(path, ImgStatus.VIEWED))
        act_saved.triggered.connect(
            lambda: self._set_img_status(path, ImgStatus.SAVED))
        act_revisit.triggered.connect(
            lambda: self._set_img_status(path, ImgStatus.UNVIEWED))
        menu.addAction(act_viewed)
        menu.addAction(act_saved)
        menu.addAction(act_revisit)
        menu.exec(self._image_list.mapToGlobal(pos))

    def _on_double_esc(self):
        if self._current_idx < 0 or not self._images:
            return
        path = self._images[self._current_idx]
        self._set_img_status(path, ImgStatus.UNVIEWED)

    # ── Close ─────────────────────────────────────────────────────────────────

    def _restore_window_geometry(self):
        try:
            d = json.loads(SETTINGS_FILE.read_text())
            geom = d.get("window_geometry")
            maximized = d.get("window_maximized", False)
            if geom:
                self.restoreGeometry(bytes.fromhex(geom))
            if maximized:
                self.showMaximized()
        except Exception:
            pass

    def _save_window_geometry(self):
        try:
            try:
                d = json.loads(SETTINGS_FILE.read_text())
            except Exception:
                d = {}
            d["window_geometry"] = self.saveGeometry().toHex().data().decode()
            d["window_maximized"] = self.isMaximized()
            SETTINGS_FILE.write_text(json.dumps(d))
        except Exception:
            pass

    def closeEvent(self, event):
        self._save_window_geometry()
        if self._dirty:
            if self._autosave_cb.isChecked():
                self._save_current()
            else:
                reply = QMessageBox.question(
                    self, "Unsaved Changes", "Save changes before closing?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                    QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
                if reply == QMessageBox.StandardButton.Yes:
                    self._save_current()
        event.accept()

    # ── Split assignment ──────────────────────────────────────────────────────

    def _get_current_split(self) -> str:
        return self._current_browse_split

    def _update_assign_row(self):
        current = self._get_current_split()
        for split, btn in self._split_btns.items():
            if split == "review":
                btn.setChecked(False)
                continue
            btn.blockSignals(True)
            btn.setChecked(split == current)
            btn.blockSignals(False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if current and current in SPLIT_COLORS:
            color = SPLIT_COLORS[current]
            self._split_badge_btn.setText(f" {current.upper()} ▾")
            self._split_badge_btn.setStyleSheet(
                f"QToolButton {{ background: {color}; color: #0c0d0f; "
                f"border: none; border-radius: 3px; "
                f"font-size: 10px; font-weight: 800; padding: 2px 8px; }}"
                f"QToolButton::menu-indicator {{ image: none; }}"
            )
        else:
            self._split_badge_btn.setText("– ▾")
            self._split_badge_btn.setStyleSheet(
                "QToolButton { background: #34373d; color: #9298a0; border: none; "
                "border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
                "QToolButton::menu-indicator { image: none; }"
            )

    def _on_assign_split(self, target: str):
        if not self._images or self._current_idx < 0 or not self._config:
            return
        current = self._get_current_split()
        if target == current or not self._move_enabled_cb.isChecked():
            self._update_assign_row()
            self._next_image()
            return

        target_dir = self._config.splits.get(target)
        if target_dir is None:
            target_img_dir = self._config.config_dir / target / "images"
            target_lbl_dir = target_img_dir.parent / "labels"
            if target != "review":
                reply = QMessageBox.question(
                    self, "Папка не найдена",
                    f"Папка для сплита '{target}' не найдена.\n"
                    f"Создать?\n{target_img_dir}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply != QMessageBox.StandardButton.Yes:
                    self._update_assign_row()
                    return
            try:
                target_img_dir.mkdir(parents=True, exist_ok=True)
                target_lbl_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Не удалось создать папку {target}:\n{e}")
                self._update_assign_row()
                return
            self._config.splits[target] = target_img_dir
            target_dir = target_img_dir

        if self._dirty:
            self._save_current()

        path = self._images[self._current_idx]
        label = get_label_path(path)
        target_img   = target_dir / path.name
        target_label = get_label_path(target_img)

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_label.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target_img))
            if label.exists():
                shutil.move(str(label), str(target_label))
        except Exception as e:
            QMessageBox.critical(self, "Move failed",
                                 f"Could not move file:\n{e}")
            self._update_assign_row()
            return

        idx = self._current_idx
        self._split_undo_stack.append({
            "src_path": path, "src_label": label,
            "dst_path": target_img, "dst_label": target_label,
            "list_idx": idx,
        })
        self._split_redo_stack.clear()
        self._image_list.takeItem(idx)
        self._image_list.remove_path(idx)
        self._images.pop(idx)
        self._dirty = False
        self._clear_undo()  # clears annotation undo; split undo already pushed above

        if self._images:
            self._current_idx = -1
            self._navigate_to(min(idx, len(self._images) - 1))
        else:
            self._current_idx = -1
            self._clear_scene()
            self._save_btn.setEnabled(False)
            self._dup_btn.setEnabled(False)
            self._del_file_btn.setEnabled(False)
            self._set_image_controls_enabled(False)
            self._update_status()
            self._update_assign_row()
