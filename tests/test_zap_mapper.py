from __future__ import annotations

import unittest

from spiderview.models import NodeKind, PageNode, TransitionType
from spiderview.zap.mapper import ZapMapper


def message(
    message_id: int,
    url: str,
    *,
    method: str = "GET",
    request_headers: str = "",
    status: int = 200,
    response_headers: str = "Content-Type: text/html; charset=UTF-8",
) -> dict:
    return {
        "id": str(message_id),
        "url": url,
        "method": method,
        "statusCode": status,
        "requestHeader": f"{method} {url} HTTP/1.1\r\n{request_headers}",
        "responseHeader": f"HTTP/1.1 {status} Test\r\n{response_headers}",
        "requestBody": "should not be persisted",
        "responseBody": "should not be persisted",
    }


class ZapMapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapper = ZapMapper()

    def test_maps_page_and_referer_transition(self) -> None:
        messages = [
            message(1, "https://example.test/", request_headers="Accept: text/html\r\nSec-Fetch-Dest: document"),
            message(
                2,
                "https://example.test/account",
                request_headers="Referer: https://example.test/\r\nAccept: text/html\r\nSec-Fetch-Dest: document",
            ),
        ]

        nodes, transitions = self.mapper.map_messages(messages)

        self.assertEqual(len(nodes), 2)
        self.assertTrue(all(node.kind == NodeKind.PAGE for node in nodes))
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].type, TransitionType.NAVIGATION)
        self.assertEqual(transitions[0].source_id, nodes[0].id)
        self.assertEqual(transitions[0].target_id, nodes[1].id)

    def test_maps_xhr_resource_as_api_node(self) -> None:
        messages = [
            message(1, "https://example.test/", request_headers="Accept: text/html\r\nSec-Fetch-Dest: document"),
            message(
                2,
                "https://example.test/api/profile",
                method="GET",
                request_headers=(
                    "Referer: https://example.test/\r\n"
                    "X-Requested-With: XMLHttpRequest\r\n"
                    "Accept: application/json"
                ),
                response_headers="Content-Type: application/json",
            ),
        ]

        nodes, transitions = self.mapper.map_messages(messages)

        api_nodes = [node for node in nodes if node.kind == NodeKind.API]
        self.assertEqual(len(api_nodes), 1)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].type, TransitionType.XHR)

    def test_normalizes_root_url_and_deduplicates_repeated_requests(self) -> None:
        messages = [
            message(1, "https://EXAMPLE.test"),
            message(2, "https://example.test/"),
        ]

        nodes, transitions = self.mapper.map_messages(messages)

        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].url, "https://example.test/")
        self.assertEqual(transitions, [])
        self.assertEqual(nodes[0].metadata["zap_message_ids"], ["1", "2"])

    def test_does_not_mutate_existing_graph_and_preserves_position(self) -> None:
        existing = PageNode(
            id="existing-page",
            title="My page",
            url="https://example.test/",
            x=123.0,
            y=456.0,
            metadata={"custom": "keep"},
        )
        nodes, transitions = self.mapper.map_messages(
            [message(1, "https://example.test/")],
            existing_nodes=[existing],
        )

        self.assertEqual(existing.status, None)
        self.assertEqual(existing.metadata, {"custom": "keep"})
        self.assertEqual(nodes[0].id, "existing-page")
        self.assertEqual(nodes[0].title, "My page")
        self.assertEqual((nodes[0].x, nodes[0].y), (123.0, 456.0))
        self.assertEqual(nodes[0].status, 200)
        self.assertEqual(transitions, [])

    def test_does_not_store_request_or_response_bodies(self) -> None:
        nodes, _ = self.mapper.map_messages([message(1, "https://example.test/")])

        self.assertNotIn("requestBody", nodes[0].metadata)
        self.assertNotIn("responseBody", nodes[0].metadata)
        self.assertNotIn("should not be persisted", repr(nodes[0].to_dict()))


if __name__ == "__main__":
    unittest.main()
