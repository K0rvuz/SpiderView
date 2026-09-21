from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from ..models import PageNode


class NoteDialog(QDialog):
    COLORS = (
        ("Dourado", "#D9A441"),
        ("Azul", "#4F8AC9"),
        ("Verde", "#4FA36C"),
        ("Vermelho", "#C85C5C"),
        ("Roxo", "#8A69B8"),
        ("Cinza", "#7D8792"),
    )

    def __init__(self, node: PageNode, parent=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle("Editar nota")
        self.setMinimumWidth(500)

        metadata = node.metadata or {}
        self.title_edit = QLineEdit(node.title or "Nota")
        self.body_edit = QTextEdit(str(metadata.get("note_text", "") or ""))
        self.body_edit.setMinimumHeight(180)

        tags = metadata.get("tags", []) or []
        if isinstance(tags, str):
            tags = [tags]
        self.tags_edit = QLineEdit(", ".join(str(tag) for tag in tags))
        self.tags_edit.setPlaceholderText("auth, evidência, revisar")

        self.color_combo = QComboBox()
        current_color = str(metadata.get("color", "#D9A441") or "#D9A441")
        current_index = 0
        for index, (label, value) in enumerate(self.COLORS):
            self.color_combo.addItem(label, value)
            if value.lower() == current_color.lower():
                current_index = index
        self.color_combo.setCurrentIndex(current_index)

        form = QFormLayout()
        form.addRow("Título", self.title_edit)
        form.addRow("Texto", self.body_edit)
        form.addRow("Tags", self.tags_edit)
        form.addRow("Cor", self.color_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def apply_to_node(self) -> None:
        self.node.title = self.title_edit.text().strip() or "Nota"
        tags = [
            part.strip().lstrip("#")
            for part in self.tags_edit.text().split(",")
            if part.strip().lstrip("#")
        ]
        metadata = dict(self.node.metadata or {})
        metadata["note_text"] = self.body_edit.toPlainText().strip()
        metadata["tags"] = tags
        metadata["color"] = str(self.color_combo.currentData() or "#D9A441")
        self.node.metadata = metadata

    @classmethod
    def edit_node(cls, parent, node: PageNode) -> bool:
        dialog = cls(node, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        dialog.apply_to_node()
        return True
