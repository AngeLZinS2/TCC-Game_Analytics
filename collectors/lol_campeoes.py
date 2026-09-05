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

import requests

from collectors import opgg_mcp
from collectors.base import BaseCollector, RawRecord
from config import get_settings

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

#: Data Dragon - o dado estatico OFICIAL da Riot para LoL: lore, retrato,
#: passiva e as quatro habilidades com icone e texto, tudo em pt_BR. E a CDN
#: da propria Riot (o mesmo papel da valorant-api.com para os agentes); nao ha
#: limite de taxa e cabe numa chamada so (`championFull.json`, ~2 MB).
DDRAGON_VERSOES = "https://ddragon.leagueoflegends.com/api/versions.json"
DDRAGON_CAMPEOES = (
    "https://ddragon.leagueoflegends.com/cdn/{versao}/data/pt_BR/championFull.json"
)
DDRAGON_IMG = "https://ddragon.leagueoflegends.com/cdn/{versao}/img"


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

        # O dado estatico da Riot. Falha aqui nao leva o resto: a tela ja
        # mostra nome, retrato e numeros sem a lore e as habilidades.
        try:
            registros.append(self._estatico())
        except requests.RequestException as exc:
            self.logger.warning("data dragon falhou", extra={"erro": str(exc)})

        return registros

    def _estatico(self) -> RawRecord:
        settings = get_settings()
        versao = requests.get(
            DDRAGON_VERSOES, timeout=settings.http_timeout_seconds
        ).json()[0]
        campeoes = requests.get(
            DDRAGON_CAMPEOES.format(versao=versao),
            timeout=settings.http_timeout_seconds,
        ).json()
        return RawRecord(
            fonte=self.fonte,
            endpoint="ddragon",
            identificador="estatico",
            payload={"versao": versao, "data": campeoes.get("data", {})},
        )

    def parse(self, registros: Sequence[RawRecord]) -> list[dict[str, Any]]:
        elenco: dict[str, dict[str, Any]] = {}
        melhor_rota: dict[str, dict[str, Any]] = {}
        # nome -> [{rota, play, win, ...}] - todas as rotas onde o campeao joga
        por_rota: dict[str, list[dict[str, Any]]] = {}
        # key do campeao (nome_interno) -> metadados
        estatico: dict[str, dict[str, Any]] = {}

        for registro in registros:
            if registro.identificador == "estatico" and isinstance(registro.payload, dict):
                estatico = _metadados_ddragon(registro.payload)
                continue

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
                por_rota.setdefault(nome, []).append({**bruto, "rota": rota})
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

            # Uma linha por rota onde o campeao aparece - o "por mapa" do LoL.
            # Pantheon topo e Pantheon meio sao dois conjuntos, e essa e a
            # leitura que a tela de detalhe mostra.
            campeao["por_mapa"] = [
                {
                    "mapa": ROTAS.get(r["rota"], r["rota"]),
                    "partidas": r.get("play"),
                    "vitorias": r.get("win"),
                    "metricas": _metricas(r),
                }
                for r in sorted(
                    por_rota.get(nome, []),
                    key=lambda x: x.get("role_rate") or 0,
                    reverse=True,
                )
            ]

            campeao["metadados"] = estatico.get(campeao["nome_interno"])
            campeoes.append(campeao)

        return campeoes

    def load(self, dados: list[dict[str, Any]]) -> int:
        from etl.load_lol import carregar_campeoes

        return carregar_campeoes(dados)


def _limpar_html(texto: str | None) -> str | None:
    """Tira as tags do texto de habilidade do Data Dragon.

    O texto vem com `<br>`, `<font color=...>` e afins - a tela mostra em
    paragrafo simples, entao a marcacao so atrapalha.
    """
    import re

    if not isinstance(texto, str):
        return None
    limpo = re.sub(r"<br\s*/?>", " ", texto)
    limpo = re.sub(r"<[^>]+>", "", limpo)
    # `%i:OnHit%` e afins - placeholders de template do Data Dragon no campo
    # `description` (o `tooltip` tem ainda mais).
    limpo = re.sub(r"\{\{[^}]+\}\}|%[a-z]?:?[A-Za-z]+%", "…", limpo)
    return re.sub(r"\s+", " ", limpo).strip() or None


def _metadados_ddragon(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`{key_do_campeao: metadados}` a partir do `championFull.json`.

    Mesmo formato do `metadados` do agente de Valorant: descricao, retrato,
    icone e as habilidades (passiva + Q/W/E/R) com nome, texto e icone. E por
    isso a tela de detalhe funciona igual nos dois - ela le `metadados`, nao
    sabe de que jogo e.
    """
    versao = payload.get("versao", "")
    img = DDRAGON_IMG.format(versao=versao)
    saida: dict[str, dict[str, Any]] = {}

    for key, campeao in (payload.get("data") or {}).items():
        if not isinstance(campeao, dict):
            continue

        habilidades: list[dict[str, Any]] = []
        passiva = campeao.get("passive") or {}
        if passiva.get("name"):
            habilidades.append(
                {
                    "slot": "Passiva",
                    "nome": passiva["name"],
                    "descricao": _limpar_html(passiva.get("description")),
                    "icone": f"{img}/passive/{passiva['image']['full']}"
                    if passiva.get("image", {}).get("full")
                    else None,
                    "video": None,
                }
            )
        for slot, feitico in zip(("Q", "W", "E", "R"), campeao.get("spells") or []):
            if not feitico.get("name"):
                continue
            habilidades.append(
                {
                    "slot": slot,
                    "nome": feitico["name"],
                    "descricao": _limpar_html(feitico.get("description")),
                    "icone": f"{img}/spell/{feitico['image']['full']}"
                    if feitico.get("image", {}).get("full")
                    else None,
                    "video": None,
                }
            )

        saida[key] = {
            "descricao": campeao.get("lore") or campeao.get("blurb"),
            "icone": f"{img}/champion/{campeao['image']['full']}"
            if campeao.get("image", {}).get("full")
            else None,
            # O "retrato" grande: a splash de carregamento, no mesmo caminho de
            # sempre da Riot.
            "retrato": (
                "https://ddragon.leagueoflegends.com/cdn/img/champion/loading/"
                f"{key}_0.jpg"
            ),
            "fundo": (
                "https://ddragon.leagueoflegends.com/cdn/img/champion/splash/"
                f"{key}_0.jpg"
            ),
            "habilidades": habilidades,
        }
    return saida


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
