"""
Núcleo de teoria dos grafos do SpiderView.

Este pacote não depende de Qt. Ele trabalha apenas com os modelos
lógicos PageNode e Transition.
"""

from .analysis import (
    GraphAnalysis,
    NodeMetrics,
    analyze_graph,
    strongly_connected_components,
)
from .graph_model import GraphModel
from .grouping import (
    GroupSpec,
    GroupingPolicy,
    build_groups,
    find_api_groups,
    find_redirect_groups,
)
from .hierarchical_layout import (
    HierarchicalLayoutConfig,
    HierarchicalLayoutResult,
    hierarchical_layout,
)
from .query import (
    DEFAULT_METHODS,
    DEFAULT_NODE_KINDS,
    DEFAULT_ORIGINS,
    DEFAULT_STATUS_FAMILIES,
    DEFAULT_TRANSPORTS,
    ViewQuery,
    ViewQueryResult,
    apply_view_query,
    collect_focus_nodes,
    infer_first_party_host,
    node_origin,
    transition_matches_transport,
)
from .view_graph import (
    ViewEdge,
    ViewGraph,
    ViewNode,
    build_view_graph,
)
from .weights import (
    EdgeVisualWeight,
    NodeVisualWeight,
    WeightProfile,
    calculate_edge_weights,
    calculate_node_weights,
)

__all__ = [
    "DEFAULT_METHODS",
    "DEFAULT_NODE_KINDS",
    "DEFAULT_ORIGINS",
    "DEFAULT_STATUS_FAMILIES",
    "DEFAULT_TRANSPORTS",

    "EdgeVisualWeight",
    "GraphAnalysis",
    "GraphModel",

    "GroupSpec",
    "GroupingPolicy",

    "HierarchicalLayoutConfig",
    "HierarchicalLayoutResult",

    "NodeMetrics",
    "NodeVisualWeight",

    "ViewEdge",
    "ViewGraph",
    "ViewNode",
    "ViewQuery",
    "ViewQueryResult",

    "WeightProfile",

    "analyze_graph",
    "apply_view_query",

    "build_groups",
    "build_view_graph",

    "calculate_edge_weights",
    "calculate_node_weights",

    "collect_focus_nodes",

    "find_api_groups",
    "find_redirect_groups",

    "hierarchical_layout",

    "infer_first_party_host",
    "node_origin",

    "strongly_connected_components",
    "transition_matches_transport",
]
