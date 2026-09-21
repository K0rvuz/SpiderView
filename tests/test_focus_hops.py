from __future__ import annotations

import unittest

from spiderview.graph.graph_model import GraphModel
from spiderview.graph.query import ViewQuery, collect_focus_nodes
from spiderview.models import PageNode, Transition, TransitionType


class FocusHopTests(unittest.TestCase):
    def setUp(self):
        self.nodes = {
            node_id: PageNode(
                id=node_id,
                title=node_id,
                url=f"https://example.test/{node_id.lower()}",
            )
            for node_id in ("A", "B", "C", "D", "E")
        }

        self.graph = GraphModel(
            nodes=self.nodes.values(),
            transitions=[
                Transition(
                    source_id="A",
                    target_id="B",
                    type=TransitionType.CLICK,
                ),
                Transition(
                    source_id="B",
                    target_id="C",
                    type=TransitionType.CLICK,
                ),
                Transition(
                    source_id="D",
                    target_id="B",
                    type=TransitionType.CLICK,
                ),
                Transition(
                    source_id="E",
                    target_id="D",
                    type=TransitionType.CLICK,
                ),
            ],
        )

        self.query = ViewQuery()

    def test_outgoing_two_hops(self):
        result = collect_focus_nodes(
            self.graph,
            {"B"},
            hops=2,
            direction="outgoing",
            query=self.query,
        )

        self.assertEqual(
            result,
            frozenset({"B", "C"}),
        )

    def test_incoming_two_hops(self):
        result = collect_focus_nodes(
            self.graph,
            {"B"},
            hops=2,
            direction="incoming",
            query=self.query,
        )

        self.assertEqual(
            result,
            frozenset({"A", "B", "D", "E"}),
        )

    def test_both_two_hops_is_union_of_both_directions_per_level(self):
        result = collect_focus_nodes(
            self.graph,
            {"B"},
            hops=2,
            direction="both",
            query=self.query,
        )

        self.assertEqual(
            result,
            frozenset({"A", "B", "C", "D", "E"}),
        )


if __name__ == "__main__":
    unittest.main()
