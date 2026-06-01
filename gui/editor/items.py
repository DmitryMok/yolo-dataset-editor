from PyQt6.QtWidgets import (QGraphicsObject, QGraphicsRectItem,
                             QGraphicsEllipseItem, QGraphicsItem)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QPointF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter, QPolygonF

HANDLE_SIZE = 9
MIN_RECT = 8
_LABEL_PX: int = 12          # label font height in screen pixels
_LABEL_MARGIN = 80           # scene-coord headroom above items for label bounding rect
_SIZE_MARGIN = 160           # bounding-rect headroom right/below for size label
_DRAG_THRESHOLD_PX = 4       # viewport pixels of movement before body-drag activates


def get_label_px() -> int:
    return _LABEL_PX


def set_label_px(px: int) -> None:
    global _LABEL_PX
    _LABEL_PX = max(8, min(32, px))

HANDLE_CURSORS = {
    'TL': Qt.CursorShape.SizeFDiagCursor,
    'TC': Qt.CursorShape.SizeVerCursor,
    'TR': Qt.CursorShape.SizeBDiagCursor,
    'ML': Qt.CursorShape.SizeHorCursor,
    'MR': Qt.CursorShape.SizeHorCursor,
    'BL': Qt.CursorShape.SizeBDiagCursor,
    'BC': Qt.CursorShape.SizeVerCursor,
    'BR': Qt.CursorShape.SizeFDiagCursor,
}


def class_color(class_id: int) -> QColor:
    hue = (class_id * 137) % 360
    return QColor.fromHsv(hue, 210, 230)


# ─── Resize handle for BBoxItem ──────────────────────────────────────────────

class _HandleItem(QGraphicsRectItem):
    def __init__(self, position: str, parent: 'BBoxItem'):
        hs = HANDLE_SIZE / 2
        super().__init__(-hs, -hs, HANDLE_SIZE, HANDLE_SIZE, parent)
        self.position = position
        self.setBrush(QBrush(Qt.GlobalColor.white))
        self.setPen(QPen(Qt.GlobalColor.darkGray, 1))
        self.setCursor(HANDLE_CURSORS.get(position, Qt.CursorShape.ArrowCursor))
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._last = QPointF()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last = event.scenePos()
            p = self.parentItem()
            if isinstance(p, BBoxItem):
                p.editing_started.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.scenePos() - self._last
            self._last = event.scenePos()
            p = self.parentItem()
            if isinstance(p, BBoxItem):
                p.move_by_handle(self.position, delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        event.accept()


# ─── Vertex handle for SegmentItem ───────────────────────────────────────────

class _VertexHandle(QGraphicsEllipseItem):
    def __init__(self, index: int, parent: 'SegmentItem'):
        r = HANDLE_SIZE / 2
        super().__init__(-r, -r, HANDLE_SIZE, HANDLE_SIZE, parent)
        self.index = index
        self.setBrush(QBrush(Qt.GlobalColor.white))
        self.setPen(QPen(Qt.GlobalColor.darkGray, 1))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._last = QPointF()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last = event.scenePos()
            p = self.parentItem()
            if isinstance(p, SegmentItem):
                p.editing_started.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.scenePos() - self._last
            self._last = event.scenePos()
            p = self.parentItem()
            if isinstance(p, SegmentItem):
                p.move_vertex(self.index, delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        event.accept()


# ─── BBoxItem ─────────────────────────────────────────────────────────────────

class BBoxItem(QGraphicsObject):
    annotation_changed = pyqtSignal()
    editing_started    = pyqtSignal()   # fired before any drag begins

    def __init__(self, rect: QRectF, class_id: int, class_name: str, color: QColor):
        super().__init__()
        self._rect = rect.normalized()
        self.class_id = class_id
        self.class_name = class_name
        self.color = color

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setZValue(1)

        self._handles: dict[str, _HandleItem] = {}
        for pos in ('TL', 'TC', 'TR', 'ML', 'MR', 'BL', 'BC', 'BR'):
            h = _HandleItem(pos, self)
            h.setVisible(False)
            self._handles[pos] = h
        self._place_handles()

        self._drag_last: QPointF | None = None
        self._drag_orig: QRectF | None = None
        self._drag_started: bool = False   # True once movement exceeds threshold
        self._drag_press_vp: QPointF | None = None   # viewport pos at press
        self._drag_siblings: list = []    # other selected items moved together
        self._crop_hint: QRectF | None = None
        self._bnd_w: int = 0
        self._bnd_h: int = 0

    def _place_handles(self):
        r = self._rect
        pts = {
            'TL': (r.left(),       r.top()),
            'TC': (r.center().x(), r.top()),
            'TR': (r.right(),      r.top()),
            'ML': (r.left(),       r.center().y()),
            'MR': (r.right(),      r.center().y()),
            'BL': (r.left(),       r.bottom()),
            'BC': (r.center().x(), r.bottom()),
            'BR': (r.right(),      r.bottom()),
        }
        for pos, (x, y) in pts.items():
            self._handles[pos].setPos(x, y)

    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_rect(self, rect: QRectF):
        self.prepareGeometryChange()
        self._rect = rect.normalized()
        self._place_handles()
        self.update()

    def move_by_handle(self, pos: str, delta: QPointF):
        r = self._rect
        x1, y1, x2, y2 = r.left(), r.top(), r.right(), r.bottom()
        if 'L' in pos: x1 += delta.x()
        if 'R' in pos: x2 += delta.x()
        if 'T' in pos: y1 += delta.y()
        if 'B' in pos: y2 += delta.y()
        if x2 - x1 < MIN_RECT:
            if 'L' in pos: x1 = x2 - MIN_RECT
            else:          x2 = x1 + MIN_RECT
        if y2 - y1 < MIN_RECT:
            if 'T' in pos: y1 = y2 - MIN_RECT
            else:          y2 = y1 + MIN_RECT
        if self._bnd_w:
            x1 = max(0.0, x1);  x2 = min(float(self._bnd_w), x2)
            if x2 - x1 < MIN_RECT:
                if 'L' in pos: x1 = max(0.0, x2 - MIN_RECT)
                else:          x2 = min(float(self._bnd_w), x1 + MIN_RECT)
        if self._bnd_h:
            y1 = max(0.0, y1);  y2 = min(float(self._bnd_h), y2)
            if y2 - y1 < MIN_RECT:
                if 'T' in pos: y1 = max(0.0, y2 - MIN_RECT)
                else:          y2 = min(float(self._bnd_h), y1 + MIN_RECT)
        self.prepareGeometryChange()
        self._rect = QRectF(x1, y1, x2 - x1, y2 - y1)
        self._place_handles()
        self.update()
        self.annotation_changed.emit()

    def set_class(self, class_id: int, class_name: str, color: QColor):
        self.class_id = class_id
        self.class_name = class_name
        self.color = color
        self.update()

    def set_crop_hint(self, rect: QRectF | None):
        self._crop_hint = rect
        self.update()

    def set_image_bounds(self, w: int, h: int):
        self._bnd_w = w
        self._bnd_h = h

    def _move_by_delta(self, delta: QPointF):
        """Move this item by delta as part of a multi-select drag led by another item."""
        self.prepareGeometryChange()
        self._rect = self._rect.translated(delta)
        self._place_handles()
        self.update()

    def _clip_to_bounds(self):
        """Clip rect to image bounds after a drag (called by drag leader on siblings)."""
        if not (self._bnd_w and self._bnd_h):
            return
        r = self._rect
        x1 = max(0.0, r.left());  x2 = min(float(self._bnd_w), r.right())
        y1 = max(0.0, r.top());   y2 = min(float(self._bnd_h), r.bottom())
        if x2 - x1 >= MIN_RECT and y2 - y1 >= MIN_RECT:
            clipped = QRectF(x1, y1, x2 - x1, y2 - y1)
            if clipped != self._rect:
                self.prepareGeometryChange()
                self._rect = clipped
                self._place_handles()
                self.update()

    def boundingRect(self) -> QRectF:
        m = HANDLE_SIZE + 2
        return self._rect.adjusted(-m, -_LABEL_MARGIN, _SIZE_MARGIN, _SIZE_MARGIN)

    def shape(self):
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRect(self._rect)
        return path

    def paint(self, painter: QPainter, option, widget):
        crop = self._crop_hint
        entirely_outside = crop is not None and not self._rect.intersects(crop)

        painter.save()
        if entirely_outside:
            painter.setOpacity(0.18)

        sel = self.isSelected()
        pen = QPen(self.color, 3 if sel else 2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        if not entirely_outside and crop is not None:
            painter.save()
            painter.setClipRect(crop)
            painter.drawRect(self._rect)
            painter.restore()
        else:
            painter.drawRect(self._rect)

        # Draw label at a fixed screen-pixel size regardless of zoom
        scale = painter.transform().m11()
        inv = 1.0 / scale if scale > 0 else 1.0
        lbl = self.class_name
        painter.save()
        painter.translate(self._rect.left(), self._rect.top())
        painter.scale(inv, inv)
        font = painter.font()
        font.setPixelSize(_LABEL_PX)
        painter.setFont(font)
        fm = painter.fontMetrics()
        lw = fm.horizontalAdvance(lbl) + 6
        lh = fm.height() + 4
        lr = QRectF(0, -lh, lw, lh)
        painter.fillRect(lr, self.color)
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(lr, Qt.AlignmentFlag.AlignCenter, lbl)
        painter.restore()

        if sel:
            size_lbl = f"{int(round(self._rect.width()))}x{int(round(self._rect.height()))}px"
            painter.save()
            painter.translate(self._rect.right(), self._rect.bottom())
            painter.scale(inv, inv)
            font2 = painter.font()
            font2.setPixelSize(_LABEL_PX)
            painter.setFont(font2)
            fm2 = painter.fontMetrics()
            sw2 = fm2.horizontalAdvance(size_lbl) + 6
            sh2 = fm2.height() + 4
            sr = QRectF(0, 0, sw2, sh2)
            painter.fillRect(sr, QColor(0, 0, 0, 160))
            painter.setPen(QPen(Qt.GlobalColor.white))
            painter.drawText(sr, Qt.AlignmentFlag.AlignCenter, size_lbl)
            painter.restore()

        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            sel = bool(value)
            for h in self._handles.values():
                h.setVisible(sel)
            self.setZValue(2 if sel else 1)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last = event.scenePos()
            self._drag_orig = QRectF(self._rect)
            self._drag_started = False
            self._drag_press_vp = event.screenPos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_last is not None:
            if not self._drag_started:
                vp = event.screenPos()
                dist = (vp - self._drag_press_vp).manhattanLength() if self._drag_press_vp else 999
                if dist < _DRAG_THRESHOLD_PX:
                    super().mouseMoveEvent(event)
                    return
                self._drag_started = True
                self.editing_started.emit()
                sc = self.scene()
                self._drag_siblings = [
                    i for i in (sc.selectedItems() if sc else [])
                    if i is not self and isinstance(i, (BBoxItem, SegmentItem))
                ]
            delta = event.scenePos() - self._drag_last
            self._drag_last = event.scenePos()
            self.prepareGeometryChange()
            self._rect = self._rect.translated(delta)
            self._place_handles()
            self.update()
            for sib in self._drag_siblings:
                sib._move_by_delta(delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_orig is not None:
            if self._bnd_w and self._bnd_h:
                r = self._rect
                x1 = max(0.0, r.left());  x2 = min(float(self._bnd_w), r.right())
                y1 = max(0.0, r.top());   y2 = min(float(self._bnd_h), r.bottom())
                if x2 - x1 >= MIN_RECT and y2 - y1 >= MIN_RECT:
                    clipped = QRectF(x1, y1, x2 - x1, y2 - y1)
                    if clipped != r:
                        self.prepareGeometryChange()
                        self._rect = clipped
                        self._place_handles()
                        self.update()
            for sib in self._drag_siblings:
                sib._clip_to_bounds()
            self._drag_siblings = []
            if self._drag_orig != self._rect:
                self.annotation_changed.emit()
            self._drag_last = None
            self._drag_orig = None
        super().mouseReleaseEvent(event)


# ─── SegmentItem ──────────────────────────────────────────────────────────────

class SegmentItem(QGraphicsObject):
    annotation_changed        = pyqtSignal()
    editing_started           = pyqtSignal()
    convert_to_bbox_requested = pyqtSignal()

    def __init__(self, points: list, class_id: int, class_name: str, color: QColor):
        super().__init__()
        self._pts: list[QPointF] = [QPointF(p) for p in points]
        self.class_id = class_id
        self.class_name = class_name
        self.color = color

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setZValue(1)

        self._vhandles: list[_VertexHandle] = []
        for i in range(len(points)):
            h = _VertexHandle(i, self)
            h.setVisible(False)
            h.setPos(self._pts[i])
            self._vhandles.append(h)

        self._drag_last: QPointF | None = None
        self._drag_started: bool = False
        self._drag_press_vp: QPointF | None = None
        self._drag_moved = False
        self._drag_siblings: list = []
        self._crop_hint: QRectF | None = None
        self._bnd_w: int = 0
        self._bnd_h: int = 0

    def points(self) -> list[QPointF]:
        return [QPointF(p) for p in self._pts]

    def move_vertex(self, idx: int, delta: QPointF):
        self.prepareGeometryChange()
        pt = self._pts[idx] + delta
        if self._bnd_w and self._bnd_h:
            pt = QPointF(max(0.0, min(float(self._bnd_w), pt.x())),
                         max(0.0, min(float(self._bnd_h), pt.y())))
        self._pts[idx] = pt
        self._vhandles[idx].setPos(pt)
        self.update()
        self.annotation_changed.emit()

    def set_class(self, class_id: int, class_name: str, color: QColor):
        self.class_id = class_id
        self.class_name = class_name
        self.color = color
        self.update()

    def set_crop_hint(self, rect: QRectF | None):
        self._crop_hint = rect
        self.update()

    def set_image_bounds(self, w: int, h: int):
        self._bnd_w = w
        self._bnd_h = h

    def _move_by_delta(self, delta: QPointF):
        """Move this item by delta as part of a multi-select drag led by another item."""
        self.prepareGeometryChange()
        self._pts = [p + delta for p in self._pts]
        for i, h in enumerate(self._vhandles):
            h.setPos(self._pts[i])
        self.update()

    def _clip_to_bounds(self):
        """Clip all vertices to image bounds (called by drag leader on siblings)."""
        if not (self._bnd_w and self._bnd_h):
            return
        bw, bh = float(self._bnd_w), float(self._bnd_h)
        clipped = [QPointF(max(0.0, min(bw, p.x())),
                           max(0.0, min(bh, p.y()))) for p in self._pts]
        if any(c != p for c, p in zip(clipped, self._pts)):
            self.prepareGeometryChange()
            self._pts = clipped
            for i, h in enumerate(self._vhandles):
                h.setPos(self._pts[i])
            self.update()

    def _polygon(self) -> QPolygonF:
        return QPolygonF(self._pts)

    def boundingRect(self) -> QRectF:
        if not self._pts:
            return QRectF()
        br = self._polygon().boundingRect()
        return br.adjusted(-HANDLE_SIZE, -_LABEL_MARGIN, HANDLE_SIZE, HANDLE_SIZE)

    def shape(self):
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addPolygon(self._polygon())
        path.closeSubpath()
        return path

    def paint(self, painter: QPainter, option, widget):
        if not self._pts:
            return
        crop = self._crop_hint
        poly = self._polygon()
        entirely_outside = crop is not None and not poly.boundingRect().intersects(crop)

        painter.save()
        if entirely_outside:
            painter.setOpacity(0.18)

        sel = self.isSelected()
        fill = QColor(self.color)
        fill.setAlpha(55)
        painter.setBrush(QBrush(fill))
        pen = QPen(self.color, 3 if sel else 2)
        pen.setCosmetic(True)
        painter.setPen(pen)

        if not entirely_outside and crop is not None:
            painter.save()
            painter.setClipRect(crop)
            painter.drawPolygon(poly)
            painter.restore()
        else:
            painter.drawPolygon(poly)

        # Draw label at a fixed screen-pixel size regardless of zoom
        pt = self._pts[0]
        scale = painter.transform().m11()
        inv = 1.0 / scale if scale > 0 else 1.0
        lbl = self.class_name
        painter.save()
        painter.translate(pt.x(), pt.y())
        painter.scale(inv, inv)
        font = painter.font()
        font.setPixelSize(_LABEL_PX)
        painter.setFont(font)
        fm = painter.fontMetrics()
        lw = fm.horizontalAdvance(lbl) + 6
        lh = fm.height() + 4
        lr = QRectF(0, -lh, lw, lh)
        painter.fillRect(lr, self.color)
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(lr, Qt.AlignmentFlag.AlignCenter, lbl)
        painter.restore()

        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            sel = bool(value)
            for h in self._vhandles:
                h.setVisible(sel)
            self.setZValue(2 if sel else 1)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last = event.scenePos()
            self._drag_started = False
            self._drag_press_vp = event.screenPos()
            self._drag_moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_last is not None:
            if not self._drag_started:
                vp = event.screenPos()
                dist = (vp - self._drag_press_vp).manhattanLength() if self._drag_press_vp else 999
                if dist < _DRAG_THRESHOLD_PX:
                    super().mouseMoveEvent(event)
                    return
                self._drag_started = True
                self.editing_started.emit()
                sc = self.scene()
                self._drag_siblings = [
                    i for i in (sc.selectedItems() if sc else [])
                    if i is not self and isinstance(i, (BBoxItem, SegmentItem))
                ]
            delta = event.scenePos() - self._drag_last
            self._drag_last = event.scenePos()
            self.prepareGeometryChange()
            self._pts = [p + delta for p in self._pts]
            for i, h in enumerate(self._vhandles):
                h.setPos(self._pts[i])
            self.update()
            self._drag_moved = True
            for sib in self._drag_siblings:
                sib._move_by_delta(delta)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.convert_to_bbox_requested.emit()
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_moved:
            if self._bnd_w and self._bnd_h:
                bw, bh = float(self._bnd_w), float(self._bnd_h)
                clipped = [QPointF(max(0.0, min(bw, p.x())),
                                   max(0.0, min(bh, p.y()))) for p in self._pts]
                if any(c != p for c, p in zip(clipped, self._pts)):
                    self.prepareGeometryChange()
                    self._pts = clipped
                    for i, h in enumerate(self._vhandles):
                        h.setPos(self._pts[i])
                    self.update()
            for sib in self._drag_siblings:
                sib._clip_to_bounds()
            self._drag_siblings = []
            self.annotation_changed.emit()
        self._drag_last = None
        self._drag_moved = False
        super().mouseReleaseEvent(event)
