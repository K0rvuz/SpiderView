from __future__ import annotations

from dataclasses import dataclass, field

from ..models import NodeKind
from .analysis import (
    GraphAnalysis,
    analyze_graph,
)
from .graph_model import GraphModel
from .weights import (
    EdgeVisualWeight,
    NodeVisualWeight,
    WeightProfile,
    calculate_edge_weights,
    calculate_node_weights,
)


@dataclass(slots=True)
class HierarchicalLayoutConfig:
    """
    Configuração do layout hierárquico ponderado.

    direction:
        "horizontal" -> esquerda para direita
        "vertical"   -> cima para baixo
    """

    direction: str = "horizontal"

    node_width: float = 320.0
    node_height: float = 250.0

    horizontal_gap: float = 250.0
    vertical_gap: float = 90.0

    weak_component_gap: float = 260.0
    scc_member_gap: float = 45.0

    # Quanto um node mais importante ganha de "respiro" vertical.
    weight_gap_factor: float = 7.0
    maximum_weight_gap: float = 140.0

    barycentric_sweeps: int = 8

    compute_betweenness: bool = True
    betweenness_limit: int = 1200

    weight_profile: WeightProfile = field(
        default_factory=WeightProfile
    )


@dataclass(slots=True)
class HierarchicalLayoutResult:
    positions: dict[
        str,
        tuple[float, float],
    ]

    layers: dict[
        int,
        tuple[str, ...],
    ]

    node_weights: dict[
        str,
        NodeVisualWeight,
    ]

    edge_weights: dict[
        str,
        EdgeVisualWeight,
    ]

    analysis: GraphAnalysis

    @property
    def layer_count(
        self,
    ) -> int:
        return len(
            self.layers
        )

    @property
    def maximum_node_weight(
        self,
    ) -> float:
        if not self.node_weights:
            return 0.0

        return max(
            weight.total
            for weight
            in self.node_weights.values()
        )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

_KIND_PRIORITY = {
    NodeKind.PAGE: 0,
    NodeKind.DOM_STATE: 1,
    NodeKind.API: 2,
    NodeKind.NOTE: 3,
}


def _component_original_order(
    graph: GraphModel,
    component: tuple[str, ...],
) -> int:
    return min(
        graph.node_order(
            node_id
        )
        for node_id
        in component
    )


def _component_kind_priority(
    graph: GraphModel,
    component: tuple[str, ...],
) -> int:
    return min(
        _KIND_PRIORITY.get(
            graph.node(
                node_id
            ).kind,
            99,
        )
        for node_id
        in component
    )


def _component_weak_group(
    analysis: GraphAnalysis,
    component: tuple[str, ...],
) -> int:
    return min(
        analysis.weak_component_of[
            node_id
        ]
        for node_id
        in component
    )


def _build_component_edge_weights(
    graph: GraphModel,
    analysis: GraphAnalysis,
    edge_weights: dict[
        str,
        EdgeVisualWeight,
    ],
) -> dict[
    tuple[int, int],
    float,
]:
    result: dict[
        tuple[int, int],
        float,
    ] = {}

    for transition in (
        graph.iter_valid_transitions()
    ):
        source_component = (
            analysis.component_of[
                transition.source_id
            ]
        )

        target_component = (
            analysis.component_of[
                transition.target_id
            ]
        )

        if (
            source_component
            == target_component
        ):
            continue

        pair = (
            source_component,
            target_component,
        )

        weight = edge_weights[
            transition.id
        ].total

        result[pair] = (
            result.get(
                pair,
                0.0,
            )
            + weight
        )

    return result


def _initial_component_layers(
    graph: GraphModel,
    analysis: GraphAnalysis,
) -> dict[
    int,
    list[int],
]:
    layers: dict[
        int,
        list[int],
    ] = {}

    for component_id, component in enumerate(
        analysis.sccs
    ):
        depth = (
            analysis.component_depth[
                component_id
            ]
        )

        layers.setdefault(
            depth,
            [],
        ).append(
            component_id
        )

    for depth, component_ids in (
        layers.items()
    ):
        component_ids.sort(
            key=lambda component_id: (
                _component_weak_group(
                    analysis,
                    analysis.sccs[
                        component_id
                    ],
                ),
                _component_kind_priority(
                    graph,
                    analysis.sccs[
                        component_id
                    ],
                ),
                _component_original_order(
                    graph,
                    analysis.sccs[
                        component_id
                    ],
                ),
            )
        )

    return layers


def _positions_in_layer(
    component_layers: dict[
        int,
        list[int],
    ],
) -> dict[
    int,
    tuple[int, int],
]:
    """
    component_id -> (depth, order)
    """

    result: dict[
        int,
        tuple[int, int],
    ] = {}

    for depth, component_ids in (
        component_layers.items()
    ):
        for order, component_id in enumerate(
            component_ids
        ):
            result[
                component_id
            ] = (
                depth,
                order,
            )

    return result


def _weighted_barycenter(
    neighbors: tuple[int, ...],
    positions: dict[
        int,
        tuple[int, int],
    ],
    edge_weights: dict[
        tuple[int, int],
        float,
    ],
    *,
    component_id: int,
    predecessor_mode: bool,
) -> float | None:
    numerator = 0.0
    denominator = 0.0

    for neighbor_id in neighbors:
        neighbor_position = positions.get(
            neighbor_id
        )

        if neighbor_position is None:
            continue

        if predecessor_mode:
            pair = (
                neighbor_id,
                component_id,
            )
        else:
            pair = (
                component_id,
                neighbor_id,
            )

        weight = edge_weights.get(
            pair,
            1.0,
        )

        numerator += (
            neighbor_position[1]
            * weight
        )

        denominator += (
            weight
        )

    if denominator <= 0:
        return None

    return (
        numerator
        / denominator
    )


def _barycentric_ordering(
    graph: GraphModel,
    analysis: GraphAnalysis,
    component_layers: dict[
        int,
        list[int],
    ],
    component_edge_weights: dict[
        tuple[int, int],
        float,
    ],
    *,
    sweeps: int,
) -> None:
    if len(component_layers) <= 1:
        return

    depths = sorted(
        component_layers
    )

    for _ in range(
        max(
            1,
            sweeps,
        )
    ):
        # --------------------------------------------------------------
        # Downward sweep: predecessors influence the next layer.
        # --------------------------------------------------------------

        positions = (
            _positions_in_layer(
                component_layers
            )
        )

        for depth in depths[1:]:
            current_order = {
                component_id: index
                for index, component_id
                in enumerate(
                    component_layers[
                        depth
                    ]
                )
            }

            def downward_key(
                component_id: int,
            ):
                component = (
                    analysis.sccs[
                        component_id
                    ]
                )

                weak_group = (
                    _component_weak_group(
                        analysis,
                        component,
                    )
                )

                barycenter = (
                    _weighted_barycenter(
                        analysis.condensation_in[
                            component_id
                        ],
                        positions,
                        component_edge_weights,
                        component_id=(
                            component_id
                        ),
                        predecessor_mode=True,
                    )
                )

                if barycenter is None:
                    barycenter = float(
                        current_order[
                            component_id
                        ]
                    )

                return (
                    weak_group,
                    barycenter,
                    _component_kind_priority(
                        graph,
                        component,
                    ),
                    _component_original_order(
                        graph,
                        component,
                    ),
                )

            component_layers[
                depth
            ].sort(
                key=downward_key
            )

        # --------------------------------------------------------------
        # Upward sweep: successors influence the previous layer.
        # --------------------------------------------------------------

        positions = (
            _positions_in_layer(
                component_layers
            )
        )

        for depth in reversed(
            depths[:-1]
        ):
            current_order = {
                component_id: index
                for index, component_id
                in enumerate(
                    component_layers[
                        depth
                    ]
                )
            }

            def upward_key(
                component_id: int,
            ):
                component = (
                    analysis.sccs[
                        component_id
                    ]
                )

                weak_group = (
                    _component_weak_group(
                        analysis,
                        component,
                    )
                )

                barycenter = (
                    _weighted_barycenter(
                        analysis.condensation_out[
                            component_id
                        ],
                        positions,
                        component_edge_weights,
                        component_id=(
                            component_id
                        ),
                        predecessor_mode=False,
                    )
                )

                if barycenter is None:
                    barycenter = float(
                        current_order[
                            component_id
                        ]
                    )

                return (
                    weak_group,
                    barycenter,
                    _component_kind_priority(
                        graph,
                        component,
                    ),
                    _component_original_order(
                        graph,
                        component,
                    ),
                )

            component_layers[
                depth
            ].sort(
                key=upward_key
            )


def _ordered_members(
    graph: GraphModel,
    component: tuple[str, ...],
    node_weights: dict[
        str,
        NodeVisualWeight,
    ],
) -> list[str]:
    """
    Dentro de um SCC:
    - páginas antes de APIs;
    - nodes mais pesados primeiro;
    - ordem de descoberta como desempate.
    """

    return sorted(
        component,
        key=lambda node_id: (
            _KIND_PRIORITY.get(
                graph.node(
                    node_id
                ).kind,
                99,
            ),
            -node_weights[
                node_id
            ].total,
            graph.node_order(
                node_id
            ),
        ),
    )


def _node_extra_gap(
    weight: float,
    *,
    minimum_weight: float,
    config: HierarchicalLayoutConfig,
) -> float:
    extra = (
        max(
            0.0,
            weight - minimum_weight,
        )
        * config.weight_gap_factor
    )

    return min(
        config.maximum_weight_gap,
        extra,
    )


def _place_layer(
    graph: GraphModel,
    analysis: GraphAnalysis,
    component_ids: list[int],
    node_weights: dict[
        str,
        NodeVisualWeight,
    ],
    *,
    x: float,
    config: HierarchicalLayoutConfig,
) -> tuple[
    dict[str, tuple[float, float]],
    tuple[str, ...],
]:
    """
    Cria a coluna vertical de um nível.

    O peso do node controla o espaço ao redor dele, não o tamanho
    do card. Isso preserva legibilidade e evita cards gigantes.
    """

    ordered_nodes: list[
        tuple[str, int]
    ] = []

    for component_id in component_ids:
        component = (
            analysis.sccs[
                component_id
            ]
        )

        for node_id in _ordered_members(
            graph,
            component,
            node_weights,
        ):
            ordered_nodes.append(
                (
                    node_id,
                    component_id,
                )
            )

    if not ordered_nodes:
        return (
            {},
            (),
        )

    minimum_weight = min(
        node_weights[
            node_id
        ].total
        for node_id, _
        in ordered_nodes
    )

    centers: list[
        tuple[str, float]
    ] = []

    cursor_y = 0.0
    previous_extra = 0.0
    previous_component: int | None = None

    for index, (
        node_id,
        component_id,
    ) in enumerate(
        ordered_nodes
    ):
        weight = (
            node_weights[
                node_id
            ].total
        )

        extra = _node_extra_gap(
            weight,
            minimum_weight=(
                minimum_weight
            ),
            config=config,
        )

        if index == 0:
            center_y = (
                config.node_height
                / 2.0
            )

        else:
            gap = (
                config.vertical_gap
                + (
                    previous_extra
                    + extra
                ) / 2.0
            )

            if (
                previous_component
                == component_id
                and len(
                    analysis.sccs[
                        component_id
                    ]
                ) > 1
            ):
                gap += (
                    config.scc_member_gap
                )

            center_y = (
                cursor_y
                + config.node_height
                + gap
                + config.node_height
                / 2.0
            )

        centers.append(
            (
                node_id,
                center_y,
            )
        )

        cursor_y = (
            center_y
            - config.node_height
            / 2.0
        )

        previous_extra = extra
        previous_component = (
            component_id
        )

    # Centraliza cada layer verticalmente em torno de y=0.
    first_center = centers[0][1]
    last_center = centers[-1][1]

    midpoint = (
        first_center
        + last_center
    ) / 2.0

    positions = {
        node_id: (
            x,
            center_y
            - midpoint
            - config.node_height
            / 2.0,
        )
        for node_id, center_y
        in centers
    }

    return (
        positions,
        tuple(
            node_id
            for node_id, _
            in centers
        ),
    )


def _normalize_direction(
    direction: str,
) -> str:
    value = str(
        direction
    ).strip().lower()

    aliases = {
        "horizontal": "horizontal",
        "left_to_right": "horizontal",
        "left-to-right": "horizontal",
        "ltr": "horizontal",

        "vertical": "vertical",
        "top_to_bottom": "vertical",
        "top-to-bottom": "vertical",
        "ttb": "vertical",
    }

    if value not in aliases:
        raise ValueError(
            "direction precisa ser "
            "'horizontal' ou 'vertical'."
        )

    return aliases[
        value
    ]


def _orient_positions(
    positions: dict[
        str,
        tuple[float, float],
    ],
    *,
    direction: str,
    config: HierarchicalLayoutConfig,
) -> dict[
    str,
    tuple[float, float],
]:
    """
    O algoritmo interno calcula left-to-right.

    Para top-to-bottom, transpomos os eixos e compensamos as
    dimensões diferentes dos cards para manter:
    - espaçamento de layers baseado na altura;
    - espaçamento entre irmãos baseado na largura.
    """

    if direction == "horizontal":
        return positions

    horizontal_depth_step = max(
        1.0,
        config.node_width
        + config.horizontal_gap,
    )

    vertical_depth_step = max(
        1.0,
        config.node_height
        + config.vertical_gap,
    )

    horizontal_cross_step = max(
        1.0,
        config.node_height
        + config.vertical_gap,
    )

    vertical_cross_step = max(
        1.0,
        config.node_width
        + config.horizontal_gap,
    )

    depth_scale = (
        vertical_depth_step
        / horizontal_depth_step
    )

    cross_scale = (
        vertical_cross_step
        / horizontal_cross_step
    )

    return {
        node_id: (
            y * cross_scale,
            x * depth_scale,
        )
        for node_id, (
            x,
            y,
        )
        in positions.items()
    }


# ----------------------------------------------------------------------
# Public layout
# ----------------------------------------------------------------------

def hierarchical_layout(
    graph: GraphModel,
    *,
    config: HierarchicalLayoutConfig | None = None,
) -> HierarchicalLayoutResult:
    """
    Layout hierárquico ponderado inspirado no pipeline Sugiyama:

        1. SCC / condensação dos ciclos;
        2. layering por longest path;
        3. ordenação baricêntrica para reduzir cruzamentos;
        4. espaçamento guiado por peso visual.

    Nenhum dado do grafo é alterado.
    """

    if config is None:
        config = (
            HierarchicalLayoutConfig()
        )

    direction = _normalize_direction(
        config.direction
    )

    analysis = analyze_graph(
        graph,
        compute_betweenness=(
            config.compute_betweenness
        ),
        betweenness_limit=(
            config.betweenness_limit
        ),
    )

    node_weights = (
        calculate_node_weights(
            graph,
            analysis,
            profile=(
                config.weight_profile
            ),
        )
    )

    edge_weights = (
        calculate_edge_weights(
            graph,
            profile=(
                config.weight_profile
            ),
        )
    )

    if graph.node_count == 0:
        return HierarchicalLayoutResult(
            positions={},
            layers={},
            node_weights=(
                node_weights
            ),
            edge_weights=(
                edge_weights
            ),
            analysis=analysis,
        )

    component_layers = (
        _initial_component_layers(
            graph,
            analysis,
        )
    )

    component_edge_weights = (
        _build_component_edge_weights(
            graph,
            analysis,
            edge_weights,
        )
    )

    _barycentric_ordering(
        graph,
        analysis,
        component_layers,
        component_edge_weights,
        sweeps=(
            config.barycentric_sweeps
        ),
    )

    x_step = (
        config.node_width
        + config.horizontal_gap
    )

    positions: dict[
        str,
        tuple[float, float],
    ] = {}

    layers: dict[
        int,
        tuple[str, ...],
    ] = {}

    # Layout por layer.
    for depth in sorted(
        component_layers
    ):
        x = (
            depth
            * x_step
        )

        (
            layer_positions,
            layer_nodes,
        ) = _place_layer(
            graph,
            analysis,
            component_layers[
                depth
            ],
            node_weights,
            x=x,
            config=config,
        )

        positions.update(
            layer_positions
        )

        layers[
            depth
        ] = layer_nodes

    # --------------------------------------------------------------
    # Se existem vários componentes fracos, deslocamos cada um para
    # manter grupos desconectados visualmente separados.
    # --------------------------------------------------------------

    if (
        len(
            analysis.weak_components
        ) > 1
    ):
        weak_bounds: dict[
            int,
            tuple[float, float],
        ] = {}

        for weak_index, component in enumerate(
            analysis.weak_components
        ):
            ys = [
                positions[
                    node_id
                ][1]
                for node_id
                in component
                if node_id
                in positions
            ]

            if not ys:
                continue

            weak_bounds[
                weak_index
            ] = (
                min(ys),
                max(ys)
                + config.node_height,
            )

        offset_y = 0.0

        for weak_index in sorted(
            weak_bounds
        ):
            top, bottom = (
                weak_bounds[
                    weak_index
                ]
            )

            group_height = (
                bottom - top
            )

            delta = (
                offset_y - top
            )

            for node_id in (
                analysis.weak_components[
                    weak_index
                ]
            ):
                if node_id not in positions:
                    continue

                x, y = positions[
                    node_id
                ]

                positions[
                    node_id
                ] = (
                    x,
                    y + delta,
                )

            offset_y += (
                group_height
                + config.weak_component_gap
            )

    positions = _orient_positions(
        positions,
        direction=direction,
        config=config,
    )

    return HierarchicalLayoutResult(
        positions=positions,
        layers=layers,
        node_weights=(
            node_weights
        ),
        edge_weights=(
            edge_weights
        ),
        analysis=analysis,
    )
