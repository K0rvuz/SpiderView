from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


SENSITIVE_REQUEST_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
    "x-access-token",
}


def normalize_headers(
    value: Any,
) -> dict[str, str]:
    if not isinstance(
        value,
        dict,
    ):
        return {}

    return {
        str(name).strip().lower():
            str(header_value)
        for name, header_value
        in value.items()
        if str(name).strip()
    }


def redact_request_headers(
    value: Any,
) -> dict[str, str]:
    headers = normalize_headers(
        value
    )

    def is_sensitive(
        name: str,
    ) -> bool:
        lowered = (
            name
            .strip()
            .lower()
        )

        return (
            lowered
            in SENSITIVE_REQUEST_HEADERS
            or any(
                marker
                in lowered
                for marker
                in (
                    "authorization",
                    "cookie",
                    "token",
                    "secret",
                    "api-key",
                    "apikey",
                )
            )
        )

    return {
        name: (
            "[redacted]"
            if is_sensitive(
                name
            )
            else header_value
        )
        for name, header_value
        in headers.items()
    }


def redact_event_for_persistence(
    event: dict[str, Any],
) -> dict[str, Any]:
    """
    Keep graph metadata useful without persisting credentials or request
    bodies captured by the runtime repeater.
    """

    safe = dict(
        event
    )

    request_headers = normalize_headers(
        safe.get(
            "request_headers"
        )
    )

    if request_headers:
        safe[
            "request_headers"
        ] = redact_request_headers(
            request_headers
        )

        safe[
            "request_header_names"
        ] = sorted(
            request_headers
        )

    request_body = str(
        safe.pop(
            "request_body",
            "",
        )
        or ""
    )

    if request_body:
        safe[
            "request_body_length"
        ] = len(
            request_body
        )

        safe[
            "request_body"
        ] = "[not persisted]"

    return safe


def _origin(
    url: str,
) -> str:
    try:
        parts = urlsplit(
            url
        )
    except ValueError:
        return ""

    if not (
        parts.scheme
        and parts.netloc
    ):
        return ""

    return (
        parts.scheme.lower()
        + "://"
        + parts.netloc.lower()
    )


def build_security_observations(
    event: dict[str, Any],
    cookie_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Derive passive security context from data the browser actually observed.

    These are observations, not vulnerability verdicts.
    """

    response_headers = (
        normalize_headers(
            event.get(
                "response_headers"
            )
        )
    )

    request_headers = (
        normalize_headers(
            event.get(
                "request_headers"
            )
        )
    )

    target_url = str(
        event.get(
            "url",
            "",
        )
        or event.get(
            "request_url",
            "",
        )
        or ""
    )

    source_url = str(
        event.get(
            "source_url",
            "",
        )
        or ""
    )

    source_origin = _origin(
        source_url
    )

    target_origin = _origin(
        target_url
    )

    cross_origin = bool(
        source_origin
        and target_origin
        and source_origin
        != target_origin
    )

    try:
        scheme = (
            urlsplit(
                target_url
            )
            .scheme
            .lower()
        )
    except ValueError:
        scheme = ""

    access_control_allow_origin = (
        response_headers.get(
            "access-control-allow-origin",
            "",
        )
    )

    access_control_allow_credentials = (
        response_headers.get(
            "access-control-allow-credentials",
            "",
        )
    )

    observations: dict[
        str,
        Any,
    ] = {
        "https":
            scheme == "https",

        "cross_origin":
            cross_origin,

        "cors_header_observed":
            bool(
                access_control_allow_origin
            ),

        "access_control_allow_origin":
            access_control_allow_origin
            or "",

        "access_control_allow_credentials":
            access_control_allow_credentials
            or "",

        "csp":
            bool(
                response_headers.get(
                    "content-security-policy"
                )
            ),

        "hsts":
            bool(
                response_headers.get(
                    "strict-transport-security"
                )
            ),

        "x_frame_options":
            bool(
                response_headers.get(
                    "x-frame-options"
                )
            ),

        "x_content_type_options":
            bool(
                response_headers.get(
                    "x-content-type-options"
                )
            ),

        "referrer_policy":
            bool(
                response_headers.get(
                    "referrer-policy"
                )
            ),

        "permissions_policy":
            bool(
                response_headers.get(
                    "permissions-policy"
                )
            ),

        "authorization_header_observed":
            any(
                (
                    name
                    == "authorization"
                    or "auth" in name
                )
                for name
                in request_headers
            ),

        "csrf_header_observed":
            any(
                (
                    "csrf" in name
                    or "xsrf" in name
                )
                for name
                in request_headers
            ),

        "server":
            response_headers.get(
                "server",
                "",
            ),

        "x_powered_by":
            response_headers.get(
                "x-powered-by",
                "",
            ),
    }

    for header_name in (
        "content-security-policy",
        "strict-transport-security",
        "x-frame-options",
        "x-content-type-options",
        "referrer-policy",
        "permissions-policy",
    ):
        value = response_headers.get(
            header_name
        )

        if value:
            observations[
                header_name
                .replace("-", "_")
                + "_value"
            ] = value

    if cookie_summary:
        observations[
            "cookies"
        ] = dict(
            cookie_summary
        )

    return observations
