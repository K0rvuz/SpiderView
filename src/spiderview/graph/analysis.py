from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .graph_model import GraphModel


@dataclass(slots=True)
class NodeMetrics:
    node_id: str

    in_degree: int
    out_degree: int

    unique_in_degree: int
    unique_out_degree: int

    in_degree_centrality: float
    out_degree_centrality: float
    degree_centrality: float

    betweenness_centrality: float

    scc_index: int
    scc_size: int

    weak_component_index: int

    discovery_depth: int


@dataclass(slots=True)
class GraphAnalysis:
    metrics: dict[str, NodeMetrics]

    sccs: tuple[
        tuple[str, ...],
        ...
    ]

    component_of: dict[
        str,
        int,
    ]

    condensation_out: dict[
        int,
        tuple[int, ...],
    ]

    condensation_in: dict[
        int,
        tuple[int, ...],
    ]

    component_depth: dict[
        int,
        int,
    ]

    weak_components: tuple[
        tuple[str, ...],
        ...
    ]

    weak_component_of: dict[
        str,
        int,
    ]

    betweenness: dict[
        str,
        float,
    ]

    @property
    def cyclic_component_count(
        self,
    ) -> int:
        return sum(
            1
            for component
            in self.sccs
            if len(component) > 1
        )

    @property
    def max_depth(
        self,
    ) -> int:
        if not self.component_depth:
            return 0

        return max(
            self.component_depth.values()
        )


# ----------------------------------------------------------------------
# Strongly connected components
# ----------------------------------------------------------------------

def strongly_connected_components(
    graph: GraphModel,
) -> tuple[tuple[str, ...], ...]:
    """
    Tarjan SCC.

    Um SCC com mais de um node representa um ciclo estrutural.
    Self-loops continuam sendo tratados pelo grafo, mas não aumentam
    o tamanho do SCC.
    """

    index_counter = 0

    stack: list[str] = []
    on_stack: set[str] = set()

    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}

    result: list[
        tuple[str, ...]
    ] = []

    def visit(
        node_id: str,
    ) -> None:
        nonlocal index_counter

        index[node_id] = (
            index_counter
        )

        lowlink[node_id] = (
            index_counter
        )

        index_counter += 1

        stack.append(
            node_id
        )

        on_stack.add(
            node_id
        )

        for successor_id in (
            graph.successors(
                node_id
            )
        ):
            if successor_id not in index:
                visit(
                    successor_id
                )

                lowlink[node_id] = min(
                    lowlink[node_id],
                    lowlink[
                        successor_id
                    ],
                )

            elif successor_id in on_stack:
                lowlink[node_id] = min(
                    lowlink[node_id],
                    index[
                        successor_id
                    ],
                )

        if (
            lowlink[node_id]
            != index[node_id]
        ):
            return

        component: list[str] = []

        while stack:
            member_id = stack.pop()

            on_stack.remove(
                member_id
            )

            component.append(
                member_id
            )

            if member_id == node_id:
                break

        component.sort(
            key=graph.node_order
        )

        result.append(
            tuple(component)
        )

    for node_id in graph.node_ids:
        if node_id not in index:
            visit(
                node_id
            )

    # Ordem determinística baseada no primeiro node inserido.
    result.sort(
        key=lambda component: min(
            graph.node_order(
                node_id
            )
            for node_id
            in component
        )
    )

    return tuple(
        result
    )


# ----------------------------------------------------------------------
# Weak components
# ----------------------------------------------------------------------

def weakly_connected_components(
    graph: GraphModel,
) -> tuple[tuple[str, ...], ...]:
    remaining = set(
        graph.node_ids
    )

    result: list[
        tuple[str, ...]
    ] = []

    while remaining:
        root_id = min(
            remaining,
            key=graph.node_order,
        )

        queue = deque(
            [root_id]
        )

        remaining.remove(
            root_id
        )

        component: list[str] = []

        while queue:
            node_id = queue.popleft()

            component.append(
                node_id
            )

            for neighbor_id in (
                graph.neighbors_undirected(
                    node_id
                )
            ):
                if (
                    neighbor_id
                    not in remaining
                ):
                    continue

                remaining.remove(
                    neighbor_id
                )

                queue.append(
                    neighbor_id
                )

        component.sort(
            key=graph.node_order
        )

        result.append(
            tuple(component)
        )

    return tuple(
        result
    )


# ----------------------------------------------------------------------
# Condensation DAG
# ----------------------------------------------------------------------

def _build_condensation(
    graph: GraphModel,
    sccs: tuple[
        tuple[str, ...],
        ...
    ],
) -> tuple[
    dict[str, int],
    dict[int, tuple[int, ...]],
    dict[int, tuple[int, ...]],
]:
    component_of: dict[
        str,
        int,
    ] = {}

    for component_index, component in enumerate(
        sccs
    ):
        for node_id in component:
            component_of[
                node_id
            ] = component_index

    out_sets: dict[
        int,
        set[int],
    ] = {
        index: set()
        for index
        in range(
            len(sccs)
        )
    }

    in_sets: dict[
        int,
        set[int],
    ] = {
        index: set()
        for index
        in range(
            len(sccs)
        )
    }

    for transition in (
        graph.iter_valid_transitions()
    ):
        source_component = (
            component_of[
                transition.source_id
            ]
        )

        target_component = (
            component_of[
                transition.target_id
            ]
        )

        if (
            source_component
            == target_component
        ):
            continue

        out_sets[
            source_component
        ].add(
            target_component
        )

        in_sets[
            target_component
        ].add(
            source_component
        )

    condensation_out = {
        component_id: tuple(
            sorted(
                targets
            )
        )
        for component_id, targets
        in out_sets.items()
    }

    condensation_in = {
        component_id: tuple(
            sorted(
                sources
            )
        )
        for component_id, sources
        in in_sets.items()
    }

    return (
        component_of,
        condensation_out,
        condensation_in,
    )


def _component_depths(
    condensation_out: dict[
        int,
        tuple[int, ...],
    ],
    condensation_in: dict[
        int,
        tuple[int, ...],
    ],
) -> dict[int, int]:
    """
    Longest-path layering sobre o DAG condensado.

    Todo SCC vira um supernode; depois disso o grafo é acíclico.
    """

    indegree = {
        component_id: len(
            condensation_in[
                component_id
            ]
        )
        for component_id
        in condensation_out
    }

    queue = deque(
        sorted(
            component_id
            for component_id, degree
            in indegree.items()
            if degree == 0
        )
    )

    depth = {
        component_id: 0
        for component_id
        in condensation_out
    }

    while queue:
        component_id = (
            queue.popleft()
        )

        for target_id in (
            condensation_out[
                component_id
            ]
        ):
            depth[target_id] = max(
                depth[target_id],
                depth[
                    component_id
                ] + 1,
            )

            indegree[target_id] -= 1

            if indegree[target_id] == 0:
                queue.append(
                    target_id
                )

    return depth


# ----------------------------------------------------------------------
# Betweenness centrality
# ----------------------------------------------------------------------

def betweenness_centrality(
    graph: GraphModel,
) -> dict[str, float]:
    """
    Brandes para grafo direcionado e não ponderado.

    Retorna valores normalizados em aproximadamente [0, 1].
    """

    node_ids = graph.node_ids

    centrality = {
        node_id: 0.0
        for node_id
        in node_ids
    }

    node_count = len(
        node_ids
    )

    if node_count < 3:
        return centrality

    for source_id in node_ids:
        stack: list[str] = []

        predecessors = {
            node_id: []
            for node_id
            in node_ids
        }

        sigma = {
            node_id: 0.0
            for node_id
            in node_ids
        }

        sigma[source_id] = 1.0

        distance = {
            node_id: -1
            for node_id
            in node_ids
        }

        distance[source_id] = 0

        queue = deque(
            [source_id]
        )

        while queue:
            node_id = queue.popleft()

            stack.append(
                node_id
            )

            for target_id in (
                graph.successors(
                    node_id
                )
            ):
                if (
                    distance[
                        target_id
                    ] < 0
                ):
                    distance[
                        target_id
                    ] = (
                        distance[node_id]
                        + 1
                    )

                    queue.append(
                        target_id
                    )

                if (
                    distance[
                        target_id
                    ]
                    == distance[node_id] + 1
                ):
                    sigma[
                        target_id
                    ] += sigma[
                        node_id
                    ]

                    predecessors[
                        target_id
                    ].append(
                        node_id
                    )

        dependency = {
            node_id: 0.0
            for node_id
            in node_ids
        }

        while stack:
            target_id = stack.pop()

            if sigma[target_id] > 0:
                coefficient = (
                    1.0
                    + dependency[
                        target_id
                    ]
                ) / sigma[
                    target_id
                ]

                for predecessor_id in (
                    predecessors[
                        target_id
                    ]
                ):
                    dependency[
                        predecessor_id
                    ] += (
                        sigma[
                            predecessor_id
                        ]
                        * coefficient
                    )

            if target_id != source_id:
                centrality[
                    target_id
                ] += dependency[
                    target_id
                ]

    normalization = (
        (node_count - 1)
        * (node_count - 2)
    )

    if normalization <= 0:
        return centrality

    for node_id in centrality:
        centrality[node_id] /= (
            normalization
        )

    return centrality


# ----------------------------------------------------------------------
# Complete analysis
# ----------------------------------------------------------------------

def analyze_graph(
    graph: GraphModel,
    *,
    compute_betweenness: bool = True,
    betweenness_limit: int = 1200,
) -> GraphAnalysis:
    sccs = (
        strongly_connected_components(
            graph
        )
    )

    (
        component_of,
        condensation_out,
        condensation_in,
    ) = _build_condensation(
        graph,
        sccs,
    )

    component_depth = (
        _component_depths(
            condensation_out,
            condensation_in,
        )
    )

    weak_components = (
        weakly_connected_components(
            graph
        )
    )

    weak_component_of: dict[
        str,
        int,
    ] = {}

    for component_index, component in enumerate(
        weak_components
    ):
        for node_id in component:
            weak_component_of[
                node_id
            ] = component_index

    if (
        compute_betweenness
        and graph.node_count
        <= betweenness_limit
    ):
        betweenness = (
            betweenness_centrality(
                graph
            )
        )
    else:
        betweenness = {
            node_id: 0.0
            for node_id
            in graph.node_ids
        }

    node_count = (
        graph.node_count
    )

    denominator = max(
        1,
        node_count - 1,
    )

    metrics: dict[
        str,
        NodeMetrics,
    ] = {}

    for node_id in graph.node_ids:
        in_degree = (
            graph.in_degree(
                node_id
            )
        )

        out_degree = (
            graph.out_degree(
                node_id
            )
        )

        unique_in = (
            graph.in_degree(
                node_id,
                unique=True,
            )
        )

        unique_out = (
            graph.out_degree(
                node_id,
                unique=True,
            )
        )

        component_index = (
            component_of[
                node_id
            ]
        )

        in_centrality = (
            unique_in
            / denominator
        )

        out_centrality = (
            unique_out
            / denominator
        )

        degree_centrality = (
            (
                unique_in
                + unique_out
            )
            / (
                2
                * denominator
            )
        )

        metrics[node_id] = (
            NodeMetrics(
                node_id=node_id,

                in_degree=in_degree,
                out_degree=out_degree,

                unique_in_degree=unique_in,
                unique_out_degree=unique_out,

                in_degree_centrality=(
                    in_centrality
                ),

                out_degree_centrality=(
                    out_centrality
                ),

                degree_centrality=(
                    degree_centrality
                ),

                betweenness_centrality=(
                    betweenness[
                        node_id
                    ]
                ),

                scc_index=(
                    component_index
                ),

                scc_size=len(
                    sccs[
                        component_index
                    ]
                ),

                weak_component_index=(
                    weak_component_of[
                        node_id
                    ]
                ),

                discovery_depth=(
                    component_depth[
                        component_index
                    ]
                ),
            )
        )

    return GraphAnalysis(
        metrics=metrics,
        sccs=sccs,
        component_of=component_of,
        condensation_out=(
            condensation_out
        ),
        condensation_in=(
            condensation_in
        ),
        component_depth=(
            component_depth
        ),
        weak_components=(
            weak_components
        ),
        weak_component_of=(
            weak_component_of
        ),
        betweenness=(
            betweenness
        ),
    )
