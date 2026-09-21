from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from spiderview.export.html_exporter import HtmlExporter
from spiderview.models import NodeKind, PageNode, Transition
from spiderview.persistence.migrations import migrate_payload


class EditorFoundationTests(unittest.TestCase):
    def test_migrate_v1_to_v2(self):
        payload = {
            "format": "spiderview",
            "version": 1,
            "nodes": [{"id": "a", "title": "A", "url": "", "metadata": None}],
            "transitions": [],
        }
        migrated = migrate_payload(payload, target_version=2)
        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["nodes"][0]["metadata"], {})
        self.assertEqual(migrated["project"]["schema"], "graph-v2")

    def test_html_export_contains_graph_and_note(self):
        note = PageNode(
            id="note1",
            title="Observação",
            url="",
            kind=NodeKind.NOTE,
            metadata={"note_text": "teste", "tags": ["auth"]},
        )
        page = PageNode(id="page1", title="Login", url="https://example.test/login")
        edge = Transition(source_id=note.id, target_id=page.id, label="relates")
        with TemporaryDirectory() as temp:
            path = Path(temp) / "snapshot.html"
            HtmlExporter().export(path, [note, page], [edge])
            text = path.read_text(encoding="utf-8")
        self.assertIn("Observação", text)
        self.assertIn("Login", text)
        self.assertIn("relates", text)


if __name__ == "__main__":
    unittest.main()
