from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QFont


def _draw_icon(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = size
    m = s * 0.03  # margin
    r = s * 0.18  # corner radius

    # Background — dark navy
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#1c2b3a")))
    p.drawRoundedRect(int(m), int(m), int(s - 2 * m), int(s - 2 * m), r, r)

    # Image frame — muted steel blue rectangle
    frame_margin = s * 0.14
    frame_w = s - 2 * frame_margin
    frame_h = frame_w * 0.72
    frame_y = (s - frame_h) / 2
    frame_pen = QPen(QColor("#4a7fa5"), max(1, s * 0.04))
    frame_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    frame_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(frame_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(
        int(frame_margin), int(frame_y),
        int(frame_w), int(frame_h),
    )

    # Bounding box — amber, slightly inset from frame
    inset = s * 0.13
    bx = frame_margin + inset
    by = frame_y + inset * 0.7
    bw = frame_w - 2 * inset
    bh = frame_h - 2 * inset * 0.7

    p.setBrush(QBrush(QColor(245, 166, 35, 45)))
    bbox_pen = QPen(QColor("#f5a623"), max(1, s * 0.045))
    bbox_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    bbox_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(bbox_pen)
    p.drawRect(int(bx), int(by), int(bw), int(bh))

    # Corner handles — filled amber squares
    h = max(3, int(s * 0.095))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#f5a623")))
    corners = [
        (int(bx) - h // 2, int(by) - h // 2),
        (int(bx + bw) - h // 2, int(by) - h // 2),
        (int(bx) - h // 2, int(by + bh) - h // 2),
        (int(bx + bw) - h // 2, int(by + bh) - h // 2),
    ]
    for cx, cy in corners:
        p.drawRoundedRect(cx, cy, h, h, h * 0.25, h * 0.25)

    p.end()
    return pix


def make_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw_icon(size))
    return icon
