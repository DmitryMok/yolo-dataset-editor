from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                             QGraphicsRectItem, QGraphicsLineItem)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QPointF
from PyQt6.QtGui import QPixmap, QPen, QBrush, QColor, QPainter, QImage

from core.models import Annotation, AnnType
from gui.editor.items import BBoxItem, SegmentItem, class_color, get_label_px, set_label_px

_CROSS_PEN = QPen(QColor(255, 255, 255, 200), 1, Qt.PenStyle.DashLine)
_CROSS_PEN.setDashPattern([6, 4])
_CROSS_PEN.setCosmetic(True)

_CROP_HANDLE_PX = 8   # handle half-size in screen pixels
_EDGE_PAD = 2000      # extra scene-coord padding on each side so image edges scroll to viewport centre

_BTN_NAMES = {"left": Qt.MouseButton.LeftButton,
              "middle": Qt.MouseButton.MiddleButton,
              "right": Qt.MouseButton.RightButton}

def _build_lut(brightness: int, contrast_slider: int) -> bytes:
    factor = (contrast_slider + 100) / 100.0
    lut = bytearray(256)
    for i in range(256):
        v = int((i - 128) * factor + 128 + brightness)
        lut[i] = max(0, min(255, v))
    lut[255] = 255  # keep alpha byte intact
    return bytes(lut)

from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem


class CropOverlay(QGraphicsObject):
    """Interactive crop-rect overlay, covers the full image at ZValue 200."""
    rect_changed = pyqtSignal(QRectF)

    def __init__(self, img_w: int, img_h: int, parent=None):
        super().__init__(parent)
        self._img_w = img_w
        self._img_h = img_h
        self._rect = QRectF(0, 0, img_w, img_h)
        self._drag_edges: set = set()
        self._drag_last: QPointF | None = None
        self.setZValue(200)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def get_rect(self) -> QRectF:
        return QRectF(self._rect)

    def boundingRect(self) -> QRectF:
        return QRectF(-1, -1, self._img_w + 2, self._img_h + 2)

    def _view_scale(self) -> float:
        sc = self.scene()
        return sc.views()[0].transform().m11() if sc and sc.views() else 1.0

    def _hit_edges(self, pos: QPointF) -> set:
        r = self._rect
        thr = _CROP_HANDLE_PX / max(self._view_scale(), 0.01)
        x, y = pos.x(), pos.y()
        edges: set = set()
        if r.top() - thr <= y <= r.bottom() + thr:
            if abs(x - r.left())  <= thr: edges.add('left')
            if abs(x - r.right()) <= thr: edges.add('right')
        if r.left() - thr <= x <= r.right() + thr:
            if abs(y - r.top())    <= thr: edges.add('top')
            if abs(y - r.bottom()) <= thr: edges.add('bottom')
        return edges

    @staticmethod
    def _edges_cursor(edges: set) -> Qt.CursorShape:
        if {'left','top'} <= edges or {'right','bottom'} <= edges:
            return Qt.CursorShape.SizeFDiagCursor
        if {'right','top'} <= edges or {'left','bottom'} <= edges:
            return Qt.CursorShape.SizeBDiagCursor
        if 'left' in edges or 'right' in edges:
            return Qt.CursorShape.SizeHorCursor
        if 'top' in edges or 'bottom' in edges:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def paint(self, painter: QPainter, option, widget):
        r = self._rect
        dark = QColor(0, 0, 0, 150)
        if r.top() > 0:
            painter.fillRect(QRectF(0, 0, self._img_w, r.top()), dark)
        if r.bottom() < self._img_h:
            painter.fillRect(QRectF(0, r.bottom(), self._img_w, self._img_h - r.bottom()), dark)
        if r.left() > 0:
            painter.fillRect(QRectF(0, r.top(), r.left(), r.height()), dark)
        if r.right() < self._img_w:
            painter.fillRect(QRectF(r.right(), r.top(), self._img_w - r.right(), r.height()), dark)

        border_pen = QPen(Qt.GlobalColor.white, 2)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawRect(r)

        # Size label at centre of crop rect
        scale = painter.transform().m11()
        inv = 1.0 / scale if scale > 0 else 1.0
        size_txt = f"{int(round(r.width()))}×{int(round(r.height()))}"
        painter.save()
        painter.translate(r.center().x(), r.center().y())
        painter.scale(inv, inv)
        font = painter.font()
        font.setPixelSize(14)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(size_txt) + 10
        th = fm.height() + 6
        painter.fillRect(QRectF(-tw / 2, -th / 2, tw, th), QColor(0, 0, 0, 180))
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(QRectF(-tw / 2, -th / 2, tw, th),
                         Qt.AlignmentFlag.AlignCenter, size_txt)
        painter.restore()

        # Handles at fixed screen size via inverse scale
        hs = _CROP_HANDLE_PX * inv
        for hx, hy in [
            (r.left(),       r.top()),    (r.center().x(), r.top()),    (r.right(), r.top()),
            (r.left(),       r.center().y()),                            (r.right(), r.center().y()),
            (r.left(),       r.bottom()), (r.center().x(), r.bottom()), (r.right(), r.bottom()),
        ]:
            painter.fillRect(QRectF(hx - hs, hy - hs, hs * 2, hs * 2), Qt.GlobalColor.white)

    def hoverMoveEvent(self, event):
        edges = self._hit_edges(event.pos())
        self.setCursor(self._edges_cursor(edges) if edges else Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_edges = self._hit_edges(event.pos())
            self._drag_last = event.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._drag_last is None:
            return
        delta = event.pos() - self._drag_last
        self._drag_last = event.pos()
        if not self._drag_edges:
            event.accept()
            return
        r = self._rect
        x1, y1, x2, y2 = r.left(), r.top(), r.right(), r.bottom()
        MIN_SZ = 10.0
        if 'left'   in self._drag_edges: x1 = max(0.0,              min(x1 + delta.x(), x2 - MIN_SZ))
        if 'right'  in self._drag_edges: x2 = min(float(self._img_w), max(x2 + delta.x(), x1 + MIN_SZ))
        if 'top'    in self._drag_edges: y1 = max(0.0,              min(y1 + delta.y(), y2 - MIN_SZ))
        if 'bottom' in self._drag_edges: y2 = min(float(self._img_h), max(y2 + delta.y(), y1 + MIN_SZ))
        self.prepareGeometryChange()
        self._rect = QRectF(x1, y1, x2 - x1, y2 - y1)
        self.update()
        self.rect_changed.emit(self._rect)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_edges = set()
        self._drag_last = None
        event.accept()


class ImageViewer(QGraphicsView):
    annotation_changed        = pyqtSignal()
    annotation_added          = pyqtSignal(object)
    pre_edit_started          = pyqtSignal()
    label_size_changed        = pyqtSignal(int)
    crop_confirmed            = pyqtSignal(QRectF)
    crop_cancelled            = pyqtSignal()
    segment_convert_requested = pyqtSignal(object)   # passes the SegmentItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(40, 40, 40)))
        self.setMouseTracking(True)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._img_w = 1
        self._img_h = 1
        self._user_zoomed = False

        # draw mode
        self._draw_mode = False
        self._drawing = False
        self._draw_start: QPointF | None = None
        self._draw_preview: QGraphicsRectItem | None = None

        # current class for new annotations
        self._cur_class_id = 0
        self._cur_class_name = ''
        self._cur_color = QColor(255, 0, 0)
        self._classes: List[str] = []

        # crosshair lines (recreated on each load_image)
        self._cross_h: QGraphicsLineItem | None = None
        self._cross_v: QGraphicsLineItem | None = None

        # pan / fit mouse buttons (configurable)
        self._pan_button = Qt.MouseButton.RightButton
        self._fit_button = Qt.MouseButton.MiddleButton
        self._pan_active = False
        self._pan_start = QPointF()

        # brightness / contrast (display-only)
        self._orig_image: QImage | None = None
        self._bc_brightness: int = 0
        self._bc_contrast: int = 0
        self._bc_buffer: bytearray | None = None  # keeps pixel data alive for QImage

        # crop mode
        self._crop_mode = False
        self._crop_item: CropOverlay | None = None

    def _safe_clear_scene(self):
        """Clear scene and null out all item references to prevent use-after-free."""
        self._scene.blockSignals(True)
        self._scene.clear()
        self._scene.blockSignals(False)
        self._pixmap_item = None
        self._cross_h = None
        self._cross_v = None
        self._crop_item = None
        self._crop_mode = False

    # ── public API ────────────────────────────────────────────────────────────

    def load_image(self, image_path: Path, annotations: List[Annotation],
                   classes: List[str]):
        self._safe_clear_scene()
        self._classes = classes

        pix = QPixmap(str(image_path))
        if pix.isNull():
            return

        self._img_w = pix.width()
        self._img_h = pix.height()
        self._orig_image = pix.toImage()
        self._bc_brightness = 0
        self._bc_contrast = 0

        self._pixmap_item = QGraphicsPixmapItem(pix)
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._pixmap_item.setZValue(0)
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(QRectF(-_EDGE_PAD, -_EDGE_PAD,
                                        self._img_w + 2 * _EDGE_PAD,
                                        self._img_h + 2 * _EDGE_PAD))

        self._create_crosshairs()

        for ann in annotations:
            item = self._make_item(ann, classes)
            if item:
                self._add_item(item)

        self._user_zoomed = False
        self.fitInView(QRectF(0, 0, self._img_w, self._img_h),
                       Qt.AspectRatioMode.KeepAspectRatio)

    def get_annotations(self) -> List[Annotation]:
        result = []
        for item in self._scene.items():
            if isinstance(item, BBoxItem):
                r = item.rect()
                cx = max(0.0, min(1.0, (r.left() + r.width()  / 2) / self._img_w))
                cy = max(0.0, min(1.0, (r.top()  + r.height() / 2) / self._img_h))
                w  = max(0.0, min(1.0, r.width()  / self._img_w))
                h  = max(0.0, min(1.0, r.height() / self._img_h))
                result.append(Annotation(item.class_id, AnnType.BBOX, [cx, cy, w, h]))
            elif isinstance(item, SegmentItem):
                data = []
                for p in item.points():
                    data.extend([max(0.0, min(1.0, p.x() / self._img_w)),
                                  max(0.0, min(1.0, p.y() / self._img_h))])
                result.append(Annotation(item.class_id, AnnType.SEGMENT, data))
        return result

    def restore_annotations(self, annotations: List[Annotation], classes: List[str]):
        """Replace current annotations without touching the image or zoom."""
        for item in list(self._scene.items()):
            if isinstance(item, (BBoxItem, SegmentItem)):
                self._scene.removeItem(item)
        self._create_crosshairs()
        for ann in annotations:
            item = self._make_item(ann, classes)
            if item:
                self._add_item(item)

    def _apply_mode_cursor(self):
        """Set cursor on both view and viewport to match the current interaction mode.

        Using setCursor(Arrow) instead of unsetCursor() prevents the scene from
        restoring a stale CrossCursor via its internal hover-item cursor tracking.
        """
        if self._pan_active:
            c = Qt.CursorShape.ClosedHandCursor
        elif self._draw_mode:
            c = Qt.CursorShape.CrossCursor
        else:
            c = Qt.CursorShape.ArrowCursor
        self.setCursor(c)
        self.viewport().setCursor(c)

    def set_draw_mode(self, enabled: bool):
        self._draw_mode = enabled
        if enabled:
            self._scene.clearSelection()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._apply_mode_cursor()
            cursor_vp = self.mapFromGlobal(self.cursor().pos())
            if self.rect().contains(cursor_vp):
                self._update_crosshair(self.mapToScene(cursor_vp))
        else:
            self._apply_mode_cursor()
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self._cancel_draw()
            if self._cross_h:
                self._cross_h.setVisible(False)
            if self._cross_v:
                self._cross_v.setVisible(False)

    def set_current_class(self, class_id: int, class_name: str, color: QColor):
        self._cur_class_id = class_id
        self._cur_class_name = class_name
        self._cur_color = color

    def start_crop_mode(self):
        if self._crop_mode or not self._pixmap_item:
            return
        if self._draw_mode:
            self.set_draw_mode(False)
        self._scene.clearSelection()
        self._crop_mode = True
        self._crop_item = CropOverlay(self._img_w, self._img_h)
        self._crop_item.rect_changed.connect(self._on_crop_rect_changed)
        self._scene.addItem(self._crop_item)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocus()

    def stop_crop_mode(self):
        if not self._crop_mode:
            return
        self._crop_mode = False
        if self._crop_item:
            self._scene.removeItem(self._crop_item)
            self._crop_item = None
        self._clear_crop_hints()
        if not self._draw_mode:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def reload_with_pixmap(self, pixmap: 'QPixmap', annotations: List[Annotation],
                           classes: List[str]):
        """Replace the displayed image without touching the file (crop / rotate preview)."""
        self._safe_clear_scene()
        self._classes = classes
        if pixmap.isNull():
            return
        self._img_w = pixmap.width()
        self._img_h = pixmap.height()
        self._orig_image = pixmap.toImage()
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._pixmap_item.setZValue(0)
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(QRectF(-_EDGE_PAD, -_EDGE_PAD,
                                        self._img_w + 2 * _EDGE_PAD,
                                        self._img_h + 2 * _EDGE_PAD))
        self._create_crosshairs()
        for ann in annotations:
            item = self._make_item(ann, classes)
            if item:
                self._add_item(item)
        self._user_zoomed = False
        self.fitInView(QRectF(0, 0, self._img_w, self._img_h),
                       Qt.AspectRatioMode.KeepAspectRatio)

    def scroll_to_item(self, item):
        if isinstance(item, BBoxItem):
            self.centerOn(item.rect().center())
        elif isinstance(item, SegmentItem):
            pts = item.points()
            xs = [p.x() for p in pts]
            ys = [p.y() for p in pts]
            self.centerOn(QPointF((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))

    def delete_selected(self):
        for item in list(self._scene.selectedItems()):
            if isinstance(item, (BBoxItem, SegmentItem)):
                self._scene.removeItem(item)
        self.annotation_changed.emit()

    def convert_selected_to_bbox(self):
        converted = False
        for item in list(self._scene.selectedItems()):
            if isinstance(item, SegmentItem):
                pts = item.points()
                xs = [p.x() for p in pts]
                ys = [p.y() for p in pts]
                rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                bbox = BBoxItem(rect, item.class_id, item.class_name, item.color)
                bbox.set_image_bounds(self._img_w, self._img_h)
                self._scene.removeItem(item)
                self._add_item(bbox)
                bbox.setSelected(True)
                converted = True
        if converted:
            self.annotation_changed.emit()

    # ── internal helpers ──────────────────────────────────────────────────────

    def _make_item(self, ann: Annotation, classes: List[str]):
        cid = ann.class_id
        cname = classes[cid] if cid < len(classes) else str(cid)
        color = class_color(cid)
        if ann.ann_type == AnnType.BBOX:
            cx, cy, w, h = ann.data
            x = (cx - w / 2) * self._img_w
            y = (cy - h / 2) * self._img_h
            item = BBoxItem(QRectF(x, y, w * self._img_w, h * self._img_h),
                            cid, cname, color)
        else:
            pts = [QPointF(ann.data[i] * self._img_w, ann.data[i + 1] * self._img_h)
                   for i in range(0, len(ann.data), 2)]
            item = SegmentItem(pts, cid, cname, color)
        item.set_image_bounds(self._img_w, self._img_h)
        return item

    def set_mouse_buttons(self, pan: str, fit: str):
        self._pan_button = _BTN_NAMES.get(pan, Qt.MouseButton.RightButton)
        self._fit_button = _BTN_NAMES.get(fit, Qt.MouseButton.MiddleButton)

    def set_bc_adjustment(self, brightness: int, contrast_slider: int):
        self._bc_brightness = brightness
        self._bc_contrast = contrast_slider
        if not self._orig_image or self._orig_image.isNull() or not self._pixmap_item:
            return
        try:
            if brightness == 0 and contrast_slider == 0:
                self._bc_buffer = None
                self._pixmap_item.setPixmap(QPixmap.fromImage(self._orig_image))
                return
            lut = _build_lut(brightness, contrast_slider)
            img32 = self._orig_image.convertToFormat(QImage.Format.Format_RGB32)
            if img32.isNull():
                return
            ptr = img32.bits()
            ptr.setsize(img32.sizeInBytes())
            self._bc_buffer = bytearray(bytes(ptr).translate(lut))
            adj = QImage(self._bc_buffer, img32.width(), img32.height(),
                         img32.bytesPerLine(), QImage.Format.Format_RGB32)
            self._pixmap_item.setPixmap(QPixmap.fromImage(adj))
        except Exception:
            pass

    def _add_item(self, item):
        self._scene.addItem(item)
        item.annotation_changed.connect(self.annotation_changed)
        item.editing_started.connect(self.pre_edit_started)
        if isinstance(item, SegmentItem):
            item.convert_to_bbox_requested.connect(
                lambda i=item: self.segment_convert_requested.emit(i))

    def _on_crop_rect_changed(self, rect: QRectF):
        for item in self._scene.items():
            if isinstance(item, (BBoxItem, SegmentItem)):
                item.set_crop_hint(rect)

    def _clear_crop_hints(self):
        for item in self._scene.items():
            if isinstance(item, (BBoxItem, SegmentItem)):
                item.set_crop_hint(None)

    def _create_crosshairs(self):
        for attr in ('_cross_h', '_cross_v'):
            old = getattr(self, attr, None)
            if old is not None:
                try:
                    self._scene.removeItem(old)
                except Exception:
                    pass

        self._cross_h = QGraphicsLineItem(0, 0, self._img_w, 0)
        self._cross_h.setPen(_CROSS_PEN)
        self._cross_h.setZValue(50)
        self._cross_h.setVisible(False)
        self._cross_h.setFlag(
            self._cross_h.GraphicsItemFlag.ItemIsSelectable, False)
        self._cross_h.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._scene.addItem(self._cross_h)

        self._cross_v = QGraphicsLineItem(0, 0, 0, self._img_h)
        self._cross_v.setPen(_CROSS_PEN)
        self._cross_v.setZValue(50)
        self._cross_v.setVisible(False)
        self._cross_v.setFlag(
            self._cross_v.GraphicsItemFlag.ItemIsSelectable, False)
        self._cross_v.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._scene.addItem(self._cross_v)

    def _cancel_draw(self):
        if self._draw_preview:
            self._scene.removeItem(self._draw_preview)
            self._draw_preview = None
        self._drawing = False
        self._draw_start = None

    def _update_crosshair(self, scene_pos: QPointF):
        if self._cross_h and self._cross_v and self._draw_mode:
            x, y = scene_pos.x(), scene_pos.y()
            self._cross_h.setLine(0, y, self._img_w, y)
            self._cross_v.setLine(x, 0, x, self._img_h)
            self._cross_h.setVisible(True)
            self._cross_v.setVisible(True)

    def _item_at(self, vp_pos) -> object:
        """Return the topmost BBoxItem/SegmentItem at the given viewport position."""
        for it in self.items(vp_pos):
            if isinstance(it, (BBoxItem, SegmentItem)):
                return it
            parent = it.parentItem() if hasattr(it, 'parentItem') else None
            if isinstance(parent, (BBoxItem, SegmentItem)):
                return parent
        return None

    # ── mouse events ─────────────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        event.accept()   # suppress right-click context menu (right btn used for pan)

    def mousePressEvent(self, event):
        # Shift+left click: toggle item selection (add to / remove from selection)
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._draw_mode and not self._crop_mode
                and event.modifiers() == Qt.KeyboardModifier.ShiftModifier):
            item = self._item_at(event.pos())
            if item is not None:
                item.setSelected(not item.isSelected())
                event.accept()
                return

        # Pan button: start pan
        if event.button() == self._pan_button:
            self._pan_active = True
            self._pan_start = event.position()
            self._apply_mode_cursor()
            event.accept()
            return

        # Fit button: fit image to view
        if event.button() == self._fit_button:
            self._user_zoomed = False
            self.fitInView(QRectF(0, 0, self._img_w, self._img_h),
                           Qt.AspectRatioMode.KeepAspectRatio)
            event.accept()
            return

        # Left button in draw mode: draw new bbox
        if self._draw_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.pos())
            if self._pixmap_item and self._pixmap_item.boundingRect().contains(pos):
                self._drawing = True
                self._draw_start = pos
                self._draw_preview = QGraphicsRectItem()
                pen = QPen(self._cur_color, 2, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self._draw_preview.setPen(pen)
                self._draw_preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                self._draw_preview.setZValue(100)
                self._scene.addItem(self._draw_preview)
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Pan
        if self._pan_active:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return

        # Draw preview (clamped to image bounds)
        if self._drawing and self._draw_preview and self._draw_start:
            pos = self.mapToScene(event.pos())
            pos = QPointF(max(0.0, min(float(self._img_w), pos.x())),
                          max(0.0, min(float(self._img_h), pos.y())))
            self._draw_preview.setRect(QRectF(self._draw_start, pos).normalized())

        # Crosshair
        self._update_crosshair(self.mapToScene(event.pos()))

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # End pan
        if event.button() == self._pan_button and self._pan_active:
            self._pan_active = False
            self._apply_mode_cursor()
            event.accept()
            return

        # Finish drawing bbox
        if self._drawing and event.button() == Qt.MouseButton.LeftButton:
            rect = QRectF()
            if self._draw_preview:
                rect = self._draw_preview.rect().normalized()
                # Final clamp to image bounds
                img_r = QRectF(0, 0, self._img_w, self._img_h)
                rect = rect.intersected(img_r)
                self._scene.removeItem(self._draw_preview)
                self._draw_preview = None
            self._drawing = False
            self._draw_start = None
            if rect.width() > 4 and rect.height() > 4:
                self.pre_edit_started.emit()   # capture state BEFORE item is added
                item = BBoxItem(rect, self._cur_class_id,
                                self._cur_class_name, self._cur_color)
                item.set_image_bounds(self._img_w, self._img_h)
                self._add_item(item)
                item.setSelected(True)
                self.annotation_added.emit(item)
                self.annotation_changed.emit()
            return

        super().mouseReleaseEvent(event)

    @property
    def image_size(self) -> tuple[int, int]:
        return self._img_w, self._img_h

    def leaveEvent(self, event):
        if self._cross_h:
            self._cross_h.setVisible(False)
        if self._cross_v:
            self._cross_v.setVisible(False)
        super().leaveEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            set_label_px(get_label_px() + delta)
            self._scene.update()
            self.label_size_changed.emit(get_label_px())
            return
        self._user_zoomed = True
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._user_zoomed and self._img_w > 1:
            self.fitInView(QRectF(0, 0, self._img_w, self._img_h),
                           Qt.AspectRatioMode.KeepAspectRatio)

    def keyPressEvent(self, event):
        if self._crop_mode:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                rect = self._crop_item.get_rect() if self._crop_item else QRectF()
                self.stop_crop_mode()
                if rect.isValid() and rect.width() > 1 and rect.height() > 1:
                    self.crop_confirmed.emit(rect)
                return
            if event.key() == Qt.Key.Key_Escape:
                self.stop_crop_mode()
                self.crop_cancelled.emit()
                return
        if event.key() == Qt.Key.Key_0:
            self._user_zoomed = False
            self.fitInView(QRectF(0, 0, self._img_w, self._img_h),
                           Qt.AspectRatioMode.KeepAspectRatio)
        else:
            super().keyPressEvent(event)
