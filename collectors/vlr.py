"""Confrontos profissionais de Valorant, raspados do vlr.gg.

O vlr.gg e o placar de Valorant do cenario - o equivalente do que o Liquipedia
ticker e para os outros jogos, so que mais completo e com id de partida
estavel. O Valorant ja tinha equipes e agenda pela wiki, mas o modelo de
confronto dele era o pior do catalogo (taxa base 22%, acuracia 33%): historico
de menos, e sem placar de mapa nenhum - a feature `saldo_recente` do
`ml/confronto` ficava zerada.

Este coletor le duas listas HTML do vlr.gg (nao ha API publica; a nao oficial
virou paga):

* `/matches/results` - partidas ja decididas, com placar de serie (2-3).
* `/matches` - partidas por vir, para a agenda.

O HTML e renderizado no servidor e estavel (classes `match-item-*` ha anos).
Cada card da: link com o id da partida, os dois times, o placar, o evento e o
horario. **O horario da lista NAO tem fuso** - o vlr.gg ajusta por JS no
cliente. Para RESULTADO isso nao importa (o modelo so ordena por data); para a
agenda, guardamos a hora como se fosse UTC e a tela mostra "por volta de".

**Onde cai no schema.** Em `agenda_partida`, a mesma tabela do ticker da
Liquipedia e dos confrontos de LoL do OP.GG - a fonte que alimenta o ajuste de
forcas para todo jogo que nao e Dota. Os times sao reconciliados contra o
`dim_equipe` que a wiki ja povoou (por nome normalizado); quem nao casa entra
com `id_externo` `vlr:<nome>`.

**O que NAO traz.** Placar por mapa, ACS/K/D por jogador - isso esta na pagina
de cada partida, nao na lista, e seria uma requisicao por partida. A serie
(3-1) ja da o `saldo_recente`; o resto fica para depois.

**Cortesia.** O vlr.gg nao publica limite. `RateLimitedClient` com folga larga
(o padrao da Liquipedia, 3s), User-Agent identificando o projeto, poucas
paginas por rodada e rodada diaria.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import get_settings

logger = logging.getLogger(__name__)

#: O codigo do jogo em `dim_jogo`.
JOGO = "valorant"

BASE = "https://www.vlr.gg"

#: Quantas paginas de cada lista por rodada. Cada uma tem ~50 cards; o upsert
#: acumula entre rodadas, entao nao precisa varrer o historico inteiro sempre.
PAGINAS_RESULTADO = 3
PAGINAS_AGENDA = 2

_TIME = re.compile(r'match-item-time"[^>]*>\s*(.*?)\s*<', re.S)
_TEAM = re.compile(
    r'match-item-vs-team(?P<venc>[^"]*)"\s*>.*?'
    r'text-of"\s*>(?P<nome>.*?)</div>.*?'
    r'match-item-vs-team-score[^"]*"[^>]*>(?P<placar>.*?)</div>',
    re.S,
)
_STATUS = re.compile(r'ml-status"\s*>\s*(.*?)\s*<', re.S)
# O bloco do evento: `<div class="match-item-event ...">
#   <div class="match-item-event-series ...">Playoffs&ndash;Lower Final</div>
#   VCT 2026: Americas Stage 2
# </div>` - a serie no filho, o nome do torneio no texto solto depois dele.
_SERIE = re.compile(r'match-item-event-series[^"]*"\s*>(.*?)</div>', re.S)
_EVENTO = re.compile(
    r'match-item-event[^"]*"\s*>.*?</div>\s*(.*?)\s*</div>\s*<div class="match-item-icon',
    re.S,
)


@dataclass
class ConfrontoVlr:
    id_externo: str
    equipe_a_nome: str
    equipe_b_nome: str
    inicio_previsto: datetime
    torneio: str | None
    formato: str | None
    vitoria_a: bool | None
    placar_a: int | None
    placar_b: int | None


@dataclass
class ResultadoVlr:
    confrontos: list[ConfrontoVlr] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.confrontos)


def _texto(bruto: str) -> str:
    sem_tag = html.unescape(re.sub(r"<[^>]+>", " ", bruto))
    return re.sub(r"\s+", " ", sem_tag).strip()


def _int(bruto: str) -> int | None:
    limpo = _texto(bruto)
    return int(limpo) if limpo.isdigit() else None


def _data_do_cabecalho(rotulo: str) -> datetime | None:
    """"Thu, September 3, 2026" -> meia-noite UTC daquele dia."""
    limpo = re.sub(r"^[A-Za-z]+,\s*", "", rotulo.strip())
    for formato in ("%B %d, %Y", "%b %d, %Y"):
        try:
            d = datetime.strptime(limpo, formato)
            return d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _hora(texto_hora: str) -> tuple[int, int]:
    """"3:00 PM" -> (15, 0). `(12, 0)` quando nao da pra ler."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", texto_hora.strip(), re.I)
    if not m:
        return 12, 0
    h, mm, ampm = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
    if ampm == "PM" and h != 12:
        h += 12
    elif ampm == "AM" and h == 12:
        h = 0
    return h % 24, mm


class VlrCollector(BaseCollector[ResultadoVlr]):
    """Resultados e agenda de Valorant do vlr.gg."""

    fonte = "vlr"

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        cliente = RateLimitedClient(
            nome="vlr",
            intervalo_minimo=settings.liquipedia_rate_limit_seconds,
            max_retries=settings.http_max_retries,
            timeout=settings.http_timeout_seconds,
            user_agent="playdb-tcc/0.1 (+https://playdb.info)",
        )

        registros: list[RawRecord] = []
        for caminho, paginas in (
            ("/matches/results", PAGINAS_RESULTADO),
            ("/matches", PAGINAS_AGENDA),
        ):
            for pagina in range(1, paginas + 1):
                url = f"{BASE}{caminho}/?page={pagina}"
                try:
                    resposta = cliente.get_text(url)
                except Exception as exc:  # noqa: BLE001 - uma pagina fora nao leva as outras
                    self.logger.warning(
                        "pagina do vlr falhou", extra={"url": url, "erro": str(exc)}
                    )
                    continue
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=caminho,
                        identificador=f"{caminho.strip('/').replace('/', '_')}:{pagina}",
                        payload=resposta,
                    )
                )
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoVlr:
        vistos: set[str] = set()
        confrontos: list[ConfrontoVlr] = []
        for registro in registros:
            if not isinstance(registro.payload, str):
                continue
            for confronto in _parse_pagina(registro.payload):
                if confronto.id_externo in vistos:
                    continue
                vistos.add(confronto.id_externo)
                confrontos.append(confronto)
        return ResultadoVlr(confrontos=confrontos)

    def load(self, dados: ResultadoVlr) -> int:
        from etl.load_vlr import carregar

        return carregar(dados)


def _parse_pagina(pagina_html: str) -> list[ConfrontoVlr]:
    """Todos os cards de partida de uma pagina de lista do vlr.gg.

    A data vem do cabecalho `wf-label mod-large` que precede um grupo de cards;
    varremos o HTML em ordem, guardando a ultima data vista.
    """
    confrontos: list[ConfrontoVlr] = []
    data_corrente: datetime | None = None

    # Um so passe: rotulos de data e cards, na ordem em que aparecem.
    marcadores = re.finditer(
        r'wf-label mod-large"\s*>\s*(?P<data>[^<]+?)\s*</div>'
        r'|<a[^>]*\bhref="/(?P<id>\d{4,8})/[a-z0-9-]+/?"[^>]*'
        r'class="[^"]*\bmatch-item\b[^"]*"[^>]*>(?P<corpo>.*?)</a>',
        pagina_html,
        re.S,
    )
    for m in marcadores:
        if m.group("data"):
            data_corrente = _data_do_cabecalho(m.group("data"))
            continue

        corpo = m.group("corpo")
        times = list(_TEAM.finditer(corpo))
        if len(times) < 2:
            continue
        a, b = times[0], times[1]
        nome_a, nome_b = _texto(a.group("nome")), _texto(b.group("nome"))
        if not nome_a or not nome_b:
            continue

        placar_a, placar_b = _int(a.group("placar")), _int(b.group("placar"))
        status = _STATUS.search(corpo)
        decidido = status is not None and "completed" in status.group(1).lower()
        vitoria_a: bool | None = None
        if decidido and placar_a is not None and placar_b is not None and placar_a != placar_b:
            vitoria_a = placar_a > placar_b
        elif decidido:
            # `mod-winner` na div do time vencedor - fallback quando o placar
            # nao da (raro: W.O., serie 1-mapa).
            vitoria_a = "mod-winner" in a.group("venc")

        hora_txt = _TIME.search(corpo)
        h, mm = _hora(hora_txt.group(1)) if hora_txt else (12, 0)
        inicio = (
            data_corrente.replace(hour=h, minute=mm)
            if data_corrente
            else datetime.now(timezone.utc)
        )

        evento = _EVENTO.search(corpo)
        serie = _SERIE.search(corpo)
        torneio = _texto(evento.group(1)) if evento else None
        rotulo_serie = _texto(serie.group(1)) if serie else ""
        if torneio and rotulo_serie:
            torneio = f"{torneio} — {rotulo_serie}"
        torneio = (torneio or rotulo_serie or None)

        formato = None
        if placar_a is not None and placar_b is not None:
            maior = max(placar_a, placar_b)
            if maior:
                formato = f"Bo{maior * 2 - 1}"

        confrontos.append(
            ConfrontoVlr(
                id_externo=f"vlr:{m.group('id')}",
                equipe_a_nome=nome_a[:120],
                equipe_b_nome=nome_b[:120],
                inicio_previsto=inicio,
                torneio=torneio,
                formato=formato,
                vitoria_a=vitoria_a,
                placar_a=placar_a,
                placar_b=placar_b,
            )
        )
    return confrontos
