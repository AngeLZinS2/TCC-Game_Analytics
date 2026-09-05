"""Descoberta de jogos na loja da Steam por caracteristica, nao por nome.

O `steam_loja` responde "o que a Steam diz DESTE jogo". Este responde a
pergunta oposta: "QUAIS jogos tem estas caracteristicas?" - FPS jogavel online
com amigos, roguelike cooperativo, battle royale gratuito.

Existe porque o nosso banco nao consegue responder isso e nunca vai conseguir:
`dim_jogo_steam` guarda os generos grossos da Steam (Action, Indie, RPG) e nao
guarda categoria nenhuma - nao ha campo que diga "tem PvP online". Perguntado
por "FPS para cinco amigos", o assistente so tinha o ranking de melhor avaliado
do catalogo pra oferecer, que responde outra pergunta.

**O que impede a lista de vir errada.** Sao tres fontes, e nenhuma delas e o
modelo de linguagem:

1. A LISTA OFICIAL DE TAGS (`IStoreService/GetTagList`) traduz a palavra da
   pergunta em um id de tag. "FPS" vira 1663 porque a Steam diz que vira, nao
   porque alguem chutou o numero.
2. A BUSCA DA LOJA filtra por essa tag e pela categoria de multijogador. Sao os
   mesmos filtros da barra lateral da loja - o resultado e o que a Steam
   mostraria a quem clicasse neles.
3. O `appdetails` CONFIRMA cada candidato um a um: e jogo (nao DLC, nao trilha
   sonora) e tem categoria de multijogador. So o que passa nas tres entra.

A busca da loja devolve HTML dentro do JSON, e dele se extrai apenas o
`data-ds-appid`. E deliberado que o HTML nao vire fato exibido: ele produz
CANDIDATOS, e todo numero e todo nome que chega na tela vem depois, da API
oficial. Se a Valve mudar o HTML, a lista fica vazia - nunca errada.

**O que esta fonte NAO sabe.** Nao existe campo de tamanho de grupo. "Cinco
amigos" nao e consultavel: o que da pra garantir e multijogador online (PvP ou
cooperativo) confirmado por categoria. Quem monta o contexto tem que dizer isso
com todas as letras, senao o modelo preenche a lacuna sozinho.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from typing import Any

from collectors.steam_loja import ficha, pegar
from config import get_settings

logger = logging.getLogger(__name__)

URL_TAGS = "https://api.steampowered.com/IStoreService/GetTagList/v1/"
URL_BUSCA_FILTRADA = "https://store.steampowered.com/search/results/"
URL_JOGADORES = (
    "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
)

#: `category2` da busca da loja - os mesmos numeros das caixas da barra lateral.
CATEGORIA_PVP_ONLINE = 36
CATEGORIA_COOP_ONLINE = 38

#: Ids de categoria que provam multijogador na ficha do app.
#:
#: Casa por ID e nao por descricao porque a descricao vem traduzida: com
#: `l=portuguese` a Steam responde "Multijogador", com `l=english`
#: "Multi-player". O id 1 e o mesmo nos dois.
#:
#: O conjunto e largo de proposito. A ficha do Counter-Strike 2 lista so
#: `Multi-player` e `Cross-Platform Multiplayer` - nao lista `Online PvP`,
#: embora o CS2 apareca na busca filtrada por PvP online. Exigir o id 36 aqui
#: reprovaria o jogo de tiro online mais obvio que existe. Quem garante o "PvP
#: online" e o filtro da busca; esta checagem so barra o que e exclusivamente single-player.
CATEGORIAS_MULTIJOGADOR = {
    1,  # Multi-player
    9,  # Co-op
    27,  # Cross-Platform Multiplayer
    36,  # Online PvP
    38,  # Online Co-op
    49,  # PvP
}

#: Tags curtas demais casariam dentro de qualquer pergunta ("Bom", "2D").
MINIMO_CARACTERES_TAG = 3


def _normalizar(texto: str) -> str:
    """Minusculas sem acento - o mesmo criterio do `ml.assistente`."""
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def tags_oficiais() -> dict[str, int]:
    """Nome normalizado -> id, com os nomes em portugues E em ingles.

    Os dois idiomas porque a mesma tag tem nomes diferentes e as duas formas
    aparecem em pergunta de brasileiro: a 1663 se chama "Tiros em Primeira
    Pessoa" em portugues e "FPS" em ingles, e ninguem escreve a primeira.

    Em cache de processo: sao ~450 tags que mudam em meses, e resolver a
    palavra da pergunta nao pode custar uma chamada de rede por pergunta.
    Devolve `{}` quando a chamada falha - e ai a descoberta simplesmente nao
    acontece e o assistente segue pelo caminho do catalogo.
    """
    mapa: dict[str, int] = {}
    for idioma in ("portuguese", "english"):
        dados = pegar(URL_TAGS, {"language": idioma})
        if not isinstance(dados, dict):
            continue
        for tag in (dados.get("response") or {}).get("tags") or []:
            nome = tag.get("name")
            tag_id = tag.get("tagid")
            if not isinstance(nome, str) or not isinstance(tag_id, int):
                continue
            chave = _normalizar(nome)
            if len(chave) >= MINIMO_CARACTERES_TAG:
                mapa[chave] = tag_id

    if not mapa:
        logger.warning("lista oficial de tags da Steam veio vazia")
    return mapa


def resolver_tag(pergunta: str) -> tuple[int, str] | None:
    """A tag da Steam que a pergunta cita, se alguma. Devolve `(id, nome)`.

    Casa por sequencia de TOKENS inteiros, nunca por trecho solto: sem isso
    "battle royale" casaria a tag "Royale" dentro de outra palavra e "arena"
    casaria dentro de "arenoso". Entre varias que casam vence a MAIS LONGA -
    "battle royale" e mais especifica que "battle", e a pergunta que traz as
    duas quer a primeira.
    """
    tokens = re.findall(r"[a-z0-9]+", _normalizar(pergunta))
    if not tokens:
        return None

    presentes = {
        " ".join(tokens[i:j])
        for i in range(len(tokens))
        for j in range(i + 1, min(i + 5, len(tokens)) + 1)
    }

    mapa = tags_oficiais()
    casadas = [(nome, mapa[nome]) for nome in presentes & mapa.keys()]
    if not casadas:
        return None

    nome, tag_id = max(casadas, key=lambda c: len(c[0]))
    return tag_id, nome


def _candidatos(tag_id: int, categoria: int, quantidade: int) -> list[int]:
    """App ids da busca da loja para uma tag + categoria.

    Ordem de RELEVANCIA (o padrao da loja), nao por nota. Ordenar por avaliacao
    aqui traz o topo de um ranking de nicho - mods de uma pessoa so com 40
    avaliacoes perfeitas - em vez dos jogos que a pergunta quer.
    """
    settings = get_settings()
    dados = pegar(
        URL_BUSCA_FILTRADA,
        {
            "json": 1,
            "term": "",
            "tags": tag_id,
            "category2": categoria,
            "cc": settings.steam_country,
            "l": settings.steam_language,
            "infinite": 1,
            "start": 0,
            "count": quantidade,
        },
    )
    if not isinstance(dados, dict):
        return []

    html = dados.get("results_html")
    if not isinstance(html, str):
        return []

    vistos: list[int] = []
    for bruto in re.findall(r'data-ds-appid="(\d+)"', html):
        app_id = int(bruto)
        if app_id not in vistos:
            vistos.append(app_id)
    return vistos


def jogadores_agora(app_id: int) -> int | None:
    """Jogadores simultaneos neste instante, direto da API oficial."""
    dados = pegar(URL_JOGADORES, {"appid": app_id})
    if not isinstance(dados, dict):
        return None
    contagem = (dados.get("response") or {}).get("player_count")
    return contagem if isinstance(contagem, int) else None


def multijogador_por_tag(
    tag_id: int,
    *,
    cooperativo: bool = True,
    competitivo: bool = True,
    desejados: int = 8,
    teto_candidatos: int = 18,
) -> list[dict[str, Any]]:
    """Jogos de uma tag jogaveis online, ordenados por quem tem gente agora.

    `cooperativo`/`competitivo` escolhem os filtros da busca (co-op online,
    PvP online). Os dois ligados e o caso de "jogar com amigos" sem dizer como.

    Ordena por jogadores simultaneos porque a pergunta e sobre jogar HOJE, com
    outras pessoas: um jogo excelente e vazio nao serve a um grupo de cinco, e
    nota de avaliacao nao distingue os dois casos.

    `teto_candidatos` limita o custo: cada candidato custa uma chamada de ficha
    e uma de jogadores, e a confirmacao para assim que junta `desejados`.
    """
    categorias = [
        categoria
        for categoria, ligada in (
            (CATEGORIA_PVP_ONLINE, competitivo),
            (CATEGORIA_COOP_ONLINE, cooperativo),
        )
        if ligada
    ]
    if not categorias:
        return []

    candidatos: list[int] = []
    for categoria in categorias:
        for app_id in _candidatos(tag_id, categoria, teto_candidatos):
            if app_id not in candidatos:
                candidatos.append(app_id)

    confirmados: list[dict[str, Any]] = []
    for app_id in candidatos[:teto_candidatos]:
        if len(confirmados) >= desejados:
            break

        dados = ficha(app_id)
        if not dados or dados.get("type") != "game":
            # DLC, trilha sonora e pacote de skin aparecem na busca por tag -
            # nenhum deles e um jogo que cinco amigos abrem.
            continue

        ids_categoria = {
            c.get("id") for c in (dados.get("categories") or []) if isinstance(c, dict)
        }
        if not (CATEGORIAS_MULTIJOGADOR & ids_categoria):
            continue

        preco = dados.get("price_overview") or {}
        confirmados.append(
            {
                "app_id": app_id,
                "nome": dados.get("name"),
                "generos": [
                    g.get("description")
                    for g in (dados.get("genres") or [])
                    if isinstance(g, dict) and g.get("description")
                ],
                "categorias": sorted(
                    c.get("description")
                    for c in (dados.get("categories") or [])
                    if isinstance(c, dict)
                    and c.get("id") in CATEGORIAS_MULTIJOGADOR
                    and c.get("description")
                ),
                "gratuito": bool(dados.get("is_free")),
                # Em centavos na API; quem exibe divide. `None` quando a loja
                # nao vende na regiao (pre-venda, removido do catalogo).
                "preco": (preco.get("final") / 100) if preco.get("final") else None,
                "moeda": preco.get("currency"),
                "imagem_header": dados.get("header_image"),
                "jogadores_agora": jogadores_agora(app_id),
            }
        )

    confirmados.sort(key=lambda j: j["jogadores_agora"] or 0, reverse=True)
    return confirmados
