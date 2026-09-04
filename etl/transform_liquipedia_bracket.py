"""Confrontos com resultado a partir do BRACKET de um torneio da Liquipedia.

**O problema que isto resolve.** `Liquipedia:Matches` (o parser em
`transform_liquipedia.py`) e um ticker: uma janela de ~5-9 dias de confrontos
recentes, passados e futuros. Depois que um confronto sai dessa janela, ele
nunca mais aparece la - e um time so ganha forca no Bradley-Terry se aparecer
em pelo menos um confronto DECIDIDO que capturamos. O efeito pratico: times
conhecidos (MIBR, BIG, GamerLegion, Natus Vincere Junior - todos ja presentes
em `dim_equipe`, coletados via `liquipedia_wiki_collector`) ficavam sem
previsao simplesmente porque nenhuma partida deles caiu na janela do ticker
nas poucas vezes que coletamos.

**A fonte mais rica.** A pagina de um torneio (ex: "BLAST/Open/2026/Fall")
tem o BRACKET inteiro - todas as fases, nao so os ultimos dias. Medido: esse
torneio sozinho tem 24 confrontos decididos, contra os poucos que o ticker
capturava dele. Cada partida do bracket carrega um popup escondido
(`.brkts-popup.brkts-match-info-popup`) com a MESMA estrutura interna do
ticker (`match-info-header-opponent`, `-winner`, `-scoreholder`) - so que sem
o wrapper `div.match-info` que `parse_agenda()` usa como raiz de busca. Por
isso este e um parser separado, e nao uma reutilizacao direta: a raiz de
busca e outra (`div.brkts-match`), mesmo que os pedacos internos se pareçam.

**De onde vem o nome do time e o vencedor**, no bracket (diferente do
ticker):

    <div aria-label="Team Spirit" class="brkts-opponent-entry ...">
      <div class="brkts-opponent-entry-left brkts-opponent-win">...</div>
      <div class="brkts-opponent-score-outer">
        <div class="brkts-opponent-score-inner"><b>2</b></div>
      </div>
    </div>

O nome sai do `aria-label` do proprio `.brkts-opponent-entry` (nao de um link
com `title`), e o vencedor da classe `brkts-opponent-win` num filho dele.

**So confrontos DECIDIDOS saem daqui.** Partida sem vencedor marcado (ainda
nao aconteceu, ou WO nao lancado) e descartada - a AGENDA futura ja vem do
ticker, que tem campos que o bracket nao da de graca (o link do torneio para
achar o `torneio` certo, por exemplo). Misturar as duas responsabilidades
numa fonte so complicaria sem necessidade.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from etl.transform_liquipedia import PartidaAgendada, ResultadoAgenda, _identificador

logger = logging.getLogger(__name__)

FONTE = "liquipedia"
ENDPOINT_BRACKET = "bracket"

_FORMATO = re.compile(r"\(?(Bo\d+)\)?", re.IGNORECASE)


def _nome_do_oponente(bloco) -> str | None:
    """O nome do time num `.brkts-opponent-entry`.

    Sai do `aria-label` do proprio elemento - o bracket nao repete o nome
    dentro de um link com `title` como o ticker faz.
    """
    nome = (bloco.get("aria-label") or "").strip()
    return nome if nome and nome.upper() != "TBD" else None


def _placar(bloco) -> int | None:
    span = bloco.select_one(".brkts-opponent-score-inner")
    if span is None:
        return None
    texto = span.get_text(strip=True)
    # Placar de W.O. ou abandono vem como texto ("W", "FF"), nao numero -
    # vira None, nao um valor inventado.
    return int(texto) if texto.isdigit() else None


def _formato(bloco) -> str | None:
    """O formato (Bo3) mora dentro do popup escondido de detalhe do match."""
    popup = bloco.select_one(".brkts-popup")
    if popup is None:
        return None
    elemento = popup.select_one(".match-info-header-scoreholder-lower")
    if elemento is None:
        return None
    achado = _FORMATO.search(elemento.get_text(" ", strip=True))
    return achado.group(1).capitalize() if achado else None


def parse_bracket(html: str, torneio: str) -> list[PartidaAgendada]:
    """HTML da PAGINA DE UM TORNEIO -> os confrontos decididos do bracket dele.

    `torneio` vem de fora - o titulo da pagina que foi consultada - e nao do
    HTML: o bracket nao repete o nome do torneio em cada partida, porque a
    pagina inteira ja e um torneio so.
    """
    if not html:
        return []

    sopa = BeautifulSoup(html, "html.parser")
    partidas: list[PartidaAgendada] = []
    vistos: set[str] = set()

    for bloco in sopa.select("div.brkts-match"):
        adversarios = bloco.select(".brkts-opponent-entry")
        if len(adversarios) != 2:
            continue

        nome_a = _nome_do_oponente(adversarios[0])
        nome_b = _nome_do_oponente(adversarios[1])
        # Time ainda nao definido (TBD) nao da para identificar - e a mesma
        # regra do parser do ticker.
        if not nome_a or not nome_b:
            continue

        venceu_a = bool(adversarios[0].select_one(".brkts-opponent-win"))
        venceu_b = bool(adversarios[1].select_one(".brkts-opponent-win"))
        # Nenhum marcado = ainda nao aconteceu. Os dois marcados seria a
        # fonte se contradizendo. Nos dois casos, sem resultado - e sem
        # resultado este parser nao tem o que acrescentar (a agenda futura ja
        # vem do ticker).
        if venceu_a == venceu_b:
            continue

        relogio = bloco.select_one("[data-timestamp]")
        if relogio is None:
            continue
        try:
            segundos = int(relogio["data-timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if segundos <= 0:
            continue

        inicio = datetime.fromtimestamp(segundos, tz=timezone.utc)
        # Mesma funcao de hash do ticker: se as duas fontes virem a MESMA
        # partida com os mesmos nomes e horario, a chave bate e o upsert
        # atualiza a mesma linha em vez de duplicar.
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
                torneio=torneio,
                formato=_formato(bloco),
                vitoria_a=venceu_a,
                placar_a=_placar(adversarios[0]),
                placar_b=_placar(adversarios[1]),
            )
        )

    return partidas


def transformar(payload: object, torneio: str) -> ResultadoAgenda:
    """Payload bruto da API MediaWiki (pagina de UM torneio) -> confrontos."""
    if not isinstance(payload, dict):
        return ResultadoAgenda()

    if "error" in payload:
        logger.warning(
            "liquipedia devolveu erro (bracket)",
            extra={"erro": str(payload["error"])[:200], "torneio": torneio},
        )
        return ResultadoAgenda()

    texto = ((payload.get("parse") or {}).get("text") or {}).get("*")
    if not isinstance(texto, str):
        return ResultadoAgenda()

    return ResultadoAgenda(partidas=parse_bracket(texto, torneio))
