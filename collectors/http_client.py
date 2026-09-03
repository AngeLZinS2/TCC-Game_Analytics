"""Cliente HTTP com rate limiting e backoff exponencial.

Cada API tem limite proprio, entao o throttle e por instancia de cliente
(um cliente por host/politica), nao global.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class RespostaInvalidaError(RuntimeError):
    """A requisicao terminou, mas o corpo nao e o JSON esperado."""


class RateLimitedClient:
    """Session `requests` com intervalo minimo entre chamadas e retry automatico.

    Args:
        nome: identificador usado nos logs.
        intervalo_minimo: segundos de espera obrigatoria entre duas chamadas.
        max_retries: tentativas para erros transitorios (429 e 5xx).
        timeout: timeout por requisicao, em segundos.
    """

    def __init__(
        self,
        nome: str,
        intervalo_minimo: float = 1.0,
        max_retries: int = 5,
        timeout: float = 30.0,
        user_agent: str = "gaming-analytics-tcc/0.1 (+https://github.com/)",
    ) -> None:
        self.nome = nome
        self.intervalo_minimo = intervalo_minimo
        self.timeout = timeout

        self._lock = threading.Lock()
        self._ultima_chamada = 0.0

        # backoff_factor=1 -> esperas de 1s, 2s, 4s, 8s... entre tentativas.
        # respect_retry_after_header faz o 429 da Steam ser obedecido.
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            backoff_factor=1.0,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=10)

        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    def _aguardar(self) -> None:
        with self._lock:
            decorrido = time.monotonic() - self._ultima_chamada
            espera = self.intervalo_minimo - decorrido
            if espera > 0:
                time.sleep(espera)
            self._ultima_chamada = time.monotonic()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET que devolve JSON decodificado, respeitando o rate limit.

        Raises:
            requests.HTTPError: status final >= 400 apos os retries.
            RespostaInvalidaError: corpo nao e JSON valido.
        """
        self._aguardar()
        inicio = time.monotonic()
        resposta = self.session.get(url, params=params, timeout=self.timeout)
        duracao_ms = round((time.monotonic() - inicio) * 1000)

        logger.debug(
            "requisicao concluida",
            extra={
                "cliente": self.nome,
                "url": url,
                "status": resposta.status_code,
                "duracao_ms": duracao_ms,
            },
        )
        resposta.raise_for_status()

        try:
            return resposta.json()
        except ValueError as exc:
            raise RespostaInvalidaError(
                f"{url} respondeu {resposta.status_code} com corpo nao-JSON "
                f"({resposta.headers.get('Content-Type')})"
            ) from exc

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> RateLimitedClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
