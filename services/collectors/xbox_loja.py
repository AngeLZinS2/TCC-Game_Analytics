"""Busca por nome na loja da Xbox/Microsoft Store, sem gravar nada.

E o equivalente Xbox do `steam_loja.buscar`: o catalogo (`dim_jogo_xbox`) so
tem o que ja passou pelo `xbox_collector` - a UNIAO do Game Pass agora, da
semente fixa e do que ja esta no banco (ver `xbox_collector.py`). Um jogo a
venda mas fora do Game Pass e fora da semente (ex.: "Grand Theft Auto V", que
saiu do Game Pass) simplesmente nunca aparecia - o catalogo nao tinha como
descobrir um `product_id` que nao lhe foi dado.

Este modulo fecha esse buraco com a busca de texto de verdade da Microsoft
Store (`storeedgefd.dsx.mp.microsoft.com/v9.0/pages/searchResults` - a mesma
API que a store.microsoft.com usa; nao-oficial, mas publica e sem chave). Os
cards da busca ja trazem titulo/preco/imagem prontos - nao precisa de uma 2a
chamada de "ficha" como a Steam precisa (`storesearch` da a Steam so um id,
o `appdetails` e que traz o resto; aqui o `searchResults` ja vem completo).
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from config import get_settings

logger = logging.getLogger(__name__)

URL_BUSCA = "https://storeedgefd.dsx.mp.microsoft.com/v9.0/pages/searchResults"

#: Versao do cliente que a API espera no `appVersion` - qualquer versao
#: valida de app da Store serve, o campo so precisa parecer uma chamada real.
APP_VERSION = "22203.1401.0.0"


def buscar(termo: str, limite: int = 10) -> list[dict[str, Any]]:
    """Busca produtos pelo nome. Devolve lista vazia quando nada casa ou a
    Store cai - mesma politica de falha do `steam_loja.buscar`.

    So `TypeTag == "app"` entra (jogos, DLC, bundles vendidos como app) - a
    busca tambem devolve filmes/series quando `mediaType` nao filtra bem o
    bastante, e o catalogo do projeto e so de jogos.
    """
    settings = get_settings()
    try:
        resposta = requests.get(
            URL_BUSCA,
            params={
                "appVersion": APP_VERSION,
                "market": settings.xbox_market,
                "locale": "pt-BR",
                "deviceFamily": "windows.desktop",
                "query": termo,
                "mediaType": "games",
            },
            timeout=settings.http_timeout_seconds,
            headers={"Accept": "application/json"},
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "busca na Microsoft Store falhou",
            extra={"termo": termo, "erro": f"{type(exc).__name__}: {exc}"},
        )
        return []

    # A resposta e uma lista de "ResponseItem"; o payload de verdade fica no
    # item cujo Payload tem `SearchResults` (o outro costuma ser metadado de
    # pagina). Percorrer em vez de indexar por posicao porque a ordem nao e
    # contratual.
    resultados: list[dict] | None = None
    if isinstance(dados, list):
        for item in dados:
            payload = item.get("Payload") if isinstance(item, dict) else None
            if isinstance(payload, dict) and isinstance(
                payload.get("SearchResults"), list
            ):
                resultados = payload["SearchResults"]
                break
    if not resultados:
        return []

    candidatos: list[dict[str, Any]] = []
    for item in resultados:
        if not isinstance(item, dict):
            continue
        product_id = item.get("ProductId")
        titulo = item.get("Title")
        if not product_id or not titulo:
            continue
        if item.get("TypeTag") != "app":
            continue

        imagem = None
        for img in item.get("Images") or []:
            if isinstance(img, dict) and img.get("ImageType") in ("Poster", "BoxArt"):
                imagem = img.get("Url")
                if img.get("ImageType") == "Poster":
                    break  # Poster e o formato que o catalogo usa; BoxArt e so fallback.

        candidatos.append(
            {
                "product_id": product_id,
                "titulo": titulo,
                "publicadora": item.get("PublisherName"),
                "preco_texto": item.get("DisplayPrice"),
                "imagem": imagem,
            }
        )
        if len(candidatos) >= limite:
            break

    return candidatos
