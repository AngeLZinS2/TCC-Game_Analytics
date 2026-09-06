"""Detalhe por mapa e por jogador de partidas de Valorant do vlr.gg.

O `vlr` (coletor de partidas) da o placar da serie - 2-3. Este pega a PAGINA de
cada partida ja decidida e extrai, por mapa: o placar, a duracao, e a linha de
cada um dos dez jogadores (agente, rating, ACS, K/D/A, ADR, HS%). E o que a
tela de detalhe da partida mostra, como a do vlr.gg.

Grava em `agenda_partida.detalhe` (JSONB) - exibicao, nao agregacao. So processa
partida DECIDIDA que ainda esta com `detalhe` nulo, e poucas por rodada: a
pagina e pesada (~700 KB) e o vlr.gg nao publica limite de taxa.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy import select

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import get_settings
from db.models import AgendaPartida, DimJogo
from db.session import session_scope

logger = logging.getLogger(__name__)

JOGO = "valorant"
BASE = "https://www.vlr.gg"

#: Quantas partidas buscar por rodada. A pagina e grande; a rodada e diaria e a
#: fila (partidas decididas sem `detalhe`) so cresce quando ha jogo novo.
POR_RODADA = 15

#: Um bloco de mapa: `<div class="vm-stats-game ..." data-game-id="280058">`.
#: `all` (o agregado da serie) fica de fora - a tela quer o recorte por mapa.
_BLOCO_MAPA = re.compile(
    r'<div class="vm-stats-game[^"]*"\s+data-game-id="(\d+|all)"[^>]*>(.*?)'
    r'(?=<div class="vm-stats-game[^"]*"\s+data-game-id="|'
    r'<div class="vm-stats-container-footer|<script|\Z)',
    re.S,
)
_NOME_MAPA = re.compile(
    r'"map">\s*<div[^>]*>\s*<span[^>]*>\s*([A-Za-z]+)\s*(?:<span[^>]*>\s*PICK)?',
    re.S,
)
_DURACAO = re.compile(r'map-duration[^>]*>\s*([\d:]+)', re.S)
_PLACAR_MAPA = re.compile(
    r'"score\s*(?:mod-\w+\s*)*"[^>]*>\s*(\d+)\s*</div>', re.S
)
_NOME_JOGO_NAV = re.compile(
    r'data-game-id="(\d+)"[^>]*>.*?<span[^>]*>\s*\d+\s*</span>\s*([A-Za-z]+)', re.S
)

#: Uma linha de jogador dentro de um bloco de mapa.
_LINHA = re.compile(
    r'ovw-player-name text-of"\s*>\s*(?P<nome>[^<]+?)\s*</div>\s*'
    r'<div class="ovw-player-tag[^"]*"\s*>\s*(?P<time>[^<]*?)\s*</div>.*?'
    r'(?:alt="(?P<agente>[a-z/]+)"[^>]*>)?\s*</span>\s*</div>\s*</div>\s*'
    r'(?P<resto>.*?)(?=<div class="ovw-row"|$)',
    re.S,
)
_COL = {
    "rating": re.compile(r'data-col="rating2">.*?mod-both"\s*>\s*([\d.]+)', re.S),
    "acs": re.compile(r'data-col="acs">.*?mod-both"\s*>\s*([\d.]+)', re.S),
    "k": re.compile(r'data-col="kills">\s*<span class="side mod-both"\s*>\s*(\d+)', re.S),
    "d": re.compile(r'data-col="deaths">\s*<span class="side mod-both"\s*>\s*(\d+)', re.S),
    "a": re.compile(r'data-col="assists">\s*<span class="side mod-both"\s*>\s*(\d+)', re.S),
    "adr": re.compile(r'data-col="adr">.*?mod-both"\s*>\s*([\d.]+)', re.S),
    "hs": re.compile(r'data-col="hs">.*?mod-both"\s*>\s*([\d.]+)%?', re.S),
}


@dataclass
class DetalhePartida:
    id_agenda: int
    detalhe: dict[str, Any]


@dataclass
class ResultadoDetalhes:
    itens: list[DetalhePartida] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.itens)


def _num(texto: str | None) -> float | int | None:
    if texto is None:
        return None
    try:
        v = float(texto)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


class VlrDetalhesCollector(BaseCollector[ResultadoDetalhes]):
    """Placar por mapa e stats por jogador das partidas de Valorant."""

    fonte = "vlr_detalhes"

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        with session_scope() as sessao:
            pendentes = sessao.execute(
                select(AgendaPartida.id, AgendaPartida.id_externo)
                .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
                .where(
                    DimJogo.codigo == JOGO,
                    AgendaPartida.id_externo.like("vlr:%"),
                    AgendaPartida.vitoria_a.is_not(None),
                    AgendaPartida.detalhe.is_(None),
                )
                .order_by(AgendaPartida.inicio_previsto.desc())
                .limit(POR_RODADA)
            ).all()

        cliente = RateLimitedClient(
            nome="vlr",
            intervalo_minimo=settings.liquipedia_rate_limit_seconds,
            max_retries=settings.http_max_retries,
            timeout=settings.http_timeout_seconds,
            user_agent="playdb-tcc/0.1 (+https://playdb.info)",
        )

        registros: list[RawRecord] = []
        for id_agenda, id_externo in pendentes:
            match_id = id_externo.split(":", 1)[1]
            try:
                pagina = cliente.get_text(f"{BASE}/{match_id}/x")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    "pagina de partida do vlr falhou",
                    extra={"id_externo": id_externo, "erro": str(exc)},
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint="/match",
                    identificador=str(id_agenda),
                    payload={"pagina": pagina},
                )
            )
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoDetalhes:
        itens: list[DetalhePartida] = []
        for registro in registros:
            if not isinstance(registro.payload, dict):
                continue
            pagina = registro.payload.get("pagina")
            if not isinstance(pagina, str):
                continue
            detalhe = _parse_partida(pagina)
            if detalhe["mapas"]:
                itens.append(DetalhePartida(int(registro.identificador), detalhe))
        return ResultadoDetalhes(itens=itens)

    def load(self, dados: ResultadoDetalhes) -> int:
        if not dados.itens:
            return 0
        with session_scope() as sessao:
            for item in dados.itens:
                sessao.execute(
                    AgendaPartida.__table__.update()
                    .where(AgendaPartida.id == item.id_agenda)
                    .values(detalhe=item.detalhe)
                )
        logger.info("detalhes de partida de valorant carregados", extra={"partidas": len(dados.itens)})
        return len(dados.itens)


def _parse_partida(pagina: str) -> dict[str, Any]:
    nomes = {gid: nome for gid, nome in _NOME_JOGO_NAV.findall(pagina)}
    mapas: list[dict[str, Any]] = []

    for gid, bloco in _BLOCO_MAPA.findall(pagina):
        if gid == "all":
            continue
        nome_mapa = nomes.get(gid)
        if not nome_mapa:
            m = _NOME_MAPA.search(bloco)
            nome_mapa = m.group(1) if m else None
        cabecalho = bloco[:2000]
        placares = _PLACAR_MAPA.findall(cabecalho)
        duracao = _DURACAO.search(cabecalho)

        jogadores: list[dict[str, Any]] = []
        for lm in _LINHA.finditer(bloco):
            resto = lm.group("resto")
            jogadores.append(
                {
                    "nome": html.unescape(lm.group("nome")).strip(),
                    "time": html.unescape(lm.group("time") or "").strip(),
                    "agente": (lm.group("agente") or "").replace("/", "") or None,
                    "rating": _num(_extrai(_COL["rating"], resto)),
                    "acs": _num(_extrai(_COL["acs"], resto)),
                    "k": _num(_extrai(_COL["k"], resto)),
                    "d": _num(_extrai(_COL["d"], resto)),
                    "a": _num(_extrai(_COL["a"], resto)),
                    "adr": _num(_extrai(_COL["adr"], resto)),
                    "hs": _num(_extrai(_COL["hs"], resto)),
                }
            )

        if not jogadores:
            continue
        mapas.append(
            {
                "nome": nome_mapa,
                "duracao": duracao.group(1) if duracao else None,
                "placar_a": _num(placares[0]) if len(placares) > 0 else None,
                "placar_b": _num(placares[1]) if len(placares) > 1 else None,
                "jogadores": jogadores,
            }
        )

    return {"fonte": "vlr.gg", "mapas": mapas}


def _extrai(padrao: re.Pattern[str], texto: str) -> str | None:
    m = padrao.search(texto)
    return m.group(1) if m else None
