"""Transformacao da agenda de partidas da Liquipedia.

A Liquipedia publica a agenda como HTML renderizado pela API MediaWiki, nao
como JSON. Entao aqui e o unico lugar do projeto que faz parsing de HTML - e o
motivo de o `beautifulsoup4` existir nas dependencias: regex sobre markup de
wiki quebra em silencio quando a estrutura muda, e um parser quebra alto, no
seletor que deixou de existir.

A estrutura de um confronto:

    <div class="match-info">
      <span class="timer-object" data-timestamp="1788436800">
      <div class="match-info-header">
        <div class="match-info-header-opponent ...-left">  -> equipe A
        <div class="match-info-header-scoreholder">        -> formato (Bo3)
        <div class="match-info-header-opponent">           -> equipe B
      <div class="match-info-tournament">                  -> torneio

O nome canonico do time sai do `title` do link para a pagina dele
(`/dota2/Team_Spirit_Academy` -> "Team Spirit Academy"), nao do texto visivel,
que costuma ser a abreviacao ("SpiritAc").
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

FONTE = "liquipedia"
ENDPOINT_AGENDA = "matches"

#: A pagina agrega os confrontos futuros de todos os torneios ativos.
PAGINA_AGENDA = "Liquipedia:Matches"

_FORMATO = re.compile(r"\(?(Bo\d+)\)?", re.IGNORECASE)


class PartidaAgendada(BaseModel):
    """Uma linha de `agenda_partida`: um confronto que ainda vai acontecer."""

    #: Hash estavel de (times, horario). A Liquipedia nao expoe id de partida,
    #: e sem chave natural cada coleta duplicaria a agenda inteira.
    id_externo: str
    equipe_a_nome: str
    equipe_b_nome: str
    inicio_previsto: datetime
    torneio: str | None = None
    formato: str | None = None


class ResultadoAgenda(BaseModel):
    partidas: list[PartidaAgendada] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.partidas)


def _identificador(a: str, b: str, inicio: datetime) -> str:
    """Chave natural do confronto.

    Times e horario: o mesmo par pode se enfrentar duas vezes no mesmo dia (Bo3
    de chaveamento duplo), e o horario e o que separa os dois. Se a Liquipedia
    remarcar a partida, ela entra como linha nova - o que esta certo, porque o
    horario faz parte do que se esta agendando.
    """
    bruto = f"{a}|{b}|{inicio.isoformat()}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:32]


def _nome_da_equipe(bloco) -> str | None:
    """O nome canonico do time dentro de um `match-info-header-opponent`.

    O bloco tem varios links para a mesma pagina (icone claro, icone escuro,
    nome). Todos carregam o mesmo `title`, entao o primeiro basta.
    """
    if bloco is None:
        return None
    link = bloco.find("a", title=True)
    if link is None:
        return None
    nome = link["title"].strip()
    # Time ainda indefinido aparece como "TBD" na chave.
    return nome if nome and nome.upper() != "TBD" else None


def _formato(bloco) -> str | None:
    if bloco is None:
        return None
    achado = _FORMATO.search(bloco.get_text(" ", strip=True))
    return achado.group(1).capitalize() if achado else None


def _torneio(bloco) -> str | None:
    """O nome do torneio, sem a ancora de dia que a Liquipedia acrescenta.

    O `title` vem como "EPL/Masters/2#September 3" - a parte depois do `#` e
    uma ancora para a secao do dia, nao parte do nome.
    """
    if bloco is None:
        return None
    link = bloco.find("a", title=True)
    if link is None:
        return None
    return link["title"].split("#", 1)[0].strip() or None


def parse_agenda(html: str) -> list[PartidaAgendada]:
    """HTML da pagina de partidas -> os confrontos agendados."""
    if not html:
        return []

    sopa = BeautifulSoup(html, "html.parser")
    partidas: list[PartidaAgendada] = []
    vistos: set[str] = set()

    for bloco in sopa.select("div.match-info"):
        relogio = bloco.select_one("[data-timestamp]")
        if relogio is None:
            continue

        try:
            segundos = int(relogio["data-timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        # A Liquipedia usa timestamp 0 para "horario a definir".
        if segundos <= 0:
            continue

        adversarios = bloco.select("div.match-info-header-opponent")
        if len(adversarios) < 2:
            continue

        nome_a = _nome_da_equipe(adversarios[0])
        nome_b = _nome_da_equipe(adversarios[1])
        # Confronto com lado indefinido nao da para prever, e guardar "TBD"
        # como time criaria uma equipe fantasma na reconciliacao.
        if not nome_a or not nome_b:
            continue

        inicio = datetime.fromtimestamp(segundos, tz=timezone.utc)
        id_externo = _identificador(nome_a, nome_b, inicio)
        if id_externo in vistos:
            continue
        vistos.add(id_externo)

        partidas.append(
            PartidaAgendada(
                id_externo=id_externo,
                equipe_a_nome=nome_a,
                equipe_b_nome=nome_b,
                inicio_previsto=inicio,
                torneio=_torneio(bloco.select_one("div.match-info-tournament")),
                formato=_formato(
                    bloco.select_one("div.match-info-header-scoreholder")
                ),
            )
        )

    return partidas


def transformar(payload: object) -> ResultadoAgenda:
    """Payload bruto da API MediaWiki -> agenda normalizada."""
    if not isinstance(payload, dict):
        return ResultadoAgenda()

    if "error" in payload:
        logger.warning(
            "liquipedia devolveu erro",
            extra={"erro": str(payload["error"])[:200]},
        )
        return ResultadoAgenda()

    texto = ((payload.get("parse") or {}).get("text") or {}).get("*")
    if not isinstance(texto, str):
        return ResultadoAgenda()

    return ResultadoAgenda(partidas=parse_agenda(texto))
