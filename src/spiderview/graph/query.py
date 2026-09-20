from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..models import (
    NodeKind,
    Transition,
    TransitionType,
)
from .graph_model import GraphModel


DEFAULT_NODE_KINDS = frozenset(
    {
        NodeKind.PAGE,
        NodeKind.API,
        NodeKind.DOM_STATE,
        NodeKind.NOTE,
    }
)

DEFAULT_METHODS = frozenset(
    {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }
)

DEFAULT_STATUS_FAMILIES = frozenset(
    {
        "2xx",
        "3xx",
        "4xx",
        "5xx",
    }
)

DEFAULT_TRANSPORTS = frozenset(
    {
        "navigation",
        "click",
        "form",
        "xhr",
        "fetch",
        "redirect",
    }
)

DEFAULT_ORIGINS = frozenset(
    {
        "first-party",
        "third-party",
    }
)


@dataclass(
    slots=True,
    frozen=True,
)
class ViewQuery:
    """
    Consulta visual aplicada sobre o Raw Graph.

    Nenhum PageNode/Transition é alterado.
    """

    focus_enabled: bool = False
    focus_hops: int = 2
    focus_direction: str = "both"

    node_kinds: frozenset[
        NodeKind
    ] = DEFAULT_NODE_KINDS

    show_groups: bool = True

    methods: frozenset[
        str
    ] = DEFAULT_METHODS

    status_families: frozenset[
        str
    ] = DEFAULT_STATUS_FAMILIES

    transports: frozenset[
        str
    ] = DEFAULT_TRANSPORTS

    origins: frozenset[
        str
    ] = DEFAULT_ORIGINS

    search_text: str = ""

    def is_default(
        self,
    ) -> bool:
        return (
            not self.focus_enabled
            and self.node_kinds
            == DEFAULT_NODE_KINDS
            and self.show_groups
            and self.methods
            == DEFAULT_METHODS
            and self.status_families
            == DEFAULT_STATUS_FAMILIES
            and self.transports
            == DEFAULT_TRANSPORTS
            and self.origins
            == DEFAULT_ORIGINS
            and not self.search_text.strip()
        )


@dataclass(
    slots=True,
)
class ViewQueryResult:
    graph: GraphModel

    raw_node_count: int
    visible_node_count: int

    raw_transition_count: int
    visible_transition_count: int

    focus_node_ids: frozenset[
        str
    ]

    first_party_host: str | None


def _normalize_focus_direction(
    direction: str,
) -> str:
    value = str(
        direction
    ).strip().lower()

    aliases = {
        "incoming": "incoming",
        "in": "incoming",

        "outgoing": "outgoing",
        "out": "outgoing",

        "both": "both",
        "all": "both",
    }

    return aliases.get(
        value,
        "both",
    )


def _transport_name(
    transition_type: TransitionType,
) -> str | None:
    if (
        transition_type
        == TransitionType.NAVIGATION
    ):
        return "navigation"

    if (
        transition_type
        == TransitionType.CLICK
    ):
        return "click"

    if (
        transition_type
        == TransitionType.FORM_SUBMIT
    ):
        return "form"

    if (
        transition_type
        == TransitionType.XHR
    ):
        return "xhr"

    if (
        transition_type
        == TransitionType.FETCH
    ):
        return "fetch"

    if (
        transition_type
        == TransitionType.REDIRECT
    ):
        return "redirect"

    # history.pushState / replaceState se existirem no Enum
    # são tratados como navegação.
    history_push = getattr(
        TransitionType,
        "HISTORY_PUSH",
        None,
    )

    history_replace = getattr(
        TransitionType,
        "HISTORY_REPLACE",
        None,
    )

    if (
        history_push is not None
        and transition_type
        == history_push
    ):
        return "navigation"

    if (
        history_replace is not None
        and transition_type
        == history_replace
    ):
        return "navigation"

    return None


def transition_matches_transport(
    transition: Transition,
    query: ViewQuery,
) -> bool:
    transport = _transport_name(
        transition.type
    )

    if transport is None:
        # Enquanto todos os filtros conhecidos estiverem ativos,
        # relações auxiliares continuam visíveis.
        return (
            query.transports
            == DEFAULT_TRANSPORTS
        )

    return (
        transport
        in query.transports
    )


def _host_from_url(
    url: str,
) -> str | None:
    try:
        parts = urlsplit(
            url
        )
    except ValueError:
        return None

    host = (
        parts.hostname
        or ""
    ).lower()

    return (
        host
        or None
    )


def infer_first_party_host(
    graph: GraphModel,
) -> str | None:
    """
    Usa a primeira PAGE/DOM_STATE HTTP(S) descoberta como origem.

    Isso mantém third-party relativo ao alvo inicial da investigação,
    e não transforma automaticamente cada host visitado em first-party.
    """

    for node_id in (
        graph.node_ids
    ):
        node = graph.node(
            node_id
        )

        if node.kind not in {
            NodeKind.PAGE,
            NodeKind.DOM_STATE,
        }:
            continue

        host = _host_from_url(
            node.url
        )

        if host:
            return host

    for node_id in (
        graph.node_ids
    ):
        host = _host_from_url(
            graph.node(
                node_id
            ).url
        )

        if host:
            return host

    return None


def _same_site_host(
    host: str,
    first_party_host: str,
) -> bool:
    host = host.lower().strip(".")
    base = (
        first_party_host
        .lower()
        .strip(".")
    )

    return (
        host == base
        or host.endswith(
            "." + base
        )
        or base.endswith(
            "." + host
        )
    )


def node_origin(
    graph: GraphModel,
    node_id: str,
    *,
    first_party_host: str | None,
) -> str:
    node = graph.node(
        node_id
    )

    host = _host_from_url(
        node.url
    )

    # Notes e recursos sem host são tratados como contexto local.
    if (
        host is None
        or first_party_host
        is None
    ):
        return "first-party"

    if _same_site_host(
        host,
        first_party_host,
    ):
        return "first-party"

    return "third-party"


def _status_family(
    status: int | None,
) -> str | None:
    if status is None:
        return None

    try:
        value = int(
            status
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if 200 <= value <= 299:
        return "2xx"

    if 300 <= value <= 399:
        return "3xx"

    if 400 <= value <= 499:
        return "4xx"

    if 500 <= value <= 599:
        return "5xx"

    return None


def _node_matches_http(
    graph: GraphModel,
    node_id: str,
    query: ViewQuery,
) -> bool:
    node = graph.node(
        node_id
    )

    # Notes não são recursos HTTP.
    if node.kind == NodeKind.NOTE:
        return True

    method = (
        str(
            node.method
            or ""
        )
        .upper()
        .strip()
    )

    if method in DEFAULT_METHODS:
        if (
            method
            not in query.methods
        ):
            return False
    else:
        # Métodos fora do conjunto padrão ficam visíveis somente
        # enquanto o filtro de métodos estiver no estado "todos".
        if (
            query.methods
            != DEFAULT_METHODS
        ):
            return False

    family = _status_family(
        node.status
    )

    if family is None:
        if (
            query.status_families
            != DEFAULT_STATUS_FAMILIES
        ):
            return False

    elif (
        family
        not in query.status_families
    ):
        return False

    return True


def _search_blob(
    graph: GraphModel,
    node_id: str,
) -> str:
    node = graph.node(
        node_id
    )

    pieces = [
        node.title,
        node.url,
        node.method,
        str(
            node.status
            if node.status is not None
            else ""
        ),
    ]

    try:
        parts = urlsplit(
            node.url
        )

        pieces.extend(
            [
                parts.hostname or "",
                parts.path or "",
                parts.query or "",
            ]
        )
    except ValueError:
        pass

    metadata = (
        node.metadata
        or {}
    )

    for key in (
        "request_url",
        "last_request_url",
        "last_source_url",
        "last_content_type",
    ):
        value = metadata.get(
            key
        )

        if value:
            pieces.append(
                str(
                    value
                )
            )

    return "\n".join(
        str(piece)
        for piece
        in pieces
        if piece is not None
    ).lower()


def _search_matching_nodes(
    graph: GraphModel,
    text: str,
) -> set[str]:
    needle = (
        text
        .strip()
        .lower()
    )

    if not needle:
        return set(
            graph.node_ids
        )

    result = {
        node_id
        for node_id
        in graph.node_ids
        if needle
        in _search_blob(
            graph,
            node_id,
        )
    }

    # Também permite encontrar nodes pelo texto humano da ligação.
    for transition in (
        graph.iter_valid_transitions()
    ):
        label = (
            transition.label
            or ""
        ).lower()

        if needle in label:
            result.add(
                transition.source_id
            )

            result.add(
                transition.target_id
            )

    return result


def collect_focus_nodes(
    graph: GraphModel,
    root_ids: set[str] | frozenset[str],
    *,
    hops: int,
    direction: str,
    query: ViewQuery,
) -> frozenset[str]:
    valid_roots = {
        node_id
        for node_id
        in root_ids
        if node_id
        in graph.nodes
    }

    if not valid_roots:
        return frozenset()

    direction = (
        _normalize_focus_direction(
            direction
        )
    )

    max_hops = max(
        0,
        int(
            hops
        ),
    )

    visited = set(
        valid_roots
    )

    queue = deque(
        (
            node_id,
            0,
        )
        for node_id
        in valid_roots
    )

    while queue:
        (
            node_id,
            depth,
        ) = queue.popleft()

        if depth >= max_hops:
            continue

        transitions: list[
            Transition
        ] = []

        if direction in {
            "outgoing",
            "both",
        }:
            transitions.extend(
                graph.outgoing_transitions(
                    node_id
                )
            )

        if direction in {
            "incoming",
            "both",
        }:
            transitions.extend(
                graph.incoming_transitions(
                    node_id
                )
            )

        for transition in transitions:
            if not transition_matches_transport(
                transition,
                query,
            ):
                continue

            if (
                transition.source_id
                == node_id
            ):
                neighbor_id = (
                    transition.target_id
                )
            else:
                neighbor_id = (
                    transition.source_id
                )

            if neighbor_id in visited:
                continue

            visited.add(
                neighbor_id
            )

            queue.append(
                (
                    neighbor_id,
                    depth + 1,
                )
            )

    return frozenset(
        visited
    )


def apply_view_query(
    graph: GraphModel,
    query: ViewQuery,
    *,
    focus_root_ids: set[str] | frozenset[str] | None = None,
) -> ViewQueryResult:
    """
    Aplica Focus + filtros e devolve outro GraphModel.

    O GraphModel original permanece intacto.
    """

    focus_root_ids = (
        frozenset(
            focus_root_ids
            or ()
        )
    )

    if (
        query.focus_enabled
        and focus_root_ids
    ):
        focus_nodes = (
            collect_focus_nodes(
                graph,
                focus_root_ids,
                hops=query.focus_hops,
                direction=(
                    query.focus_direction
                ),
                query=query,
            )
        )
    else:
        focus_nodes = frozenset(
            graph.node_ids
        )

    search_nodes = (
        _search_matching_nodes(
            graph,
            query.search_text,
        )
    )

    first_party_host = (
        infer_first_party_host(
            graph
        )
    )

    visible_node_ids: set[
        str
    ] = set()

    for node_id in (
        graph.node_ids
    ):
        node = graph.node(
            node_id
        )

        if (
            node_id
            not in focus_nodes
        ):
            continue

        if (
            node.kind
            not in query.node_kinds
        ):
            continue

        if (
            node_id
            not in search_nodes
        ):
            continue

        if not _node_matches_http(
            graph,
            node_id,
            query,
        ):
            continue

        origin = node_origin(
            graph,
            node_id,
            first_party_host=(
                first_party_host
            ),
        )

        if origin not in query.origins:
            continue

        visible_node_ids.add(
            node_id
        )

    # O foco escolhido continua visível como contexto, mesmo quando
    # um filtro de tipo/status o excluiria.
    if query.focus_enabled:
        visible_node_ids.update(
            node_id
            for node_id
            in focus_root_ids
            if node_id
            in graph.nodes
        )

    visible_nodes = [
        graph.node(
            node_id
        )
        for node_id
        in graph.node_ids
        if node_id
        in visible_node_ids
    ]

    visible_transitions = []

    for transition in (
        graph.iter_valid_transitions()
    ):
        if (
            transition.source_id
            not in visible_node_ids
            or transition.target_id
            not in visible_node_ids
        ):
            continue

        if not transition_matches_transport(
            transition,
            query,
        ):
            continue

        visible_transitions.append(
            transition
        )

    filtered = GraphModel(
        nodes=visible_nodes,
        transitions=(
            visible_transitions
        ),
    )

    return ViewQueryResult(
        graph=filtered,

        raw_node_count=(
            graph.node_count
        ),

        visible_node_count=(
            filtered.node_count
        ),

        raw_transition_count=(
            graph.transition_count
        ),

        visible_transition_count=(
            filtered.transition_count
        ),

        focus_node_ids=(
            focus_nodes
        ),

        first_party_host=(
            first_party_host
        ),
    )
