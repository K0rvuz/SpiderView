import unittest

from spiderview.security_observations import (
    build_security_observations,
    redact_event_for_persistence,
)


class SecurityObservationsTests(unittest.TestCase):
    def test_builds_cors_and_header_observations(self):
        event = {
            "source_url": "https://app.example.test/page",
            "request_url": "https://api.example.test/users",
            "url": "https://api.example.test/users",
            "response_headers": {
                "Access-Control-Allow-Origin": "https://app.example.test",
                "Strict-Transport-Security": "max-age=31536000",
                "X-Content-Type-Options": "nosniff",
            },
        }

        observations = build_security_observations(
            event,
            cookie_summary={
                "count": 2,
                "http_only_true": 1,
                "http_only_false": 1,
                "secure_true": 2,
                "secure_false": 0,
                "same_site": {
                    "Lax": 2,
                },
                "names": [
                    "session",
                    "prefs",
                ],
            },
        )

        self.assertTrue(
            observations["https"]
        )
        self.assertTrue(
            observations["cross_origin"]
        )
        self.assertTrue(
            observations["cors_header_observed"]
        )
        self.assertEqual(
            observations["access_control_allow_origin"],
            "https://app.example.test",
        )
        self.assertTrue(
            observations["hsts"]
        )
        self.assertTrue(
            observations["x_content_type_options"]
        )
        self.assertFalse(
            observations["csp"]
        )
        self.assertEqual(
            observations["cookies"]["http_only_false"],
            1,
        )

    def test_redacts_credentials_and_drops_body(self):
        event = {
            "method": "POST",
            "request_headers": {
                "Authorization": "Bearer secret",
                "X-API-Key": "abc123",
                "Content-Type": "application/json",
            },
            "request_body": '{"password":"secret"}',
            "response_headers": {
                "content-type": "application/json",
            },
        }

        safe = redact_event_for_persistence(
            event
        )

        self.assertEqual(
            safe["request_headers"]["authorization"],
            "[redacted]",
        )
        self.assertEqual(
            safe["request_headers"]["x-api-key"],
            "[redacted]",
        )
        self.assertEqual(
            safe["request_headers"]["content-type"],
            "application/json",
        )
        self.assertEqual(
            safe["request_body"],
            "[not persisted]",
        )
        self.assertGreater(
            safe["request_body_length"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
