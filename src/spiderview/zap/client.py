"""Cliente de comunicação entre o SpiderView e a API do OWASP ZAP."""

from __future__ import annotations

import os
from typing import Any

from zapv2 import ZAPv2


class ZapClientError(RuntimeError):
    """Erro de comunicação ou consulta à API do OWASP ZAP."""


class ZapClient:
    """Encapsula as operações da API do ZAP usadas pelo SpiderView."""

    def __init__(
        self,
        api_key: str | None = None,
        address: str = "127.0.0.1",
        port: int = 8080,
    ) -> None:
        self.address = address
        self.port = port
        self.base_url = f"http://{address}:{port}"
        self._api_key = api_key or os.getenv("SPIDERVIEW_ZAP_API_KEY")

        if not self._api_key:
            raise ZapClientError(
                "Chave da API do ZAP não configurada. Defina "
                "SPIDERVIEW_ZAP_API_KEY ou forneça api_key."
            )

        # A API de controle é acessada diretamente; não deve passar
        # pelo proxy HTTP que o próprio ZAP disponibiliza para o tráfego.
        self._zap = ZAPv2(
            apikey=self._api_key,
            proxies={},
        )

    def get_version(self) -> str:
        """Retorna a versão do ZAP, confirmando que a API responde."""
        try:
            return str(self._zap.core.version)
        except Exception as exc:
            raise ZapClientError(
                f"Não foi possível consultar a API do ZAP em {self.base_url}. "
                "Verifique se o ZAP está aberto, se a API está habilitada "
                "e se a chave é válida."
            ) from exc

    def is_available(self) -> bool:
        """Informa se a API do ZAP está respondendo."""
        try:
            self.get_version()
            return True
        except ZapClientError:
            return False

    def get_sites(self) -> list[str]:
        """Retorna os sites conhecidos pelo ZAP."""
        try:
            return list(self._zap.core.sites or [])
        except Exception as exc:
            raise ZapClientError(
                "Não foi possível recuperar os sites conhecidos pelo ZAP."
            ) from exc

    def get_urls(self, base_url: str | None = None) -> list[str]:
        """Retorna URLs conhecidas pelo ZAP, opcionalmente filtradas por site."""
        try:
            return list(self._zap.core.urls(base_url or "") or [])
        except Exception as exc:
            raise ZapClientError(
                "Não foi possível recuperar as URLs conhecidas pelo ZAP."
            ) from exc

    def get_messages(
        self,
        start: int = 0,
        count: int = 100,
    ) -> list[dict[str, Any]]:
        """Retorna mensagens HTTP capturadas, usando paginação."""
        if start < 0:
            raise ValueError("'start' não pode ser negativo.")
        if count < 1:
            raise ValueError("'count' deve ser maior que zero.")

        try:
            return list(self._zap.core.messages(start, count) or [])
        except Exception as exc:
            raise ZapClientError(
                "Não foi possível recuperar as mensagens HTTP do ZAP."
            ) from exc

    def get_all_messages(
        self,
        page_size: int = 100,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        """Recupera mensagens em páginas, com limite de volume."""
        if page_size < 1:
            raise ValueError("'page_size' deve ser maior que zero.")
        if max_pages < 1:
            raise ValueError("'max_pages' deve ser maior que zero.")

        result: list[dict[str, Any]] = []
        for page in range(max_pages):
            batch = self.get_messages(start=page * page_size, count=page_size)
            result.extend(batch)
            if len(batch) < page_size:
                break

        return result

    def get_status(self) -> dict[str, Any]:
        """Retorna um resumo do estado do motor."""
        version = self.get_version()
        try:
            total_messages = int(self._zap.core.number_of_messages)
            sites = self.get_sites()
        except Exception as exc:
            raise ZapClientError(
                "O ZAP respondeu, mas não foi possível consultar seu estado."
            ) from exc

        return {
            "available": True,
            "version": version,
            "address": self.address,
            "port": self.port,
            "total_messages": total_messages,
            "total_sites": len(sites),
        }
