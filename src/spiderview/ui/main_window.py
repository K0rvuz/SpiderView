from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from ..browser.browser_host import BrowserHost
from ..models import (
    PageNode,
    Transition,
    TransitionType,
)
from .canvas import SpiderCanvas
from .edge_item import EdgeItem
from .page_card import PageCard


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "OZAP SpiderView"
        )


        self.canvas = SpiderCanvas()

        self.setCentralWidget(
            self.canvas
        )

        self.browser_host = BrowserHost()

        self.browser_dock = QDockWidget(
            "Browser",
            self,
        )

        self.browser_dock.setWidget(
            self.browser_host
        )

        self.browser_dock.setMinimumWidth(
            500
        )

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

        self._manual_node_counter = 1

        self._create_toolbar()
        self._connect_signals()
        self._configure_status_bar()

        self._load_demo_graph()

        QTimer.singleShot(
            0,
            self.canvas.fit_graph,
        )
        self._apply_theme()

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _create_toolbar(self) -> None:
        toolbar = QToolBar(
            "SpiderView",
            self,
        )

        toolbar.setMovable(False)

        self.addToolBar(toolbar)

        # --------------------------------------------------------------
        # Novo card
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

        toolbar.addAction(
            add_node_action
        )

        # --------------------------------------------------------------
        # Demo
        # --------------------------------------------------------------

        demo_action = QAction(
            "Carregar demo",
            self,
        )

        demo_action.triggered.connect(
            self._load_demo_graph
        )

        toolbar.addAction(
            demo_action
        )

        toolbar.addSeparator()

        # --------------------------------------------------------------
        # Fit
        # --------------------------------------------------------------

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

        toolbar.addAction(
            fit_action
        )

        # --------------------------------------------------------------
        # Delete
        # --------------------------------------------------------------

        delete_action = QAction(
            "Excluir",
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

        self.addAction(
            delete_action
        )

        toolbar.addAction(
            delete_action
        )

        toolbar.addSeparator()

        # --------------------------------------------------------------
        # Clear
        # --------------------------------------------------------------

        clear_action = QAction(
            "Limpar",
            self,
        )

        clear_action.triggered.connect(
            self._clear_graph
        )

        toolbar.addAction(
            clear_action
        )

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.canvas.nodeDoubleClicked.connect(
            self._open_node
        )

        self.browser_host.closeRequested.connect(
            self.browser_dock.hide
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _configure_status_bar(self) -> None:
        self.statusBar().showMessage(
    "Scroll  Zoom     •     MMB  Pan     •     "
    "Drag  Move card     •     Double Click  Open page"
)

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------

    def _open_node(
        self,
        node_id: str,
    ) -> None:
        card = self.canvas.get_node(
            node_id
        )

        if card is None:
            return

        url = card.node.url

        if not url:
            return

        self.browser_host.open_url(
            url
        )

        self.browser_dock.show()
        self.browser_dock.raise_()

    # ------------------------------------------------------------------
    # Manual nodes
    # ------------------------------------------------------------------

    def _add_manual_node(self) -> None:
        center = self.canvas.mapToScene(
            self.canvas.viewport()
            .rect()
            .center()
        )

        counter = self._manual_node_counter

        node = PageNode(
            title=f"Página {counter}",
            url="https://example.com",
            method="GET",
            status=None,
            x=center.x() - 160,
            y=center.y() - 125,
        )

        self._manual_node_counter += 1

        card = self.canvas.add_node(
            node
        )

        card.setSelected(True)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete_selected(self) -> None:
        selected = list(
            self.canvas.scene().selectedItems()
        )

        if not selected:
            return

        # Primeiro removemos edges explicitamente selecionadas.
        for item in selected:
            if isinstance(item, EdgeItem):
                self.canvas.remove_edge(
                    item.transition.id
                )

        # Depois os nodes.
        #
        # remove_node() já remove todas as edges associadas.
        for item in selected:
            if isinstance(item, PageCard):
                self.canvas.remove_node(
                    item.node.id
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

    # ------------------------------------------------------------------
    # Demo
    # ------------------------------------------------------------------

    def _load_demo_graph(self) -> None:
        self.canvas.clear_graph()

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

        for node in (
            home,
            login,
            dashboard,
            profile,
            admin,
            users,
        ):
            self.canvas.add_node(
                node
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
    def _apply_theme(self) -> None:
        self.setStyleSheet("""
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
    """)

        self.statusBar().setSizeGripEnabled(False)