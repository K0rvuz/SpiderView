from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from ..browser.browser_host import BrowserHost
from ..export.html_exporter import HtmlExportError, HtmlExporter
from ..graph import (
    GraphModel,
    GroupingPolicy,
    HierarchicalLayoutConfig,
    analyze_graph,
    apply_view_query,
    build_view_graph,
    calculate_node_weights,
    hierarchical_layout,
)
from ..models import NodeKind, PageNode, Transition, TransitionType
from ..persistence.project_store import ProjectStore, ProjectStoreError
from .analysis_toolbar import AnalysisToolbar
from .canvas import SpiderCanvas
from .edge_item import EdgeItem
from .group_card import GroupCard
from .node_details import NodeDetailsPanel
from .node_metadata_dialog import NodeMetadataDialog
from .note_dialog import NoteDialog
from .page_card import PageCard
from .tree_layout import arrange_tree


class MainWindow(QMainWindow):
    """
    Janela principal do SpiderView.

    Responsabilidades:
    - manter o canvas e o browser embutido;
    - transformar navegações reais em PageNodes;
    - transformar clicks/submits/navegações SPA em Transitions;
    - deduplicar páginas pela URL normalizada;
    - capturar previews temporários das páginas.
    """

    PENDING_INTERACTION_MAX_AGE = 30.0
    MAX_EDGE_LABEL_LENGTH = 90

    def __init__(self):
        super().__init__()

        self.setWindowTitle("OZAP SpiderView")

        # --------------------------------------------------------------
        # Mapping state
        # --------------------------------------------------------------

        # URL normalizada -> node_id de página.
        self._url_index: dict[str, str] = {}

        # "METHOD normalized_url" -> node_id de API.
        #
        # A mesma URL pode representar operações diferentes:
        #
        #   GET  /api/users
        #   POST /api/users
        #
        # e por isso método + URL formam a identidade do node API.
        self._api_index: dict[str, str] = {}

        # Página atualmente ativa no browser.
        self._current_node_id: str | None = None

        # Usado quando abrimos um card existente pelo canvas.
        #
        # Isso evita criar uma edge artificial entre o node atual
        # e o node aberto manualmente.
        self._pending_existing_node_id: str | None = None

        # Última interação capturada pelo JavaScript do BrowserHost.
        #
        # Exemplos:
        #   {"kind": "click", ...}
        #   {"kind": "submit", ...}
        self._pending_interaction: dict | None = None
        self._pending_interaction_at = 0.0

        # Diretório temporário usado pelos screenshots.
        #
        # Na etapa de persistência isso pode ser substituído
        # por uma pasta dentro do projeto salvo.
        self._preview_dir = TemporaryDirectory(
            prefix="spiderview-previews-"
        )

        self._manual_node_counter = 1

        # Projeto atualmente associado ao canvas.
        self._project_dir: Path | None = None

        # Resultado derivado do último layout de teoria dos grafos.
        #
        # Não é persistido: pode ser recalculado a qualquer momento.
        self._graph_layout_result = None

        # Orientação comum dos layouts.
        #
        # False -> esquerda para direita
        # True  -> cima para baixo
        self._vertical_layout = False

        # Último layout raw utilizado. Serve para reaplicar a mesma
        # família quando o usuário troca Horizontal / Vertical.
        self._last_raw_layout = "graph"

        # --------------------------------------------------------------
        # Investigation View
        # --------------------------------------------------------------

        self._investigation_mode = False

        # IDs de grupos atualmente expandidos.
        # Também é estado apenas de visualização.
        self._expanded_view_groups: set[str] = set()

        self._view_graph = None

        # Evita reconstruir a view dezenas de vezes quando uma página
        # dispara várias fetch/XHR em sequência.
        self._investigation_refresh_pending = False

        # Focus Mode usa IDs do Raw Graph.
        #
        # GroupCard selecionado expande para seus member_node_ids.
        self._focus_root_ids: set[str] = set()

        # --------------------------------------------------------------
        # Canvas
        # --------------------------------------------------------------

        self.canvas = SpiderCanvas()
        self.setCentralWidget(self.canvas)

        # --------------------------------------------------------------
        # Browser
        # --------------------------------------------------------------

        self.browser_host = BrowserHost()

        self.browser_dock = QDockWidget(
            "Browser",
            self,
        )

        self.browser_dock.setWidget(self.browser_host)
        self.browser_dock.setMinimumWidth(500)

        self.browser_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.browser_dock,
        )

        self.browser_dock.hide()

        # --------------------------------------------------------------
        # Details
        # --------------------------------------------------------------

        self.node_details = NodeDetailsPanel()

        self.details_dock = QDockWidget(
            "Details",
            self,
        )

        self.details_dock.setWidget(
            self.node_details
        )

        self.details_dock.setMinimumWidth(
            340
        )

        self.details_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea,
            self.details_dock,
        )

        self.details_dock.hide()

        # --------------------------------------------------------------
        # UI
        # --------------------------------------------------------------

        self._create_toolbar()
        self._create_analysis_toolbar()
        self._connect_signals()
        self._configure_status_bar()
        self._apply_theme()

        # Não carregamos mais a demo automaticamente.
        # O programa inicia pronto para um mapeamento real.

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _create_toolbar(self) -> None:
        """
        Menus de comandos da aplicação.

        A antiga toolbar principal cresceu junto com o projeto e
        começou a competir por espaço com o canvas. Os comandos ficam
        agora organizados por função, preservando todos os atalhos.
        A toolbar Analysis continua separada por ser uma superfície
        de consulta/filtros em tempo real.
        """

        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu(
            "Arquivo"
        )

        edit_menu = menu_bar.addMenu(
            "Editar"
        )

        view_menu = menu_bar.addMenu(
            "Visualização"
        )

        layout_menu = menu_bar.addMenu(
            "Layout"
        )

        tools_menu = menu_bar.addMenu(
            "Ferramentas"
        )

        # --------------------------------------------------------------
        # Arquivo
        # --------------------------------------------------------------

        open_action = QAction(
            "Abrir projeto",
            self,
        )
        open_action.setShortcut(
            QKeySequence("Ctrl+O")
        )
        open_action.triggered.connect(
            self._open_project
        )
        file_menu.addAction(
            open_action
        )

        save_action = QAction(
            "Salvar",
            self,
        )
        save_action.setShortcut(
            QKeySequence("Ctrl+S")
        )
        save_action.triggered.connect(
            self._save_project
        )
        file_menu.addAction(
            save_action
        )

        save_as_action = QAction(
            "Salvar como…",
            self,
        )
        save_as_action.setShortcut(
            QKeySequence("Ctrl+Shift+S")
        )
        save_as_action.triggered.connect(
            self._save_project_as
        )
        file_menu.addAction(
            save_as_action
        )

        file_menu.addSeparator()

        export_action = QAction(
            "Exportar visualização atual como HTML…",
            self,
        )
        export_action.setShortcut(
            QKeySequence("Ctrl+E")
        )
        export_action.triggered.connect(
            self._export_html
        )
        file_menu.addAction(
            export_action
        )

        # --------------------------------------------------------------
        # Editar
        # --------------------------------------------------------------

        add_node_action = QAction(
            "Novo card",
            self,
        )
        add_node_action.setShortcut(
            QKeySequence("Ctrl+N")
        )
        add_node_action.triggered.connect(
            self._add_manual_node
        )
        edit_menu.addAction(
            add_node_action
        )

        add_note_action = QAction(
            "Nova nota",
            self,
        )
        add_note_action.setShortcut(
            QKeySequence("Ctrl+Shift+N")
        )
        add_note_action.triggered.connect(
            self._add_note
        )
        edit_menu.addAction(
            add_note_action
        )

        note_selection_action = QAction(
            "Nota da seleção",
            self,
        )
        note_selection_action.setShortcut(
            QKeySequence("Ctrl+Alt+N")
        )
        note_selection_action.triggered.connect(
            self._add_note_for_selection
        )
        edit_menu.addAction(
            note_selection_action
        )

        metadata_action = QAction(
            "Tags / Status",
            self,
        )
        metadata_action.setShortcut(
            QKeySequence("Alt+Return")
        )
        metadata_action.triggered.connect(
            self._edit_selected_metadata
        )
        edit_menu.addAction(
            metadata_action
        )

        edit_menu.addSeparator()

        delete_action = QAction(
            "Excluir seleção",
            self,
        )
        delete_action.setShortcut(
            QKeySequence(
                Qt.Key.Key_Delete
            )
        )
        delete_action.triggered.connect(
            self._delete_selected
        )
        edit_menu.addAction(
            delete_action
        )

        clear_action = QAction(
            "Limpar grafo",
            self,
        )
        clear_action.triggered.connect(
            self._clear_graph
        )
        edit_menu.addAction(
            clear_action
        )

        # --------------------------------------------------------------
        # Visualização
        # --------------------------------------------------------------

        browser_action = QAction(
            "Browser",
            self,
        )
        browser_action.setShortcut(
            QKeySequence("Ctrl+L")
        )
        browser_action.triggered.connect(
            self._show_browser
        )
        view_menu.addAction(
            browser_action
        )

        details_action = QAction(
            "Details",
            self,
        )
        details_action.setShortcut(
            QKeySequence("Ctrl+D")
        )
        details_action.triggered.connect(
            self._show_details
        )
        view_menu.addAction(
            details_action
        )

        view_menu.addSeparator()

        self._investigation_action = QAction(
            "Investigation",
            self,
        )
        self._investigation_action.setCheckable(
            True
        )
        self._investigation_action.setShortcut(
            QKeySequence("Ctrl+I")
        )
        self._investigation_action.toggled.connect(
            self._set_investigation_mode
        )
        view_menu.addAction(
            self._investigation_action
        )

        fit_action = QAction(
            "Fit Graph",
            self,
        )
        fit_action.setShortcut(
            QKeySequence("Ctrl+0")
        )
        fit_action.triggered.connect(
            self.canvas.fit_graph
        )
        view_menu.addAction(
            fit_action
        )

        # --------------------------------------------------------------
        # Layout
        # --------------------------------------------------------------

        graph_layout_action = QAction(
            "Organizar grafo",
            self,
        )
        graph_layout_action.setShortcut(
            QKeySequence("Ctrl+Alt+0")
        )
        graph_layout_action.triggered.connect(
            self._organize_graph
        )
        layout_menu.addAction(
            graph_layout_action
        )

        organize_action = QAction(
            "Organizar árvore",
            self,
        )
        organize_action.setShortcut(
            QKeySequence("Ctrl+Shift+0")
        )
        organize_action.triggered.connect(
            self._organize_tree
        )
        layout_menu.addAction(
            organize_action
        )

        layout_menu.addSeparator()

        self._vertical_layout_action = QAction(
            "Orientação vertical",
            self,
        )
        self._vertical_layout_action.setCheckable(
            True
        )
        self._vertical_layout_action.setShortcut(
            QKeySequence("Ctrl+Alt+V")
        )
        self._vertical_layout_action.toggled.connect(
            self._set_vertical_layout
        )
        layout_menu.addAction(
            self._vertical_layout_action
        )

        # --------------------------------------------------------------
        # Ferramentas
        # --------------------------------------------------------------

        demo_action = QAction(
            "Carregar demo",
            self,
        )
        demo_action.triggered.connect(
            self._load_demo_graph
        )
        tools_menu.addAction(
            demo_action
        )

    def _create_analysis_toolbar(
        self,
    ) -> None:
        """
        Toolbar dedicada a Focus/Filters/Search.

        Os comandos gerais ficam no menu; esta barra permanece porque
        seus controles representam uma consulta viva sobre o canvas.
        """

        self.analysis_toolbar = (
            AnalysisToolbar(
                self
            )
        )

        self.addToolBar(
            self.analysis_toolbar
        )

    # ------------------------------------------------------------------
    # Analysis query helpers
    # ------------------------------------------------------------------

    def _current_view_query(
        self,
    ):
        return (
            self.analysis_toolbar
            .query()
        )

    def _analysis_query_active(
        self,
    ) -> bool:
        return not (
            self._current_view_query()
            .is_default()
        )

    def _analysis_view_required(
        self,
    ) -> bool:
        return (
            self._investigation_mode
            or self._analysis_query_active()
        )

    def _selected_focus_roots(
        self,
    ) -> set[str]:
        roots: set[str] = set()

        selected = (
            self.canvas
            .scene()
            .selectedItems()
        )

        for item in selected:
            if isinstance(
                item,
                PageCard,
            ):
                roots.add(
                    item.node.id
                )

            elif isinstance(
                item,
                GroupCard,
            ):
                roots.update(
                    item.view_node
                    .raw_node_ids
                )

            elif isinstance(
                item,
                EdgeItem,
            ):
                source_id = (
                    item.transition
                    .source_id
                )

                target_id = (
                    item.transition
                    .target_id
                )

                if source_id in (
                    self.canvas.nodes
                ):
                    roots.add(
                        source_id
                    )

                if target_id in (
                    self.canvas.nodes
                ):
                    roots.add(
                        target_id
                    )

        return roots

    def _on_focus_requested(
        self,
    ) -> None:
        roots = (
            self._selected_focus_roots()
        )

        if not roots:
            self.analysis_toolbar.set_focus_checked(
                False
            )

            self._focus_root_ids.clear()

            self.statusBar().showMessage(
                "Focus: selecione um card ou conexão primeiro.",
                4500,
            )

            return

        self._focus_root_ids = roots

        self._refresh_analysis_view(
            fit=True
        )

    def _on_focus_cleared(
        self,
    ) -> None:
        self._focus_root_ids.clear()

        self._refresh_analysis_or_restore(
            fit=False
        )

    def _on_analysis_query_changed(
        self,
        _query,
    ) -> None:
        self._refresh_analysis_or_restore(
            fit=False
        )

    def _refresh_analysis_or_restore(
        self,
        *,
        fit: bool,
    ) -> None:
        if (
            self._analysis_view_required()
        ):
            self._refresh_analysis_view(
                fit=fit
            )
            return

        self.canvas.clear_virtual_view()

        self._view_graph = None
        self._expanded_view_groups.clear()

        if fit:
            QTimer.singleShot(
                0,
                self.canvas.fit_graph,
            )

        self.statusBar().showMessage(
            "Raw Graph · filtros limpos",
            3000,
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _layout_direction(
        self,
    ) -> str:
        return (
            "vertical"
            if self._vertical_layout
            else "horizontal"
        )

    def _layout_direction_label(
        self,
    ) -> str:
        return (
            "vertical"
            if self._vertical_layout
            else "horizontal"
        )

    def _set_vertical_layout(
        self,
        enabled: bool,
    ) -> None:
        self._vertical_layout = bool(
            enabled
        )

        if not self.canvas.nodes:
            return

        # Investigation/Focus/Filters usam posições temporárias.
        if self._analysis_view_required():
            self._refresh_analysis_view(
                fit=True
            )
            return

        # No raw graph, reaplicamos a última família usada.
        if self._last_raw_layout == "tree":
            self._organize_tree()
        else:
            self._organize_graph()

    def _build_graph_model(self) -> GraphModel:
        """
        Cria um snapshot lógico do grafo atualmente visível.

        Nenhum objeto Qt entra na camada graph/.
        """

        nodes = [
            card.node
            for card
            in self.canvas.nodes.values()
        ]

        transitions = [
            edge.transition
            for edge
            in self.canvas.edges.values()
        ]

        return GraphModel(
            nodes=nodes,
            transitions=transitions,
        )

    def _organize_graph(self) -> None:
        """
        Layout principal do SpiderView.

        Usa:
        - SCC para ciclos;
        - longest-path layering;
        - ordenação baricêntrica;
        - pesos estruturais;
        - centralidade;
        - frequência de requests.

        Apenas as posições visuais são alteradas.
        """

        if not self.canvas.nodes:
            return

        if self._analysis_view_required():
            self._last_raw_layout = "graph"

            self._refresh_analysis_view(
                fit=True
            )
            return

        self._last_raw_layout = "graph"

        graph = self._build_graph_model()

        config = HierarchicalLayoutConfig(
            direction=self._layout_direction(),

            node_width=PageCard.WIDTH,
            node_height=PageCard.HEIGHT,

            horizontal_gap=260.0,
            vertical_gap=95.0,

            weight_gap_factor=7.0,
            maximum_weight_gap=150.0,

            barycentric_sweeps=8,
        )

        result = hierarchical_layout(
            graph,
            config=config,
        )

        self._graph_layout_result = result

        # Aplicamos apenas coordenadas.
        #
        # PageCard.itemChange() já:
        # - sincroniza PageNode.x/y;
        # - recalcula as edges;
        # - mantém persistência compatível.
        for node_id, (
            x,
            y,
        ) in result.positions.items():

            card = self.canvas.get_node(
                node_id
            )

            if card is None:
                continue

            card.setPos(
                x,
                y,
            )

        # A cena cresce com o grafo antes do enquadramento.
        self.canvas.grow_scene_to_graph()

        # Um repaint final evita trabalho visual intermediário
        # restante depois de muitos setPos().
        self.canvas.viewport().update()

        QTimer.singleShot(
            0,
            self.canvas.fit_graph,
        )

        cyclic_components = (
            result.analysis
            .cyclic_component_count
        )

        self.statusBar().showMessage(
            "Grafo organizado · "
            f"{graph.node_count} nodes · "
            f"{result.layer_count} níveis · "
            f"{len(result.analysis.weak_components)} componente(s) · "
            f"{cyclic_components} ciclo(s) · "
            f"{self._layout_direction_label()}",
            6000,
        )

    def _organize_tree(self) -> None:
        """
        Reorganiza o grafo em uma árvore hierárquica.

        O layout só altera posições. Nodes, edges, metadata,
        URLs e demais dados permanecem intactos.
        """

        if not self.canvas.nodes:
            return

        if self._analysis_view_required():
            self.statusBar().showMessage(
                "Tree usa o Raw Graph. Use Reset nos filtros/Focus antes de organizar como árvore.",
                5500,
            )
            return

        self._last_raw_layout = "tree"

        result = arrange_tree(
            self.canvas,
            direction=self._layout_direction(),
        )

        self.statusBar().showMessage(
            "Árvore organizada · "
            f"{result.nodes} nodes · "
            f"{result.components} componente(s) · "
            f"profundidade {result.max_depth} · "
            f"{self._layout_direction_label()}",
            5000,
        )

    # ------------------------------------------------------------------
    # Investigation View
    # ------------------------------------------------------------------

    def _set_investigation_action_checked(
        self,
        checked: bool,
    ) -> None:
        """
        Atualiza o QAction sem disparar uma segunda troca de modo.
        """

        action = getattr(
            self,
            "_investigation_action",
            None,
        )

        if action is None:
            return

        previous = action.blockSignals(
            True
        )

        action.setChecked(
            checked
        )

        action.blockSignals(
            previous
        )

    def _set_investigation_mode(
        self,
        enabled: bool,
    ) -> None:
        self._investigation_mode = bool(
            enabled
        )

        if not enabled:
            self._expanded_view_groups.clear()
            self._investigation_refresh_pending = False

            if self._analysis_query_active():
                self._refresh_analysis_view(
                    fit=True
                )
            else:
                self.canvas.clear_virtual_view()

                self._view_graph = None

                QTimer.singleShot(
                    0,
                    self.canvas.fit_graph,
                )

                self.statusBar().showMessage(
                    "Raw Graph · visualização completa restaurada",
                    4000,
                )

            return

        self._refresh_analysis_view(
            fit=True
        )

    def _refresh_analysis_view(
        self,
        *,
        fit: bool = True,
    ) -> None:
        """
        Pipeline de visualização:

            Raw Graph
                ↓
            Focus + Filters + Search
                ↓
            optional Investigation grouping
                ↓
            hierarchical layout
                ↓
            Canvas virtual

        O Raw Graph e suas posições persistidas continuam intactos.
        """

        if not self.canvas.nodes:
            return

        raw_graph = (
            self._build_graph_model()
        )

        query = (
            self._current_view_query()
        )

        query_result = (
            apply_view_query(
                raw_graph,
                query,
                focus_root_ids=(
                    self._focus_root_ids
                ),
            )
        )

        filtered_graph = (
            query_result.graph
        )

        use_groups = (
            self._investigation_mode
            and query.show_groups
        )

        policy = GroupingPolicy(
            group_apis=use_groups,

            api_min_size=2,

            api_group_by_first_path_segment=True,

            collapse_redirect_chains=(
                use_groups
            ),

            redirect_min_size=2,
        )

        view_graph = build_view_graph(
            filtered_graph,
            policy=policy,
            expanded_group_ids=(
                self._expanded_view_groups
                if use_groups
                else set()
            ),
        )

        layout_graph = (
            view_graph.to_layout_graph(
                filtered_graph
            )
        )

        config = (
            HierarchicalLayoutConfig(
                direction=self._layout_direction(),

                node_width=(
                    PageCard.WIDTH
                ),
                node_height=(
                    PageCard.HEIGHT
                ),

                horizontal_gap=280.0,
                vertical_gap=105.0,

                weight_gap_factor=5.0,
                maximum_weight_gap=100.0,

                barycentric_sweeps=10,
            )
        )

        layout_result = (
            hierarchical_layout(
                layout_graph,
                config=config,
            )
        )

        self._view_graph = (
            view_graph
        )

        self._graph_layout_result = (
            layout_result
        )

        self.canvas.apply_view_graph(
            view_graph,
            layout_result.positions,
        )

        if fit:
            QTimer.singleShot(
                0,
                self.canvas.fit_graph,
            )

        group_count = len(
            view_graph.groups
        )

        collapsed_count = sum(
            1
            for group_id
            in view_graph.groups
            if group_id
            not in self._expanded_view_groups
        )

        mode_parts = []

        if self._investigation_mode:
            mode_parts.append(
                "Investigation"
            )

        if query.focus_enabled:
            mode_parts.append(
                f"Focus {query.focus_hops} hop(s) {query.focus_direction}"
            )

        if (
            query.search_text.strip()
        ):
            mode_parts.append(
                f'Search "{query.search_text.strip()}"'
            )

        if not mode_parts:
            mode_parts.append(
                "Filtered View"
            )

        mode_label = (
            " + ".join(
                mode_parts
            )
        )

        first_party = (
            query_result.first_party_host
            or "—"
        )

        self.statusBar().showMessage(
            f"{mode_label} · "
            f"{query_result.raw_node_count} → "
            f"{query_result.visible_node_count} nodes · "
            f"{query_result.raw_transition_count} → "
            f"{query_result.visible_transition_count} edges · "
            f"{group_count} group(s) · "
            f"{collapsed_count} collapsed · "
            f"first-party {first_party} · "
            f"{self._layout_direction_label()}",
            7000,
        )

    def _schedule_investigation_refresh(
        self,
    ) -> None:
        """
        Atualiza a projeção após mutações do raw graph sem refazer
        o layout para cada fetch/XHR individual.
        """

        if not self._analysis_view_required():
            return

        if self._investigation_refresh_pending:
            return

        self._investigation_refresh_pending = True

        QTimer.singleShot(
            120,
            self._run_scheduled_investigation_refresh,
        )

    def _run_scheduled_investigation_refresh(
        self,
    ) -> None:
        self._investigation_refresh_pending = False

        if not self._analysis_view_required():
            return

        self._refresh_analysis_view(
            fit=False
        )

    def _toggle_view_group(
        self,
        group_id: str,
    ) -> None:
        """
        Double click em um GroupCard:
            collapsed -> expanded
            expanded  -> collapsed
        """

        if (
            group_id
            in self._expanded_view_groups
        ):
            self._expanded_view_groups.remove(
                group_id
            )
        else:
            self._expanded_view_groups.add(
                group_id
            )

        if self._investigation_mode:
            self._investigation_refresh_pending = False

            self._refresh_analysis_view(
                fit=False
            )

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.analysis_toolbar.queryChanged.connect(
            self._on_analysis_query_changed
        )

        self.analysis_toolbar.focusRequested.connect(
            self._on_focus_requested
        )

        self.analysis_toolbar.focusCleared.connect(
            self._on_focus_cleared
        )

        self.canvas.nodeDoubleClicked.connect(
            self._open_node
        )

        self.canvas.groupDoubleClicked.connect(
            self._toggle_view_group
        )

        self.canvas.manualConnectionRequested.connect(
            self._create_manual_note_connection
        )

        self.canvas.scene().selectionChanged.connect(
            self._on_canvas_selection_changed
        )

        self.browser_host.closeRequested.connect(
            self.browser_dock.hide
        )

        self.browser_host.navigationFinished.connect(
            self._on_browser_navigation_finished
        )

        self.browser_host.interactionDetected.connect(
            self._on_browser_interaction
        )

        self.browser_host.spaNavigationDetected.connect(
            self._on_spa_navigation
        )

        self.browser_host.apiRequestDetected.connect(
            self._on_api_request
        )

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _configure_status_bar(self) -> None:
        self.statusBar().showMessage(
            "Ctrl+L  Browser     •     "
            "Ctrl+D  Details     •     "
            "Ctrl+I  Investigation     •     "
            "Focus/Filters na barra Analysis     •     "
            "Ctrl+Alt+V  Vertical     •     "
            "Ctrl+Alt+0  Organizar     •     "
            "Scroll  Zoom     •     "
            "MMB  Pan     •     "
            "Drag background  Select     •     "
            "Ctrl+Click  Multi-select     •     "
            "Drag card  Move selection     •     "
            "Connector -> card  Manual link     •     "
            "Ctrl+Alt+N  Note from selection     •     "
            "Alt+Enter  Tags/Status     •     "
            "Double Click  Open/Edit"
        )

    # ------------------------------------------------------------------
    # Details
    # ------------------------------------------------------------------

    def _show_details(self) -> None:
        self.details_dock.show()
        self.details_dock.raise_()

        self._on_canvas_selection_changed()

    def _on_canvas_selection_changed(
        self,
    ) -> None:
        selected = list(
            self.canvas
            .scene()
            .selectedItems()
        )

        if not selected:
            self.node_details.clear()
            return

        # Cards têm prioridade sobre edges em seleção múltipla.
        item = next(
            (
                candidate
                for candidate in selected
                if isinstance(
                    candidate,
                    (
                        PageCard,
                        GroupCard,
                    ),
                )
            ),
            selected[0],
        )

        if isinstance(
            item,
            PageCard,
        ):
            self._show_page_details(
                item.node
            )

        elif isinstance(
            item,
            GroupCard,
        ):
            self.node_details.show_group(
                item.view_node
            )

        elif isinstance(
            item,
            EdgeItem,
        ):
            self.node_details.show_edge(
                item.transition,
                source_title=(
                    self._view_item_title(
                        item.transition.source_id
                    )
                ),
                target_title=(
                    self._view_item_title(
                        item.transition.target_id
                    )
                ),
            )

        else:
            self.node_details.clear()
            return

        if not self.details_dock.isVisible():
            self.details_dock.show()

    def _show_page_details(
        self,
        node: PageNode,
    ) -> None:
        metrics = None
        weight = None

        try:
            graph = (
                self._build_graph_model()
            )

            analysis = analyze_graph(
                graph,
                compute_betweenness=(
                    graph.node_count <= 600
                ),
                betweenness_limit=600,
            )

            metrics = (
                analysis.metrics.get(
                    node.id
                )
            )

            if metrics is not None:
                weights = (
                    calculate_node_weights(
                        graph,
                        analysis,
                    )
                )

                weight = weights.get(
                    node.id
                )

        except Exception:
            # O painel não pode interromper o canvas
            # caso uma análise derivada falhe.
            metrics = None
            weight = None

        self.node_details.show_node(
            node,
            metrics=metrics,
            weight=weight,
        )

    def _view_item_title(
        self,
        item_id: str,
    ) -> str:
        card = self.canvas.get_node(
            item_id
        )

        if card is not None:
            return card.node.title

        if (
            self._view_graph is not None
            and item_id
            in self._view_graph.nodes
        ):
            return (
                self._view_graph
                .nodes[
                    item_id
                ]
                .title
            )

        return item_id

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------

    def _show_browser(self) -> None:
        self.browser_dock.show()
        self.browser_dock.raise_()
        self.browser_host.focus_address_bar()

    def _open_node(
        self,
        node_id: str,
    ) -> None:
        card = self.canvas.get_node(node_id)

        if card is None:
            return

        if card.node.kind == NodeKind.NOTE:
            self._edit_note(
                node_id
            )
            return

        if card.node.kind == NodeKind.API:
            self.statusBar().showMessage(
                "API "
                f"{card.node.method.upper()} "
                f"{card.node.url}",
                5000,
            )
            return

        url = card.node.url.strip()

        if not url:
            return

        # Um click antigo da página não pode ser reaproveitado
        # quando abrimos um card manualmente.
        self._clear_pending_interaction()

        # Marca que esta navegação veio de um card já existente.
        # Quando loadFinished ocorrer, não criaremos nova edge.
        self._pending_existing_node_id = node_id
        self._current_node_id = node_id

        self._select_node(node_id)

        self.browser_host.open_url(
            url,
            origin="canvas",
        )

        self.browser_dock.show()
        self.browser_dock.raise_()

    # ------------------------------------------------------------------
    # Browser interaction
    # ------------------------------------------------------------------

    def _on_browser_interaction(
        self,
        event: dict,
    ) -> None:
        """
        Guarda temporariamente o último click/submit detectado.

        A navegação real costuma acontecer logo depois. Quando ela
        terminar, o evento será consumido e usado para nomear/tipar
        a edge corretamente.
        """

        if not isinstance(event, dict):
            return

        self._pending_interaction = dict(event)
        self._pending_interaction_at = monotonic()

    def _clear_pending_interaction(self) -> None:
        self._pending_interaction = None
        self._pending_interaction_at = 0.0

    def _consume_pending_interaction(
        self,
        source_id: str | None,
    ) -> dict | None:
        event = self._pending_interaction

        if event is None:
            return None

        age = (
            monotonic()
            - self._pending_interaction_at
        )

        self._clear_pending_interaction()

        # Evita usar um click antigo em uma navegação
        # completamente diferente.
        if age > self.PENDING_INTERACTION_MAX_AGE:
            return None

        if source_id is None:
            return None

        source_card = self.canvas.get_node(
            source_id
        )

        if source_card is None:
            return None

        event_source_url = str(
            event.get(
                "source_url",
                "",
            )
            or ""
        )

        if event_source_url:
            current_source_url = self._normalize_url(
                source_card.node.url
            )

            normalized_event_source = self._normalize_url(
                event_source_url
            )

            if (
                current_source_url
                != normalized_event_source
            ):
                return None

        return event

    # ------------------------------------------------------------------
    # Browser filtering / display helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_transient_challenge(
        url: str,
        title: str,
    ) -> bool:
        """
        Detecta páginas intermediárias de challenge que não devem
        virar nodes no mapa principal.
        """

        normalized_title = (
            title.strip()
            .casefold()
            .replace("…", "...")
        )

        if normalized_title == "just a moment...":
            return True

        try:
            parts = urlsplit(url)
        except ValueError:
            return False

        if (
            "/cdn-cgi/challenge-platform/"
            in parts.path
        ):
            return True

        try:
            query = parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
        except ValueError:
            query = []

        for key, _ in query:
            if key.startswith(
                "__cf_chl_"
            ):
                return True

        return False

    @classmethod
    def _compact_label(
        cls,
        text: str,
    ) -> str:
        text = " ".join(
            str(text).split()
        )

        if (
            len(text)
            <= cls.MAX_EDGE_LABEL_LENGTH
        ):
            return text

        return (
            text[
                : cls.MAX_EDGE_LABEL_LENGTH - 1
            ]
            + "…"
        )

    @classmethod
    def _display_path(
        cls,
        url: str,
    ) -> str:
        """
        Produz uma versão curta da URL apenas para exibição.

        A URL completa continua preservada no node e nos metadata.
        """

        try:
            parts = urlsplit(url)
        except ValueError:
            return "/"

        path = parts.path or "/"

        if not parts.query:
            return cls._compact_label(
                path
            )

        try:
            query = parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
        except ValueError:
            return cls._compact_label(
                path
            )

        query = [
            (key, value)
            for key, value in query
            if not key.startswith(
                "__cf_chl_"
            )
        ]

        if not query:
            return cls._compact_label(
                path
            )

        keys = [
            key
            for key, _ in query
        ]

        suffix = "?" + "&".join(
            keys[:4]
        )

        if len(keys) > 4:
            suffix += "&…"

        return cls._compact_label(
            path + suffix
        )

    # ------------------------------------------------------------------
    # Browser -> Graph
    # ------------------------------------------------------------------

    def _get_or_create_browser_node(
        self,
        url: str,
        title: str,
        source_id: str | None,
    ) -> str | None:
        """
        Retorna um node já conhecido para a URL ou cria um novo.

        Essa função centraliza a deduplicação usada tanto por
        navegações tradicionais quanto por History API / SPA.
        """

        normalized_url = self._normalize_url(
            url
        )

        if not normalized_url:
            return None

        target_id = self._url_index.get(
            normalized_url
        )

        # --------------------------------------------------------------
        # Node existente
        # --------------------------------------------------------------

        if target_id is not None:
            card = self.canvas.get_node(
                target_id
            )

            if card is not None:
                self._update_node_from_browser(
                    card,
                    url,
                    title,
                )
                return target_id

            # Referência velha no índice.
            self._url_index.pop(
                normalized_url,
                None,
            )

        # --------------------------------------------------------------
        # Novo node
        # --------------------------------------------------------------

        x, y = self._suggest_position(
            source_id
        )

        node = PageNode(
            title=title or url,
            url=url,
            method="GET",
            status=None,
            x=x,
            y=y,
        )

        self.canvas.add_node(node)

        self._register_url(
            node.id,
            url,
        )

        return node.id

    def _on_browser_navigation_finished(
        self,
        url: str,
        title: str,
        success: bool,
        origin: str,
    ) -> None:
        """
        Trata navegações que efetivamente carregaram um documento.

        Para navegação originada pela própria página, tenta associar
        o último click/submit capturado e transformar a edge em CLICK
        ou FORM_SUBMIT.
        """

        url = url.strip()

        if not success:
            self._pending_existing_node_id = None
            self._clear_pending_interaction()
            return

        if not url:
            return

        # Não queremos nodes de páginas internas do Chromium.
        if url.startswith("about:"):
            return

        # Challenges transitórios (ex.: Cloudflare) não devem
        # poluir o grafo nem consumir o click pendente.
        if self._is_transient_challenge(
            url,
            title,
        ):
            return

        normalized_url = self._normalize_url(
            url
        )

        if not normalized_url:
            return

        # --------------------------------------------------------------
        # Página aberta por duplo clique no canvas
        # --------------------------------------------------------------

        if self._pending_existing_node_id is not None:
            node_id = self._pending_existing_node_id
            self._pending_existing_node_id = None
            self._clear_pending_interaction()

            card = self.canvas.get_node(
                node_id
            )

            if card is None:
                return

            self._update_node_from_browser(
                card,
                url,
                title,
            )

            self._register_url(
                node_id,
                url,
            )

            self._current_node_id = node_id
            self._select_node(node_id)

            self._schedule_preview(
                node_id,
                normalized_url,
            )
            return

        # --------------------------------------------------------------
        # Normal navigation
        # --------------------------------------------------------------

        source_id = self._current_node_id

        target_id = self._get_or_create_browser_node(
            url=url,
            title=title,
            source_id=source_id,
        )

        if target_id is None:
            return

        # --------------------------------------------------------------
        # Descobre a causa da navegação
        # --------------------------------------------------------------

        browser_event: dict | None = None

        if origin == "page":
            browser_event = (
                self._consume_pending_interaction(
                    source_id
                )
            )
        else:
            # Address bar / reload / history / canvas não devem
            # herdar um click anterior.
            self._clear_pending_interaction()

        # --------------------------------------------------------------
        # Edge
        # --------------------------------------------------------------

        non_edge_origins = {
            "history",
            "reload",
            "canvas",
            "programmatic",
        }

        if (
            source_id is not None
            and source_id != target_id
            and origin not in non_edge_origins
        ):
            self._add_browser_edge(
                source_id=source_id,
                target_id=target_id,
                url=url,
                origin=origin,
                browser_event=browser_event,
            )

        # --------------------------------------------------------------
        # Current node
        # --------------------------------------------------------------

        self._current_node_id = target_id
        self._select_node(target_id)

        self._schedule_preview(
            target_id,
            normalized_url,
        )

        self._schedule_investigation_refresh()

    def _on_spa_navigation(
        self,
        event: dict,
    ) -> None:
        """
        Trata pushState/replaceState sem reload da página.

        Se houver um click/submit imediatamente anterior, esse evento
        é usado como causa da transição. Caso contrário, a edge será
        marcada como pushState/replaceState.
        """

        if not isinstance(event, dict):
            return

        url = str(
            event.get(
                "url",
                "",
            )
            or ""
        ).strip()

        if not url:
            return

        normalized_url = self._normalize_url(
            url
        )

        if not normalized_url:
            return

        source_id = self._current_node_id

        title = str(
            event.get(
                "title",
                "",
            )
            or ""
        ).strip()

        target_id = self._get_or_create_browser_node(
            url=url,
            title=title,
            source_id=source_id,
        )

        if target_id is None:
            return

        # Preferimos a ação humana que causou o pushState.
        cause = self._consume_pending_interaction(
            source_id
        )

        if cause is None:
            cause = dict(event)

        if (
            source_id is not None
            and source_id != target_id
        ):
            self._add_browser_edge(
                source_id=source_id,
                target_id=target_id,
                url=url,
                origin="page",
                browser_event=cause,
            )

        self._current_node_id = target_id
        self._select_node(target_id)

        self._schedule_preview(
            target_id,
            normalized_url,
        )

        self._schedule_investigation_refresh()

    # ------------------------------------------------------------------
    # API requests
    # ------------------------------------------------------------------

    @classmethod
    def _api_key(
        cls,
        method: str,
        url: str,
    ) -> str:
        normalized_url = cls._normalize_url(
            url
        )

        if not normalized_url:
            return ""

        return (
            method.strip().upper()
            + " "
            + normalized_url
        )

    @classmethod
    def _api_node_title(
        cls,
        method: str,
        url: str,
        source_url: str = "",
    ) -> str:
        """
        Título compacto para nodes API.

        Para chamadas cross-origin também mostra o hostname,
        evitando ambiguidades entre APIs diferentes com o mesmo path.
        """

        method = (
            method.strip().upper()
            or "GET"
        )

        try:
            target_parts = urlsplit(
                url
            )
        except ValueError:
            return cls._compact_label(
                f"{method} {url}"
            )

        display_path = cls._display_path(
            url
        )

        target_host = (
            target_parts.netloc.lower()
        )

        source_host = ""

        if source_url:
            try:
                source_host = (
                    urlsplit(
                        source_url
                    )
                    .netloc
                    .lower()
                )
            except ValueError:
                source_host = ""

        if (
            target_host
            and source_host
            and target_host != source_host
        ):
            target = (
                target_host
                + display_path
            )
        else:
            target = display_path

        return cls._compact_label(
            f"{method} {target}"
        )

    @staticmethod
    def _api_duration_label(
        duration_ms,
    ) -> str:
        try:
            duration = float(
                duration_ms
            )
        except (
            TypeError,
            ValueError,
        ):
            return ""

        if duration < 0:
            return ""

        if duration >= 1000:
            return (
                f"{duration / 1000:.2f}s"
            )

        if duration >= 100:
            return (
                f"{duration:.0f}ms"
            )

        return (
            f"{duration:.1f}ms"
        )

    def _resolve_api_source_node(
        self,
        event: dict,
    ) -> str | None:
        """
        Resolve a página que originou o fetch/XHR.

        Usamos source_url primeiro porque uma resposta pode chegar
        depois de o usuário já ter começado outra navegação.
        """

        source_url = str(
            event.get(
                "source_url",
                "",
            )
            or ""
        ).strip()

        if source_url:
            normalized = self._normalize_url(
                source_url
            )

            if normalized:
                node_id = self._url_index.get(
                    normalized
                )

                if node_id is not None:
                    return node_id

        # Fallback para a página atualmente ativa.
        node_id = self._current_node_id

        if node_id is None:
            return None

        card = self.canvas.get_node(
            node_id
        )

        if card is None:
            return None

        if card.node.kind == NodeKind.API:
            return None

        return node_id

    def _register_api_node(
        self,
        node: PageNode,
    ) -> None:
        key = self._api_key(
            node.method,
            node.url,
        )

        if not key:
            return

        self._api_index[
            key
        ] = node.id

    def _get_or_create_api_node(
        self,
        event: dict,
        source_id: str | None,
    ) -> str | None:
        url = str(
            event.get(
                "url",
                "",
            )
            or event.get(
                "request_url",
                "",
            )
            or ""
        ).strip()

        if not url:
            return None

        try:
            parts = urlsplit(
                url
            )
        except ValueError:
            return None

        # Não poluímos o grafo com data:, blob:, chrome:, etc.
        if (
            parts.scheme.lower()
            not in {
                "http",
                "https",
            }
        ):
            return None

        method = str(
            event.get(
                "method",
                "GET",
            )
            or "GET"
        ).upper()

        key = self._api_key(
            method,
            url,
        )

        if not key:
            return None

        source_url = str(
            event.get(
                "source_url",
                "",
            )
            or ""
        )

        title = self._api_node_title(
            method=method,
            url=url,
            source_url=source_url,
        )

        raw_status = event.get(
            "status"
        )

        try:
            status = (
                int(raw_status)
                if raw_status is not None
                else None
            )
        except (
            TypeError,
            ValueError,
        ):
            status = None

        if status is not None and status <= 0:
            status = None

        content_type = str(
            event.get(
                "content_type",
                "",
            )
            or ""
        ).strip()

        error = str(
            event.get(
                "error",
                "",
            )
            or ""
        ).strip()

        transport = str(
            event.get(
                "kind",
                "request",
            )
            or "request"
        ).lower()

        existing_id = (
            self._api_index.get(
                key
            )
        )

        # --------------------------------------------------------------
        # Existing API node
        # --------------------------------------------------------------

        if existing_id is not None:
            card = self.canvas.get_node(
                existing_id
            )

            if card is not None:
                node = card.node

                node.title = title
                node.url = url
                node.method = method
                node.status = status

                request_count = int(
                    node.metadata.get(
                        "request_count",
                        0,
                    )
                    or 0
                ) + 1

                transports = list(
                    node.metadata.get(
                        "transports",
                        [],
                    )
                    or []
                )

                if transport not in transports:
                    transports.append(
                        transport
                    )

                node.metadata.update(
                    {
                        "request_count":
                            request_count,

                        "transports":
                            transports,

                        "last_transport":
                            transport,

                        "last_status":
                            status,

                        "last_content_type":
                            content_type,

                        "last_duration_ms":
                            event.get(
                                "duration_ms"
                            ),

                        "last_ok":
                            bool(
                                event.get(
                                    "ok",
                                    False,
                                )
                            ),

                        "last_error":
                            error,

                        "last_source_url":
                            source_url,

                        "last_request_url":
                            str(
                                event.get(
                                    "request_url",
                                    "",
                                )
                                or ""
                            ),
                    }
                )

                card.update()

                return existing_id

            # Referência antiga.
            self._api_index.pop(
                key,
                None,
            )

        # --------------------------------------------------------------
        # New API node
        # --------------------------------------------------------------

        x, y = self._suggest_position(
            source_id
        )

        node = PageNode(
            title=title,
            url=url,
            kind=NodeKind.API,
            method=method,
            status=status,
            x=x,
            y=y,
            metadata={
                "request_count": 1,
                "transports": [
                    transport
                ],
                "last_transport":
                    transport,
                "last_status":
                    status,
                "last_content_type":
                    content_type,
                "last_duration_ms":
                    event.get(
                        "duration_ms"
                    ),
                "last_ok":
                    bool(
                        event.get(
                            "ok",
                            False,
                        )
                    ),
                "last_error":
                    error,
                "last_source_url":
                    source_url,
                "last_request_url":
                    str(
                        event.get(
                            "request_url",
                            "",
                        )
                        or ""
                    ),
            },
        )

        self.canvas.add_node(
            node
        )

        self._register_api_node(
            node
        )

        return node.id

    def _on_api_request(
        self,
        event: dict,
    ) -> None:
        """
        Converte fetch/XMLHttpRequest em node NodeKind.API
        e cria uma edge entre a página e o endpoint.
        """

        if not isinstance(
            event,
            dict,
        ):
            return

        kind = str(
            event.get(
                "kind",
                "",
            )
            or ""
        ).lower()

        if kind not in {
            "fetch",
            "xhr",
        }:
            return

        source_id = (
            self._resolve_api_source_node(
                event
            )
        )

        if source_id is None:
            return

        target_id = (
            self._get_or_create_api_node(
                event=event,
                source_id=source_id,
            )
        )

        if target_id is None:
            return

        self._add_or_update_api_edge(
            source_id=source_id,
            target_id=target_id,
            event=event,
        )

        self._schedule_investigation_refresh()

    def _add_or_update_api_edge(
        self,
        source_id: str,
        target_id: str,
        event: dict,
    ) -> None:
        kind = str(
            event.get(
                "kind",
                "request",
            )
            or "request"
        ).lower()

        if kind == "fetch":
            transition_type = (
                TransitionType.FETCH
            )
            transport_label = "fetch"

        elif kind == "xhr":
            transition_type = (
                TransitionType.XHR
            )
            transport_label = "XHR"

        else:
            transition_type = (
                TransitionType.REQUEST
            )
            transport_label = "request"

        method = str(
            event.get(
                "method",
                "GET",
            )
            or "GET"
        ).upper()

        url = str(
            event.get(
                "url",
                "",
            )
            or event.get(
                "request_url",
                "",
            )
            or ""
        )

        path = self._display_path(
            url
        )

        status = event.get(
            "status"
        )

        duration_label = (
            self._api_duration_label(
                event.get(
                    "duration_ms"
                )
            )
        )

        label_parts = [
            transport_label,
            method,
            path,
        ]

        if status not in {
            None,
            0,
            "0",
            "",
        }:
            label_parts.append(
                str(status)
            )
        elif event.get("error"):
            label_parts.append(
                "ERR"
            )

        if duration_label:
            label_parts.append(
                duration_label
            )

        label = self._compact_label(
            " · ".join(
                label_parts
            )
        )

        # --------------------------------------------------------------
        # Existing edge
        # --------------------------------------------------------------

        for edge in self.canvas.edges.values():
            transition = edge.transition

            if (
                transition.source_id
                == source_id
                and transition.target_id
                == target_id
                and transition.type
                == transition_type
            ):
                count = int(
                    transition.metadata.get(
                        "request_count",
                        1,
                    )
                    or 1
                ) + 1

                transition.metadata.update(
                    {
                        "request_count":
                            count,

                        "last_event":
                            dict(event),
                    }
                )

                edge.set_label(
                    label
                )

                return

        # --------------------------------------------------------------
        # New edge
        # --------------------------------------------------------------

        transition = Transition(
            source_id=source_id,
            target_id=target_id,
            type=transition_type,
            label=label,
            metadata={
                "request_count": 1,
                "last_event":
                    dict(event),
            },
        )

        self.canvas.add_edge(
            transition
        )

    # ------------------------------------------------------------------
    # Node update
    # ------------------------------------------------------------------

    def _update_node_from_browser(
        self,
        card: PageCard,
        url: str,
        title: str,
    ) -> None:
        card.node.url = url

        if title:
            card.node.title = title

        card.update()

    # ------------------------------------------------------------------
    # URL index
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_url(
        url: str,
    ) -> str:
        """
        Remove fragmentos e pequenas diferenças irrelevantes.

        Exemplos:

            https://site.com/page#top
            https://site.com/page#bottom

        viram o mesmo node.

        Query string continua sendo considerada porque pode
        representar recursos/páginas diferentes.
        """

        try:
            parts = urlsplit(
                url.strip()
            )
        except ValueError:
            return ""

        if not parts.scheme:
            return ""

        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()
        path = parts.path or "/"

        if path != "/":
            path = path.rstrip("/")

        return urlunsplit(
            (
                scheme,
                netloc,
                path,
                parts.query,
                "",
            )
        )

    def _register_url(
        self,
        node_id: str,
        url: str,
    ) -> None:
        normalized = self._normalize_url(
            url
        )

        if not normalized:
            return

        # Remove URLs antigas associadas ao mesmo node.
        # Isso é útil quando uma página aberta pelo canvas
        # terminou em uma URL diferente.
        for key, value in list(
            self._url_index.items()
        ):
            if (
                value == node_id
                and key != normalized
            ):
                del self._url_index[key]

        self._url_index[
            normalized
        ] = node_id

    def _unregister_node(
        self,
        node_id: str,
    ) -> None:
        for key, value in list(
            self._url_index.items()
        ):
            if value == node_id:
                del self._url_index[key]

        for key, value in list(
            self._api_index.items()
        ):
            if value == node_id:
                del self._api_index[key]

        if self._current_node_id == node_id:
            self._current_node_id = None
            self._clear_pending_interaction()

        if self._pending_existing_node_id == node_id:
            self._pending_existing_node_id = None

    # ------------------------------------------------------------------
    # Automatic positioning
    # ------------------------------------------------------------------

    def _suggest_position(
        self,
        source_id: str | None,
    ) -> tuple[float, float]:
        """
        Distribui novos nodes nas 8 direções ao redor do source.

        Isso aproveita diretamente o sistema de 8 anchors
        implementado nas edges.
        """

        if source_id is None:
            center = self.canvas.mapToScene(
                self.canvas
                .viewport()
                .rect()
                .center()
            )

            return (
                center.x()
                - PageCard.WIDTH / 2,
                center.y()
                - PageCard.HEIGHT / 2,
            )

        source = self.canvas.get_node(
            source_id
        )

        if source is None:
            return (
                0.0,
                0.0,
            )

        outgoing_count = 0

        for edge in self.canvas.edges.values():
            if (
                edge.transition.source_id
                == source_id
            ):
                outgoing_count += 1

        # E, SE, NE, S, N, SW, NW, W
        offsets = [
            (520, 0),
            (480, 340),
            (480, -340),
            (0, 390),
            (0, -390),
            (-480, 340),
            (-480, -340),
            (-520, 0),
        ]

        index = (
            outgoing_count
            % len(offsets)
        )

        ring = (
            outgoing_count
            // len(offsets)
        ) + 1

        dx, dy = offsets[index]

        return (
            source.node.x
            + dx * ring,
            source.node.y
            + dy * ring,
        )

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def _add_browser_edge(
        self,
        source_id: str,
        target_id: str,
        url: str,
        origin: str,
        browser_event: dict | None = None,
    ) -> None:
        """
        Cria uma edge a partir da causa observada no browser.

        Exemplos:
            click "Sign in"
            POST /login · "Sign in"
            pushState /dashboard
            navigate /profile
        """

        path = self._display_path(
            url
        )

        # --------------------------------------------------------------
        # Default
        # --------------------------------------------------------------

        transition_type = (
            TransitionType.NAVIGATION
        )

        if origin == "address":
            label = f"open {path}"
        else:
            label = f"navigate {path}"

        # --------------------------------------------------------------
        # Browser event
        # --------------------------------------------------------------

        if browser_event:
            kind = str(
                browser_event.get(
                    "kind",
                    "",
                )
                or ""
            )

            # Click
            if kind == "click":
                transition_type = (
                    TransitionType.CLICK
                )

                element_label = self._compact_label(
                    str(
                        browser_event.get(
                            "label",
                            "",
                        )
                        or ""
                    )
                )

                if element_label:
                    label = (
                        f'click "{element_label}"'
                    )
                else:
                    label = f"click {path}"

            # Submit
            elif kind == "submit":
                transition_type = (
                    TransitionType.FORM_SUBMIT
                )

                method = str(
                    browser_event.get(
                        "method",
                        "GET",
                    )
                    or "GET"
                ).upper()

                submit_label = self._compact_label(
                    str(
                        browser_event.get(
                            "label",
                            "",
                        )
                        or ""
                    )
                )

                if submit_label:
                    label = (
                        f'{method} {path} '
                        f'· "{submit_label}"'
                    )
                else:
                    label = (
                        f"{method} {path}"
                    )

            # History.pushState
            elif kind == "history_push":
                # Compatível mesmo antes de models.py receber
                # HISTORY_PUSH.
                transition_type = getattr(
                    TransitionType,
                    "HISTORY_PUSH",
                    TransitionType.NAVIGATION,
                )
                label = (
                    f"pushState {path}"
                )

            # History.replaceState
            elif kind == "history_replace":
                # Compatível mesmo antes de models.py receber
                # HISTORY_REPLACE.
                transition_type = getattr(
                    TransitionType,
                    "HISTORY_REPLACE",
                    TransitionType.NAVIGATION,
                )
                label = (
                    f"replaceState {path}"
                )

        # --------------------------------------------------------------
        # Deduplication
        # --------------------------------------------------------------

        for edge in self.canvas.edges.values():
            transition = edge.transition

            if (
                transition.source_id
                == source_id
                and transition.target_id
                == target_id
                and transition.type
                == transition_type
                and transition.label
                == label
            ):
                return

        # --------------------------------------------------------------
        # Create
        # --------------------------------------------------------------

        transition = Transition(
            source_id=source_id,
            target_id=target_id,
            type=transition_type,
            label=label,
            metadata={
                "origin": origin,
                "browser_event": (
                    browser_event
                    or {}
                ),
            },
        )

        self.canvas.add_edge(
            transition
        )

    # ------------------------------------------------------------------
    # Screenshot / preview
    # ------------------------------------------------------------------

    def _schedule_preview(
        self,
        node_id: str,
        expected_url: str,
    ) -> None:
        """
        Espera um pouco depois da navegação para permitir
        que a interface da página termine de renderizar.
        """

        QTimer.singleShot(
            350,
            lambda: self._capture_preview(
                node_id,
                expected_url,
            ),
        )

    def _capture_preview(
        self,
        node_id: str,
        expected_url: str,
    ) -> None:
        current_url = self._normalize_url(
            self.browser_host.current_url()
        )

        # O usuário pode ter navegado para outra página
        # antes do timer executar.
        if current_url != expected_url:
            return

        card = self.canvas.get_node(
            node_id
        )

        if card is None:
            return

        preview_path = (
            Path(self._preview_dir.name)
            / f"{node_id}.png"
        )

        success = (
            self.browser_host
            .capture_preview(
                preview_path
            )
        )

        if not success:
            return

        card.set_preview_path(
            str(preview_path)
        )

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _select_node(
        self,
        node_id: str,
    ) -> None:
        self.canvas.scene().clearSelection()

        card = self.canvas.get_node(
            node_id
        )

        if card is not None:
            card.setSelected(True)

    # ------------------------------------------------------------------
    # Manual nodes
    # ------------------------------------------------------------------

    def _add_manual_node(self) -> None:
        center = self.canvas.mapToScene(
            self.canvas
            .viewport()
            .rect()
            .center()
        )

        counter = self._manual_node_counter

        node = PageNode(
            title=f"Página {counter}",
            url="",
            method="GET",
            status=None,
            x=center.x() - 160,
            y=center.y() - 125,
        )

        self._manual_node_counter += 1

        card = self.canvas.add_node(
            node
        )

        self.canvas.scene().clearSelection()
        card.setSelected(True)

    def _add_note(self) -> None:
        center = self.canvas.mapToScene(
            self.canvas
            .viewport()
            .rect()
            .center()
        )

        counter = self._manual_node_counter
        node = PageNode(
            title=f"Nota {counter}",
            url="",
            kind=NodeKind.NOTE,
            method="",
            status=None,
            x=center.x() - 155,
            y=center.y() - 95,
            metadata={
                "note_text": "",
                "tags": [],
                "color": "#D9A441",
            },
        )
        self._manual_node_counter += 1

        card = self.canvas.add_node(
            node
        )
        self.canvas.scene().clearSelection()
        card.setSelected(True)
        self._edit_note(
            node.id
        )

    def _selected_raw_cards(
        self,
    ) -> list[PageCard]:
        result: list[PageCard] = []

        for item in (
            self.canvas
            .scene()
            .selectedItems()
        ):
            if not isinstance(
                item,
                PageCard,
            ):
                continue

            if (
                item.node.id
                not in self.canvas.nodes
            ):
                continue

            result.append(
                item
            )

        return result

    def _add_note_for_selection(
        self,
    ) -> None:
        targets = self._selected_raw_cards()

        if not targets:
            self.statusBar().showMessage(
                "Selecione um ou mais cards antes de criar a nota.",
                3500,
            )
            return

        average_x = sum(
            card.scenePos().x()
            for card in targets
        ) / len(targets)

        average_y = sum(
            card.scenePos().y()
            for card in targets
        ) / len(targets)

        counter = self._manual_node_counter

        node = PageNode(
            title=f"Nota {counter}",
            url="",
            kind=NodeKind.NOTE,
            method="",
            status=None,
            x=average_x - 155,
            y=average_y - 300,
            metadata={
                "note_text": "",
                "tags": [],
                "color": "#D9A441",
            },
        )

        self._manual_node_counter += 1

        card = self.canvas.add_node(
            node
        )

        if not NoteDialog.edit_node(
            self,
            node,
        ):
            self.canvas.remove_node(
                node.id
            )
            return

        card.update()

        marker = getattr(
            card,
            "_metadata_marker",
            None,
        )
        if marker is not None:
            marker.refresh()

        target_ids = [
            target.node.id
            for target in targets
            if target.node.id != node.id
        ]

        for target_id in target_ids:
            self._create_manual_note_connection(
                node.id,
                target_id,
            )

        self.canvas.scene().clearSelection()
        card.setSelected(
            True
        )

        self.statusBar().showMessage(
            f"Nota criada e ligada a {len(target_ids)} card(s).",
            4000,
        )

    def _edit_selected_metadata(
        self,
    ) -> None:
        cards = self._selected_raw_cards()

        if not cards:
            self.statusBar().showMessage(
                "Selecione um ou mais cards para editar tags/status.",
                3500,
            )
            return

        nodes = [
            card.node
            for card in cards
        ]

        if not NodeMetadataDialog.edit_nodes(
            self,
            nodes,
        ):
            return

        for card in cards:
            marker = getattr(
                card,
                "_metadata_marker",
                None,
            )

            if marker is not None:
                marker.refresh()

            card.update()

        self._schedule_investigation_refresh()

        self.statusBar().showMessage(
            f"Metadados atualizados em {len(cards)} card(s).",
            3500,
        )

    def _edit_note(
        self,
        node_id: str,
    ) -> None:
        card = self.canvas.get_node(
            node_id
        )
        if card is None or card.node.kind != NodeKind.NOTE:
            return

        if not NoteDialog.edit_node(
            self,
            card.node,
        ):
            return

        card.update()

        note_color = str(
            (card.node.metadata or {}).get(
                "color",
                "#D9A441",
            )
            or "#D9A441"
        )

        for edge in self.canvas.edges.values():
            transition = edge.transition

            if (
                transition.source_id == node_id
                and transition.metadata.get(
                    "manual_note"
                )
            ):
                transition.metadata[
                    "note_color"
                ] = note_color

                edge.refresh_style()

        self._schedule_investigation_refresh()
        self._on_canvas_selection_changed()
        self.statusBar().showMessage(
            "Nota atualizada.",
            2500,
        )

    def _create_manual_note_connection(
        self,
        source_id: str,
        target_id: str,
    ) -> None:
        source = self.canvas.get_node(
            source_id
        )
        target = self.canvas.get_node(
            target_id
        )

        if (
            source is None
            or target is None
            or source_id == target_id
        ):
            return

        source_is_note = (
            source.node.kind
            == NodeKind.NOTE
        )

        for edge in self.canvas.edges.values():
            transition = edge.transition

            if (
                transition.source_id == source_id
                and transition.target_id == target_id
                and transition.type == TransitionType.MANUAL
            ):
                self.statusBar().showMessage(
                    "Essa conexão manual já existe.",
                    3000,
                )
                return

        metadata = {
            (
                "manual_note"
                if source_is_note
                else "manual_edge"
            ): True,
        }

        if source_is_note:
            metadata[
                "note_color"
            ] = str(
                (source.node.metadata or {}).get(
                    "color",
                    "#D9A441",
                )
                or "#D9A441"
            )

        transition = Transition(
            source_id=source_id,
            target_id=target_id,
            type=TransitionType.MANUAL,
            label=(
                "note"
                if source_is_note
                else "manual"
            ),
            metadata=metadata,
        )

        edge = self.canvas.add_edge(
            transition
        )

        self.canvas.scene().clearSelection()
        edge.setSelected(
            True
        )

        self._schedule_investigation_refresh()

        prefix = (
            "Nota"
            if source_is_note
            else "Conexão manual"
        )

        self.statusBar().showMessage(
            f'{prefix}: "{source.node.title}" -> "{target.node.title}"',
            4000,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete_selected(self) -> None:
        selected = list(
            self.canvas
            .scene()
            .selectedItems()
        )

        if not selected:
            return

        # Primeiro edges.
        for item in selected:
            if isinstance(
                item,
                EdgeItem,
            ):
                self.canvas.remove_edge(
                    item.transition.id
                )

        # Depois nodes.
        #
        # remove_node() também remove as edges associadas.
        for item in selected:
            if isinstance(
                item,
                PageCard,
            ):
                node_id = item.node.id

                self._unregister_node(
                    node_id
                )

                self.canvas.remove_node(
                    node_id
                )

    # ------------------------------------------------------------------
    # HTML export
    # ------------------------------------------------------------------

    def _html_export_snapshot(
        self,
    ) -> tuple[
        list[PageNode],
        list[Transition],
    ]:
        """
        Captura exatamente a projeção visual atual do canvas.

        Em Raw Graph exporta os cards/edges reais nas posições atuais.
        Em Focus/Filters/Investigation exporta apenas os itens visíveis,
        incluindo GroupCards e as edges virtuais da projeção.
        """

        nodes: list[PageNode] = []

        for card in self.canvas.nodes.values():
            if not card.isVisible():
                continue

            node = PageNode.from_dict(
                card.node.to_dict()
            )

            position = card.scenePos()
            node.x = float(
                position.x()
            )
            node.y = float(
                position.y()
            )

            nodes.append(
                node
            )

        for card in self.canvas.view_groups.values():
            if not card.isVisible():
                continue

            view_node = card.view_node
            metadata = dict(
                view_node.metadata
                or {}
            )

            metadata.update(
                {
                    "export_kind":
                        "group",

                    "group_kind":
                        view_node.group_kind,

                    "raw_node_ids":
                        list(
                            view_node.raw_node_ids
                        ),
                }
            )

            position = card.scenePos()

            nodes.append(
                PageNode(
                    id=view_node.id,
                    title=view_node.title,
                    url="",
                    kind=NodeKind.NOTE,
                    method="GROUP",
                    status=None,
                    x=float(
                        position.x()
                    ),
                    y=float(
                        position.y()
                    ),
                    metadata=metadata,
                )
            )

        if self.canvas.view_edges:
            transitions = [
                edge.transition
                for edge
                in self.canvas.view_edges.values()
                if edge.isVisible()
            ]
        else:
            transitions = [
                edge.transition
                for edge
                in self.canvas.edges.values()
                if edge.isVisible()
            ]

        return (
            nodes,
            transitions,
        )

    def _export_html(self) -> None:
        if not self.canvas.nodes:
            QMessageBox.information(
                self,
                "Exportar HTML",
                "O canvas está vazio.",
            )
            return

        if self._project_dir is not None:
            initial_path = self._project_dir.parent / f"{self._project_dir.stem}.html"
            title = self._project_dir.stem
        else:
            initial_path = Path.cwd() / "spiderview-investigation.html"
            title = "SpiderView Investigation"

        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar investigação como HTML",
            str(initial_path),
            "HTML (*.html)",
        )
        if not selected:
            return

        output_path = Path(selected)
        if output_path.suffix.lower() not in {".html", ".htm"}:
            output_path = output_path.with_suffix(".html")

        (
            nodes,
            transitions,
        ) = self._html_export_snapshot()

        try:
            HtmlExporter().export(
                output_path,
                nodes,
                transitions,
                title=title,
                redact_sensitive=True,
            )
        except HtmlExportError as exc:
            QMessageBox.critical(
                self,
                "Erro ao exportar HTML",
                str(exc),
            )
            return

        self.statusBar().showMessage(
            "Visualização atual exportada: "
            f"{output_path.name} · "
            f"{len(nodes)} nodes · "
            f"{len(transitions)} edges",
            5000,
        )

    # ------------------------------------------------------------------
    # Project persistence
    # ------------------------------------------------------------------

    def _open_project(self) -> None:
        if self.canvas.nodes:
            answer = QMessageBox.question(
                self,
                "Abrir projeto",
                "Abrir outro projeto substituirá o canvas atual. Continuar?",
            )

            if (
                answer
                != QMessageBox.StandardButton.Yes
            ):
                return

        initial_dir = (
            str(self._project_dir.parent)
            if self._project_dir is not None
            else str(Path.cwd())
        )

        selected = QFileDialog.getExistingDirectory(
            self,
            "Abrir projeto SpiderView",
            initial_dir,
        )

        if not selected:
            return

        project_dir = Path(
            selected
        )

        try:
            nodes, transitions = (
                ProjectStore.load(
                    project_dir
                )
            )
        except ProjectStoreError as exc:
            QMessageBox.critical(
                self,
                "Erro ao abrir projeto",
                str(exc),
            )
            return

        self.canvas.clear_graph()
        self._reset_mapping_state()

        try:
            for node in nodes:
                self.canvas.add_node(
                    node
                )

                if not node.url:
                    continue

                if node.kind == NodeKind.API:
                    self._register_api_node(
                        node
                    )
                else:
                    self._register_url(
                        node.id,
                        node.url,
                    )

            for transition in transitions:
                self.canvas.add_edge(
                    transition
                )

        except Exception as exc:
            self.canvas.clear_graph()
            self._reset_mapping_state()

            QMessageBox.critical(
                self,
                "Erro ao montar projeto",
                str(exc),
            )
            return

        self._project_dir = project_dir
        self._manual_node_counter = (
            len(nodes) + 1
        )

        self._update_window_title()

        self.statusBar().showMessage(
            f"Projeto aberto: {project_dir.name}",
            4000,
        )

        QTimer.singleShot(
            0,
            self.canvas.fit_graph,
        )

    def _save_project(self) -> None:
        if self._project_dir is None:
            self._save_project_as()
            return

        self._write_project(
            self._project_dir
        )

    def _save_project_as(self) -> None:
        if self._project_dir is not None:
            initial_path = str(
                self._project_dir
            )
        else:
            initial_path = str(
                Path.cwd()
                / "projeto.spiderview"
            )

        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar projeto SpiderView",
            initial_path,
            "SpiderView Project (*.spiderview)",
        )

        if not selected:
            return

        project_dir = Path(
            selected
        )

        if (
            project_dir.suffix.lower()
            != ".spiderview"
        ):
            project_dir = project_dir.with_name(
                project_dir.name
                + ".spiderview"
            )

        if (
            project_dir.exists()
            and project_dir.is_file()
        ):
            QMessageBox.critical(
                self,
                "Erro ao salvar projeto",
                "O caminho escolhido já existe como arquivo.",
            )
            return

        self._write_project(
            project_dir
        )

    def _write_project(
        self,
        project_dir: Path,
    ) -> None:
        nodes = [
            card.node
            for card
            in self.canvas.nodes.values()
        ]

        transitions = [
            edge.transition
            for edge
            in self.canvas.edges.values()
        ]

        try:
            ProjectStore.save(
                project_dir=project_dir,
                nodes=nodes,
                transitions=transitions,
            )
        except ProjectStoreError as exc:
            QMessageBox.critical(
                self,
                "Erro ao salvar projeto",
                str(exc),
            )
            return

        self._project_dir = project_dir
        self._update_window_title()

        self.statusBar().showMessage(
            f"Projeto salvo: {project_dir.name}",
            4000,
        )

    def _update_window_title(self) -> None:
        if self._project_dir is None:
            self.setWindowTitle(
                "OZAP SpiderView"
            )
            return

        self.setWindowTitle(
            "OZAP SpiderView — "
            f"{self._project_dir.name}"
        )

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def _clear_graph(self) -> None:
        if not self.canvas.nodes:
            return

        answer = QMessageBox.question(
            self,
            "Limpar canvas",
            "Remover todos os cards e conexões?",
        )

        if (
            answer
            != QMessageBox.StandardButton.Yes
        ):
            return

        self.canvas.clear_graph()
        self._reset_mapping_state()

    def _reset_mapping_state(self) -> None:
        self._graph_layout_result = None

        self._investigation_mode = False
        self._expanded_view_groups.clear()
        self._view_graph = None
        self._investigation_refresh_pending = False
        self._focus_root_ids.clear()

        if hasattr(
            self,
            "analysis_toolbar",
        ):
            self.analysis_toolbar.reset_filters(
                emit=False
            )

        self._set_investigation_action_checked(
            False
        )

        self._url_index.clear()
        self._api_index.clear()
        self._current_node_id = None
        self._pending_existing_node_id = None
        self._clear_pending_interaction()

        if hasattr(
            self,
            "node_details",
        ):
            self.node_details.clear()

    # ------------------------------------------------------------------
    # Demo
    # ------------------------------------------------------------------

    def _load_demo_graph(self) -> None:
        self.canvas.clear_graph()
        self._reset_mapping_state()

        home = PageNode(
            title="Home",
            url="https://example.com",
            method="GET",
            status=200,
            x=-900,
            y=0,
        )

        login = PageNode(
            title="Login",
            url="https://example.com/login",
            method="GET",
            status=200,
            x=-400,
            y=-300,
        )

        dashboard = PageNode(
            title="Dashboard",
            url="https://example.com/dashboard",
            method="GET",
            status=200,
            x=100,
            y=0,
        )

        profile = PageNode(
            title="Profile",
            url="https://example.com/profile",
            method="GET",
            status=200,
            x=650,
            y=-300,
        )

        admin = PageNode(
            title="Admin",
            url="https://example.com/admin",
            method="GET",
            status=200,
            x=650,
            y=300,
        )

        users = PageNode(
            title="Users",
            url="https://example.com/admin/users",
            method="GET",
            status=200,
            x=1200,
            y=300,
        )

        nodes = (
            home,
            login,
            dashboard,
            profile,
            admin,
            users,
        )

        for node in nodes:
            self.canvas.add_node(node)

            self._register_url(
                node.id,
                node.url,
            )

        transitions = [
            Transition(
                source_id=home.id,
                target_id=login.id,
                type=TransitionType.CLICK,
                label='click "Login"',
            ),
            Transition(
                source_id=login.id,
                target_id=dashboard.id,
                type=TransitionType.FORM_SUBMIT,
                label="POST /login",
            ),
            Transition(
                source_id=dashboard.id,
                target_id=profile.id,
                type=TransitionType.CLICK,
                label='click "Profile"',
            ),
            Transition(
                source_id=dashboard.id,
                target_id=admin.id,
                type=TransitionType.CLICK,
                label='click "Admin"',
            ),
            Transition(
                source_id=admin.id,
                target_id=users.id,
                type=TransitionType.NAVIGATION,
                label="open Users",
            ),
        ]

        for transition in transitions:
            self.canvas.add_edge(
                transition
            )

        QTimer.singleShot(
            0,
            self.canvas.fit_graph,
        )

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #14171C;
            }

            QToolBar {
                background: #1B1F26;
                border: none;
                border-bottom: 1px solid #2C323B;

                spacing: 6px;

                padding-left: 8px;
                padding-right: 8px;
                padding-top: 6px;
                padding-bottom: 6px;
            }

            QToolBar::separator {
                background: #343A45;

                width: 1px;

                margin-left: 8px;
                margin-right: 8px;
                margin-top: 5px;
                margin-bottom: 5px;
            }

            QToolButton {
                background: transparent;

                color: #D8DEE9;

                border: 1px solid transparent;
                border-radius: 6px;

                padding-left: 10px;
                padding-right: 10px;
                padding-top: 6px;
                padding-bottom: 6px;

                font-size: 12px;
            }

            QToolButton:hover {
                background: #292F38;
                border: 1px solid #3A424E;
            }

            QToolButton:pressed {
                background: #343C48;
            }

            QStatusBar {
                background: #1B1F26;

                color: #8E99A8;

                border-top: 1px solid #2C323B;

                font-size: 11px;
            }

            QStatusBar::item {
                border: none;
            }

            QDockWidget {
                color: #D8DEE9;
                font-weight: 600;
            }

            QDockWidget::title {
                background: #1B1F26;

                border-bottom: 1px solid #2C323B;

                padding: 7px;
            }

            QLineEdit {
                background: #111419;

                color: #D8DEE9;

                border: 1px solid #343B46;
                border-radius: 6px;

                padding: 6px;
            }

            QLineEdit:focus {
                border: 1px solid #4C9AFF;
            }
            """
        )

        self.statusBar().setSizeGripEnabled(
            False
        )

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(
        self,
        event,
    ) -> None:
        self._preview_dir.cleanup()

        super().closeEvent(
            event
        )
