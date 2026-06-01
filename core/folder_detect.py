from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

from core.models import IMAGE_EXTENSIONS

_SPLIT_NAMES: Set[str] = {"train", "val", "test", "valid"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _images(d: Path) -> List[Path]:
    if not d.is_dir():
        return []
    return [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]


def _txts(d: Path) -> List[Path]:
    if not d.is_dir():
        return []
    return [p for p in d.iterdir() if p.is_file() and p.suffix == '.txt']


def _scan_class_ids(paths) -> Set[int]:
    ids: Set[int] = set()
    for p in paths:
        try:
            for line in Path(p).read_text(encoding='utf-8', errors='ignore').splitlines():
                tok = line.strip().split()
                if tok:
                    try:
                        ids.add(int(tok[0]))
                    except ValueError:
                        pass
        except OSError:
            pass
    return ids


# ── public data types ─────────────────────────────────────────────────────────

@dataclass
class Proposal:
    key: str
    label: str
    required: bool = False


@dataclass
class _SplitState:
    name: str
    split_dir: Path
    cur_img_dir: Path
    has_imgs_subdir: bool
    wrong_subdir_name: Optional[str]
    imgs_in_root_of_split: bool
    labels_mixed: bool
    labels_dir_exists: bool
    wrap: bool
    img_count: int
    lbl_count: int


@dataclass
class DetectResult:
    root: Path
    yaml_path: Optional[Path]
    proposals: List[Proposal]
    class_ids: Set[int]
    _splits: List[_SplitState] = field(default_factory=list, repr=False)


# ── detection ────────────────────────────────────────────────────────────────

def detect_folder(root: Path) -> DetectResult:
    root = root.resolve()

    for name in ("data.yaml", "dataset.yaml", "data.yml", "dataset.yml"):
        p = root / name
        if p.exists():
            return DetectResult(root=root, yaml_path=p, proposals=[], class_ids=set())

    split_subdirs = {
        sub.name.lower(): sub
        for sub in root.iterdir()
        if sub.is_dir() and sub.name.lower() in _SPLIT_NAMES
    }

    split_states: List[_SplitState] = []
    all_txts: List[Path] = []

    if split_subdirs:
        for sname in sorted(split_subdirs):
            st = _analyze_dir(sname, split_subdirs[sname], wrap=False)
            split_states.append(st)
    else:
        split_states.append(_analyze_dir("train", root, wrap=True))

    for st in split_states:
        all_txts.extend(_txts(st.cur_img_dir))
        lbl_dir = st.split_dir / "labels"
        if lbl_dir != st.cur_img_dir and lbl_dir.exists():
            all_txts.extend(_txts(lbl_dir))

    return DetectResult(
        root=root,
        yaml_path=None,
        proposals=_build_proposals(split_states),
        class_ids=_scan_class_ids(all_txts),
        _splits=split_states,
    )


def _analyze_dir(name: str, split_dir: Path, wrap: bool) -> _SplitState:
    imgs_in_root = len(_images(split_dir)) > 0

    img_subdir: Optional[Path] = None
    wrong_name: Optional[str] = None

    if not imgs_in_root:
        for sub in split_dir.iterdir():
            if sub.is_dir() and _images(sub):
                img_subdir = sub
                if sub.name.lower() != "images":
                    wrong_name = sub.name
                break

    cur_img_dir = img_subdir if img_subdir else split_dir
    mixed = _txts(cur_img_dir)
    lbl_dir = split_dir / "labels"

    return _SplitState(
        name=name,
        split_dir=split_dir,
        cur_img_dir=cur_img_dir,
        has_imgs_subdir=img_subdir is not None,
        wrong_subdir_name=wrong_name,
        imgs_in_root_of_split=imgs_in_root,
        labels_mixed=len(mixed) > 0,
        labels_dir_exists=lbl_dir.is_dir(),
        wrap=wrap,
        img_count=len(_images(cur_img_dir)),
        lbl_count=len(mixed) or len(_txts(lbl_dir)),
    )


def _build_proposals(splits: List[_SplitState]) -> List[Proposal]:
    props: List[Proposal] = []

    for st in splits:
        prefix = "" if st.wrap else f"[{st.name}] "

        # Images placement
        if st.img_count > 0:
            if st.imgs_in_root_of_split:
                dest = f"{st.name}/images/" if st.wrap else "images/"
                props.append(Proposal(
                    f"imgs_files:{st.name}",
                    f"{prefix}Переместить {st.img_count} фото → {dest}",
                ))
            elif st.wrong_subdir_name:
                dest = f"{st.name}/images/" if st.wrap else "images/"
                props.append(Proposal(
                    f"imgs_dir:{st.name}",
                    f"{prefix}Переименовать '{st.wrong_subdir_name}/' → '{dest}'",
                ))
            elif st.wrap and st.has_imgs_subdir:
                # correct name "images/" but needs wrapping into train/
                props.append(Proposal(
                    f"imgs_dir:{st.name}",
                    f"Переместить 'images/' → '{st.name}/images/'",
                ))

        # Labels placement
        if st.labels_mixed and st.lbl_count > 0:
            dest = f"{st.name}/labels/" if st.wrap else "labels/"
            props.append(Proposal(
                f"lbls_mixed:{st.name}",
                f"{prefix}Вынести {st.lbl_count} файлов меток → {dest}",
            ))
        elif st.labels_dir_exists and st.wrap:
            props.append(Proposal(
                f"lbls_dir:{st.name}",
                f"Переместить 'labels/' → '{st.name}/labels/'",
            ))

    props.append(Proposal("create_yaml", "Создать data.yaml", required=True))
    return props


# ── execution ────────────────────────────────────────────────────────────────

def execute_normalization(
    result: DetectResult,
    accepted: Set[str],
    class_names: List[str],
) -> Path:
    """Execute accepted proposals, write data.yaml, return its path."""
    root = result.root
    final_splits: Dict[str, Path] = {}

    for st in result._splits:
        final_img_dir = st.cur_img_dir

        imgs_files_key = f"imgs_files:{st.name}"
        imgs_dir_key   = f"imgs_dir:{st.name}"
        lbls_mixed_key = f"lbls_mixed:{st.name}"
        lbls_dir_key   = f"lbls_dir:{st.name}"

        target_imgs = (root / st.name / "images") if st.wrap else (st.split_dir / "images")
        target_lbls = (root / st.name / "labels") if st.wrap else (st.split_dir / "labels")

        # -- move images --
        if imgs_files_key in accepted:
            target_imgs.mkdir(parents=True, exist_ok=True)
            for img in _images(st.cur_img_dir):
                shutil.move(str(img), str(target_imgs / img.name))
            final_img_dir = target_imgs
            lbl_source = st.cur_img_dir   # txts still in original dir

        elif imgs_dir_key in accepted:
            target_imgs.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(st.cur_img_dir), str(target_imgs))
            final_img_dir = target_imgs
            lbl_source = target_imgs       # txts moved together with dir

        else:
            lbl_source = st.cur_img_dir

        # -- move labels --
        if lbls_mixed_key in accepted:
            target_lbls.mkdir(parents=True, exist_ok=True)
            for txt in list(lbl_source.iterdir()):
                if txt.suffix == '.txt':
                    shutil.move(str(txt), str(target_lbls / txt.name))

        elif lbls_dir_key in accepted:
            src_lbls = st.split_dir / "labels"
            if src_lbls.is_dir():
                target_lbls.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_lbls), str(target_lbls))

        final_splits[st.name] = final_img_dir

    # write yaml
    data: dict = {"nc": len(class_names), "names": class_names}
    for sname, img_dir in final_splits.items():
        try:
            rel = img_dir.relative_to(root)
        except ValueError:
            rel = img_dir
        data[sname] = str(rel).replace("\\", "/")

    yaml_path = root / "data.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    return yaml_path
