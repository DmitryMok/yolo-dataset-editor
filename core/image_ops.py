from typing import List

from core.models import Annotation, AnnType


def recalc_annotations_crop(
    anns: List[Annotation],
    img_w: float, img_h: float,
    cx: float, cy: float, cw: float, ch: float,
) -> List[Annotation]:
    result = []
    for ann in anns:
        if ann.ann_type == AnnType.BBOX:
            ncx, ncy, nw, nh = ann.data
            x1 = (ncx - nw / 2) * img_w;  x2 = (ncx + nw / 2) * img_w
            y1 = (ncy - nh / 2) * img_h;  y2 = (ncy + nh / 2) * img_h
            x1c = max(x1, cx) - cx;  x2c = min(x2, cx + cw) - cx
            y1c = max(y1, cy) - cy;  y2c = min(y2, cy + ch) - cy
            if x2c > x1c and y2c > y1c:
                result.append(Annotation(ann.class_id, AnnType.BBOX, [
                    (x1c + x2c) / (2 * cw), (y1c + y2c) / (2 * ch),
                    (x2c - x1c) / cw,        (y2c - y1c) / ch]))
        elif ann.ann_type == AnnType.SEGMENT:
            pts = [(ann.data[i] * img_w, ann.data[i+1] * img_h)
                   for i in range(0, len(ann.data), 2)]
            xs = [p[0] for p in pts];  ys = [p[1] for p in pts]
            if max(xs) < cx or min(xs) > cx+cw or max(ys) < cy or min(ys) > cy+ch:
                continue
            data = []
            for px, py in pts:
                data.extend([max(0.0, min(cw, px-cx)) / cw,
                              max(0.0, min(ch, py-cy)) / ch])
            result.append(Annotation(ann.class_id, AnnType.SEGMENT, data))
    return result


def recalc_annotations_rotate(
    anns: List[Annotation],
    clockwise: bool,
) -> List[Annotation]:
    result = []
    for ann in anns:
        if ann.ann_type == AnnType.BBOX:
            cx, cy, w, h = ann.data
            if clockwise:
                result.append(Annotation(ann.class_id, AnnType.BBOX, [1-cy, cx, h, w]))
            else:
                result.append(Annotation(ann.class_id, AnnType.BBOX, [cy, 1-cx, h, w]))
        elif ann.ann_type == AnnType.SEGMENT:
            pts = [(ann.data[i], ann.data[i+1]) for i in range(0, len(ann.data), 2)]
            if clockwise:
                new_pts = [(1-y, x) for x, y in pts]
            else:
                new_pts = [(y, 1-x) for x, y in pts]
            result.append(Annotation(ann.class_id, AnnType.SEGMENT,
                                     [c for p in new_pts for c in p]))
    return result
