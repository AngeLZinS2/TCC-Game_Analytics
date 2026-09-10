"""Normalizacao do cenario de LoL profissional (API oficial da LoL Esports).

Funcao pura sobre os payloads de `getStandings` (classificacao por split) e
`getTeams` (elenco). Nada de rede, nada de banco.

- `getStandings` -> `LinhaRanking` por time, com `vitorias`/`derrotas` do
  `record`. A regiao e o slug da liga (`lec`, `lck`, `lpl`...).
- `getTeams` -> `EquipeCenario` (time, com `id_externo = "lolesports:<id>"`) +
  `JogadorCenario` (elenco: apelido, nome civil, rota, foto).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

from services.collectors.base import RawRecord

logger = logging.getLogger(__name__)

FONTE = "lolesports"
JOGO = "leagueoflegends"

ENDPOINT_STANDINGS = "standings"
ENDPOINT_TEAM = "team"

#: slug da liga -> slug de regiao no `ranking_externo`. O que nao estiver aqui
#: cai no proprio slug com `_`->`-` e o sufixo de pais removido.
_REGIAO: dict[str, str] = {
    "lck": "lck",
    "lpl": "lpl",
    "lec": "lec",
    "lcs": "lta-north",
    "lta_n": "lta-north",
    "lta_north": "lta-north",
    "lta-north": "lta-north",
    "lta_s": "lta-south",
    "lta_south": "lta-south",
    "lta-south": "lta-south",
    "cblol": "cblol",
    "cblol-brazil": "cblol",
    "cblol_brazil": "cblol",
    "ljl": "ljl",
    "ljl-japan": "ljl",
    "ljl_japan": "ljl",
    "lcp": "lcp",
    "nacl": "nacl",
    "worlds": "international",
    "msi": "international",
    "first_stand": "international",
}


def _regiao_da_liga(slug: str) -> str:
    slug = (slug or "").lower().strip()
    if slug in _REGIAO:
        return _REGIAO[slug]
    base = slug.replace("_", "-")
    for sufixo in ("-brazil", "-japan", "-korea", "-china", "-turkey"):
        if base.endswith(sufixo):
            base = base[: -len(sufixo)]
    return base or "international"


@dataclass
class LinhaRanking:
    equipe_nome: str
    posicao: int
    regiao: str
    vitorias: int | None = None
    derrotas: int | None = None


@dataclass
class EquipeCenario:
    id_externo: str
    nome: str
    tag: str | None
    logo_url: str | None
    regiao: str | None


@dataclass
class JogadorCenario:
    id_externo: str
    nome: str
    nome_completo: str | None
    papel: str | None
    imagem: str | None
    equipe_id_externo: str


@dataclass
class ResultadoLolCenario:
    data_referencia: date
    linhas_ranking: list[LinhaRanking] = field(default_factory=list)
    equipes: list[EquipeCenario] = field(default_factory=list)
    jogadores: list[JogadorCenario] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.linhas_ranking) + len(self.equipes) + len(self.jogadores)


def _inteiro(valor: Any) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


#: Stages que são chave de mata-mata, não classificação — ignorados.
_STAGES_BRACKET = {
    "playoffs", "play_ins", "play-ins", "knockouts", "regional_championship",
    "regional_finals", "gauntlet",
}


def _linhas_de_standings(payload: dict, slug_liga: str) -> list[LinhaRanking]:
    """`getStandings` -> linhas de classificação.

    O `ordinal` da API **não é confiável** (LCK 2026 traz a ordem do sorteio do
    grupo, VCS traz tudo em #1). Quando há `record` (V-D), a posição é
    recalculada por vitórias desc / derrotas asc. Também junta TODAS as seções
    do stage de classificação — a LCK divide em dois grupos e a tabela pública
    é a dos dois juntos.
    """
    standings = (payload.get("data") or {}).get("standings") or []
    regiao = _regiao_da_liga(slug_liga)

    # Candidatos = (é_regular_season, total_de_times, rankings_achatados) por
    # stage não-bracket com rankings. Escolhe regular_season, senão o de mais times.
    candidatos: list[tuple[int, int, list[dict]]] = []
    for st in standings:
        for stage in st.get("stages") or []:
            slug = (stage.get("slug") or "").lower()
            if slug in _STAGES_BRACKET:
                continue
            achatado = [
                rk
                for sec in stage.get("sections") or []
                for rk in (sec.get("rankings") or [])
            ]
            if achatado:
                n_times = sum(len(rk.get("teams") or []) for rk in achatado)
                candidatos.append((0 if slug == "regular_season" else 1, -n_times, achatado))

    if not candidatos:
        return []
    candidatos.sort()
    rankings = candidatos[0][2]

    # (nome, wins, losses) por time + a ordem que a API deu (fallback)
    times: dict[str, tuple[str, int | None, int | None]] = {}
    ordem_api: dict[str, int] = {}
    for indice, rk in enumerate(rankings):
        ordv = _inteiro(rk.get("ordinal"))
        for time in rk.get("teams") or []:
            nome = (time.get("name") or "").strip()
            chave = nome.lower()
            if not nome or chave in times:
                continue
            rec = time.get("record") or {}
            times[chave] = (nome[:120], _inteiro(rec.get("wins")), _inteiro(rec.get("losses")))
            ordem_api[chave] = ordv if ordv is not None else indice

    if not times:
        return []

    tem_record = any(w is not None for (_, w, _) in times.values())
    if tem_record:
        ordenados = sorted(
            times.items(),
            key=lambda kv: (-(kv[1][1] or 0), kv[1][2] or 0, kv[1][0].lower()),
        )
    else:
        ordenados = sorted(times.items(), key=lambda kv: (ordem_api[kv[0]], kv[1][0].lower()))

    return [
        LinhaRanking(
            equipe_nome=nome,
            posicao=i + 1,
            regiao=regiao,
            vitorias=w,
            derrotas=l,
        )
        for i, (_, (nome, w, l)) in enumerate(ordenados)
    ]


def _time_e_elenco(
    payload: dict,
) -> tuple[EquipeCenario | None, list[JogadorCenario]]:
    times = (payload.get("data") or {}).get("teams") or []
    if not times or not isinstance(times[0], dict):
        return None, []
    t = times[0]
    tid = t.get("id")
    if not tid or not t.get("name"):
        return None, []

    id_externo = f"lolesports:{tid}"
    liga = (t.get("homeLeague") or {}).get("name") or ""
    equipe = EquipeCenario(
        id_externo=id_externo,
        nome=(t.get("name") or "")[:120],
        tag=(t.get("code") or None),
        logo_url=(t.get("image") or None),
        regiao=_regiao_da_liga(liga) if liga else None,
    )

    jogadores: list[JogadorCenario] = []
    for p in t.get("players") or []:
        pid = p.get("id")
        apelido = (p.get("summonerName") or "").strip()
        if not pid or not apelido:
            continue
        nome_completo = f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip()
        jogadores.append(
            JogadorCenario(
                id_externo=str(pid),
                nome=apelido[:120],
                nome_completo=nome_completo or None,
                papel=(p.get("role") or None),
                imagem=(p.get("image") or None),
                equipe_id_externo=id_externo,
            )
        )
    return equipe, jogadores


def transformar(registros: Iterable[RawRecord]) -> ResultadoLolCenario:
    linhas: list[LinhaRanking] = []
    equipes: dict[str, EquipeCenario] = {}
    jogadores: dict[str, JogadorCenario] = {}

    for registro in registros:
        if registro.fonte != FONTE:
            continue
        payload = registro.payload
        if not isinstance(payload, dict):
            continue

        if registro.endpoint == ENDPOINT_STANDINGS:
            linhas.extend(_linhas_de_standings(payload, registro.identificador))
        elif registro.endpoint == ENDPOINT_TEAM:
            equipe, elenco = _time_e_elenco(payload)
            if equipe is not None:
                equipes[equipe.id_externo] = equipe
                for jog in elenco:
                    jogadores[jog.id_externo] = jog

    return ResultadoLolCenario(
        data_referencia=datetime.now(timezone.utc).date(),
        linhas_ranking=linhas,
        equipes=list(equipes.values()),
        jogadores=list(jogadores.values()),
    )
