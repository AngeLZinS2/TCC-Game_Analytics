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
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import func, or_, select

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import get_settings
from models.models import AgendaPartida, DimJogo
from models.session import session_scope

logger = logging.getLogger(__name__)

JOGO = "valorant"
BASE = "https://www.vlr.gg"

#: Quantas partidas buscar por rodada. A pagina e grande; a rodada e diaria e a
#: fila (partidas decididas sem `detalhe`) so cresce quando ha jogo novo.
POR_RODADA = 15

#: Janela para a PRIMEIRA coleta de uma partida (pega status/canais/veto uma
#: vez). Larga para trás porque o `inicio_previsto` de algumas linhas vem de
#: fonte imprecisa e a partida pode já estar rolando.
JANELA_PRIMEIRA_ANTES = timedelta(hours=12)
JANELA_PRIMEIRA_DEPOIS = timedelta(hours=24)

#: Janela onde a partida provavelmente está AO VIVO — essas revalidam a cada
#: rodada (placar, mapas e status andam). Estreita: são poucas por vez.
JANELA_AO_VIVO_ANTES = timedelta(hours=6)
JANELA_AO_VIVO_DEPOIS = timedelta(minutes=30)

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
        agora = datetime.now(timezone.utc)
        with session_scope() as sessao:
            # Quatro filas, ordenadas por proximidade de "agora" (a partida
            # perto do horário é a que provavelmente está ao vivo, prioritária):
            #   (a) decidida sem `detalhe` — fila histórica, preenche uma vez;
            #   (b) sem `detalhe` e perto de hoje — primeira coleta (status,
            #       canais, veto), uma vez;
            #   (c) na janela de ao vivo — revalida a cada rodada;
            #   (d) marcada `ao_vivo` no `detalhe` mas fora da janela (horário
            #       impreciso, ou travou) — revalida até fechar.
            sem_detalhe = AgendaPartida.detalhe.is_(None)
            primeira_coleta = sem_detalhe & AgendaPartida.inicio_previsto.between(
                agora - JANELA_PRIMEIRA_ANTES, agora + JANELA_PRIMEIRA_DEPOIS
            )
            na_janela_ao_vivo = AgendaPartida.inicio_previsto.between(
                agora - JANELA_AO_VIVO_ANTES, agora + JANELA_AO_VIVO_DEPOIS
            )
            ainda_ao_vivo = AgendaPartida.detalhe["status"].astext == "ao_vivo"
            pendentes = sessao.execute(
                select(AgendaPartida.id, AgendaPartida.id_externo)
                .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
                .where(
                    DimJogo.codigo == JOGO,
                    AgendaPartida.id_externo.like("vlr:%"),
                    or_(
                        AgendaPartida.vitoria_a.is_not(None) & sem_detalhe,
                        primeira_coleta,
                        na_janela_ao_vivo,
                        ainda_ao_vivo,
                    ),
                )
                .order_by(
                    func.abs(
                        func.extract(
                            "epoch", AgendaPartida.inicio_previsto - agora
                        )
                    )
                )
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
            # Guarda se pegou QUALQUER coisa útil — uma partida ao vivo sem
            # mapa começado ainda tem status + placar + canais pra mostrar.
            if (
                detalhe["mapas"]
                or detalhe.get("streams")
                or detalhe.get("status") in ("ao_vivo", "encerrada")
            ):
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

        # Numa série ao vivo o vlr.gg já renderiza a linha do elenco dos mapas
        # que ainda não começaram — sem nenhum número. Esses ficam de fora.
        if not jogadores or not any(
            j["rating"] is not None or j["acs"] is not None or j["k"] is not None
            for j in jogadores
        ):
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

    return {"fonte": "vlr.gg", "mapas": mapas, **_parse_cabecalho(pagina)}


def _extrai(padrao: re.Pattern[str], texto: str) -> str | None:
    m = padrao.search(texto)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Cabeçalho da partida (status, placar de série, transmissões, veto)
# ---------------------------------------------------------------------------

_PLACAR_SERIE = re.compile(
    r'match-header-vs-score">\s*<div class="sp-hide">\s*'
    r'<span[^>]*>\s*(\d+)\s*</span>\s*'
    r'<span class="match-header-vs-score-colon">\s*:\s*</span>\s*'
    r'<span[^>]*>\s*(\d+)\s*</span>',
    re.S,
)
_FORMATO_SERIE = re.compile(r'match-header-vs-note">\s*(Bo\d)\s*<', re.S)
_VETO_SERIE = re.compile(r'<div class="match-header-note">\s*(.*?)\s*</div>', re.S)

#: Bloco `match-streams-container` até os VODs — onde ficam os canais ao vivo.
_BLOCO_STREAMS = re.compile(
    r'<div class="match-streams-container">(.*?)(?:<div class="match-vods">|</div>\s*</div>\s*<div class="match-stream-embed)',
    re.S,
)
_FLAG_LINGUA = {
    "us": "EN", "gb": "EN", "eu": "EN", "br": "PT", "kr": "KO", "jp": "JA",
    "cn": "ZH", "ru": "RU", "es": "ES", "fr": "FR", "de": "DE", "tr": "TR",
}
_HOST_PLATAFORMA_VLR = {
    "twitch.tv": "twitch",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "kick.com": "kick",
}


def _plataforma(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)/", url + "/")
    host = (m.group(1) if m else "").lower()
    return _HOST_PLATAFORMA_VLR.get(host, "other")


def _parse_streams(pagina: str) -> list[dict[str, Any]]:
    bloco = _BLOCO_STREAMS.search(pagina)
    if not bloco:
        return []
    trecho = bloco.group(1)
    saida: list[dict[str, Any]] = []
    vistos: set[str] = set()

    for card in re.split(r'<a href="|<div class="wf-card', trecho):
        url_m = re.search(r'href="(https?://[^"]+)"', "<a href=\"" + card) or re.search(
            r'href="(https?://[^"]+)"', card
        )
        nome_m = re.search(r'<span[^>]*>\s*([^<]+?)\s*</span>', card)
        flag_m = re.search(r"flag mod-(\w+)", card)
        if not url_m or not nome_m:
            continue
        url = html.unescape(url_m.group(1))
        if url in vistos:
            continue
        vistos.add(url)
        saida.append(
            {
                "url": url,
                "nome": html.unescape(nome_m.group(1)).strip()[:60],
                "plataforma": _plataforma(url),
                "lingua": _FLAG_LINGUA.get((flag_m.group(1) if flag_m else "").lower()),
                "principal": not saida,
            }
        )
    return saida[:8]


def _parse_cabecalho(pagina: str) -> dict[str, Any]:
    cab = pagina[: pagina.find("Maps/Stats")] if "Maps/Stats" in pagina else pagina[:8000]

    if "match-header-vs-note mod-live" in cab:
        status = "ao_vivo"
    elif re.search(r"match-header-vs-note[^>]*>\s*final\b", cab):
        status = "encerrada"
    else:
        status = "em_breve"

    out: dict[str, Any] = {"status": status}

    placar = _PLACAR_SERIE.search(cab)
    if placar and status in ("ao_vivo", "encerrada"):
        out["placar_serie"] = {"a": int(placar.group(1)), "b": int(placar.group(2))}

    fmt = _FORMATO_SERIE.search(cab)
    if fmt:
        out["formato"] = fmt.group(1)

    veto = _VETO_SERIE.search(cab)
    if veto:
        texto = html.unescape(re.sub(r"<[^>]+>", "", veto.group(1))).strip()
        if texto:
            out["veto"] = texto[:400]

    streams = _parse_streams(pagina)
    if streams:
        out["streams"] = streams

    return out
