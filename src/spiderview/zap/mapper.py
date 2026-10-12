"""Converte mensagens HTTP do OWASP ZAP para o modelo lógico do SpiderView.

O mapper não depende de Qt e não modifica o grafo recebido. Ele preserva IDs,
posições e transições existentes, acrescentando somente observações novas.
Corpos e cabeçalhos completos não são persistidos, pois podem conter tokens,
cookies ou outros dados sensíveis.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace
from typing import Any, Iterable
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

from ..models import NodeKind, PageNode, Transition, TransitionType


_HEADER_SEPARATOR = re.compile(r"\r?\n")
_REQUEST_LINE = re.compile(r"^([A-Z]+)\s+(\S+)\s+HTTP/\d(?:\.\d)?$", re.I)
_STATUS_LINE = re.compile(r"^HTTP/\d(?:\.\d)?\s+(\d{3})", re.I)


def _parse_headers(raw: str) -> tuple[str, dict[str, str]]:
    lines = _HEADER_SEPARATOR.split(raw or "")
    first_line = lines[0].strip() if lines else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        name = name.strip().lower()
        if name:
            headers[name] = value.strip()
    return first_line, headers


def _clean_url(value: str, base_url: str | None = None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if base_url:
        value = urljoin(base_url, value)
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not hostname:
        return None

    # Fragments are client-side state, not part of an HTTP request target.
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    hostname = hostname.lower()
    netloc = hostname
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"
    normalized = urlunsplit((scheme, netloc, path, parsed.query, ""))
    normalized, _fragment = urldefrag(normalized)
    return normalized


def _request_details(message: dict[str, Any]) -> dict[str, Any] | None:
    request_line, request_headers = _parse_headers(
        str(message.get("requestHeader") or "")
    )
    match = _REQUEST_LINE.match(request_line)
    method = str(message.get("method") or "").upper()
    raw_url = str(message.get("url") or "")

    if match:
        method = method or match.group(1).upper()
        raw_url = raw_url or match.group(2)
    if not method:
        method = "GET"

    url = _clean_url(raw_url)
    if url is None and match:
        target = match.group(2)
        host = request_headers.get("host")
        if host and target.startswith("/"):
            scheme = (
                "https"
                if request_headers.get("x-forwarded-proto") == "https"
                else "http"
            )
            url = _clean_url(f"{scheme}://{host}{target}")

    if url is None:
        return None

    referer = _clean_url(request_headers.get("referer"), url)
    response_line, response_headers = _parse_headers(
        str(message.get("responseHeader") or "")
    )
    status_match = _STATUS_LINE.match(response_line)
    raw_status = message.get("statusCode", message.get("status"))
    try:
        status = int(raw_status) if raw_status not in (None, "") else (
            int(status_match.group(1)) if status_match else None
        )
    except (TypeError, ValueError):
        status = int(status_match.group(1)) if status_match else None

    content_type = (
        response_headers.get("content-type", "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )
    accept = request_headers.get("accept", "").lower()
    destination = request_headers.get("sec-fetch-dest", "").lower()
    is_document = (
        "text/html" in content_type
        or destination == "document"
        or (
            "text/html" in accept
            and destination not in {"script", "style", "image", "font"}
        )
    )
    kind = NodeKind.PAGE if is_document else NodeKind.API

    if request_headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        transition_type = TransitionType.XHR
    elif request_headers.get("sec-fetch-mode", "").lower() == "cors":
        transition_type = TransitionType.FETCH
    elif is_document:
        transition_type = TransitionType.NAVIGATION
    else:
        transition_type = TransitionType.REQUEST

    location = (
        _clean_url(response_headers.get("location"), url)
        if status and 300 <= status < 400
        else None
    )
    return {
        "url": url,
        "method": method,
        "referer": referer,
        "status": status,
        "content_type": content_type or None,
        "kind": kind,
        "transition_type": transition_type,
        "location": location,
        "message_id": str(message.get("id")) if message.get("id") is not None else None,
        "timestamp": message.get("timestamp"),
    }


def _title_for_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if path else ""
    title = segment or parsed.hostname or url
    if "." in title and title.rsplit(".", 1)[-1].lower() in {
        "css", "js", "png", "jpg", "jpeg", "gif", "svg", "ico", "woff", "woff2", "ttf"
    }:
        return title
    return title.replace("-", " ").replace("_", " ").strip() or parsed.hostname or url


class ZapMapper:
    """Mapeia mensagens capturadas pelo ZAP para PageNode e Transition."""

    def map_messages(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        existing_nodes: Iterable[PageNode] = (),
        existing_transitions: Iterable[Transition] = (),
    ) -> tuple[list[PageNode], list[Transition]]:
        """Retorna o grafo combinado sem modificar os objetos recebidos.

        Páginas são identificadas por URL; recursos/API são identificados por
        URL e método. Uma transição só é criada quando há evidência explícita
        de Referer ou de redirecionamento para uma URL também observada.
        """
        nodes = [replace(node, metadata=dict(node.metadata)) for node in existing_nodes]
        transitions = [
            replace(edge, metadata=dict(edge.metadata))
            for edge in existing_transitions
        ]
        observations = [
            details
            for message in messages
            if isinstance(message, dict)
            and (details := _request_details(message)) is not None
        ]

        kinds_by_url: dict[str, set[NodeKind]] = defaultdict(set)
        for item in observations:
            kinds_by_url[item["url"]].add(item["kind"])

        url_to_node: dict[str, PageNode] = {}
        api_to_node: dict[tuple[str, str], PageNode] = {}
        for node in nodes:
            normalized = _clean_url(node.url)
            if normalized is None:
                continue
            if node.kind == NodeKind.API:
                api_to_node.setdefault((normalized, node.method.upper()), node)
            else:
                url_to_node.setdefault(normalized, node)

        for item in observations:
            url = item["url"]
            is_page = NodeKind.PAGE in kinds_by_url[url]
            existing = (
                url_to_node.get(url)
                if is_page
                else api_to_node.get((url, item["method"]))
            )
            if existing is not None:
                existing.status = (
                    item["status"]
                    if item["status"] is not None
                    else existing.status
                )
                metadata = dict(existing.metadata)
                if item["content_type"]:
                    metadata["content_type"] = item["content_type"]
                metadata["source"] = "owasp_zap"
                if item["message_id"]:
                    ids = list(metadata.get("zap_message_ids", []))
                    if item["message_id"] not in ids:
                        ids.append(item["message_id"])
                    metadata["zap_message_ids"] = ids
                existing.metadata = metadata
                continue

            node_kind = NodeKind.PAGE if is_page else NodeKind.API
            metadata: dict[str, Any] = {"source": "owasp_zap"}
            if item["content_type"]:
                metadata["content_type"] = item["content_type"]
            if item["message_id"]:
                metadata["zap_message_ids"] = [item["message_id"]]
            if item["timestamp"] is not None:
                metadata["zap_timestamp"] = item["timestamp"]

            node = PageNode(
                title=_title_for_url(url),
                url=url,
                kind=node_kind,
                method=item["method"],
                status=item["status"],
                metadata=metadata,
            )
            nodes.append(node)
            if node_kind == NodeKind.PAGE:
                url_to_node[url] = node
            else:
                api_to_node[(url, item["method"])] = node

        transition_keys = {
            (edge.source_id, edge.target_id, edge.type, edge.label)
            for edge in transitions
        }
        node_by_url = {
            normalized: node
            for node in nodes
            if (normalized := _clean_url(node.url)) is not None
            and node.kind != NodeKind.API
        }
        api_node_by_key = {
            (_clean_url(node.url), node.method.upper()): node
            for node in nodes
            if node.kind == NodeKind.API and _clean_url(node.url) is not None
        }

        def target_node(item: dict[str, Any]) -> PageNode | None:
            if item["kind"] == NodeKind.PAGE or item["url"] in node_by_url:
                return node_by_url.get(item["url"])
            return api_node_by_key.get((item["url"], item["method"]))

        for item in observations:
            target = target_node(item)
            if target is None:
                continue

            source = node_by_url.get(item["referer"]) if item["referer"] else None
            if source is not None and source.id != target.id:
                transition_type = item["transition_type"]
                label = f'{item["method"]} {urlsplit(item["url"]).path or "/"}'
                key = (source.id, target.id, transition_type, label)
                if key not in transition_keys:
                    transitions.append(
                        Transition(
                            source_id=source.id,
                            target_id=target.id,
                            type=transition_type,
                            label=label,
                            metadata={
                                "source": "owasp_zap",
                                "http_method": item["method"],
                                "status_code": item["status"],
                                "zap_message_id": item["message_id"],
                            },
                        )
                    )
                    transition_keys.add(key)

            # Redirect edges are created only if the destination was observed.
            destination = (
                node_by_url.get(item["location"])
                if item["location"]
                else None
            )
            if destination is not None and destination.id != target.id:
                label = str(item["status"] or "redirect")
                key = (target.id, destination.id, TransitionType.REDIRECT, label)
                if key not in transition_keys:
                    transitions.append(
                        Transition(
                            source_id=target.id,
                            target_id=destination.id,
                            type=TransitionType.REDIRECT,
                            label=label,
                            metadata={
                                "source": "owasp_zap",
                                "status_code": item["status"],
                                "location": item["location"],
                                "zap_message_id": item["message_id"],
                            },
                        )
                    )
                    transition_keys.add(key)

        return nodes, transitions
