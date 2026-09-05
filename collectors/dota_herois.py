"""Dado estatico dos herois de Dota 2, do datafeed oficial da Valve.

Os herois ja existem em `dim_personagem` - eles entram pela ingestao de
partidas da OpenDota. O que faltava para a tela de detalhe e a parte que NAO
muda: a lore e as habilidades com nome, texto e icone. A OpenDota nao serve
isso; o datafeed do proprio dota2.com serve, em portugues.

Sao 128 chamadas por rodada (uma lista + uma por heroi). O datafeed e o mesmo
que o site oficial usa, entao a cortesia aqui e a mesma de sempre: uma pausa
curta entre as chamadas, e a rodada e semanal.

**O que este coletor NAO traz.** Nao ha estatistica por posicao. Dota tem
posicoes (1 a 5), mas a OpenDota gratuita nao publica winrate por posicao e as
nossas ~100 partidas coletadas nao dao amostra para calcular. A tela de detalhe
mostra, para o heroi, so o agregado que ja temos das nossas partidas -
diferente do Valorant (por mapa) e do LoL (por rota), porque a fonte e outra.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Sequence

import requests

from collectors.base import BaseCollector, RawRecord
from config import get_settings

logger = logging.getLogger(__name__)

#: O codigo do jogo em `dim_jogo`.
JOGO = "dota2"

URL_LISTA = "https://www.dota2.com/datafeed/herolist"
URL_HEROI = "https://www.dota2.com/datafeed/herodata"

#: A CDN da Valve, os mesmos caminhos que a tela ja usa para o retrato.
CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react"

PAUSA = 0.3

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
            headers={"User-Agent": "Mozilla/5.0 (GamingAnalyticsTCC)"},
        )
        lista.raise_for_status()
        ids = [
            h["id"]
            for h in lista.json().get("result", {}).get("data", {}).get("heroes", [])
            if isinstance(h.get("id"), int)
        ]

        registros: list[RawRecord] = []
        for hero_id in ids:
            try:
                resposta = requests.get(
                    URL_HEROI,
                    params={"language": "brazilian", "hero_id": hero_id},
                    timeout=settings.http_timeout_seconds,
                    headers={"User-Agent": "Mozilla/5.0 (GamingAnalyticsTCC)"},
                )
                resposta.raise_for_status()
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=URL_HEROI,
                        identificador=str(hero_id),
                        payload=resposta.json(),
                    )
                )
            except requests.RequestException as exc:
                # Um heroi que falha nao leva os outros - o detalhe dele cai no
                # que ja temos (retrato + numeros das nossas partidas).
                self.logger.warning(
                    "herodata falhou", extra={"hero_id": hero_id, "erro": str(exc)}
                )
            time.sleep(PAUSA)

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> list[dict[str, Any]]:
        herois: list[dict[str, Any]] = []
        for registro in registros:
            dados = registro.payload
            if not isinstance(dados, dict):
                continue
            for heroi in (
                dados.get("result", {}).get("data", {}).get("heroes", [])
            ):
                normalizado = _normalizar_heroi(heroi)
                if normalizado is not None:
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
