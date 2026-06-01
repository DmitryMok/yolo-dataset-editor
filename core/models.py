from dataclasses import dataclass
from typing import List
from enum import Enum, auto

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}


class AnnType(Enum):
    BBOX = auto()
    SEGMENT = auto()


@dataclass
class Annotation:
    class_id: int
    ann_type: AnnType
    data: List[float]  # bbox: [cx,cy,w,h]; segment: [x1,y1,x2,y2,...]

    def to_bbox(self) -> 'Annotation':
        if self.ann_type == AnnType.BBOX:
            return Annotation(self.class_id, AnnType.BBOX, self.data[:])
        xs = self.data[0::2]
        ys = self.data[1::2]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        return Annotation(self.class_id, AnnType.BBOX,
                          [(x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1])

    def to_line(self) -> str:
        parts = [str(self.class_id)] + [f'{v:.6f}' for v in self.data]
        return ' '.join(parts)
