from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid5, NAMESPACE_URL

from ..models import (
    NodeKind,
    PageNode,
    Transition,
    TransitionType,
)
from .graph_model import GraphModel
from .grouping import (
    GroupSpec,
    GroupingPolicy,
    build_groups,
)


@dataclass(slots=True)
class ViewNode:
    id: str
    kind: str

    title: str

    raw_node_ids: tuple[
        str,
        ...
    ]

    group_kind: str | None = None

    metadata: dict = field(
        default_factory=dict
    )

    @property
    def is_group(
        self,
    ) -> bool:
        return (
            self.kind == "group"
        )

    @property
    def is_real(
        self,
    ) -> bool:
        return (
            self.kind == "real"
        )


@dataclass(slots=True)
class ViewEdge:
    id: str

    source_id: str
    target_id: str

    raw_transition_ids: tuple[
        str,
        ...
    ]

    type: TransitionType
    label: str

    aggregated: bool = False

    metadata: dict = field(
        default_factory=dict
    )

    @property
    def layout_only(
        self,
    ) -> bool:
        return bool(
            self.metadata.get(
                "layout_only",
                False,
            )
        )

    @property
    def visual_only(
        self,
    ) -> bool:
        return bool(
            self.metadata.get(
                "visual_only",
                False,
            )
        )


@dataclass(slots=True)
class ViewGraph:
    nodes: dict[
        str,
        ViewNode,
    ]

    edges: dict[
        str,
        ViewEdge,
    ]

    groups: dict[
        str,
        GroupSpec,
    ]

    raw_to_view: dict[
        str,
        str,
    ]

    expanded_group_ids: frozenset[
        str
    ]

    def to_layout_graph(
        self,
        raw_graph: GraphModel,
    ) -> GraphModel:
        """
        Converte a projeção visual em um grafo temporário de layout.

        Edges visual_only NÃO entram no layout. Elas existem apenas
        para rastreabilidade da relação real quando um grupo é aberto.
        """

        layout_nodes: list[
            PageNode
        ] = []

        for view_node in (
            self.nodes.values()
        ):
            if view_node.is_real:
                raw_id = (
                    view_node.raw_node_ids[
                        0
                    ]
                )

                raw_node = (
                    raw_graph.node(
                        raw_id
                    )
                )

                layout_nodes.append(
                    PageNode(
                        id=view_node.id,
                        title=raw_node.title,
                        url=raw_node.url,
                        kind=raw_node.kind,
                        method=raw_node.method,
                        status=raw_node.status,
                        preview_path=None,
                        x=0.0,
                        y=0.0,
                        metadata=dict(
                            raw_node.metadata
                        ),
                    )
                )

                continue

            count = int(
                view_node.metadata.get(
                    "count",
                    len(
                        view_node.raw_node_ids
                    ),
                )
                or len(
                    view_node.raw_node_ids
                )
            )

            request_count = int(
                view_node.metadata.get(
                    "request_count",
                    count,
                )
                or count
            )

            layout_nodes.append(
                PageNode(
                    id=view_node.id,
                    title=view_node.title,
                    url="",
                    kind=NodeKind.NOTE,
                    method="GROUP",
                    status=None,
                    preview_path=None,
                    x=0.0,
                    y=0.0,
                    metadata={
                        "request_count":
                            request_count,

                        "view_group_kind":
                            view_node.group_kind,

                        "member_count":
                            count,
                    },
                )
            )

        layout_transitions: list[
            Transition
        ] = []

        for view_edge in (
            self.edges.values()
        ):
            if view_edge.visual_only:
                continue

            layout_transitions.append(
                Transition(
                    id=view_edge.id,
                    source_id=(
                        view_edge.source_id
                    ),
                    target_id=(
                        view_edge.target_id
                    ),
                    type=view_edge.type,
                    label=view_edge.label,
                    metadata=dict(
                        view_edge.metadata
                    ),
                )
            )

        return GraphModel(
            nodes=layout_nodes,
            transitions=layout_transitions,
        )


def _stable_virtual_edge_id(
    source_id: str,
    target_id: str,
    raw_ids: tuple[str, ...],
    *,
    prefix: str = "view-edge",
) -> str:
    token = (
        source_id
        + "->"
        + target_id
        + ":"
        + ",".join(
            sorted(
                raw_ids
            )
        )
        + ":"
        + prefix
    )

    return (
        prefix
        + ":"
        + uuid5(
            NAMESPACE_URL,
            token,
        ).hex
    )


def _aggregate_label(
    *,
    count: int,
    source_group_kind: str | None,
    target_group_kind: str | None,
) -> str:
    if (
        target_group_kind
        == "api"
    ):
        return (
            f"{count} request"
            if count == 1
            else f"{count} requests"
        )

    if (
        source_group_kind
        == "redirect"
        or target_group_kind
        == "redirect"
    ):
        return (
            f"{count} redirect"
            if count == 1
            else f"{count} redirects"
        )

    return (
        f"{count} relation"
        if count == 1
        else f"{count} relations"
    )


def build_view_graph(
    raw_graph: GraphModel,
    *,
    policy: GroupingPolicy | None = None,
    expanded_group_ids: set[str] | frozenset[str] | None = None,
) -> ViewGraph:
    """
    Investigation View.

    COLLAPSED:
        Page -> Group

    EXPANDED:
        Page -> Group
                  |
                  +--> member
                  +--> member

        E também desenhamos relações reais em modo "detail":
            Page -----> exact member

        Essas detail edges são finas e não participam do layout.
        Assim temos rastreabilidade sem destruir a hierarquia visual.
    """

    if policy is None:
        policy = (
            GroupingPolicy()
        )

    expanded = frozenset(
        expanded_group_ids
        or ()
    )

    group_specs = build_groups(
        raw_graph,
        policy,
    )

    groups = {
        group.id: group
        for group
        in group_specs
    }

    member_to_group: dict[
        str,
        str,
    ] = {}

    for group in group_specs:
        for node_id in (
            group.member_node_ids
        ):
            member_to_group[
                node_id
            ] = group.id

    nodes: dict[
        str,
        ViewNode,
    ] = {}

    raw_to_view: dict[
        str,
        str,
    ] = {}

    # --------------------------------------------------------------
    # Real nodes
    # --------------------------------------------------------------

    for node_id in (
        raw_graph.node_ids
    ):
        group_id = (
            member_to_group.get(
                node_id
            )
        )

        if group_id is None:
            raw_node = (
                raw_graph.node(
                    node_id
                )
            )

            nodes[
                node_id
            ] = ViewNode(
                id=node_id,
                kind="real",
                title=raw_node.title,
                raw_node_ids=(
                    node_id,
                ),
            )

            raw_to_view[
                node_id
            ] = node_id

            continue

        # A relação principal sempre aponta para o GroupCard.
        raw_to_view[
            node_id
        ] = group_id

        # Se expandido, o membro real também entra na visualização.
        if group_id in expanded:
            raw_node = (
                raw_graph.node(
                    node_id
                )
            )

            nodes[
                node_id
            ] = ViewNode(
                id=node_id,
                kind="real",
                title=raw_node.title,
                raw_node_ids=(
                    node_id,
                ),
                metadata={
                    "expanded_member_of":
                        group_id,
                },
            )

    # --------------------------------------------------------------
    # Group nodes
    # --------------------------------------------------------------

    for group in (
        group_specs
    ):
        metadata = dict(
            group.metadata
        )

        metadata[
            "expanded"
        ] = (
            group.id
            in expanded
        )

        nodes[
            group.id
        ] = ViewNode(
            id=group.id,
            kind="group",
            title=group.title,
            raw_node_ids=(
                group.member_node_ids
            ),
            group_kind=(
                group.kind
            ),
            metadata=metadata,
        )

    # --------------------------------------------------------------
    # Main projected relations
    # --------------------------------------------------------------

    aggregated_buckets: dict[
        tuple[str, str],
        list[Transition],
    ] = {}

    direct_edges: list[
        ViewEdge
    ] = []

    for transition in (
        raw_graph.iter_valid_transitions()
    ):
        source_group = (
            member_to_group.get(
                transition.source_id
            )
        )

        target_group = (
            member_to_group.get(
                transition.target_id
            )
        )

        source_view = (
            source_group
            if source_group
            is not None
            else transition.source_id
        )

        target_view = (
            target_group
            if target_group
            is not None
            else transition.target_id
        )

        # Relação interna de um mesmo grupo não entra como
        # relação principal. Ela poderá aparecer como detail edge.
        if (
            source_view
            == target_view
        ):
            pass

        elif (
            source_view in groups
            or target_view in groups
        ):
            aggregated_buckets.setdefault(
                (
                    source_view,
                    target_view,
                ),
                [],
            ).append(
                transition
            )

        else:
            direct_edges.append(
                ViewEdge(
                    id=transition.id,
                    source_id=(
                        transition.source_id
                    ),
                    target_id=(
                        transition.target_id
                    ),
                    raw_transition_ids=(
                        transition.id,
                    ),
                    type=transition.type,
                    label=(
                        transition.label
                        or transition.type.value
                    ),
                    aggregated=False,
                    metadata=dict(
                        transition.metadata
                    ),
                )
            )

        # ----------------------------------------------------------
        # Detail edge for expanded groups.
        # ----------------------------------------------------------

        source_expanded = (
            source_group in expanded
            if source_group
            is not None
            else False
        )

        target_expanded = (
            target_group in expanded
            if target_group
            is not None
            else False
        )

        if (
            source_expanded
            or target_expanded
        ):
            detail_id = (
                _stable_virtual_edge_id(
                    transition.source_id,
                    transition.target_id,
                    (
                        transition.id,
                    ),
                    prefix="view-detail",
                )
            )

            direct_edges.append(
                ViewEdge(
                    id=detail_id,
                    source_id=(
                        transition.source_id
                    ),
                    target_id=(
                        transition.target_id
                    ),
                    raw_transition_ids=(
                        transition.id,
                    ),
                    type=transition.type,
                    label=(
                        transition.label
                        or transition.type.value
                    ),
                    aggregated=False,
                    metadata={
                        **dict(
                            transition.metadata
                        ),
                        "visual_only": True,
                        "view_detail": True,
                    },
                )
            )

    edges: dict[
        str,
        ViewEdge,
    ] = {
        edge.id: edge
        for edge in direct_edges
    }

    # --------------------------------------------------------------
    # Aggregate Page -> Group relations
    # --------------------------------------------------------------

    for (
        source_id,
        target_id,
    ), transitions in (
        aggregated_buckets.items()
    ):
        raw_ids = tuple(
            transition.id
            for transition
            in transitions
        )

        source_group = (
            groups.get(
                source_id
            )
        )

        target_group = (
            groups.get(
                target_id
            )
        )

        count = len(
            transitions
        )

        request_count = 0

        for transition in (
            transitions
        ):
            raw_count = (
                transition.metadata.get(
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

        label = _aggregate_label(
            count=count,
            source_group_kind=(
                source_group.kind
                if source_group
                else None
            ),
            target_group_kind=(
                target_group.kind
                if target_group
                else None
            ),
        )

        transition_type = (
            TransitionType.REQUEST
        )

        if (
            (
                source_group
                and source_group.kind
                == "redirect"
            )
            or (
                target_group
                and target_group.kind
                == "redirect"
            )
        ):
            transition_type = (
                TransitionType.REDIRECT
            )

        view_edge_id = (
            _stable_virtual_edge_id(
                source_id,
                target_id,
                raw_ids,
            )
        )

        edge_metadata = {
            "request_count":
                request_count,

            "raw_count":
                count,

            "view_aggregated":
                True,
        }

        if (
            transitions
            and all(
                transition.metadata.get(
                    "manual_note"
                )
                for transition
                in transitions
            )
        ):
            edge_metadata[
                "manual_note"
            ] = True

            note_color = next(
                (
                    transition.metadata.get(
                        "note_color"
                    )
                    for transition
                    in transitions
                    if transition.metadata.get(
                        "note_color"
                    )
                ),
                None,
            )

            if note_color:
                edge_metadata[
                    "note_color"
                ] = note_color

        edges[
            view_edge_id
        ] = ViewEdge(
            id=view_edge_id,
            source_id=source_id,
            target_id=target_id,
            raw_transition_ids=(
                raw_ids
            ),
            type=transition_type,
            label=label,
            aggregated=True,
            metadata=edge_metadata,
        )

    # --------------------------------------------------------------
    # Group -> Member ownership edges.
    # --------------------------------------------------------------

    for group_id in (
        expanded
    ):
        group = groups.get(
            group_id
        )

        if group is None:
            continue

        for member_id in (
            group.member_node_ids
        ):
            if member_id not in nodes:
                continue

            edge_id = (
                _stable_virtual_edge_id(
                    group_id,
                    member_id,
                    (),
                    prefix=(
                        "view-membership"
                    ),
                )
            )

            edges[
                edge_id
            ] = ViewEdge(
                id=edge_id,
                source_id=(
                    group_id
                ),
                target_id=(
                    member_id
                ),
                raw_transition_ids=(),
                type=(
                    TransitionType.MANUAL
                ),
                label="",
                aggregated=True,
                metadata={
                    "view_membership": True,
                },
            )

    return ViewGraph(
        nodes=nodes,
        edges=edges,
        groups=groups,
        raw_to_view=(
            raw_to_view
        ),
        expanded_group_ids=(
            expanded
        ),
    )
