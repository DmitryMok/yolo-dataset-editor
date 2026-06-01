from typing import List, Set
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QCheckBox,
    QDialogButtonBox, QPlainTextEdit, QGroupBox,
)
from PyQt6.QtCore import Qt

from core.folder_detect import DetectResult


class FolderImportDialog(QDialog):
    def __init__(self, result: DetectResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройка датасета")
        self.setModal(True)
        self.setMinimumWidth(500)
        self._result = result
        self._checkboxes: dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Path header
        lbl = QLabel(f"<b>Корень датасета:</b> {self._result.root}")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(lbl)

        # Proposals
        action_proposals = [p for p in self._result.proposals if not p.required]
        required_proposals = [p for p in self._result.proposals if p.required]

        if action_proposals:
            grp = QGroupBox("Предлагаемые изменения")
            glay = QVBoxLayout(grp)
            glay.setSpacing(4)
            for prop in action_proposals:
                cb = QCheckBox(prop.label)
                cb.setChecked(True)
                self._checkboxes[prop.key] = cb
                glay.addWidget(cb)
            layout.addWidget(grp)
        else:
            layout.addWidget(QLabel("Структура папок уже соответствует стандарту."))

        if required_proposals:
            grp2 = QGroupBox("Обязательные действия")
            g2lay = QVBoxLayout(grp2)
            g2lay.setSpacing(4)
            for prop in required_proposals:
                cb = QCheckBox(prop.label)
                cb.setChecked(True)
                cb.setEnabled(False)
                self._checkboxes[prop.key] = cb
                g2lay.addWidget(cb)
            layout.addWidget(grp2)

        # Class names
        grp3 = QGroupBox("Имена классов (по одному на строку)")
        g3lay = QVBoxLayout(grp3)
        self._classes_edit = QPlainTextEdit()
        self._classes_edit.setFixedHeight(90)
        if self._result.class_ids:
            text = "\n".join(f"class_{i}" for i in sorted(self._result.class_ids))
        else:
            text = "class_0"
        self._classes_edit.setPlainText(text)
        hint = QLabel("Переименуйте классы после загрузки датасета.")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        g3lay.addWidget(self._classes_edit)
        g3lay.addWidget(hint)
        layout.addWidget(grp3)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Применить и открыть")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def accepted_keys(self) -> Set[str]:
        return {key for key, cb in self._checkboxes.items() if cb.isChecked()}

    def class_names(self) -> List[str]:
        text = self._classes_edit.toPlainText().strip()
        return [line.strip() for line in text.splitlines() if line.strip()]
