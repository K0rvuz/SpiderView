from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..models import NodeKind, TransitionType
from .graph_model import GraphModel


@dataclass(slots=True, frozen=True)
class GroupSpec:
    """
    Grupo virtual usado somente pela visualização.

    member_node_ids sempre aponta para nodes reais do GraphModel.
    """

    id: str
    kind: str
    title: str
    member_node_ids: tuple[str, ...]
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class GroupingPolicy:
    """
    Política padrão do modo Investigation.

    API:
        Agrupa por host + primeiro segmento do path.

        Exemplos:
            example.com/api/users
            example.com/api/session
                -> api:example.com:/api

            example.com/cdn-cgi/rum
                -> api:example.com:/cdn-cgi

    Redirect:
        Agrupa apenas nodes intermediários "puros", isto é,
        nodes cujo tráfego estrutural relevante é composto por
        redirects de entrada e saída.
    """

    group_apis: bool = True
    api_min_size: int = 2
    api_group_by_first_path_segment: bool = True

    collapse_redirect_chains: bool = True
    redirect_min_size: int = 2


def _slug(
    value: str,
) -> str:
    safe = []

    for char in value.lower():
        if char.isalnum():
            safe.append(char)
        else:
            safe.append("-")

    result = "".join(safe)

    while "--" in result:
        result = result.replace(
            "--",
            "-",
        )

    return result.strip("-") or "group"


def _api_bucket(
    url: str,
    *,
    by_first_segment: bool,
) -> tuple[str, str]:
    try:
        parts = urlsplit(url)
    except ValueError:
        return (
            "unknown",
            "/",
        )

    host = (
        parts.netloc.lower()
        or "unknown"
    )

    if not by_first_segment:
        return (
            host,
            "/",
        )

    segments = [
        segment
        for segment
        in parts.path.split("/")
        if segment
    ]

    if not segments:
        prefix = "/"
    else:
        prefix = (
            "/"
            + segments[0]
        )

    return (
        host,
        prefix,
    )


def find_api_groups(
    graph: GraphModel,
    policy: GroupingPolicy,
) -> list[GroupSpec]:
    if not policy.group_apis:
        return []

    buckets: dict[
        tuple[str, str],
        list[str],
    ] = {}

    for node_id in graph.node_ids:
        node = graph.node(
            node_id
        )

        if node.kind != NodeKind.API:
            continue

        bucket = _api_bucket(
            node.url,
            by_first_segment=(
                policy.api_group_by_first_path_segment
            ),
        )

        buckets.setdefault(
            bucket,
            [],
        ).append(
            node_id
        )

    result: list[
        GroupSpec
    ] = []

    for (
        host,
        prefix,
    ), member_ids in buckets.items():

        if (
            len(member_ids)
            < policy.api_min_size
        ):
            continue

        methods: dict[str, int] = {}
        statuses: dict[str, int] = {}
        transports: dict[str, int] = {}

        request_count = 0

        for node_id in member_ids:
            node = graph.node(
                node_id
            )

            method = (
                node.method.upper()
                if node.method
                else "GET"
            )

            methods[method] = (
                methods.get(
                    method,
                    0,
                )
                + 1
            )

            if node.status is not None:
                status_family = (
                    f"{int(node.status) // 100}xx"
                )

                statuses[
                    status_family
                ] = (
                    statuses.get(
                        status_family,
                        0,
                    )
                    + 1
                )

            raw_count = (
                node.metadata.get(
                    "request_count",
                    1,
                )
            )

            try:
                request_count += max(
                    1,
                    int(raw_count),
                )
            except (
                TypeError,
                ValueError,
            ):
                request_count += 1

            for transport in (
                node.metadata.get(
                    "transports",
                    [],
                )
                or []
            ):
                transport = str(
                    transport
                )

                transports[
                    transport
                ] = (
                    transports.get(
                        transport,
                        0,
                    )
                    + 1
                )

        if prefix == "/":
            title = (
                f"{host} APIs"
            )
        else:
            title = (
                f"{host}{prefix} APIs"
            )

        group_id = (
            "view-group:api:"
            + _slug(host)
            + ":"
            + _slug(prefix)
        )

        result.append(
            GroupSpec(
                id=group_id,
                kind="api",
                title=title,
                member_node_ids=tuple(
                    member_ids
                ),
                metadata={
                    "host": host,
                    "path_prefix": prefix,
                    "count": len(
                        member_ids
                    ),
                    "request_count":
                        request_count,
                    "methods": methods,
                    "statuses": statuses,
                    "transports":
                        transports,
                },
            )
        )

    result.sort(
        key=lambda group: (
            group.metadata.get(
                "host",
                "",
            ),
            group.metadata.get(
                "path_prefix",
                "",
            ),
        )
    )

    return result


def _is_pure_redirect_intermediate(
    graph: GraphModel,
    node_id: str,
) -> bool:
    incoming = (
        graph.incoming_transitions(
            node_id
        )
    )

    outgoing = (
        graph.outgoing_transitions(
            node_id
        )
    )

    if not incoming or not outgoing:
        return False

    # API não deve virar node intermediário de redirect.
    if (
        graph.node(
            node_id
        ).kind
        == NodeKind.API
    ):
        return False

    all_transitions = (
        incoming
        + outgoing
    )

    return all(
        transition.type
        == TransitionType.REDIRECT
        for transition
        in all_transitions
    )


def find_redirect_groups(
    graph: GraphModel,
    policy: GroupingPolicy,
) -> list[GroupSpec]:
    if not (
        policy.collapse_redirect_chains
    ):
        return []

    candidates = {
        node_id
        for node_id
        in graph.node_ids
        if _is_pure_redirect_intermediate(
            graph,
            node_id,
        )
    }

    if not candidates:
        return []

    # Componentes não direcionados entre intermediários.
    adjacency: dict[
        str,
        set[str],
    ] = {
        node_id: set()
        for node_id
        in candidates
    }

    for transition in (
        graph.iter_valid_transitions()
    ):
        if (
            transition.type
            != TransitionType.REDIRECT
        ):
            continue

        source_id = (
            transition.source_id
        )

        target_id = (
            transition.target_id
        )

        if (
            source_id in candidates
            and target_id in candidates
        ):
            adjacency[
                source_id
            ].add(
                target_id
            )

            adjacency[
                target_id
            ].add(
                source_id
            )

    remaining = set(
        candidates
    )

    groups: list[
        GroupSpec
    ] = []

    sequence = 1

    while remaining:
        start = min(
            remaining,
            key=graph.node_order,
        )

        stack = [
            start
        ]

        remaining.remove(
            start
        )

        component: list[str] = []

        while stack:
            node_id = stack.pop()

            component.append(
                node_id
            )

            for neighbor_id in (
                adjacency[
                    node_id
                ]
            ):
                if (
                    neighbor_id
                    not in remaining
                ):
                    continue

                remaining.remove(
                    neighbor_id
                )

                stack.append(
                    neighbor_id
                )

        component.sort(
            key=graph.node_order
        )

        if (
            len(component)
            < policy.redirect_min_size
        ):
            continue

        group_id = (
            f"view-group:redirect:{sequence}"
        )

        groups.append(
            GroupSpec(
                id=group_id,
                kind="redirect",
                title=(
                    f"Redirect chain · "
                    f"{len(component)}"
                ),
                member_node_ids=tuple(
                    component
                ),
                metadata={
                    "count": len(
                        component
                    ),
                },
            )
        )

        sequence += 1

    return groups


def build_groups(
    graph: GraphModel,
    policy: GroupingPolicy | None = None,
) -> list[GroupSpec]:
    if policy is None:
        policy = (
            GroupingPolicy()
        )

    result: list[
        GroupSpec
    ] = []

    occupied: set[str] = set()

    # Redirect primeiro para não permitir que uma futura
    # heurística sobreponha o mesmo node em dois grupos.
    for group in find_redirect_groups(
        graph,
        policy,
    ):
        if any(
            node_id in occupied
            for node_id
            in group.member_node_ids
        ):
            continue

        result.append(
            group
        )

        occupied.update(
            group.member_node_ids
        )

    for group in find_api_groups(
        graph,
        policy,
    ):
        if any(
            node_id in occupied
            for node_id
            in group.member_node_ids
        ):
            continue

        result.append(
            group
        )

        occupied.update(
            group.member_node_ids
        )

    return result
