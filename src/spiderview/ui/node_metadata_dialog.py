from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..graph.metadata import (
    STATUS_OPTIONS,
    apply_investigation_metadata,
    node_investigation_status,
    node_tags,
)
from ..models import PageNode


class NodeMetadataDialog(QDialog):
    def __init__(self, nodes: Sequence[PageNode], parent=None):
        super().__init__(parent)

        self.nodes = list(nodes)
        count = len(self.nodes)

        self.setWindowTitle(
            "Metadados da seleção"
            if count != 1
            else "Metadados do card"
        )
        self.setMinimumWidth(430)

        intro = QLabel(f"{count} card(s) selecionado(s).")
        intro.setWordWrap(True)

        self.status_combo = QComboBox()

        if count > 1:
            self.status_combo.addItem(
                "(manter status atual)",
                None,
            )

        for label, value in STATUS_OPTIONS:
            self.status_combo.addItem(label, value)

        if count == 1:
            current = node_investigation_status(self.nodes[0])
            for index in range(self.status_combo.count()):
                if self.status_combo.itemData(index) == current:
                    self.status_combo.setCurrentIndex(index)
                    break

        self.tags_edit = QLineEdit()

        if count == 1:
            self.tags_edit.setText(
                ", ".join(node_tags(self.nodes[0]))
            )
        else:
            self.tags_edit.setPlaceholderText(
                "ex.: auth, admin, revisar"
            )

        self.append_tags = QCheckBox(
            "Adicionar às tags existentes"
        )
        self.append_tags.setChecked(count > 1)

        form = QFormLayout()
        form.addRow("Status", self.status_combo)
        form.addRow("Tags", self.tags_edit)
        form.addRow("", self.append_tags)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def apply(self) -> None:
        status = self.status_combo.currentData()
        raw_tags = self.tags_edit.text()

        tags = raw_tags
        if len(self.nodes) > 1 and not raw_tags.strip():
            tags = None

        for node in self.nodes:
            apply_investigation_metadata(
                node,
                status=status,
                tags=tags,
                append_tags=self.append_tags.isChecked(),
            )

    @classmethod
    def edit_nodes(
        cls,
        parent,
        nodes: Sequence[PageNode],
    ) -> bool:
        if not nodes:
            return False

        dialog = cls(nodes, parent)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        dialog.apply()
        return True
