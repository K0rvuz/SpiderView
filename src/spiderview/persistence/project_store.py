from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from ..models import PageNode, Transition
from .migrations import migrate_payload


class ProjectStoreError(Exception):
    """Erro de leitura ou escrita de um projeto SpiderView."""


class ProjectStore:
    """
    Persistência de projetos SpiderView.

    Estrutura:

        projeto.spiderview/
        ├── project.json
        └── previews/
            ├── <node-id>.png
            └── ...

    O JSON guarda caminhos relativos para que o projeto possa ser
    movido ou compartilhado sem quebrar os previews.
    """

    FORMAT_NAME = "spiderview"
    FORMAT_VERSION = 2

    PROJECT_FILE = "project.json"
    PREVIEWS_DIR = "previews"

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    @classmethod
    def save(
        cls,
        project_dir: str | Path,
        nodes: Iterable[PageNode],
        transitions: Iterable[Transition],
    ) -> Path:
        project_dir = Path(project_dir).expanduser()

        try:
            project_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise ProjectStoreError(
                f"Não foi possível criar a pasta do projeto: {exc}"
            ) from exc

        if not project_dir.is_dir():
            raise ProjectStoreError(
                f"O caminho do projeto não é uma pasta: {project_dir}"
            )

        previews_dir = (
            project_dir
            / cls.PREVIEWS_DIR
        )

        try:
            previews_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise ProjectStoreError(
                f"Não foi possível criar a pasta de previews: {exc}"
            ) from exc

        serialized_nodes: list[dict] = []

        for node in nodes:
            data = node.to_dict()

            # Nunca persistimos um caminho absoluto temporário.
            # Se houver preview, copiamos para dentro do projeto
            # e guardamos apenas o caminho relativo.
            data["preview_path"] = cls._persist_preview(
                node=node,
                previews_dir=previews_dir,
            )

            serialized_nodes.append(
                data
            )

        serialized_transitions = [
            transition.to_dict()
            for transition in transitions
        ]

        payload = {
            "format": cls.FORMAT_NAME,
            "version": cls.FORMAT_VERSION,
            "project": {
                "schema": "graph-v2",
            },
            "nodes": serialized_nodes,
            "transitions": serialized_transitions,
        }

        project_file = (
            project_dir
            / cls.PROJECT_FILE
        )

        temporary_file = (
            project_dir
            / f"{cls.PROJECT_FILE}.tmp"
        )

        try:
            text = json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )

            temporary_file.write_text(
                text,
                encoding="utf-8",
            )

            # Escrita atômica: project.json antigo só é substituído
            # depois que o novo JSON foi escrito com sucesso.
            temporary_file.replace(
                project_file
            )

        except (OSError, TypeError, ValueError) as exc:
            try:
                temporary_file.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise ProjectStoreError(
                f"Não foi possível salvar o projeto: {exc}"
            ) from exc

        return project_file

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        project_dir: str | Path,
    ) -> tuple[list[PageNode], list[Transition]]:
        project_dir = cls._resolve_project_dir(
            project_dir
        )

        project_file = (
            project_dir
            / cls.PROJECT_FILE
        )

        if not project_file.is_file():
            raise ProjectStoreError(
                f"{cls.PROJECT_FILE} não encontrado em: {project_dir}"
            )

        try:
            payload = json.loads(
                project_file.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectStoreError(
                f"Não foi possível ler o projeto: {exc}"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ProjectStoreError(
                "Formato de projeto inválido."
            )

        if (
            payload.get("format")
            != cls.FORMAT_NAME
        ):
            raise ProjectStoreError(
                "Este arquivo não é um projeto SpiderView válido."
            )

        try:
            payload = migrate_payload(
                payload,
                target_version=cls.FORMAT_VERSION,
            )
        except ValueError as exc:
            raise ProjectStoreError(
                str(exc)
            ) from exc

        version = payload.get(
            "version"
        )

        if version != cls.FORMAT_VERSION:
            raise ProjectStoreError(
                "Falha ao migrar o projeto para a versão atual."
            )

        raw_nodes = payload.get(
            "nodes",
            [],
        )

        raw_transitions = payload.get(
            "transitions",
            [],
        )

        if not isinstance(
            raw_nodes,
            list,
        ):
            raise ProjectStoreError(
                "'nodes' precisa ser uma lista."
            )

        if not isinstance(
            raw_transitions,
            list,
        ):
            raise ProjectStoreError(
                "'transitions' precisa ser uma lista."
            )

        nodes: list[PageNode] = []

        for raw_node in raw_nodes:
            if not isinstance(
                raw_node,
                dict,
            ):
                raise ProjectStoreError(
                    "Node inválido encontrado no projeto."
                )

            node_data = dict(
                raw_node
            )

            node_data["preview_path"] = (
                cls._resolve_preview_path(
                    project_dir=project_dir,
                    stored_path=node_data.get(
                        "preview_path"
                    ),
                )
            )

            try:
                node = PageNode.from_dict(
                    node_data
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise ProjectStoreError(
                    f"Node inválido no projeto: {exc}"
                ) from exc

            nodes.append(
                node
            )

        node_ids = {
            node.id
            for node in nodes
        }

        transitions: list[Transition] = []

        for raw_transition in raw_transitions:
            if not isinstance(
                raw_transition,
                dict,
            ):
                raise ProjectStoreError(
                    "Transition inválida encontrada no projeto."
                )

            try:
                transition = Transition.from_dict(
                    raw_transition
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise ProjectStoreError(
                    f"Transition inválida no projeto: {exc}"
                ) from exc

            if (
                transition.source_id
                not in node_ids
            ):
                raise ProjectStoreError(
                    "Transition aponta para source_id inexistente: "
                    f"{transition.source_id}"
                )

            if (
                transition.target_id
                not in node_ids
            ):
                raise ProjectStoreError(
                    "Transition aponta para target_id inexistente: "
                    f"{transition.target_id}"
                )

            transitions.append(
                transition
            )

        return (
            nodes,
            transitions,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_project_dir(
        cls,
        path: str | Path,
    ) -> Path:
        path = Path(path).expanduser()

        # Também aceitamos project.json diretamente,
        # embora a UI normalmente selecione a pasta.
        if (
            path.is_file()
            and path.name == cls.PROJECT_FILE
        ):
            return path.parent

        return path

    @classmethod
    def _persist_preview(
        cls,
        node: PageNode,
        previews_dir: Path,
    ) -> str | None:
        preview_path = node.preview_path

        if not preview_path:
            return None

        source = Path(
            preview_path
        ).expanduser()

        if not source.is_file():
            return None

        # Os previews atuais são PNG. Mantemos a extensão original
        # se existir, para não quebrar projetos futuros.
        suffix = (
            source.suffix.lower()
            or ".png"
        )

        filename = (
            f"{node.id}{suffix}"
        )

        destination = (
            previews_dir
            / filename
        )

        try:
            source_resolved = (
                source.resolve()
            )

            destination_resolved = (
                destination.resolve()
            )

            if (
                source_resolved
                != destination_resolved
            ):
                shutil.copy2(
                    source_resolved,
                    destination_resolved,
                )

        except OSError as exc:
            raise ProjectStoreError(
                "Não foi possível copiar o preview "
                f"do node {node.id}: {exc}"
            ) from exc

        relative_path = (
            Path(cls.PREVIEWS_DIR)
            / filename
        )

        return relative_path.as_posix()

    @classmethod
    def _resolve_preview_path(
        cls,
        project_dir: Path,
        stored_path,
    ) -> str | None:
        if not stored_path:
            return None

        if not isinstance(
            stored_path,
            str,
        ):
            raise ProjectStoreError(
                "preview_path inválido."
            )

        relative_path = Path(
            stored_path
        )

        # Projetos SpiderView são portáveis:
        # preview_path deve ser relativo ao diretório do projeto.
        if relative_path.is_absolute():
            raise ProjectStoreError(
                "Projeto contém preview_path absoluto."
            )

        project_root = (
            project_dir.resolve()
        )

        candidate = (
            project_root
            / relative_path
        ).resolve()

        # Evita caminhos como ../../arquivo.png escapando
        # da pasta do projeto.
        if (
            candidate != project_root
            and project_root
            not in candidate.parents
        ):
            raise ProjectStoreError(
                "preview_path aponta para fora "
                "da pasta do projeto."
            )

        if not candidate.is_file():
            return None

        return str(
            candidate
        )
