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

#: Teto para o `Retry-After` que o servidor pede (segundos).
#:
#: Existe porque o agendador roda as ~35 tarefas em SERIE, numa thread so:
#: um `sleep` dentro de uma requisicao nao atrasa aquela coleta, atrasa
#: TODAS as outras. Falhar rapido e deixar a tarefa ser reagendada
#: (`ESPERA_APOS_FALHA_SEGUNDOS`) custa uma rodada; dormir custa o dia.
#:
#: Dois minutos ainda absorve o 429 curto de quem so quer que a gente
#: desacelere - que era o motivo de `respect_retry_after_header` existir.
ESPERA_MAXIMA_SEGUNDOS = 120.0


class _RetryComTeto(Retry):
    """`Retry` que obedece o `Retry-After`, mas com limite.

    **O bug que isto conserta (2026-09-16).** `backoff_max` (120s por padrao)
    limita so o backoff EXPONENCIAL - o `Retry-After` do servidor passa
    intacto. Medido na versao instalada (urllib3 2.7.0):

        Retry(...).get_retry_after(resposta_com_retry_after_3600)  ->  3600.0

    Com `total=5`, um servidor pedindo 1 hora prende o cliente por ate CINCO.
    Foi exatamente o que aconteceu: o ITAD (atras da Cloudflare) devolveu 429
    com espera longa, e o agendador ficou 8 horas em `hrtimer_nanosleep` -
    CPU em 0%, sem log nenhum - enquanto steam_online, vlr, lolesports e
    todas as outras fontes envelheciam sem ninguem coletar.

    O teto NAO derruba o respeito ao servidor: a espera continua sendo
    honrada ate o limite, e acima dele a tentativa falha e a tarefa volta pra
    fila em vez de segurar a fila inteira.
    """

    def get_retry_after(self, response):  # type: ignore[override]
        espera = super().get_retry_after(response)
        if espera is None:
            return None
        if espera > ESPERA_MAXIMA_SEGUNDOS:
            logger.warning(
                "Retry-After acima do teto - falhando rapido em vez de dormir",
                extra={"pedido_segundos": espera, "teto_segundos": ESPERA_MAXIMA_SEGUNDOS},
            )
            return ESPERA_MAXIMA_SEGUNDOS
        return espera


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
        user_agent: str = "playdb-tcc/0.1 (+https://playdb.info)",
    ) -> None:
        self.nome = nome
        self.intervalo_minimo = intervalo_minimo
        self.timeout = timeout

        self._lock = threading.Lock()
        self._ultima_chamada = 0.0

        # backoff_factor=1 -> esperas de 1s, 2s, 4s, 8s... entre tentativas.
        # respect_retry_after_header faz o 429 da Steam ser obedecido - com
        # teto, via `_RetryComTeto` (ver a nota de bug na classe).
        retry = _RetryComTeto(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            status_forcelist=(429, 500, 502, 503, 504),
            # POST entra porque as APIs que usamos com POST sao de consulta
            # (o ITAD recebe a lista de ids no corpo), nao de escrita - repetir
            # nao causa efeito colateral.
            allowed_methods=frozenset(["GET", "POST"]),
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

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """GET que devolve JSON decodificado, respeitando o rate limit.

        `headers` se soma aos da sessao (User-Agent, Accept) sem substitui-los -
        e o que o HowLongToBeat precisa para o `x-auth-token` por requisicao.

        Raises:
            requests.HTTPError: status final >= 400 apos os retries.
            RespostaInvalidaError: corpo nao e JSON valido.
        """
        self._aguardar()
        inicio = time.monotonic()
        resposta = self.session.get(
            url, params=params, headers=headers, timeout=self.timeout
        )
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

    def post_json(
        self,
        url: str,
        json: Any,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """POST com corpo JSON que devolve JSON, respeitando o rate limit.

        O IsThereAnyDeal recebe a lista de ids no corpo e os parametros
        (`key`, `country`) na query. O HowLongToBeat usa `headers` para o
        token de sessao por requisicao (`x-auth-token`, `x-hp-key`, `x-hp-val`).

        Raises:
            requests.HTTPError: status final >= 400 apos os retries.
            RespostaInvalidaError: corpo nao e JSON valido.
        """
        self._aguardar()
        inicio = time.monotonic()
        resposta = self.session.post(
            url, params=params, json=json, headers=headers, timeout=self.timeout
        )
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

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """GET que devolve o corpo como texto, respeitando o rate limit.

        Para fontes que servem texto puro (markdown, CSV) em vez de JSON -
        o Regional Standings da Valve publica tabelas markdown no GitHub.

        Raises:
            requests.HTTPError: status final >= 400 apos os retries.
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
        return resposta.text

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> RateLimitedClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
