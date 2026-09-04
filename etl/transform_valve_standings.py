"""Markdown do Regional Standings da Valve -> linhas de ranking validadas.

**A fonte.** O repositorio `ValveSoftware/counter-strike_regional_standings`
publica, todo mes, uma tabela markdown com o ranking mundial de CS2. Cada
linha e uma equipe, com posicao, pontos e o elenco:

    | Standing | Points | Team Name | Roster                        | ...      |
    | :- | -: | :- | :- | :- |
    | 1        |   2011 | Spirit    | donk, magixx, sh1ro, ...      | [details]|
    | 2        |   1950 | Falcons   | karrigan, kyousuke, m0NESY, ..| [details]|

**Por que markdown e nao um regex de uma linha.** As celulas tem largura fixa
por padding de espacos, e o roster tem virgulas e ate `-` no fim de nick
(`huNter-`). O parser aqui e simples de proposito - split por `|`, strip de
cada celula - mas trata o cabecalho, a linha de alinhamento (`:-`) e linhas
que nao sejam de dados sem se confundir.

**O nome.** A Valve escreve nomes curtos e limpos ("Spirit", "MOUZ", "Natus
Vincere", "The MongolZ") - proximos do que a Liquipedia usa como titulo de
pagina. A reconciliacao com `dim_equipe` fica em `load_valve_standings.py`,
reaproveitando a escada de `load_liquipedia.py`.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

FONTE = "valve"
ENDPOINT = "regional-standings"

#: `standings_global_2026_08_03.md` -> date(2026, 8, 3). O nome do arquivo e a
#: unica fonte confiavel da data de referencia: o titulo dentro do md tras
#: `2026_08_03` tambem, mas o do arquivo e o que a URL garante.
_DATA_NO_NOME = re.compile(r"(\d{4})_(\d{2})_(\d{2})")

#: `### Standings as of 2026_08_03` dentro do proprio markdown - fallback se o
#: nome do arquivo nao vier.
_DATA_NO_TITULO = re.compile(r"as of\s+(\d{4})_(\d{2})_(\d{2})", re.IGNORECASE)


class LinhaRanking(BaseModel):
    """Uma equipe numa posicao do ranking."""

    posicao: int
    pontos: int | None
    equipe_nome: str


class ResultadoRanking(BaseModel):
    data_referencia: date | None = None
    regiao: str = "global"
    linhas: list[LinhaRanking] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.linhas)


def data_do_arquivo(nome: str) -> date | None:
    """`standings_global_2026_08_03.md` -> date(2026, 8, 3)."""
    achado = _DATA_NO_NOME.search(nome)
    if achado is None:
        return None
    try:
        return date(int(achado[1]), int(achado[2]), int(achado[3]))
    except ValueError:
        return None


def _celulas(linha: str) -> list[str]:
    """`| 1 | 2011 | Spirit | ... |` -> ['1', '2011', 'Spirit', ...]."""
    cru = linha.strip()
    if cru.startswith("|"):
        cru = cru[1:]
    if cru.endswith("|"):
        cru = cru[:-1]
    return [c.strip() for c in cru.split("|")]


def _e_linha_de_alinhamento(celulas: list[str]) -> bool:
    """A linha `| :- | -: | :- |` que o markdown poe abaixo do cabecalho."""
    return all(set(c) <= {":", "-", " "} and "-" in c for c in celulas if c)


def parse_standings(markdown: str, regiao: str = "global") -> ResultadoRanking:
    """Markdown da tabela -> `ResultadoRanking`.

    Ignora tudo que nao seja uma linha de dados da tabela: titulo, `<br />`,
    cabecalho, linha de alinhamento, e qualquer linha cuja primeira celula nao
    seja um numero de posicao.
    """
    resultado = ResultadoRanking(regiao=regiao)

    achado = _DATA_NO_TITULO.search(markdown)
    if achado is not None:
        try:
            resultado.data_referencia = date(
                int(achado[1]), int(achado[2]), int(achado[3])
            )
        except ValueError:
            pass

    vistos: set[str] = set()
    for linha in markdown.splitlines():
        if "|" not in linha:
            continue
        celulas = _celulas(linha)
        if len(celulas) < 3:
            continue
        if _e_linha_de_alinhamento(celulas):
            continue

        posicao_txt, pontos_txt, nome = celulas[0], celulas[1], celulas[2]
        if not posicao_txt.isdigit():
            # Cabecalho ("Standing") e qualquer lixo caem aqui.
            continue

        nome = nome.strip()
        if not nome or nome in vistos:
            continue
        vistos.add(nome)

        resultado.linhas.append(
            LinhaRanking(
                posicao=int(posicao_txt),
                pontos=int(pontos_txt) if pontos_txt.lstrip("-").isdigit() else None,
                equipe_nome=nome,
            )
        )

    if not resultado.linhas:
        logger.warning("standings sem nenhuma linha de dados", extra={"regiao": regiao})

    return resultado


def transformar(
    texto: object, nome_arquivo: str = "", regiao: str = "global"
) -> ResultadoRanking:
    """Corpo bruto (texto markdown) -> `ResultadoRanking`.

    `nome_arquivo` tem prioridade sobre a data lida do titulo: a URL garante o
    nome, o conteudo pode ter erro de digitacao.
    """
    if not isinstance(texto, str) or not texto.strip():
        return ResultadoRanking(regiao=regiao)

    resultado = parse_standings(texto, regiao=regiao)

    do_nome = data_do_arquivo(nome_arquivo)
    if do_nome is not None:
        resultado.data_referencia = do_nome

    return resultado
