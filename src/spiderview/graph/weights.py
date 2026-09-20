from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..models import NodeKind, TransitionType
from .analysis import GraphAnalysis
from .graph_model import GraphModel


def _default_node_base() -> dict[
    NodeKind,
    float,
]:
    return {
        NodeKind.PAGE: 10.0,
        NodeKind.DOM_STATE: 8.0,
        NodeKind.API: 5.0,
        NodeKind.NOTE: 4.0,
    }


def _default_edge_base() -> dict[
    TransitionType,
    float,
]:
    result = {
        TransitionType.NAVIGATION: 4.0,
        TransitionType.CLICK: 5.0,
        TransitionType.FORM_SUBMIT: 6.0,
        TransitionType.REDIRECT: 3.5,
        TransitionType.FETCH: 2.5,
        TransitionType.XHR: 2.5,
        TransitionType.REQUEST: 2.0,
        TransitionType.DOM_MUTATION: 2.0,
        TransitionType.MANUAL: 1.5,
    }

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

    if history_push is not None:
        result[
            history_push
        ] = 4.0

    if history_replace is not None:
        result[
            history_replace
        ] = 3.5

    return result


@dataclass(slots=True)
class WeightProfile:
    """
    Heurística de importância VISUAL.

    Não representa risco ou criticidade de segurança.

    O peso é derivado de:
    - tipo do node;
    - conectividade;
    - frequência observada;
    - centralidade estrutural.
    """

    node_base: dict[
        NodeKind,
        float,
    ] = field(
        default_factory=(
            _default_node_base
        )
    )

    edge_base: dict[
        TransitionType,
        float,
    ] = field(
        default_factory=(
            _default_edge_base
        )
    )

    raw_degree_factor: float = 0.75
    unique_degree_factor: float = 1.80

    request_count_factor: float = 1.35

    degree_centrality_factor: float = 8.0
    betweenness_factor: float = 14.0

    scc_bonus_per_extra_node: float = 0.75

    minimum_node_weight: float = 1.0
    minimum_edge_weight: float = 0.5


@dataclass(slots=True)
class NodeVisualWeight:
    node_id: str

    base: float
    connectivity: float
    traffic: float
    centrality: float
    cycle_bonus: float

    total: float


@dataclass(slots=True)
class EdgeVisualWeight:
    transition_id: str

    base: float
    frequency: float

    total: float


def _safe_request_count(
    metadata: dict,
) -> int:
    raw = metadata.get(
        "request_count",
        1,
    )

    try:
        count = int(
            raw
        )
    except (
        TypeError,
        ValueError,
    ):
        return 1

    return max(
        1,
        count,
    )


def calculate_node_weights(
    graph: GraphModel,
    analysis: GraphAnalysis,
    *,
    profile: WeightProfile | None = None,
) -> dict[str, NodeVisualWeight]:
    if profile is None:
        profile = WeightProfile()

    result: dict[
        str,
        NodeVisualWeight,
    ] = {}

    for node_id in graph.node_ids:
        node = graph.node(
            node_id
        )

        metrics = analysis.metrics[
            node_id
        ]

        base = profile.node_base.get(
            node.kind,
            profile.minimum_node_weight,
        )

        raw_degree = (
            metrics.in_degree
            + metrics.out_degree
        )

        unique_degree = (
            metrics.unique_in_degree
            + metrics.unique_out_degree
        )

        connectivity = (
            math.log2(
                1.0
                + raw_degree
            )
            * profile.raw_degree_factor

            + math.log2(
                1.0
                + unique_degree
            )
            * profile.unique_degree_factor
        )

        request_count = (
            _safe_request_count(
                node.metadata
            )
        )

        traffic = (
            math.log2(
                1.0
                + request_count
            )
            * profile.request_count_factor
        )

        centrality = (
            metrics.degree_centrality
            * profile.degree_centrality_factor

            + metrics.betweenness_centrality
            * profile.betweenness_factor
        )

        cycle_bonus = (
            max(
                0,
                metrics.scc_size - 1,
            )
            * profile.scc_bonus_per_extra_node
        )

        total = max(
            profile.minimum_node_weight,
            (
                base
                + connectivity
                + traffic
                + centrality
                + cycle_bonus
            ),
        )

        result[node_id] = (
            NodeVisualWeight(
                node_id=node_id,
                base=base,
                connectivity=(
                    connectivity
                ),
                traffic=traffic,
                centrality=(
                    centrality
                ),
                cycle_bonus=(
                    cycle_bonus
                ),
                total=total,
            )
        )

    return result


def calculate_edge_weights(
    graph: GraphModel,
    *,
    profile: WeightProfile | None = None,
) -> dict[
    str,
    EdgeVisualWeight,
]:
    if profile is None:
        profile = WeightProfile()

    result: dict[
        str,
        EdgeVisualWeight,
    ] = {}

    for transition in (
        graph.iter_valid_transitions()
    ):
        base = profile.edge_base.get(
            transition.type,
            profile.minimum_edge_weight,
        )

        request_count = (
            _safe_request_count(
                transition.metadata
            )
        )

        # A frequência aumenta a influência da edge, mas em
        # escala logarítmica para não dominar todo o layout.
        frequency = (
            math.log2(
                1.0
                + request_count
            )
            * 0.45
        )

        total = max(
            profile.minimum_edge_weight,
            base
            * (
                1.0
                + frequency
            ),
        )

        result[
            transition.id
        ] = EdgeVisualWeight(
            transition_id=(
                transition.id
            ),
            base=base,
            frequency=(
                frequency
            ),
            total=total,
        )

    return result
