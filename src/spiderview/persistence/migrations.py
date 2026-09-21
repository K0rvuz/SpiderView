from __future__ import annotations

from copy import deepcopy


def migrate_payload(payload: dict, *, target_version: int) -> dict:
    """Migra project.json antigo sem alterar o dicionário recebido."""
    result = deepcopy(payload)
    version = result.get("version", 1)

    if not isinstance(version, int):
        raise ValueError(f"Versão de projeto inválida: {version!r}")
    if version > target_version:
        raise ValueError(
            f"Projeto usa versão {version}, mas esta instalação suporta até {target_version}."
        )

    while version < target_version:
        if version == 1:
            result = _v1_to_v2(result)
            version = 2
            continue
        raise ValueError(f"Não existe migração registrada para a versão {version}.")

    return result


def _v1_to_v2(payload: dict) -> dict:
    result = deepcopy(payload)
    project = result.get("project")
    if not isinstance(project, dict):
        project = {}

    project.setdefault("schema", "graph-v2")
    result["project"] = project
    result["version"] = 2

    for node in result.get("nodes", []) or []:
        if isinstance(node, dict) and not isinstance(node.get("metadata"), dict):
            node["metadata"] = {}

    for transition in result.get("transitions", []) or []:
        if isinstance(transition, dict) and not isinstance(transition.get("metadata"), dict):
            transition["metadata"] = {}

    return result
