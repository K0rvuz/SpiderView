import json
import unittest

from spiderview.ui.browser_console import (
    format_console_value,
    parse_headers,
)


class BrowserConsoleHelpersTests(unittest.TestCase):
    def test_parse_line_headers(self):
        headers = parse_headers(
            "Content-Type: application/json\n"
            "X-Test: abc:123"
        )

        self.assertEqual(
            headers,
            {
                "Content-Type": "application/json",
                "X-Test": "abc:123",
            },
        )

    def test_parse_json_headers(self):
        headers = parse_headers(
            json.dumps(
                {
                    "Accept": "application/json",
                    "X-Number": 42,
                }
            )
        )

        self.assertEqual(
            headers,
            {
                "Accept": "application/json",
                "X-Number": "42",
            },
        )

    def test_invalid_line_header(self):
        with self.assertRaises(ValueError):
            parse_headers(
                "Authorization Bearer token"
            )

    def test_format_json_console_value(self):
        value = format_console_value(
            {
                "type": "json",
                "value": {
                    "ok": True,
                    "items": [1, 2],
                },
            }
        )

        self.assertIn(
            '"ok": true',
            value,
        )
        self.assertIn(
            '"items": [',
            value,
        )

    def test_format_undefined(self):
        self.assertEqual(
            format_console_value(
                {
                    "type": "undefined",
                    "value": "undefined",
                }
            ),
            "undefined",
        )


if __name__ == "__main__":
    unittest.main()
