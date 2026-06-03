from pathlib import Path
from typing import List

from PyQt6.QtWidgets import QListWidget, QLabel
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QIcon, QPixmap, QImage, QColor

from core.models import IMAGE_EXTENSIONS


class _IconLoader(QThread):
    """Loads small list icons in background using QImage (thread-safe)."""
    icon_ready = pyqtSignal(int, QImage)

    def __init__(self, paths: List[Path], w: int, h: int,
                 order: List[int], parent=None):
        super().__init__(parent)
        self._paths = paths
        self._w = w
        self._h = h
        self._order = order
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        for i in self._order:
            if self._cancelled:
                break
            try:
                img = QImage(str(self._paths[i]))
                if not img.isNull():
                    img = img.scaled(self._w, self._h,
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                self.icon_ready.emit(i, img)
            except Exception:
                pass


class _PreviewLoader(QThread):
    """Loads one hover-preview at a time; latest request wins."""
    preview_ready = pyqtSignal(int, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._index = -1
        self._path: Path | None = None
        self._pending_index = -1
        self._pending_path: Path | None = None

    def request(self, index: int, path: Path):
        self._pending_index = index
        self._pending_path = path
        if not self.isRunning():
            self.start()

    def run(self):
        while self._pending_path is not None:
            index = self._pending_index
            path = self._pending_path
            self._pending_path = None
            try:
                img = QImage(str(path))
                if not img.isNull():
                    img = img.scaled(320, 240,
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                # Only emit if no newer request came in
                if self._pending_path is None:
                    self.preview_ready.emit(index, img)
            except Exception:
                pass


class ImageListWidget(QListWidget):
    ICON_W = 24
    ICON_H = 18
    files_dropped = pyqtSignal(list)  # List[Path]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths: List[Path] = []
        self._icon_loader: _IconLoader | None = None
        self._preview_loader = _PreviewLoader(self)
        self._preview_loader.preview_ready.connect(self._on_preview_ready)
        self._preview_cache: dict[int, QPixmap] = {}
        self._hover_row = -1
        self._icons_loaded: set = set()

        self.setIconSize(QSize(self.ICON_W, self.ICON_H))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        pix = QPixmap(self.ICON_W, self.ICON_H)
        pix.fill(QColor(50, 52, 58))
        self._placeholder_icon = QIcon(pix)

        # Floating preview label (ToolTip window type stays above everything)
        self._preview_lbl = QLabel()
        self._preview_lbl.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self._preview_lbl.setStyleSheet(
            "QLabel{border:1px solid #666;background:#1e1e1e;padding:2px;}")
        self._preview_lbl.hide()

        # Re-prioritize icon loading after scrolling settles
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._on_scroll_settled)
        self.verticalScrollBar().valueChanged.connect(
            lambda: self._scroll_timer.start(400))

    def set_paths(self, paths: List[Path]):
        self._paths = list(paths)
        self._preview_cache.clear()
        self._icons_loaded.clear()
        self._hover_row = -1
        self._preview_lbl.hide()

        if self._icon_loader and self._icon_loader.isRunning():
            self._icon_loader.cancel()

        if not paths:
            return

        for i in range(self.count()):
            item = self.item(i)
            if item:
                item.setIcon(self._placeholder_icon)

        self._icon_loader = self._make_icon_loader()
        self._icon_loader.icon_ready.connect(self._on_icon_ready)
        self._icon_loader.start()

    def _make_icon_loader(self) -> '_IconLoader':
        n = len(self._paths)
        vs = self._first_visible_row()
        ve = vs + self._estimate_visible_count()
        loaded = self._icons_loaded
        visible = [i for i in range(max(0, vs), min(n, ve + 1)) if i not in loaded]
        return _IconLoader(self._paths, self.ICON_W, self.ICON_H, visible, self)

    def _first_visible_row(self) -> int:
        item = self.itemAt(0, 0)
        return self.row(item) if item else 0

    def _estimate_visible_count(self) -> int:
        if self.count() == 0:
            return 30
        h = self.sizeHintForRow(0)
        return (max(1, self.viewport().height() // h) + 2) if h > 0 else 30

    def _on_scroll_settled(self):
        if not self._paths:
            return
        if self._icon_loader and self._icon_loader.isRunning():
            self._icon_loader.cancel()
        self._icon_loader = self._make_icon_loader()
        self._icon_loader.icon_ready.connect(self._on_icon_ready)
        self._icon_loader.start()

    def _on_icon_ready(self, index: int, img: QImage):
        if index in self._icons_loaded:
            return
        if index < self.count() and not img.isNull():
            item = self.item(index)
            if item:
                item.setIcon(QIcon(QPixmap.fromImage(img)))
                self._icons_loaded.add(index)

    def _on_preview_ready(self, index: int, img: QImage):
        if img.isNull():
            return
        pix = QPixmap.fromImage(img)
        self._preview_cache[index] = pix
        if index == self._hover_row:
            self._show_preview(pix)

    def _show_preview(self, pix: QPixmap):
        self._preview_lbl.setPixmap(pix)
        self._preview_lbl.resize(pix.size())
        self._reposition_preview()
        self._preview_lbl.show()
        handle = self._preview_lbl.windowHandle()
        parent_handle = self.window().windowHandle()
        if handle and parent_handle and handle.transientParent() is None:
            handle.setTransientParent(parent_handle)

    def _reposition_preview(self):
        cursor_global = self.mapToGlobal(
            self.mapFromGlobal(self.cursor().pos()))
        screen = self.screen().availableGeometry()
        w = self._preview_lbl.width()
        h = self._preview_lbl.height()
        x = cursor_global.x() + 20
        y = cursor_global.y() - h // 2
        if x + w > screen.right():
            x = cursor_global.x() - w - 10
        y = max(screen.top(), min(y, screen.bottom() - h))
        self._preview_lbl.move(x, y)

    def mouseMoveEvent(self, event):
        item = self.itemAt(event.pos())
        row = self.row(item) if item else -1
        if row != self._hover_row:
            self._hover_row = row
            if row >= 0 and row < len(self._paths):
                if row in self._preview_cache:
                    self._show_preview(self._preview_cache[row])
                else:
                    self._preview_lbl.hide()
                    self._preview_loader.request(row, self._paths[row])
            else:
                self._preview_lbl.hide()
        elif self._preview_lbl.isVisible():
            self._reposition_preview()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_row = -1
        self._preview_lbl.hide()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._preview_lbl.hide()
        super().hideEvent(event)

    def _has_image_urls(self, event) -> bool:
        if not event.mimeData().hasUrls():
            return False
        return any(Path(u.toLocalFile()).suffix.lower() in IMAGE_EXTENSIONS
                   for u in event.mimeData().urls())

    def dragEnterEvent(self, event):
        if self._has_image_urls(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._has_image_urls(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()
                 if Path(u.toLocalFile()).suffix.lower() in IMAGE_EXTENSIONS]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def remove_path(self, index: int):
        """Remove one entry without restarting the icon loader."""
        if not (0 <= index < len(self._paths)):
            return
        self._paths.pop(index)
        self._preview_lbl.hide()
        self._hover_row = -1
        # Shift preview cache keys down
        new_cache = {}
        for k, v in self._preview_cache.items():
            if k < index:
                new_cache[k] = v
            elif k > index:
                new_cache[k - 1] = v
        self._preview_cache = new_cache

    def insert_path(self, index: int, path: Path):
        """Insert one entry, shifting existing caches and triggering icon load."""
        self._paths.insert(index, path)
        self._preview_lbl.hide()
        self._hover_row = -1
        new_cache = {(k + 1 if k >= index else k): v
                     for k, v in self._preview_cache.items()}
        self._preview_cache = new_cache
        self._icons_loaded = {(k + 1 if k >= index else k) for k in self._icons_loaded}
        item = self.item(index)
        if item:
            item.setIcon(self._placeholder_icon)
        loader = _IconLoader(self._paths, self.ICON_W, self.ICON_H, [index], self)
        loader.icon_ready.connect(self._on_icon_ready)
        loader.start()
