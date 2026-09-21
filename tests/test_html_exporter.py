from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from spiderview.export.html_exporter import HtmlExporter
from spiderview.models import PageNode, Transition, TransitionType


class HtmlExporterInteractionTests(unittest.TestCase):
    def test_export_contains_read_only_card_dragging(self):
        source = PageNode(
            id="page-a",
            title="Home",
            url="https://example.test/",
            x=10,
            y=20,
        )
        target = PageNode(
            id="page-b",
            title="Dashboard",
            url="https://example.test/dashboard",
            x=500,
            y=20,
        )
        edge = Transition(
            id="edge-a",
            source_id=source.id,
            target_id=target.id,
            type=TransitionType.CLICK,
            label="open dashboard",
        )

        with TemporaryDirectory() as temp:
            output = Path(temp) / "view.html"

            HtmlExporter().export(
                output,
                [source, target],
                [edge],
            )

            html = output.read_text(
                encoding="utf-8"
            )

        self.assertIn(
            "function startCardDrag",
            html,
        )
        self.assertIn(
            "function moveCardDrag",
            html,
        )
        self.assertIn(
            "function endCardDrag",
            html,
        )
        self.assertIn(
            "renderEdges();",
            html,
        )
        self.assertIn(
            "function cardAnchor",
            html,
        )
        self.assertIn(
            "marker-end",
            html,
        )
        self.assertIn(
            "Arraste um card: mover",
            html,
        )
        self.assertNotIn(
            'contenteditable="true"',
            html,
        )


if __name__ == "__main__":
    unittest.main()
