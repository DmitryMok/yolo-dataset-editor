import yaml
from pathlib import Path
from typing import Dict, List, Optional


class DatasetConfig:
    def __init__(self, yaml_path: str):
        self.config_path = Path(yaml_path).resolve()
        self.config_dir = self.config_path.parent

        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)

        self.nc: int = data.get('nc', 0)
        names_raw = data.get('names', [])
        if isinstance(names_raw, dict):
            self.names: List[str] = [names_raw[i] for i in sorted(names_raw.keys())]
        else:
            self.names: List[str] = list(names_raw)

        self.splits: Dict[str, Path] = {}
        for split in ['train', 'val', 'test']:
            rel = data.get(split)
            if rel:
                resolved = self._resolve(rel)
                if resolved:
                    self.splits[split] = resolved

    def _resolve(self, rel: str) -> Optional[Path]:
        """Resolve a YAML path against the config dir.

        Roboflow often writes '../train/images' when the folder is actually
        'train/images' next to data.yaml.  We try several candidates.
        """
        candidates = []

        # 1. Direct resolution (handles correct relative paths)
        candidates.append((self.config_dir / rel).resolve())

        # 2. Strip every leading '..' component and retry
        #    e.g. '../train/images' → 'train/images' relative to config_dir
        parts = Path(rel).parts
        stripped = [p for p in parts if p != '..']
        if stripped and stripped != list(parts):
            candidates.append((self.config_dir / Path(*stripped)).resolve())

        # 3. Just the last component inside config_dir
        #    e.g. '../train/images' → config_dir / 'images'
        if parts:
            candidates.append((self.config_dir / parts[-1]).resolve())

        for p in candidates:
            if p.exists():
                return p
        return None
