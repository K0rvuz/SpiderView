from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from spiderview.models import NodeKind, PageNode, Transition, TransitionType
from spiderview.persistence.project_store import ProjectStore


class NoteConnectionTests(unittest.TestCase):
    def test_manual_note_edge_roundtrip(self):
        note = PageNode(
            id="note-a",
            title="Auth note",
            url="",
            kind=NodeKind.NOTE,
            method="",
            metadata={"note_text": "Relacionado ao login"},
        )
        page = PageNode(
            id="page-b",
            title="Login",
            url="https://example.test/login",
        )
        edge = Transition(
            id="edge-c",
            source_id=note.id,
            target_id=page.id,
            type=TransitionType.MANUAL,
            label="note",
            metadata={"manual_note": True},
        )

        with TemporaryDirectory() as temp:
            project = Path(temp) / "note-link.spiderview"
            ProjectStore.save(project, [note, page], [edge])
            nodes, transitions = ProjectStore.load(project)

        self.assertEqual(len(nodes), 2)
        self.assertEqual(len(transitions), 1)
        loaded = transitions[0]
        self.assertEqual(loaded.source_id, note.id)
        self.assertEqual(loaded.target_id, page.id)
        self.assertEqual(loaded.type, TransitionType.MANUAL)
        self.assertTrue(loaded.metadata.get("manual_note"))


if __name__ == "__main__":
    unittest.main()
