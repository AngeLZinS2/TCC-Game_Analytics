"""Agentes do VALORANT, da valorant-api.com.

O banco ja tinha VALORANT: 87 equipes e 87 confrontos na agenda, vindos da
Liquipedia. O que faltava era o elenco - `dim_personagem` tinha 127 herois de
Dota e zero agentes. O efeito disso no assistente era pior do que uma lacuna:
perguntado sobre Valorant ele respondia que "Valorant nao esta no nosso banco",
o que e falso, e caia no conhecimento geral.

**Por que nao a API oficial da Riot.** A `val/content/v1/contents` responde 401
sem chave, exige aprovacao de projeto e, mesmo com chave, devolve so nomes e
ids localizados - nao devolve funcao nem habilidade. A valorant-api.com e um
espelho comunitario do proprio cliente do jogo (le os assets do jogo), sem
chave, com os campos que a pergunta usa: funcao e habilidades, em portugues.

**O que esta fonte NAO responde.** Ela e um CATALOGO, nao um placar. Nao ha
taxa de escolha, taxa de vitoria nem nada que sustente "o melhor agente do meta
atual" - isso exigiria dado de partida competitiva de Valorant, que esta
plataforma nao coleta. Quem monta o contexto tem que dizer isso: o elenco
responde "quem existe e o que faz", nunca "quem esta forte agora".
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import requests

from collectors import opgg_mcp
from collectors.base import BaseCollector, RawRecord
from config import get_settings

logger = logging.getLogger(__name__)

URL_AGENTES = "https://valorant-api.com/v1/agents"

#: O codigo do jogo em `dim_jogo`, semeado pela migration das wikis.
JOGO = "valorant"

#: Idioma dos nomes de funcao e habilidade. A pergunta chega em portugues
#: ("quais agentes sao duelistas"), entao o contexto tambem tem que estar.
IDIOMA = "pt-BR"


class AgentesValorantCollector(BaseCollector[list[dict[str, Any]]]):
    """Elenco completo de agentes jogaveis, com funcao e habilidades."""

    fonte = "valorant_agentes"

    def collect(self) -> list[RawRecord]:
        registros = [self._elenco()]

        # A estatistica e de outra fonte e pode faltar sem levar o elenco
        # junto: sem ela a tela mostra quem existe e diz que falta o numero,
        # que e melhor do que nao mostrar agente nenhum.
        if get_settings().opgg_enabled:
            try:
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint="valorant_list_agent_statistics",
                        identificador="estatisticas",
                        payload=opgg_mcp.estatisticas_agentes_valorant(),
                    )
                )
            except opgg_mcp.OpggIndisponivel as exc:
                self.logger.warning("estatistica do opgg falhou", extra={"erro": str(exc)})

        return registros

    def _elenco(self) -> RawRecord:
        settings = get_settings()
        resposta = requests.get(
            URL_AGENTES,
            # `isPlayableCharacter` tira o duplicado do Sova que a API mantem
            # por compatibilidade - sem ele o elenco vem com um agente a mais
            # que nao existe no jogo.
            params={"isPlayableCharacter": "true", "language": IDIOMA},
            timeout=settings.http_timeout_seconds,
            headers={"Accept": "application/json"},
        )
        resposta.raise_for_status()
        return RawRecord(
            fonte=self.fonte,
            endpoint=URL_AGENTES,
            identificador="agentes",
            payload=resposta.json(),
        )

    def parse(self, registros: Sequence[RawRecord]) -> list[dict[str, Any]]:
        agentes: dict[str, dict[str, Any]] = {}
        estatisticas: dict[str, dict[str, Any]] = {}

        for registro in registros:
            if registro.identificador == "estatisticas":
                for linha in registro.payload or []:
                    if isinstance(linha, dict) and linha.get("id_externo"):
                        estatisticas[linha["id_externo"]] = linha
                continue

            payload = registro.payload
            if not isinstance(payload, dict):
                continue
            for bruto in payload.get("data") or []:
                agente = _normalizar_agente(bruto)
                if agente is not None:
                    agentes[agente["id_externo"]] = agente

        # O casamento e por uuid: o OP.GG usa o MESMO identificador de agente
        # que a valorant-api.com, entao nao ha heuristica de nome no meio.
        for id_externo, agente in agentes.items():
            numeros = estatisticas.get(id_externo)
            if numeros:
                agente["partidas"] = numeros.get("partidas")
                agente["vitorias"] = numeros.get("vitorias")
                agente["metricas"] = numeros.get("metricas") or {}

        return list(agentes.values())

    def load(self, dados: list[dict[str, Any]]) -> int:
        from etl.load_valorant import carregar_agentes, carregar_estatisticas

        carregados = carregar_agentes(dados)
        carregar_estatisticas(dados)
        return carregados


def _normalizar_agente(bruto: Any) -> dict[str, Any] | None:
    """Um agente da API no formato de `dim_personagem`, ou `None` se incompleto.

    O `uuid` vira `id_externo` por ser o que a fonte usa como chave - o mesmo
    criterio do heroi da OpenDota. Nome muda de traducao, uuid nao.
    """
    if not isinstance(bruto, dict):
        return None

    uuid = bruto.get("uuid")
    nome = bruto.get("displayName")
    if not isinstance(uuid, str) or not isinstance(nome, str) or not nome.strip():
        return None

    papel = (bruto.get("role") or {}).get("displayName")

    # `developerName` e o nome interno do agente no cliente ("Clay" e o Raze,
    # "Pandemic" e a Viper). Mesmo papel do `npc_dota_hero_*` no Dota: e por
    # ele que se casa com dado de outra fonte quando o nome exibido diverge.
    return {
        "id_externo": uuid,
        "nome": nome.strip()[:64],
        "nome_interno": (bruto.get("developerName") or None),
        "papel": papel.strip()[:32] if isinstance(papel, str) and papel.strip() else None,
        # Fica fora de `dim_personagem` (nao ha coluna), mas o coletor devolve
        # pra quem quiser montar contexto sem uma segunda chamada.
        "habilidades": [
            h.get("displayName")
            for h in (bruto.get("abilities") or [])
            if isinstance(h, dict) and h.get("displayName")
        ],
    }
