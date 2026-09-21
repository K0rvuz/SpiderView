from __future__ import annotations

from collections.abc import Iterable
from ..models import PageNode

STATUS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Sem status", ""),
    ("Revisar", "review"),
    ("Interessante", "interesting"),
    ("Testado", "tested"),
    ("Confirmado", "confirmed"),
    ("Descartado", "dismissed"),
)

STATUS_LABELS = {value: label for label, value in STATUS_OPTIONS}

STATUS_COLORS = {
    "review": "#E0A94A",
    "interesting": "#5B8DEF",
    "tested": "#48A868",
    "confirmed": "#D45A5A",
    "dismissed": "#7D8792",
}


def normalize_tags(values: Iterable[str] | str | None) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        values = values.split(",")

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        tag = str(value).strip().lstrip("#").strip()
        if not tag:
            continue

        key = tag.casefold()
        if key in seen:
            continue

        seen.add(key)
        result.append(tag)

    return result


def node_tags(node: PageNode) -> list[str]:
    return normalize_tags((node.metadata or {}).get("tags", []))


def node_investigation_status(node: PageNode) -> str:
    value = str((node.metadata or {}).get("investigation_status", "") or "").strip()
    valid = {item_value for _, item_value in STATUS_OPTIONS}
    return value if value in valid else ""


def apply_investigation_metadata(
    node: PageNode,
    *,
    status: str | None = None,
    tags: Iterable[str] | str | None = None,
    append_tags: bool = False,
) -> None:
    metadata = dict(node.metadata or {})

    if status is not None:
        valid = {item_value for _, item_value in STATUS_OPTIONS}
        if status not in valid:
            raise ValueError(f"Status de investigação inválido: {status!r}")
        metadata["investigation_status"] = status

    if tags is not None:
        new_tags = normalize_tags(tags)
        if append_tags:
            new_tags = normalize_tags(node_tags(node) + new_tags)
        metadata["tags"] = new_tags

    node.metadata = metadata
