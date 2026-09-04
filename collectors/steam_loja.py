"""Consulta pontual a loja da Steam, sem gravar nada.

E o oposto do `steam_collector`: aquele coleta para o banco, gravando payload
bruto e normalizando; este apenas PERGUNTA e devolve. Nao escreve em
`data/raw/`, nao abre sessao do banco, nao tem `run()`.

Existe porque o banco nao pode conter a Steam inteira. Sao ~200 mil apps, e
armazenar todos para que uma pergunta ocasional seja respondida seria pagar
semanas de coleta por dado que quase nunca e lido. Quando alguem pergunta sobre
um jogo que nao esta no banco, a resposta certa nao e "nao sei" - e ir buscar.

Os tres endpoints sao publicos e **nao usam `STEAM_API_KEY`**. A chave da Steam
serve a endpoints de dados de JOGADOR (inventario, biblioteca, amigos), que este
projeto nao consome.

**Sobre nao ter cache.** Cada consulta refaz as chamadas. Guardar a resposta
tornaria o numero exibido possivelmente velho enquanto a tela afirma "consultada
agora" - e a afirmacao de procedencia e justamente o que da valor a este bloco.
Tres chamadas por pergunta cabem folgadamente no limite de taxa da loja.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from config import get_settings

logger = logging.getLogger(__name__)

URL_BUSCA = "https://store.steampowered.com/api/storesearch/"
URL_FICHA = "https://store.steampowered.com/api/appdetails"
URL_AVALIACOES = "https://store.steampowered.com/appreviews/{app_id}"
URL_STEAMSPY = "https://steamspy.com/api.php"

#: Abaixo disto, "pior avaliado" so mediria obscuridade - um app com 3
#: avaliacoes pode cair em 0% so por acaso de amostra pequena, o que nao e o
#: mesmo que ser realmente malvisto por um publico de verdade.
MINIMO_AVALIACOES_EXTREMO = 1000


def _pegar(url: str, params: dict[str, Any]) -> Any | None:
    """GET que devolve `None` em vez de estourar.

    Quem chama monta contexto para um assistente: uma consulta que falhou
    significa um bloco a menos, nao uma pergunta sem resposta.
    """
    settings = get_settings()
    try:
        resposta = requests.get(
            url,
            params=params,
            timeout=settings.http_timeout_seconds,
            headers={"Accept": "application/json"},
        )
        resposta.raise_for_status()
        return resposta.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "consulta a loja da Steam falhou",
            extra={"url": url, "erro": f"{type(exc).__name__}: {exc}"},
        )
        return None


def buscar(termo: str, limite: int = 5) -> list[dict[str, Any]]:
    """Busca apps pelo nome. Devolve lista vazia quando nada casa ou a loja cai."""
    settings = get_settings()
    dados = _pegar(
        URL_BUSCA,
        {"term": termo, "cc": settings.steam_country, "l": settings.steam_language},
    )
    if not isinstance(dados, dict):
        return []

    itens = dados.get("items")
    if not isinstance(itens, list):
        return []

    return [item for item in itens if isinstance(item.get("id"), int)][:limite]


def ficha(app_id: int) -> dict[str, Any] | None:
    """Ficha da loja: nome, desenvolvedora, generos, preco, lancamento.

    A Steam responde 200 com `success: false` para app inexistente, DLC sem
    pagina ou item indisponivel na regiao - por isso o `success` e conferido em
    vez de so olhar o status HTTP.
    """
    settings = get_settings()
    dados = _pegar(
        URL_FICHA,
        {
            "appids": app_id,
            "cc": settings.steam_country,
            "l": settings.steam_language,
        },
    )
    if not isinstance(dados, dict):
        return None

    entrada = dados.get(str(app_id))
    if not isinstance(entrada, dict) or not entrada.get("success"):
        return None

    corpo = entrada.get("data")
    return corpo if isinstance(corpo, dict) else None


def resumo_avaliacoes(app_id: int) -> dict[str, Any] | None:
    """So o `query_summary` das avaliacoes - total, positivas e a classificacao.

    `num_per_page=0` pede zero avaliacoes e mesmo assim traz o agregado: os
    campos do resumo vem iguais com ou sem a lista, entao a chamada e barata.
    """
    dados = _pegar(
        URL_AVALIACOES.format(app_id=app_id),
        {
            "json": 1,
            "language": "all",
            "purchase_type": "all",
            "num_per_page": 0,
        },
    )
    if not isinstance(dados, dict) or not dados.get("success"):
        return None

    resumo = dados.get("query_summary")
    return resumo if isinstance(resumo, dict) else None


def extremo_avaliacao_por_genero(genero: str, pior: bool) -> dict[str, Any] | None:
    """O jogo com a melhor/pior proporcao de avaliacoes positivas de um genero,
    sobre TODO o catalogo que o SteamSpy indexa - nao so os jogos no nosso banco.

    Existe porque "qual o pior jogo da Steam" nao tem resposta correta dentro
    de um catalogo de 20 e poucos jogos: a Steam tem centenas de milhares. O
    SteamSpy e a unica fonte que devolve avaliacao de um genero INTEIRO numa
    chamada so (dezenas de milhares de apps) - a API oficial da Steam so fala
    de UM app por vez, e nao ha endpoint (oficial ou nao) que ordene a loja
    inteira por nota.

    Fonte: SteamSpy, um terceiro - as contagens sao estimativas dele sobre
    avaliacoes publicas da Steam, nao a Steam nem nossa medicao. Quem chama
    isto deve marcar a procedencia de acordo (`fonte="steam"` no `Bloco`, e a
    instrucao do assistente ja pede a frase "segundo o SteamSpy").
    """
    dados = _pegar(URL_STEAMSPY, {"request": "genre", "genre": genero})
    if not isinstance(dados, dict):
        return None

    candidatos: list[tuple[float, int, dict[str, Any]]] = []
    for item in dados.values():
        if not isinstance(item, dict):
            continue
        positivas = item.get("positive") or 0
        negativas = item.get("negative") or 0
        total = positivas + negativas
        if total < MINIMO_AVALIACOES_EXTREMO:
            continue
        candidatos.append((positivas / total, total, item))

    if not candidatos:
        return None

    candidatos.sort(key=lambda c: c[0], reverse=not pior)
    proporcao, total, item = candidatos[0]
    return {
        "app_id": item.get("appid"),
        "nome": item.get("name"),
        "proporcao_positiva": proporcao,
        "positivas": item.get("positive"),
        "negativas": item.get("negative"),
        "total_avaliacoes": total,
        "owners": item.get("owners"),
    }
