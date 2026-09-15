from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


def generate_id() -> str:
    return uuid4().hex


class NodeKind(str, Enum):
    """
    Tipo lógico do node.

    PAGE:
        Página visual tradicional.

    DOM_STATE:
        Estado relevante de uma SPA após uma alteração de DOM.

    API:
        Recurso/API que futuramente terá representação própria.

    NOTE:
        Anotação manual criada pelo pentester.
    """

    PAGE = "page"
    DOM_STATE = "dom_state"
    API = "api"
    NOTE = "note"


class TransitionType(str, Enum):
    """
    Motivo pelo qual o grafo chegou do node A ao node B.
    """

    NAVIGATION = "navigation"
    CLICK = "click"
    FORM_SUBMIT = "form_submit"
    REDIRECT = "redirect"
    FETCH = "fetch"
    XHR = "xhr"
    REQUEST = "request"
    DOM_MUTATION = "dom_mutation"
    MANUAL = "manual"


@dataclass(slots=True)
class PageNode:
    """
    Representação lógica de um node do SpiderView.

    Esta classe NÃO possui nenhuma dependência de Qt.
    """

    title: str
    url: str

    id: str = field(default_factory=generate_id)

    kind: NodeKind = NodeKind.PAGE

    method: str = "GET"
    status: int | None = None

    preview_path: str | None = None

    # Posição persistida no canvas.
    x: float = 0.0
    y: float = 0.0

    # Campo livre para informações futuras:
    #
    # content_type
    # response_time
    # alerts
    # zap_message_id
    # dom_hash
    # etc.
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "kind": self.kind.value,
            "method": self.method,
            "status": self.status,
            "preview_path": self.preview_path,
            "x": self.x,
            "y": self.y,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PageNode":
        return cls(
            id=data["id"],
            title=data["title"],
            url=data["url"],
            kind=NodeKind(data.get("kind", NodeKind.PAGE.value)),
            method=data.get("method", "GET"),
            status=data.get("status"),
            preview_path=data.get("preview_path"),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class Transition:
    """
    Relação direcionada entre dois nodes.

    Exemplo:

        Login
          |
          | POST /login
          v
        Dashboard
    """

    source_id: str
    target_id: str

    id: str = field(default_factory=generate_id)

    type: TransitionType = TransitionType.NAVIGATION

    # Texto humano mostrado no canvas.
    #
    # Exemplos:
    # "click: Login"
    # "POST /login"
    # "302"
    label: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type.value,
            "label": self.label,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transition":
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            type=TransitionType(
                data.get("type", TransitionType.NAVIGATION.value)
            ),
            label=data.get("label"),
            metadata=data.get("metadata", {}),
        )