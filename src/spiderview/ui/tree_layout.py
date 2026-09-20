from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import NodeKind, TransitionType
from .page_card import PageCard

if TYPE_CHECKING:
    from .canvas import SpiderCanvas


@dataclass(slots=True)
class TreeLayoutResult:
    nodes: int
    components: int
    max_depth: int


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


def arrange_tree(
    canvas: "SpiderCanvas",
    *,
    direction: str = "horizontal",
    horizontal_gap: float = 220.0,
    vertical_gap: float = 90.0,
    component_gap: float = 180.0,
) -> TreeLayoutResult:
    """
    Organiza o grafo como spanning forest.

    horizontal:
        profundidade cresce da esquerda para a direita.

    vertical:
        profundidade cresce de cima para baixo.

    O grafo real pode conter ciclos e múltiplos pais. O algoritmo
    usa a primeira relação que alcança um node apenas para decidir
    seu pai visual. Todas as edges reais continuam existindo.
    """

    direction = _normalize_direction(
        direction
    )

    if not canvas.nodes:
        return TreeLayoutResult(
            nodes=0,
            components=0,
            max_depth=0,
        )

    node_ids = list(
        canvas.nodes.keys()
    )

    order_index = {
        node_id: index
        for index, node_id
        in enumerate(
            node_ids
        )
    }

    outgoing: dict[
        str,
        list[
            tuple[
                str,
                TransitionType,
            ]
        ],
    ] = {
        node_id: []
        for node_id in node_ids
    }

    indegree: dict[
        str,
        int,
    ] = {
        node_id: 0
        for node_id in node_ids
    }

    seen_pairs: set[
        tuple[str, str]
    ] = set()

    for edge in (
        canvas.edges.values()
    ):
        transition = (
            edge.transition
        )

        source_id = (
            transition.source_id
        )

        target_id = (
            transition.target_id
        )

        if (
            source_id
            not in canvas.nodes
            or target_id
            not in canvas.nodes
            or source_id
            == target_id
        ):
            continue

        pair = (
            source_id,
            target_id,
        )

        if pair in seen_pairs:
            continue

        seen_pairs.add(
            pair
        )

        outgoing[
            source_id
        ].append(
            (
                target_id,
                transition.type,
            )
        )

        indegree[
            target_id
        ] += 1

    kind_priority = {
        NodeKind.PAGE: 0,
        NodeKind.DOM_STATE: 1,
        NodeKind.API: 2,
        NodeKind.NOTE: 3,
    }

    transition_priority = {
        TransitionType.NAVIGATION: 0,
        TransitionType.CLICK: 1,
        TransitionType.FORM_SUBMIT: 2,
        TransitionType.REDIRECT: 3,

        getattr(
            TransitionType,
            "HISTORY_PUSH",
            TransitionType.NAVIGATION,
        ): 4,

        getattr(
            TransitionType,
            "HISTORY_REPLACE",
            TransitionType.NAVIGATION,
        ): 5,

        TransitionType.FETCH: 10,
        TransitionType.XHR: 11,
        TransitionType.REQUEST: 12,
        TransitionType.DOM_MUTATION: 13,
        TransitionType.MANUAL: 20,
    }

    def node_sort_key(
        node_id: str,
    ) -> tuple[int, int]:
        card = canvas.nodes[
            node_id
        ]

        return (
            kind_priority.get(
                card.node.kind,
                99,
            ),
            order_index[
                node_id
            ],
        )

    for source_id in outgoing:
        outgoing[
            source_id
        ].sort(
            key=lambda item: (
                kind_priority.get(
                    canvas.nodes[
                        item[0]
                    ].node.kind,
                    99,
                ),
                transition_priority.get(
                    item[1],
                    99,
                ),
                order_index[
                    item[0]
                ],
            )
        )

    roots = [
        node_id
        for node_id in node_ids
        if indegree[
            node_id
        ] == 0
    ]

    roots.sort(
        key=node_sort_key
    )

    if not roots:
        roots = [
            min(
                node_ids,
                key=node_sort_key,
            )
        ]

    tree_children: dict[
        str,
        list[str],
    ] = {
        node_id: []
        for node_id in node_ids
    }

    depth: dict[
        str,
        int,
    ] = {}

    assigned: set[str] = set()

    component_roots: list[
        str
    ] = []

    def grow_component(
        root_id: str,
    ) -> None:
        if root_id in assigned:
            return

        component_roots.append(
            root_id
        )

        assigned.add(
            root_id
        )

        depth[
            root_id
        ] = 0

        queue = [
            root_id
        ]

        while queue:
            source_id = (
                queue.pop(0)
            )

            next_depth = (
                depth[
                    source_id
                ]
                + 1
            )

            for (
                target_id,
                _transition_type,
            ) in outgoing[
                source_id
            ]:
                if (
                    target_id
                    in assigned
                ):
                    continue

                assigned.add(
                    target_id
                )

                depth[
                    target_id
                ] = (
                    next_depth
                )

                tree_children[
                    source_id
                ].append(
                    target_id
                )

                queue.append(
                    target_id
                )

    for root_id in roots:
        grow_component(
            root_id
        )

    while (
        len(assigned)
        < len(node_ids)
    ):
        remaining = [
            node_id
            for node_id in node_ids
            if node_id
            not in assigned
        ]

        next_root = min(
            remaining,
            key=node_sort_key,
        )

        grow_component(
            next_root
        )

    subtree_units: dict[
        str,
        float,
    ] = {}

    def calculate_units(
        node_id: str,
    ) -> float:
        children = (
            tree_children[
                node_id
            ]
        )

        if not children:
            subtree_units[
                node_id
            ] = 1.0

            return 1.0

        units = sum(
            calculate_units(
                child_id
            )
            for child_id
            in children
        )

        units = max(
            1.0,
            units,
        )

        subtree_units[
            node_id
        ] = units

        return units

    for root_id in (
        component_roots
    ):
        calculate_units(
            root_id
        )

    horizontal_step = (
        PageCard.WIDTH
        + horizontal_gap
    )

    vertical_step = (
        PageCard.HEIGHT
        + vertical_gap
    )

    max_depth = 0

    # Offset entre componentes desconectados no eixo transversal.
    component_offset = 0.0

    def place_subtree(
        node_id: str,
        top_unit: float,
    ) -> None:
        nonlocal max_depth

        node_depth = (
            depth[
                node_id
            ]
        )

        max_depth = max(
            max_depth,
            node_depth,
        )

        units = (
            subtree_units[
                node_id
            ]
        )

        center_unit = (
            top_unit
            + units
            / 2.0
        )

        if direction == "horizontal":
            x = (
                node_depth
                * horizontal_step
            )

            y = (
                component_offset
                + center_unit
                * vertical_step
                - PageCard.HEIGHT
                / 2.0
            )

        else:
            x = (
                component_offset
                + center_unit
                * horizontal_step
                - PageCard.WIDTH
                / 2.0
            )

            y = (
                node_depth
                * vertical_step
            )

        card = canvas.nodes[
            node_id
        ]

        card.setPos(
            x,
            y,
        )

        child_top = (
            top_unit
        )

        for child_id in (
            tree_children[
                node_id
            ]
        ):
            place_subtree(
                child_id,
                child_top,
            )

            child_top += (
                subtree_units[
                    child_id
                ]
            )

    for root_id in (
        component_roots
    ):
        place_subtree(
            root_id,
            0.0,
        )

        if direction == "horizontal":
            component_span = (
                subtree_units[
                    root_id
                ]
                * vertical_step
            )
        else:
            component_span = (
                subtree_units[
                    root_id
                ]
                * horizontal_step
            )

        component_offset += (
            component_span
            + component_gap
        )

    canvas.grow_scene_to_graph()

    canvas.viewport().update()

    canvas.fit_graph()

    return TreeLayoutResult(
        nodes=len(
            node_ids
        ),
        components=len(
            component_roots
        ),
        max_depth=max_depth,
    )
