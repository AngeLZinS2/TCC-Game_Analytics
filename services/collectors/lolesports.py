"""Detalhe AO VIVO de partidas de League of Legends — API oficial da LoL Esports.

O `opgg_esports` e a PandaScore (free) dão o placar da série (3x1) e, no máximo,
quem ganhou cada mapa. O que aconteceu DENTRO do jogo — campeão, K/D/A, farm,
ouro, torres, dragões, barões, por jogador — só a API oficial da Riot entrega,
e de graça: `esports-api.lolesports.com` usa uma chave pública que o site
`lolesports.com` embute no bundle há anos, e `feed.lolesports.com/livestats` é o
mesmo feed que alimenta o placar ao vivo da transmissão.

**É um feed AO VIVO.** Enquanto o jogo rola, `livestats/window` devolve um frame
a cada ~10 s. Terminada a partida o feed expira em pouco tempo — aí sobra o
placar da série + os VODs (de `getEventDetails`), e o detalhe por jogador fica
congelado no último frame que a gente pegou. Partida antiga não tem como.

**Casamento de id.** Nossas linhas de `agenda_partida` usam id do OP.GG/PandaScore;
a lolesports tem o dela. Casamos por `{nomes normalizados dos dois times} + dia`
contra o `getSchedule` (fallback pelo código/tag). Só as partidas perto do
horário agora entram — é feed ao vivo, não há o que buscar de uma partida de
semana passada.

**Onde cai.** `agenda_partida.detalhe` (JSONB), como o `vlr_detalhes`: `status`,
`placar_serie`, `mapas` (scoreboard por jogo) e `mapas_resultado` (quem ganhou
cada jogo). A tela de detalhe da partida lê daí.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import func, or_, select

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import get_settings
from models.models import AgendaPartida, DimJogo
from models.session import session_scope
from services.etl.load_liquipedia import normalizar

logger = logging.getLogger(__name__)

JOGO = "leagueoflegends"

#: Chave pública embutida em lolesports.com — não é segredo, é a mesma para
#: todo mundo há anos. Só dá acesso de leitura ao schedule/eventos.
CHAVE_API = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
ESPORTS_API = "https://esports-api.lolesports.com/persisted/gw"
FEED = "https://feed.lolesports.com/livestats/v1"

#: Janela em torno de "agora" onde uma partida pode estar ao vivo. O feed é
#: ao vivo, então não adianta olhar mais longe do que isso.
JANELA_ANTES = timedelta(hours=8)
JANELA_DEPOIS = timedelta(minutes=30)

#: Quantas partidas por rodada. São várias chamadas por partida (evento + um
#: window por jogo em andamento); o normal é 0-2 partidas ao vivo.
POR_RODADA = 8

_PAPEL_ORDEM = {"top": 0, "jungle": 1, "mid": 2, "bottom": 3, "support": 4}


@dataclass
class DetalheLol:
    id_agenda: int
    detalhe: dict[str, Any]


@dataclass
class ResultadoLolEsports:
    itens: list[DetalheLol] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.itens)


class LolEsportsCollector(BaseCollector[ResultadoLolEsports]):
    """Scoreboard por jogo das partidas de LoL que estão ao vivo agora."""

    fonte = "lolesports"

    def _cliente(self) -> RateLimitedClient:
        s = get_settings()
        return RateLimitedClient(
            nome="lolesports",
            intervalo_minimo=1.0,
            max_retries=s.http_max_retries,
            timeout=s.http_timeout_seconds,
            user_agent="playdb-tcc/0.1 (+https://playdb.info)",
        )

    # -- candidatos ----------------------------------------------------------

    def _candidatos(self) -> list[tuple[int, str, str, datetime]]:
        agora = datetime.now(timezone.utc)
        na_janela = AgendaPartida.inicio_previsto.between(
            agora - JANELA_ANTES, agora + JANELA_DEPOIS
        )
        ainda_ao_vivo = AgendaPartida.detalhe["status"].astext == "ao_vivo"
        # Já temos o detalhe final da lolesports pra esta partida — não busca de
        # novo (o feed ao vivo já expirou mesmo).
        ja_fechado = (
            AgendaPartida.detalhe["fonte"].astext == "lolesports"
        ) & (AgendaPartida.detalhe["status"].astext == "encerrada")
        with session_scope() as sessao:
            linhas = sessao.execute(
                select(
                    AgendaPartida.id,
                    AgendaPartida.equipe_a_nome,
                    AgendaPartida.equipe_b_nome,
                    AgendaPartida.inicio_previsto,
                )
                .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
                .where(
                    DimJogo.codigo == JOGO,
                    or_(na_janela, ainda_ao_vivo),
                    or_(AgendaPartida.detalhe.is_(None), ~ja_fechado),
                )
                .order_by(
                    func.abs(
                        func.extract("epoch", AgendaPartida.inicio_previsto - agora)
                    )
                )
                .limit(POR_RODADA)
            ).all()
        return [(r[0], r[1], r[2], r[3]) for r in linhas]

    # -- casamento com a lolesports ---------------------------------------

    @staticmethod
    def _indice_schedule(eventos: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
        """`{(par de times normalizados, dia) -> evento}`."""
        indice: dict[Any, dict[str, Any]] = {}
        for ev in eventos:
            match = ev.get("match") or {}
            times = match.get("teams") or []
            if len(times) != 2:
                continue
            inicio = _instante(ev.get("startTime"))
            if inicio is None:
                continue
            nomes = frozenset(normalizar(t.get("name") or "") for t in times)
            if "" in nomes:
                continue
            indice.setdefault(
                (nomes, inicio.date()), {**ev, "_match_id": match.get("id")}
            )
        return indice

    def _achar_match_id(
        self,
        indice: dict[Any, dict[str, Any]],
        nome_a: str,
        nome_b: str,
        inicio: datetime,
    ) -> str | None:
        chaves_nome = frozenset((normalizar(nome_a), normalizar(nome_b)))
        # Fuso e horário marcado divergem por algumas horas — tenta o dia e os
        # vizinhos.
        for delta in (0, -1, 1):
            dia = (inicio + timedelta(days=delta)).date()
            ev = indice.get((chaves_nome, dia))
            if ev:
                return ev.get("_match_id")
        return None

    # -- coleta ------------------------------------------------------------

    def collect(self) -> list[RawRecord]:
        candidatos = self._candidatos()
        if not candidatos:
            return []

        cliente = self._cliente()
        registros: list[RawRecord] = []
        try:
            agenda = cliente.get_json(
                f"{ESPORTS_API}/getSchedule",
                params={"hl": "en-US"},
                headers={"x-api-key": CHAVE_API},
            )
            eventos = (
                (agenda or {}).get("data", {}).get("schedule", {}).get("events", [])
            )
            indice = self._indice_schedule(eventos)

            for id_agenda, nome_a, nome_b, inicio in candidatos:
                match_id = self._achar_match_id(indice, nome_a, nome_b, inicio)
                if match_id is None:
                    continue
                try:
                    evento = cliente.get_json(
                        f"{ESPORTS_API}/getEventDetails",
                        params={"hl": "en-US", "id": match_id},
                        headers={"x-api-key": CHAVE_API},
                    )
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning(
                        "getEventDetails falhou",
                        extra={"match_id": match_id, "erro": str(exc)},
                    )
                    continue

                dados_evento = (evento or {}).get("data", {}).get("event") or {}
                jogos = ((dados_evento.get("match") or {}).get("games")) or []
                janelas: dict[str, Any] = {}
                for jogo in jogos:
                    if jogo.get("state") not in ("inProgress", "completed"):
                        continue
                    gid = jogo.get("id")
                    if not gid:
                        continue
                    janela = _buscar_janela(cliente, gid)
                    if janela is not None:
                        janelas[gid] = janela

                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint="/match",
                        identificador=str(id_agenda),
                        payload={
                            "nome_a": nome_a,
                            "nome_b": nome_b,
                            "evento": dados_evento,
                            "janelas": janelas,
                        },
                    )
                )
        finally:
            cliente.close()
        return registros

    # -- parse -----------------------------------------------------------

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoLolEsports:
        itens: list[DetalheLol] = []
        for registro in registros:
            if not isinstance(registro.payload, dict):
                continue
            detalhe = _montar_detalhe(
                registro.payload.get("evento") or {},
                registro.payload.get("janelas") or {},
                registro.payload.get("nome_a") or "",
                registro.payload.get("nome_b") or "",
            )
            if detalhe and (detalhe.get("mapas") or detalhe.get("mapas_resultado")):
                itens.append(DetalheLol(int(registro.identificador), detalhe))
        return ResultadoLolEsports(itens=itens)

    def load(self, dados: ResultadoLolEsports) -> int:
        if not dados.itens:
            return 0
        with session_scope() as sessao:
            for item in dados.itens:
                # Preserva os canais que outra fonte (PandaScore) já tinha
                # gravado, quando a lolesports não trouxe os seus.
                existente = sessao.execute(
                    select(AgendaPartida.detalhe).where(
                        AgendaPartida.id == item.id_agenda
                    )
                ).scalar()
                novo = dict(item.detalhe)
                if not novo.get("streams") and (existente or {}).get("streams"):
                    novo["streams"] = existente["streams"]
                sessao.execute(
                    AgendaPartida.__table__.update()
                    .where(AgendaPartida.id == item.id_agenda)
                    .values(detalhe=novo)
                )
        logger.info(
            "detalhe ao vivo de LoL carregado", extra={"partidas": len(dados.itens)}
        )
        return len(dados.itens)


# ---------------------------------------------------------------------------
# Feed livestats
# ---------------------------------------------------------------------------


def _buscar_janela(cliente: RateLimitedClient, gid: str) -> dict[str, Any] | None:
    """O frame mais recente de um jogo. Sem `startingTime` o feed devolve o
    começo do jogo (tudo zero); então tenta primeiro agora-30s, e cai no
    sem-parâmetro só se o jogo acabou de começar."""
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    # o feed só aceita segundos múltiplos de 10
    agora = agora.replace(second=agora.second - agora.second % 10)
    tentativas = [
        {"startingTime": (agora - timedelta(seconds=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )},
        {},
    ]
    for params in tentativas:
        try:
            dados = cliente.get_json(f"{FEED}/window/{gid}", params=params)
        except Exception:  # noqa: BLE001
            continue
        frames = (dados or {}).get("frames") or []
        if frames:
            return dados
    return None


def _instante(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _lado_do_time_a(evento: dict[str, Any], nome_a: str) -> str | None:
    """`blue` ou `red` para o nosso time A, casando o nome contra o `teams`
    do evento."""
    alvo = normalizar(nome_a)
    times = ((evento.get("match") or {}).get("teams")) or []
    id_a = None
    for t in times:
        if normalizar(t.get("name") or "") == alvo or (
            (t.get("code") or "").lower() == alvo
        ):
            id_a = t.get("id")
            break
    if id_a is None and len(times) == 2:
        # sem casar o nome, assume a ordem do evento (teams[0] = nosso A)
        id_a = times[0].get("id")
    return id_a


def _montar_detalhe(
    evento: dict[str, Any],
    janelas: dict[str, Any],
    nome_a: str,
    nome_b: str = "",
) -> dict[str, Any] | None:
    match = evento.get("match") or {}
    times = match.get("teams") or []
    if len(times) != 2:
        return None

    id_a = _lado_do_time_a(evento, nome_a)
    # gameWins -> placar de série
    def _wins(t: dict[str, Any]) -> int | None:
        return ((t.get("result") or {}).get("gameWins"))

    if times[0].get("id") == id_a:
        time_a, time_b = times[0], times[1]
    else:
        time_a, time_b = times[1], times[0]
    placar_serie = None
    if _wins(time_a) is not None or _wins(time_b) is not None:
        placar_serie = {"a": _wins(time_a), "b": _wins(time_b)}

    jogos = match.get("games") or []
    jogados = [g for g in jogos if g.get("state") != "unneeded"]

    mapas: list[dict[str, Any]] = []
    mapas_resultado: list[dict[str, Any]] = []
    algum_ao_vivo = False

    for jogo in jogos:
        estado = jogo.get("state")
        if estado == "unneeded":
            continue
        posicao = jogo.get("number")
        # de que lado (blue/red) está o nosso time A neste jogo
        lado_a = None
        for gt in jogo.get("teams") or []:
            if gt.get("id") == id_a:
                lado_a = gt.get("side")
        lado_a = lado_a or "blue"
        lado_b = "red" if lado_a == "blue" else "blue"

        janela = janelas.get(jogo.get("id"))
        frame = None
        if janela:
            frames = janela.get("frames") or []
            frame = frames[-1] if frames else None

        if frame:
            meta = janela.get("gameMetadata") or {}
            meta_a = meta.get(f"{lado_a}TeamMetadata") or {}
            meta_b = meta.get(f"{lado_b}TeamMetadata") or {}
            time_frame_a = frame.get(f"{lado_a}Team") or {}
            time_frame_b = frame.get(f"{lado_b}Team") or {}
            gstate = frame.get("gameState")
            if gstate == "in_game":
                algum_ao_vivo = True

            rotulo_a = nome_a or "A"
            rotulo_b = nome_b or _nome_time(time_b) or "B"
            jogadores = _jogadores(meta_a, time_frame_a, rotulo_a) + _jogadores(
                meta_b, time_frame_b, rotulo_b
            )
            if jogadores:
                mapas.append(
                    {
                        "nome": f"Jogo {posicao}" if posicao else "Jogo",
                        "duracao": None,
                        "placar_a": time_frame_a.get("totalKills"),
                        "placar_b": time_frame_b.get("totalKills"),
                        "objetivos_a": _objetivos(time_frame_a),
                        "objetivos_b": _objetivos(time_frame_b),
                        "jogadores": jogadores,
                    }
                )
                vit_a = None
                if gstate == "finished":
                    vit_a = (time_frame_a.get("totalKills") or 0) > (
                        time_frame_b.get("totalKills") or 0
                    )
                mapas_resultado.append(
                    {
                        "posicao": posicao,
                        "status": {
                            "finished": "encerrado",
                            "in_game": "ao_vivo",
                        }.get(gstate, "ao_vivo"),
                        "vitoria_a": vit_a,
                    }
                )
                continue

        # sem frame utilizável: registra só o estado do jogo
        if estado == "inProgress":
            algum_ao_vivo = True
        mapas_resultado.append(
            {
                "posicao": posicao,
                "status": {
                    "completed": "encerrado",
                    "inProgress": "ao_vivo",
                    "unstarted": "em_breve",
                }.get(estado, estado),
                "vitoria_a": None,
            }
        )

    if algum_ao_vivo:
        status = "ao_vivo"
    elif jogados and all(g.get("state") == "completed" for g in jogados):
        status = "encerrada"
    else:
        status = "em_breve"

    out = {
        "fonte": "lolesports",
        "status": status,
        "placar_serie": placar_serie,
        "mapas": mapas,
        "mapas_resultado": mapas_resultado,
    }
    streams = _streams_do_evento(evento)
    if streams:
        out["streams"] = streams
    return out


_PROVEDOR_URL = {
    "twitch": lambda p: f"https://www.twitch.tv/{p}",
    "youtube": lambda p: f"https://www.youtube.com/watch?v={p}",
    "afreecatv": lambda p: f"https://play.afreecatv.com/{p}",
    "trovo": lambda p: f"https://trovo.live/{p}",
}
_LOCALE_LINGUA = {
    "en": "EN", "ko": "KO", "zh": "ZH", "pt": "PT", "es": "ES", "fr": "FR",
    "de": "DE", "ru": "RU", "ja": "JA", "vi": "VI", "tr": "TR", "pl": "PL",
}


def _streams_do_evento(evento: dict[str, Any]) -> list[dict[str, Any]]:
    saida: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for s in evento.get("streams") or []:
        if not isinstance(s, dict):
            continue
        provedor = (s.get("provider") or "").lower()
        param = s.get("parameter")
        montar = _PROVEDOR_URL.get(provedor)
        if not param or not montar:
            continue
        url = montar(param)
        if url in vistos:
            continue
        vistos.add(url)
        loc = (s.get("locale") or "").split("-")[0].lower()
        saida.append(
            {
                "url": url,
                "nome": param if provedor != "youtube" else f"{provedor} ({loc})",
                "plataforma": provedor if provedor in ("twitch", "youtube") else "other",
                "lingua": _LOCALE_LINGUA.get(loc),
                "principal": not saida,
            }
        )
    return saida[:8]


def _nome_time(t: dict[str, Any]) -> str | None:
    return t.get("name") or t.get("code")


def _objetivos(time_frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "torres": time_frame.get("towers"),
        "baroes": time_frame.get("barons"),
        "dragoes": len(time_frame.get("dragons") or []),
        "ouro": time_frame.get("totalGold"),
    }


def _jogadores(
    meta: dict[str, Any], time_frame: dict[str, Any], nome_time: str
) -> list[dict[str, Any]]:
    por_id = {
        p.get("participantId"): p for p in (time_frame.get("participants") or [])
    }
    saida: list[dict[str, Any]] = []
    for pm in meta.get("participantMetadata") or []:
        pid = pm.get("participantId")
        p = por_id.get(pid) or {}
        saida.append(
            {
                "nome": pm.get("summonerName") or "",
                "time": nome_time,
                "papel": pm.get("role"),
                "campeao": pm.get("championId"),
                "k": p.get("kills"),
                "d": p.get("deaths"),
                "a": p.get("assists"),
                "cs": p.get("creepScore"),
                "ouro": p.get("totalGold"),
                "nivel": p.get("level"),
            }
        )
    saida.sort(key=lambda j: _PAPEL_ORDEM.get((j.get("papel") or "").lower(), 9))
    return saida
