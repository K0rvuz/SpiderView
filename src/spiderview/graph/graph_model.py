from __future__ import annotations

from collections.abc import Iterable, Iterator

from ..models import PageNode, Transition


class GraphModel:
    """
    Snapshot lógico do grafo do SpiderView.

    Não depende de Qt e não altera PageNode/Transition.

    O mesmo par de nodes pode possuir várias transitions diferentes:
        PAGE --click--> PAGE
        PAGE --fetch--> API
        PAGE --xhr----> API

    Por isso os índices armazenam IDs de transitions, e os métodos
    successors()/predecessors() oferecem uma visão deduplicada quando
    o algoritmo precisa apenas da topologia.
    """

    def __init__(
        self,
        nodes: Iterable[PageNode],
        transitions: Iterable[Transition],
        *,
        strict: bool = False,
    ) -> None:
        self.nodes: dict[str, PageNode] = {}
        self.transitions: dict[str, Transition] = {}

        self._out_edges: dict[str, list[str]] = {}
        self._in_edges: dict[str, list[str]] = {}

        self._node_order: dict[str, int] = {}
        self._transition_order: dict[str, int] = {}

        self._valid_transition_ids: list[str] = []
        self._dangling_transition_ids: list[str] = []

        for index, node in enumerate(nodes):
            if node.id in self.nodes:
                raise ValueError(
                    f"Node duplicado: {node.id}"
                )

            self.nodes[node.id] = node
            self._node_order[node.id] = index
            self._out_edges[node.id] = []
            self._in_edges[node.id] = []

        for index, transition in enumerate(transitions):
            if transition.id in self.transitions:
                raise ValueError(
                    f"Transition duplicada: {transition.id}"
                )

            self.transitions[
                transition.id
            ] = transition

            self._transition_order[
                transition.id
            ] = index

            source_exists = (
                transition.source_id
                in self.nodes
            )

            target_exists = (
                transition.target_id
                in self.nodes
            )

            if not (
                source_exists
                and target_exists
            ):
                self._dangling_transition_ids.append(
                    transition.id
                )

                if strict:
                    raise ValueError(
                        "Transition aponta para node inexistente: "
                        f"{transition.id} "
                        f"({transition.source_id} -> "
                        f"{transition.target_id})"
                    )

                continue

            self._out_edges[
                transition.source_id
            ].append(
                transition.id
            )

            self._in_edges[
                transition.target_id
            ].append(
                transition.id
            )

            self._valid_transition_ids.append(
                transition.id
            )

    # ------------------------------------------------------------------
    # Basic properties
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        return len(
            self.nodes
        )

    @property
    def transition_count(self) -> int:
        return len(
            self._valid_transition_ids
        )

    @property
    def dangling_transition_count(self) -> int:
        return len(
            self._dangling_transition_ids
        )

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(
            self.nodes.keys()
        )

    @property
    def valid_transition_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            self._valid_transition_ids
        )

    @property
    def dangling_transition_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            self._dangling_transition_ids
        )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def node(
        self,
        node_id: str,
    ) -> PageNode:
        return self.nodes[
            node_id
        ]

    def transition(
        self,
        transition_id: str,
    ) -> Transition:
        return self.transitions[
            transition_id
        ]

    def node_order(
        self,
        node_id: str,
    ) -> int:
        return self._node_order[
            node_id
        ]

    def transition_order(
        self,
        transition_id: str,
    ) -> int:
        return self._transition_order[
            transition_id
        ]

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def outgoing_transitions(
        self,
        node_id: str,
    ) -> tuple[Transition, ...]:
        return tuple(
            self.transitions[
                transition_id
            ]
            for transition_id
            in self._out_edges.get(
                node_id,
                (),
            )
        )

    def incoming_transitions(
        self,
        node_id: str,
    ) -> tuple[Transition, ...]:
        return tuple(
            self.transitions[
                transition_id
            ]
            for transition_id
            in self._in_edges.get(
                node_id,
                (),
            )
        )

    def iter_valid_transitions(
        self,
    ) -> Iterator[Transition]:
        for transition_id in (
            self._valid_transition_ids
        ):
            yield self.transitions[
                transition_id
            ]

    # ------------------------------------------------------------------
    # Neighborhood
    # ------------------------------------------------------------------

    def successors(
        self,
        node_id: str,
    ) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []

        for transition in (
            self.outgoing_transitions(
                node_id
            )
        ):
            target_id = (
                transition.target_id
            )

            if target_id in seen:
                continue

            seen.add(
                target_id
            )
            result.append(
                target_id
            )

        return tuple(
            result
        )

    def predecessors(
        self,
        node_id: str,
    ) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []

        for transition in (
            self.incoming_transitions(
                node_id
            )
        ):
            source_id = (
                transition.source_id
            )

            if source_id in seen:
                continue

            seen.add(
                source_id
            )
            result.append(
                source_id
            )

        return tuple(
            result
        )

    def neighbors_undirected(
        self,
        node_id: str,
    ) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []

        for neighbor_id in (
            self.predecessors(
                node_id
            )
            + self.successors(
                node_id
            )
        ):
            if neighbor_id in seen:
                continue

            seen.add(
                neighbor_id
            )
            result.append(
                neighbor_id
            )

        return tuple(
            result
        )

    # ------------------------------------------------------------------
    # Degree
    # ------------------------------------------------------------------

    def in_degree(
        self,
        node_id: str,
        *,
        unique: bool = False,
    ) -> int:
        if unique:
            return len(
                self.predecessors(
                    node_id
                )
            )

        return len(
            self._in_edges.get(
                node_id,
                (),
            )
        )

    def out_degree(
        self,
        node_id: str,
        *,
        unique: bool = False,
    ) -> int:
        if unique:
            return len(
                self.successors(
                    node_id
                )
            )

        return len(
            self._out_edges.get(
                node_id,
                (),
            )
        )

    def degree(
        self,
        node_id: str,
        *,
        unique: bool = False,
    ) -> int:
        return (
            self.in_degree(
                node_id,
                unique=unique,
            )
            + self.out_degree(
                node_id,
                unique=unique,
            )
        )

    # ------------------------------------------------------------------
    # Roots / sinks
    # ------------------------------------------------------------------

    def roots(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            node_id
            for node_id
            in self.node_ids
            if self.in_degree(
                node_id,
                unique=True,
            ) == 0
        )

    def sinks(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            node_id
            for node_id
            in self.node_ids
            if self.out_degree(
                node_id,
                unique=True,
            ) == 0
        )
