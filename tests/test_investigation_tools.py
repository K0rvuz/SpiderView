from __future__ import annotations

import unittest

from spiderview.graph.metadata import (
    apply_investigation_metadata,
    node_investigation_status,
    node_tags,
    normalize_tags,
)
from spiderview.models import PageNode


class InvestigationMetadataTests(unittest.TestCase):
    def test_normalize_tags(self):
        self.assertEqual(
            normalize_tags("auth, #Admin, AUTH, , revisar"),
            ["auth", "Admin", "revisar"],
        )

    def test_apply_metadata_append(self):
        node = PageNode(
            title="Login",
            url="https://example.test/login",
            metadata={"tags": ["auth"]},
        )

        apply_investigation_metadata(
            node,
            status="interesting",
            tags=["admin", "AUTH"],
            append_tags=True,
        )

        self.assertEqual(
            node_investigation_status(node),
            "interesting",
        )
        self.assertEqual(
            node_tags(node),
            ["auth", "admin"],
        )

    def test_invalid_status(self):
        node = PageNode(title="X", url="")

        with self.assertRaises(ValueError):
            apply_investigation_metadata(
                node,
                status="not-a-status",
            )


if __name__ == "__main__":
    unittest.main()
