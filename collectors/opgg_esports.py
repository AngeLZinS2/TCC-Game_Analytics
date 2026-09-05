"""Confrontos profissionais de League of Legends, via servidor MCP do OP.GG.

A tela de Partidas cobre 13 esportes cadastrados e **doze deles nao tem partida
nenhuma**: so Dota 2 tem, porque so a OpenDota entrega partida. Os outros vivem
de equipes e agenda da Liquipedia. League of Legends estava pior ainda - zero
de tudo, e por isso nem aparecia no seletor de jogo.

Este coletor traz confrontos de LoL com placar, liga, horario e escudo dos
times. Sao as mesmas duas chamadas do `esports.op.gg`: a janela de jogos por
vir e a de jogos ja decididos.

**Onde isso cai no schema, e por que importa.** Em `agenda_partida`, a mesma
tabela do ticker da Liquipedia - o docstring dela ja diz que e a fonte que
alimenta o ajuste de forcas (Bradley-Terry) para todo jogo que nao e Dota 2.
Entao carregar aqui nao enche so uma tela: LoL passa a ter equipes, confrontos,
resultados e previsao de confronto, tudo pelo caminho que ja existia.

**O que este coletor NAO faz.** Nao ha dado por jogador, por campeao nem por
partida individual da serie - o OP.GG entrega o placar da serie (3x1), nao o
que aconteceu dentro dela. Entao LoL continua sem `fato_partida_jogador`, e a
tela de Partidas mostra para ele o que a agenda tem, nao o detalhe que Dota
tem. Fingir o contrario seria pior do que a lacuna.

**Sobre o namespace do `id_externo`.** As equipes da Liquipedia usam o `teamid`
dela como `id_externo`; as do OP.GG usam o id do OP.GG, e os dois sao inteiros
pequenos. Sem prefixo, o dia em que alguem coletar a wiki de LoL fundiria dois
times diferentes que por acaso tem o mesmo numero. Dai o `opgg:` em tudo que
entra por aqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from collectors import opgg_mcp
from collectors.base import BaseCollector, RawRecord

logger = logging.getLogger(__name__)

FERRAMENTA = "lol_esports_list_schedules"

#: O codigo do jogo em `dim_jogo`, semeado pela migration das wikis.
JOGO = "leagueoflegends"

#: Prefixo de namespace - ver o docstring do modulo.
PREFIXO = "opgg:"

#: O servidor devolve a janela inteira de jogos por vir (~67) independente do
#: valor, mas trava os resultados em 50. Pedir mais nao custa nem traz mais;
#: o historico cresce pela repeticao das rodadas, nao pelo tamanho do pedido.
LIMITE = 50


@dataclass
class EquipeOpgg:
    id_externo: str
    nome: str
    tag: str | None
    logo_url: str | None


@dataclass
class ConfrontoOpgg:
    id_externo: str
    equipe_a_nome: str
    equipe_b_nome: str
    equipe_a_externo: str
    equipe_b_externo: str
    inicio_previsto: datetime
    torneio: str | None
    formato: str | None
    vitoria_a: bool | None
    placar_a: int | None
    placar_b: int | None


@dataclass
class ResultadoOpggEsports:
    equipes: list[EquipeOpgg] = field(default_factory=list)
    confrontos: list[ConfrontoOpgg] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Quantos itens o parse produziu.

        `total` e nao `__len__`: e o atributo que `collectors.base._tamanho`
        procura para o resumo da execucao. Com `__len__` o resultado nao e uma
        `Sequence`, cai no ramo final e a CLI relatava "processados 1" tendo
        normalizado 67.
        """
        return len(self.confrontos)


class OpggEsportsCollector(BaseCollector[ResultadoOpggEsports]):
    """Agenda e resultados do cenario profissional de LoL."""

    fonte = "opgg_esports"

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []
        for modo in ("schedule", "result"):
            try:
                dados = opgg_mcp.chamar_ferramenta(
                    FERRAMENTA, {"mode": modo, "limit": LIMITE}
                )
            except opgg_mcp.OpggIndisponivel as exc:
                # Uma das duas janelas pode falhar sem levar a outra junto: ter
                # so os resultados ja e melhor do que nao ter nada.
                self.logger.warning(
                    "janela do opgg falhou", extra={"modo": modo, "erro": str(exc)}
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=FERRAMENTA,
                    identificador=modo,
                    payload=dados,
                )
            )
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoOpggEsports:
        resultado = ResultadoOpggEsports()
        equipes: dict[str, EquipeOpgg] = {}
        confrontos: dict[str, ConfrontoOpgg] = {}

        for registro in registros:
            for bruto in registro.payload or []:
                convertido = _converter(bruto, equipes)
                if convertido is not None:
                    # Um confronto pode aparecer nas DUAS janelas quando termina
                    # entre as duas chamadas. A versao com resultado vence.
                    anterior = confrontos.get(convertido.id_externo)
                    if anterior is None or convertido.vitoria_a is not None:
                        confrontos[convertido.id_externo] = convertido

        resultado.equipes = list(equipes.values())
        resultado.confrontos = list(confrontos.values())
        return resultado

    def load(self, dados: ResultadoOpggEsports) -> int:
        from etl.load_opgg_esports import carregar

        return carregar(dados)


def _time(bruto: Any, equipes: dict[str, EquipeOpgg]) -> EquipeOpgg | None:
    """Registra a equipe no acumulador e devolve, ou `None` se veio incompleta."""
    if not isinstance(bruto, dict):
        return None
    id_bruto = bruto.get("id")
    nome = bruto.get("name")
    if id_bruto is None or not isinstance(nome, str) or not nome.strip():
        return None

    id_externo = f"{PREFIXO}{id_bruto}"
    equipe = EquipeOpgg(
        id_externo=id_externo,
        nome=nome.strip()[:120],
        tag=(bruto.get("acronym") or None),
        logo_url=(bruto.get("image_url") or None),
    )
    equipes.setdefault(id_externo, equipe)
    return equipe


def _converter(bruto: Any, equipes: dict[str, EquipeOpgg]) -> ConfrontoOpgg | None:
    if not isinstance(bruto, dict):
        return None

    id_bruto = bruto.get("id")
    casa = _time(bruto.get("homeTeam"), equipes)
    fora = _time(bruto.get("awayTeam"), equipes)
    if id_bruto is None or casa is None or fora is None:
        # Chaveamento sem os dois lados definidos ("vencedor da semi 1") nao e
        # confronto ainda - guardar viraria uma linha com time fantasma.
        return None

    inicio = _instante(bruto.get("scheduledAt"))
    if inicio is None:
        return None

    terminado = bruto.get("status") == "FINISHED"
    placar_a = bruto.get("homeScore")
    placar_b = bruto.get("awayScore")
    vitoria_a: bool | None = None
    if terminado and isinstance(placar_a, int) and isinstance(placar_b, int):
        # Empate existe em fase de grupos de alguns formatos: fica sem
        # vencedor em vez de virar derrota do time de fora.
        if placar_a != placar_b:
            vitoria_a = placar_a > placar_b

    jogos = bruto.get("numberOfGames")
    return ConfrontoOpgg(
        id_externo=f"{PREFIXO}{id_bruto}",
        equipe_a_nome=casa.nome,
        equipe_b_nome=fora.nome,
        equipe_a_externo=casa.id_externo,
        equipe_b_externo=fora.id_externo,
        inicio_previsto=inicio,
        torneio=(bruto.get("league") or None),
        formato=f"Bo{jogos}" if isinstance(jogos, int) and jogos > 0 else None,
        vitoria_a=vitoria_a,
        placar_a=placar_a if isinstance(placar_a, int) and terminado else None,
        placar_b=placar_b if isinstance(placar_b, int) and terminado else None,
    )


def _instante(bruto: Any) -> datetime | None:
    """ISO 8601 com `Z` -> datetime ciente de fuso.

    `fromisoformat` do Python so aceita `Z` a partir do 3.11; a troca por
    `+00:00` mantem o parse explicito em vez de depender da versao.
    """
    if not isinstance(bruto, str) or not bruto:
        return None
    try:
        momento = datetime.fromisoformat(bruto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)
