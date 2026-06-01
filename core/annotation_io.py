from pathlib import Path
from typing import List

from core.models import Annotation, AnnType, IMAGE_EXTENSIONS


def get_images(images_dir: Path) -> List[Path]:
    return sorted(p for p in images_dir.iterdir()
                  if p.suffix.lower() in IMAGE_EXTENSIONS)


def get_label_path(image_path: Path) -> Path:
    parts = list(image_path.parts)
    replaced = False
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == 'images':
            parts[i] = 'labels'
            replaced = True
            break
    label = Path(*parts).with_suffix('.txt')
    if not replaced:
        label = image_path.with_suffix('.txt')
    return label


def load_annotations(image_path: Path) -> List[Annotation]:
    txt_path = get_label_path(image_path)
    if not txt_path.exists():
        return []
    result = []
    with open(txt_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            class_id = int(parts[0])
            values = [float(x) for x in parts[1:]]
            ann_type = AnnType.BBOX if len(values) == 4 else AnnType.SEGMENT
            result.append(Annotation(class_id, ann_type, values))
    return result


def save_annotations(image_path: Path, annotations: List[Annotation]):
    txt_path = get_label_path(image_path)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_path, 'w') as f:
        for ann in annotations:
            f.write(ann.to_line() + '\n')
