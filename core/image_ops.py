from typing import List

from core.models import Annotation, AnnType


def _viewport_transform(
    anns: List[Annotation],
    src_w: float, src_h: float,
    scale: float,
    offset_x: float, offset_y: float,
    clip_w: float, clip_h: float,
    out_offset_x: float, out_offset_y: float,
    out_w: float, out_h: float,
) -> List[Annotation]:
    """
    General viewport transform for annotations.

    Pipeline per point:
      1. norm → src pixels:    px = x * src_w
      2. scale:                px *= scale
      3. subtract offset:      px -= offset_x
      4. clip to [0, clip_w]
      5. translate to output:  px += out_offset_x
      6. normalize:            x_out = px / out_w

    Annotations clipped entirely outside the viewport are dropped.
    """
    result = []
    for ann in anns:
        if ann.ann_type == AnnType.BBOX:
            ncx, ncy, nw, nh = ann.data
            sx1 = (ncx - nw / 2) * src_w * scale - offset_x
            sx2 = (ncx + nw / 2) * src_w * scale - offset_x
            sy1 = (ncy - nh / 2) * src_h * scale - offset_y
            sy2 = (ncy + nh / 2) * src_h * scale - offset_y
            cx1 = max(sx1, 0.0);  cx2 = min(sx2, clip_w)
            cy1 = max(sy1, 0.0);  cy2 = min(sy2, clip_h)
            if cx2 <= cx1 or cy2 <= cy1:
                continue
            result.append(Annotation(ann.class_id, AnnType.BBOX, [
                ((cx1 + cx2) / 2 + out_offset_x) / out_w,
                ((cy1 + cy2) / 2 + out_offset_y) / out_h,
                (cx2 - cx1) / out_w,
                (cy2 - cy1) / out_h,
            ]))
        elif ann.ann_type == AnnType.SEGMENT:
            pts = [(ann.data[i] * src_w * scale - offset_x,
                    ann.data[i + 1] * src_h * scale - offset_y)
                   for i in range(0, len(ann.data), 2)]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if max(xs) < 0 or min(xs) > clip_w or max(ys) < 0 or min(ys) > clip_h:
                continue
            data = []
            for px, py in pts:
                data.extend([
                    (max(0.0, min(clip_w, px)) + out_offset_x) / out_w,
                    (max(0.0, min(clip_h, py)) + out_offset_y) / out_h,
                ])
            result.append(Annotation(ann.class_id, AnnType.SEGMENT, data))
    return result


def recalc_annotations_crop(
    anns: List[Annotation],
    img_w: float, img_h: float,
    cx: float, cy: float, cw: float, ch: float,
) -> List[Annotation]:
    return _viewport_transform(
        anns, img_w, img_h,
        scale=1.0, offset_x=cx, offset_y=cy,
        clip_w=cw, clip_h=ch,
        out_offset_x=0.0, out_offset_y=0.0,
        out_w=cw, out_h=ch,
    )


def recalc_annotations_mosaic(
    anns: List[Annotation],
    src_w: float, src_h: float,
    tile_scale: float,
    crop_x: float, crop_y: float,
    cell_x: float, cell_y: float,
    cell_w: float, cell_h: float,
    out_w: float, out_h: float,
) -> List[Annotation]:
    return _viewport_transform(
        anns, src_w, src_h,
        scale=tile_scale, offset_x=crop_x, offset_y=crop_y,
        clip_w=cell_w, clip_h=cell_h,
        out_offset_x=cell_x, out_offset_y=cell_y,
        out_w=out_w, out_h=out_h,
    )


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
