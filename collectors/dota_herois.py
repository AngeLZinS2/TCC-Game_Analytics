"""Dado estatico e guia de itens dos herois de Dota 2.

Os herois ja existem em `dim_personagem` - eles entram pela ingestao de
partidas da OpenDota. O que faltava para a tela de detalhe:

- **A parte que NAO muda** (lore, habilidades com nome/texto/icone): o datafeed
  oficial do dota2.com serve, em portugues. Uma lista + uma chamada por heroi.
- **O guia de itens do meta atual**: a OpenDota publica `itemPopularity` por
  heroi - o que a comunidade compra em cada fase (inicio, comeco, meio, fim).
  Uma chamada por heroi. Os nomes em pt-BR vem do `itemlist` da Valve; o icone,
  da CDN da Steam.

Sao ~256 chamadas por rodada (lista + itemlist + herodata e itemPopularity por
heroi). Datafeed e OpenDota tem, cada um, o seu intervalo minimo; a rodada e
semanal.

**O que este coletor NAO traz.** Nao ha estatistica por posicao nem ordem de
habilidade agregada: a OpenDota gratuita nao publica winrate por posicao, e a
ordem de skill so existe partida a partida (as nossas ~100 nao dao amostra). A
tela mostra, do heroi, o agregado das nossas partidas e o guia de itens -
diferente do Valorant (por mapa) e do LoL (por rota, com build completa),
porque a fonte e outra.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Sequence

import requests

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient, RespostaInvalidaError
from config import get_settings

logger = logging.getLogger(__name__)

#: O codigo do jogo em `dim_jogo`.
JOGO = "dota2"

URL_LISTA = "https://www.dota2.com/datafeed/herolist"
URL_HEROI = "https://www.dota2.com/datafeed/herodata"
URL_ITENS_VALVE = "https://www.dota2.com/datafeed/itemlist"

#: A OpenDota - a mesma fonte das nossas partidas de Dota. `itemPopularity` e a
#: contagem de quem comprou cada item, por fase da partida.
URL_OPENDOTA = "https://api.opendota.com/api"

#: A CDN da Valve, os mesmos caminhos que a tela ja usa para o retrato.
CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react"
CDN_STEAM = "https://cdn.cloudflare.steamstatic.com"

PAUSA = 0.3

#: As fases de `itemPopularity` e o rotulo pt-BR de cada uma. A ordem importa:
#: e a linha do tempo da partida.
FASES_DOTA: list[tuple[str, str]] = [
    ("start_game_items", "Itens iniciais"),
    ("early_game_items", "Comeco de jogo"),
    ("mid_game_items", "Meio de jogo"),
    ("late_game_items", "Fim de jogo"),
]

#: Quantos itens mostrar por fase, e o minimo de compras para um item contar -
#: abaixo disso e cauda, nao meta.
ITENS_POR_FASE = 6
MIN_COMPRAS = 5

#: A descricao pt-BR de cada habilidade comeca com "Em inglês: <b>...</b>" e o
#: nome em ingles antes do texto de verdade. Tira isso e o resto da marcacao.
_PREFIXO_INGLES = re.compile(r"^\s*Em ingl[eê]s:.*?</b>\s*", re.S)


def _limpar(texto: str | None) -> str | None:
    if not isinstance(texto, str):
        return None
    limpo = _PREFIXO_INGLES.sub("", texto)
    limpo = re.sub(r"<br\s*/?>", " ", limpo)
    limpo = re.sub(r"<[^>]+>", "", limpo)
    # `%pop_damage_delay%`, `%damage_stat_bonus_pct%%%`, `%AbilityCharges%` -
    # tokens de template que a Valve nao resolve no desc_loc; aparecem em minuscula
    # (valor que escala com atributo) e em CamelCase (contagem de cargas).
    limpo = re.sub(r"%+[A-Za-z_:]+%+", "…", limpo)
    return re.sub(r"\s+", " ", limpo).strip() or None


class HeroisDotaCollector(BaseCollector[list[dict[str, Any]]]):
    """Lore e habilidades de cada heroi de Dota, do datafeed da Valve."""

    fonte = "dota_herois"

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        lista = requests.get(
            URL_LISTA,
            params={"language": "brazilian"},
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "Mozilla/5.0 (PlayDB-TCC; +https://playdb.info)"},
        )
        lista.raise_for_status()
        ids = [
            h["id"]
            for h in lista.json().get("result", {}).get("data", {}).get("heroes", [])
            if isinstance(h.get("id"), int)
        ]

        registros: list[RawRecord] = []

        # O contexto do guia de itens: nome pt-BR (Valve) e icone (Steam) por
        # id. Falha aqui nao leva o resto - o guia sai sem, os herois seguem.
        try:
            registros.append(self._contexto_itens(settings))
        except requests.RequestException as exc:
            self.logger.warning("itemlist da valve falhou", extra={"erro": str(exc)})

        opendota = RateLimitedClient(
            nome="opendota",
            intervalo_minimo=settings.opendota_rate_limit_seconds,
            max_retries=settings.http_max_retries,
            timeout=settings.http_timeout_seconds,
        )
        if settings.opendota_api_key:
            opendota.session.headers["Authorization"] = (
                f"Bearer {settings.opendota_api_key}"
            )

        for hero_id in ids:
            heroi_payload: dict[str, Any] | None = None
            try:
                resposta = requests.get(
                    URL_HEROI,
                    params={"language": "brazilian", "hero_id": hero_id},
                    timeout=settings.http_timeout_seconds,
                    headers={"User-Agent": "Mozilla/5.0 (PlayDB-TCC; +https://playdb.info)"},
                )
                resposta.raise_for_status()
                heroi_payload = resposta.json()
            except requests.RequestException as exc:
                # Um heroi que falha nao leva os outros - o detalhe dele cai no
                # que ja temos (retrato + numeros das nossas partidas).
                self.logger.warning(
                    "herodata falhou", extra={"hero_id": hero_id, "erro": str(exc)}
                )
            time.sleep(PAUSA)

            popularidade: Any = None
            try:
                popularidade = opendota.get_json(
                    f"{URL_OPENDOTA}/heroes/{hero_id}/itemPopularity"
                )
            except (requests.RequestException, RespostaInvalidaError) as exc:
                self.logger.warning(
                    "itemPopularity falhou",
                    extra={"hero_id": hero_id, "erro": str(exc)},
                )

            if heroi_payload is not None:
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=URL_HEROI,
                        identificador=str(hero_id),
                        payload={"heroi": heroi_payload, "itens": popularidade},
                    )
                )

        return registros

    def _contexto_itens(self, settings) -> RawRecord:
        """`{id -> nome pt-BR, id -> icone}` para montar o guia de itens.

        O nome vem do `itemlist` da Valve (uma chamada, em portugues); o icone
        sai do `name` interno (`item_blink` -> `.../items/blink.png`).
        """
        resposta = requests.get(
            URL_ITENS_VALVE,
            params={"language": "brazilian"},
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "Mozilla/5.0 (PlayDB-TCC; +https://playdb.info)"},
        )
        resposta.raise_for_status()
        nomes: dict[str, str] = {}
        icones: dict[str, str] = {}
        bruto = resposta.json().get("result", {}).get("data", {})
        for item in bruto.get("itemabilities", []) or []:
            id_item = item.get("id")
            nome = item.get("name_loc") or item.get("name_english_loc")
            interno = item.get("name") or ""
            if not isinstance(id_item, int) or not nome:
                continue
            nomes[str(id_item)] = nome
            curto = interno.removeprefix("item_")
            if curto:
                icones[str(id_item)] = f"{CDN}/items/{curto}.png"
        return RawRecord(
            fonte=self.fonte,
            endpoint=URL_ITENS_VALVE,
            identificador="itens_ctx",
            payload={"nomes": nomes, "icones": icones},
        )

    def parse(self, registros: Sequence[RawRecord]) -> list[dict[str, Any]]:
        nomes_item: dict[str, str] = {}
        icones_item: dict[str, str] = {}
        for registro in registros:
            if registro.identificador == "itens_ctx" and isinstance(
                registro.payload, dict
            ):
                nomes_item = registro.payload.get("nomes") or {}
                icones_item = registro.payload.get("icones") or {}

        herois: list[dict[str, Any]] = []
        for registro in registros:
            dados = registro.payload
            if not isinstance(dados, dict) or "heroi" not in dados:
                continue
            heroi_bruto = dados.get("heroi")
            if not isinstance(heroi_bruto, dict):
                continue
            guia = _montar_guia_dota(dados.get("itens"), nomes_item, icones_item)
            for heroi in (
                heroi_bruto.get("result", {}).get("data", {}).get("heroes", [])
            ):
                normalizado = _normalizar_heroi(heroi)
                if normalizado is None:
                    continue
                if guia is not None:
                    normalizado["metadados"]["guia"] = guia
                herois.append(normalizado)
        return herois

    def load(self, dados: list[dict[str, Any]]) -> int:
        from etl.load_dota_herois import carregar_herois

        return carregar_herois(dados)


def _normalizar_heroi(bruto: Any) -> dict[str, Any] | None:
    if not isinstance(bruto, dict):
        return None
    hero_id = bruto.get("id")
    npc = bruto.get("name")  # "npc_dota_hero_pudge"
    nome = bruto.get("name_loc")
    if not isinstance(hero_id, int) or not isinstance(npc, str) or not nome:
        return None

    curto = npc.removeprefix("npc_dota_hero_")
    habilidades = []
    for ab in bruto.get("abilities") or []:
        if not isinstance(ab, dict) or ab.get("is_item"):
            continue
        nome_ab = ab.get("name_loc")
        interno = ab.get("name")
        # "generic_hidden" e placeholder de slot vazio - nao e habilidade.
        if not nome_ab or not isinstance(interno, str) or "generic_hidden" in interno:
            continue
        habilidades.append(
            {
                "slot": "Passiva" if ab.get("ability_is_innate") else None,
                "nome": nome_ab,
                "descricao": _limpar(ab.get("desc_loc")),
                "icone": f"{CDN}/abilities/{interno}.png",
                "video": None,
            }
        )

    return {
        # O `id_externo` de `dim_personagem` no Dota e o id numerico da Valve,
        # o mesmo que a OpenDota usa - entao o upsert casa direto.
        "id_externo": str(hero_id),
        "nome": nome[:64],
        "nome_interno": npc[:64],
        "metadados": {
            "descricao": _limpar(bruto.get("bio_loc")),
            "icone": f"{CDN}/heroes/icons/{curto}.png",
            "retrato": f"{CDN}/heroes/{curto}.png",
            "fundo": f"{CDN}/heroes/{curto}.png",
            "habilidades": habilidades,
        },
    }


def _montar_guia_dota(
    popularidade: Any,
    nomes_item: dict[str, str],
    icones_item: dict[str, str],
) -> dict[str, Any] | None:
    """O guia de itens do heroi, do `itemPopularity` da OpenDota.

    Uma fase (`{titulo, itens, nota}`) por etapa da partida, com os
    `ITENS_POR_FASE` itens mais comprados que passaram de `MIN_COMPRAS`. Sem
    ordem de habilidade: a fonte nao publica agregado disso (a nota explica).
    """
    if not isinstance(popularidade, dict):
        return None

    grupos: list[dict[str, Any]] = []
    for chave, titulo in FASES_DOTA:
        contagem = popularidade.get(chave)
        if not isinstance(contagem, dict) or not contagem:
            continue
        ordenado = sorted(
            (
                (id_item, n)
                for id_item, n in contagem.items()
                if isinstance(n, (int, float)) and n >= MIN_COMPRAS
            ),
            key=lambda par: par[1],
            reverse=True,
        )[:ITENS_POR_FASE]
        itens = [
            {"nome": nomes_item.get(str(id_item)), "icone": icones_item.get(str(id_item))}
            for id_item, _ in ordenado
            if nomes_item.get(str(id_item))
        ]
        if itens:
            grupos.append({"titulo": titulo, "itens": itens, "nota": None})

    if not grupos:
        return None

    return {
        "fonte": "OpenDota",
        "rota": None,
        "atualizado_em": _hoje(),
        "grupos": grupos,
        "feiticos": [],
        "runa_primaria": None,
        "runa_secundaria": None,
        "ordem_habilidades": [],
        "prioridade_habilidades": [],
        "combos": [],
        "nota_habilidades": (
            "A OpenDota gratuita nao publica a ordem de habilidades agregada; "
            "o guia mostra so os itens do meta."
        ),
    }


def _hoje() -> str:
    from datetime import date

    return date.today().isoformat()
