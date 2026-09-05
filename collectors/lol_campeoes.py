"""Campeoes de League of Legends e o desempenho deles por rota, via OP.GG.

LoL nao aparecia na tela de personagens por um motivo simples: `dim_personagem`
tinha 127 herois de Dota, 29 agentes de Valorant e ZERO campeoes. Nunca foram
coletados. O seletor esconde jogo sem personagem, entao ele nem era oferecido.

**A rota e o eixo da estatistica aqui, e isso e proprio do jogo.** Um campeao
nao tem "um" desempenho: Pantheon no topo e Pantheon no meio sao dois conjuntos
de numeros diferentes, e o proprio OP.GG publica assim - uma tabela por rota.
Este coletor busca as cinco e guarda, para cada campeao, a rota em que ele mais
e jogado (`role_rate` mais alto) junto dos numeros dessa rota. E a leitura que
responde "como esse campeao esta?" sem inventar uma media entre rotas que
ninguem joga.

**As metricas sao as de League, nao as de outro jogo.** Taxa de banimento nao
existe em Dota nem em Valorant e e das leituras mais fortes do meta - um
campeao com 40% de ban esta forte mesmo com winrate mediano, porque quase
metade das partidas nao deixa ele ser escolhido. `tier` e o rank que o OP.GG
publica (1 e o melhor), e vem junto por ser o resumo que a comunidade usa.

Sao seis chamadas por rodada: uma do elenco e cinco de rota.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from collectors import opgg_mcp
from collectors.base import BaseCollector, RawRecord

logger = logging.getLogger(__name__)

#: O codigo do jogo em `dim_jogo`, semeado pela migration das wikis.
JOGO = "leagueoflegends"

#: As rotas, e como cada uma se chama em portugues. A chave e o que a
#: ferramenta aceita; o valor vira `dim_personagem.papel`, do mesmo jeito que
#: "Duelista" e "Sentinela" no Valorant.
ROTAS: dict[str, str] = {
    "TOP": "Topo",
    "JUNGLE": "Selva",
    "MID": "Meio",
    "ADC": "Atirador",
    "SUPPORT": "Suporte",
}

FERRAMENTA_ELENCO = "lol_list_champions"
FERRAMENTA_ROTA = "lol_list_lane_meta_champions"

#: O idioma dos nomes. "Nunu & Willump" em pt_BR, "Nunu & Willump" em en_US -
#: varios sao iguais, mas alguns mudam, e a tela e em portugues.
IDIOMA = "pt_BR"


class CampeoesLolCollector(BaseCollector[list[dict[str, Any]]]):
    """Elenco de campeoes e o desempenho na rota principal de cada um."""

    fonte = "lol_campeoes"

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []

        # Sem tratamento: falhar aqui derruba a rodada, e e o certo - sem o
        # elenco nao ha personagem a cadastrar, e as cinco chamadas de rota
        # seriam trabalho para jogar fora.
        registros.append(
            RawRecord(
                fonte=self.fonte,
                endpoint=FERRAMENTA_ELENCO,
                identificador="elenco",
                payload=opgg_mcp.chamar_ferramenta(
                    FERRAMENTA_ELENCO, {"lang": IDIOMA, "desired_output_fields": []}
                ),
            )
        )

        for rota in ROTAS:
            try:
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=FERRAMENTA_ROTA,
                        identificador=f"rota:{rota}",
                        payload=opgg_mcp.chamar_ferramenta(
                            FERRAMENTA_ROTA,
                            {"position": rota, "desired_output_fields": []},
                        ),
                    )
                )
            except opgg_mcp.OpggIndisponivel as exc:
                # Uma rota fora do ar nao leva as outras quatro: o campeao que
                # so aparece nela fica sem numero, os demais seguem.
                self.logger.warning(
                    "rota do opgg falhou", extra={"rota": rota, "erro": str(exc)}
                )

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> list[dict[str, Any]]:
        elenco: dict[str, dict[str, Any]] = {}
        melhor_rota: dict[str, dict[str, Any]] = {}

        for registro in registros:
            texto = registro.payload
            if not isinstance(texto, str):
                continue

            if registro.identificador == "elenco":
                for bruto in opgg_mcp.analisar_notacao_compacta(texto, "Champion"):
                    nome = bruto.get("name")
                    chave = bruto.get("key")
                    if not isinstance(nome, str) or not isinstance(chave, str):
                        continue
                    identificador = bruto.get("champion_id")
                    if not isinstance(identificador, int):
                        continue

                    # A fonte devolve 236 linhas para 173 campeoes: 63 sao
                    # variantes de modo de jogo, com o MESMO nome exibido e id
                    # 60000+ ("Jade_Annie", 60001). Ficar com a ultima punha
                    # `Jade_Annie` no lugar da Annie. O canonico e o de MENOR
                    # id - criterio que nao depende do prefixo do momento.
                    anterior = elenco.get(nome)
                    if anterior is not None and int(anterior["id_externo"]) <= identificador:
                        continue

                    elenco[nome] = {
                        # `champion_id` e a chave estavel da Riot; `key` e o
                        # nome interno ("MonkeyKing" e o Wukong), mesmo papel
                        # do `npc_dota_hero_*`.
                        "id_externo": str(identificador),
                        "nome": nome[:64],
                        "nome_interno": chave[:64],
                    }
                continue

            rota = registro.identificador.removeprefix("rota:")
            # A classe da notacao e o nome da rota capitalizado: `Mid`, `Top`.
            for bruto in opgg_mcp.analisar_notacao_compacta(texto, rota.capitalize()):
                nome = bruto.get("champion")
                if not isinstance(nome, str):
                    continue
                atual = melhor_rota.get(nome)
                # A rota principal e a de maior `role_rate` - a proporcao das
                # partidas do campeao que acontecem nela. Media entre rotas
                # descreveria um campeao que ninguem joga.
                if atual is None or (bruto.get("role_rate") or 0) > (
                    atual.get("role_rate") or 0
                ):
                    melhor_rota[nome] = {**bruto, "rota": rota}

        campeoes: list[dict[str, Any]] = []
        for nome, campeao in elenco.items():
            numeros = melhor_rota.get(nome)
            if numeros is not None:
                campeao["papel"] = ROTAS.get(numeros["rota"], numeros["rota"])
                campeao["partidas"] = numeros.get("play")
                campeao["vitorias"] = numeros.get("win")
                campeao["metricas"] = _metricas(numeros)
            campeoes.append(campeao)

        return campeoes

    def load(self, dados: list[dict[str, Any]]) -> int:
        from etl.load_lol import carregar_campeoes

        return carregar_campeoes(dados)


def _fracao_para_percentual(valor: Any) -> float | None:
    """O OP.GG publica taxa como fracao (0.51). A tela mostra em pontos."""
    if not isinstance(valor, (int, float)):
        return None
    return round(100 * float(valor), 1)


def _metricas(bruto: dict[str, Any]) -> dict[str, float | None]:
    return {
        "pick_rate": _fracao_para_percentual(bruto.get("pick_rate")),
        # Nao existe em Dota nem em Valorant, e e das leituras mais fortes do
        # meta de League: um campeao com 40% de ban esta forte mesmo com
        # winrate mediano - quase metade das partidas nao deixa escolhe-lo.
        "ban_rate": _fracao_para_percentual(bruto.get("ban_rate")),
        "role_rate": _fracao_para_percentual(bruto.get("role_rate")),
        "kda": bruto.get("kda") if isinstance(bruto.get("kda"), (int, float)) else None,
        # 1 e o melhor. A tela sabe disso por `maior_melhor=False` no perfil.
        "tier": bruto.get("tier") if isinstance(bruto.get("tier"), int) else None,
    }
