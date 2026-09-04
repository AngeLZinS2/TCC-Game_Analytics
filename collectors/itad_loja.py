"""Consulta pontual ao IsThereAnyDeal para UM jogo, sem gravar nada.

Espelha `steam_loja.py`: existe para responder uma pergunta sobre um jogo que
talvez nunca tenha passado pelo coletor `itad` (que so roda pra jogos ja no
nosso banco), sem esperar a proxima rodada agendada. Mesma logica de "sem
cache": cada pergunta refaz a chamada, porque a afirmacao "consultado agora"
e o que da valor ao bloco - guardar a resposta a deixaria potencialmente
velha enquanto a tela afirma o contrario.

Reusa o parsing de `etl.transform_itad` (`ofertas_de`, `historico_de`) em vez
de duplicar: o formato do payload `deals`/`low` e o mesmo, seja a chamada
feita pelo coletor em lote ou por esta consulta avulsa.
"""

from __future__ import annotations

import logging

import requests

from config import get_settings
from etl.transform_itad import MenorHistorico, OfertaItad, historico_de, ofertas_de

logger = logging.getLogger(__name__)


def preco_ao_vivo(app_id: int) -> tuple[list[OfertaItad], MenorHistorico | None] | None:
    """Ofertas atuais + menor preco historico de UM jogo, agora.

    Devolve `None` quando falta `ITAD_API_KEY`, o jogo nao existe no ITAD, ou
    a consulta falha - os tres casos sao "sem esse bloco", nunca um erro para
    quem perguntou. `(ofertas_vazias, None)` e diferente de `None`: significa
    que o jogo existe no ITAD mas nenhuma loja tem oferta agora.
    """
    settings = get_settings()
    if not settings.itad_api_key:
        return None

    base = settings.itad_base_url.rstrip("/")
    chave = {"key": settings.itad_api_key}

    try:
        lookup = requests.get(
            f"{base}/games/lookup/v1",
            params={**chave, "appid": app_id},
            timeout=settings.http_timeout_seconds,
        )
        lookup.raise_for_status()
        achado = lookup.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "lookup ao vivo do itad falhou",
            extra={"app_id": app_id, "erro": f"{type(exc).__name__}: {exc}"},
        )
        return None

    if not isinstance(achado, dict) or not achado.get("found"):
        return None
    uuid = (achado.get("game") or {}).get("id")
    if not uuid:
        return None

    try:
        precos = requests.post(
            f"{base}/games/prices/v3",
            params={**chave, "country": settings.itad_country, "capacity": 8},
            json=[uuid],
            timeout=settings.http_timeout_seconds,
        )
        precos.raise_for_status()
        historico = requests.post(
            f"{base}/games/historylow/v1",
            params={**chave, "country": settings.itad_country},
            json=[uuid],
            timeout=settings.http_timeout_seconds,
        )
        historico.raise_for_status()
        dados_precos = precos.json()
        dados_historico = historico.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "preco ao vivo do itad falhou",
            extra={"app_id": app_id, "erro": f"{type(exc).__name__}: {exc}"},
        )
        return None

    item_preco = next(
        (i for i in (dados_precos or []) if isinstance(i, dict) and i.get("id") == uuid),
        None,
    )
    item_historico = next(
        (i for i in (dados_historico or []) if isinstance(i, dict) and i.get("id") == uuid),
        None,
    )

    ofertas = ofertas_de((item_preco or {}).get("deals"))
    menor = historico_de((item_historico or {}).get("low"))
    return ofertas, menor
