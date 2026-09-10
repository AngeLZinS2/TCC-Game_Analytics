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

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import get_settings
from models.models import AgendaPartida, DimJogador, DimJogo, FatoLolJogadorPartida
from models.session import session_scope
from services.etl.load_liquipedia import normalizar
from services.etl.lotes import em_lotes

logger = logging.getLogger(__name__)

JOGO = "leagueoflegends"

#: Chave pública embutida em lolesports.com — não é segredo, é a mesma para
#: todo mundo há anos. Só dá acesso de leitura ao schedule/eventos.
CHAVE_API = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
ESPORTS_API = "https://esports-api.lolesports.com/persisted/gw"
FEED = "https://feed.lolesports.com/livestats/v1"

#: Ligas cujo calendário completo o `getSchedule` (só perto de agora) não cobre —
#: usadas para montar o índice de casamento das partidas decididas no backfill,
#: e para o `lolesports_cenario` puxar classificação/elenco.
LIGAS_TIER1 = frozenset(
    {
        "worlds", "msi", "first_stand",
        "lck", "lpl", "lec", "lcs", "lta_n", "lta_s", "lta_north", "lta_south",
        "lcp", "ljl", "ljl-japan", "cblol", "cblol-brazil", "nacl",
        "nlc", "lfl", "superliga", "tcl", "vcs", "pcs", "emea_masters",
    }
)

#: Janela em torno de "agora" onde uma partida pode estar ao vivo. O feed é
#: ao vivo, então não adianta olhar mais longe do que isso.
JANELA_ANTES = timedelta(hours=8)
JANELA_DEPOIS = timedelta(minutes=30)

#: Quantas partidas por rodada. São várias chamadas por partida (evento + um
#: window por jogo em andamento); o normal é 0-2 partidas ao vivo.
POR_RODADA = 8

#: Backfill de partidas JÁ decididas — o `feed.lolesports.com/livestats` guarda
#: o histórico de frames por ~1-2 semanas, então dá pra pegar o frame final
#: (K/D/A/ouro/CS reais) de partidas recentes que a gente não flagrou ao vivo.
#: 20/rodada: a cena tem ~130 partidas decididas na janela e o coletor roda de
#: 5 em 5 min — a 5/rodada levaria horas; a 20 fecha o backlog em ~30 min.
POR_RODADA_BACKFILL = 20
BACKFILL_JANELA = timedelta(days=12)

#: O índice de partidas encerradas (getLeagues + getTournamentsForLeague +
#: getCompletedEvents) é caro — dezenas de chamadas. Cacheado no processo.
_TTL_INDICE_COMPLETOS = timedelta(hours=1)
_indice_completos_cache: dict[str, Any] = {}

#: literal JSONB `[]` pra usar em `coalesce` no filtro de candidatos.
_JSONB_VAZIO = text("'[]'::jsonb")

_PAPEL_ORDEM = {"top": 0, "jungle": 1, "mid": 2, "bottom": 3, "support": 4}


@dataclass
class DetalheLol:
    id_agenda: int
    detalhe: dict[str, Any]
    backfill: bool = False


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

    def _candidatos_backfill(self) -> list[tuple[int, str, str, datetime]]:
        """Partidas de LoL já decididas, recentes, ainda sem scoreboard por
        jogador — pra puxar o frame final do feed (que guarda ~1-2 semanas)."""
        agora = datetime.now(timezone.utc)
        tem_mapas = (
            func.jsonb_array_length(
                func.coalesce(AgendaPartida.detalhe["mapas"], _JSONB_VAZIO)
            )
            > 0
        )
        # `detalhe ? 'lol_backfill_em'` — já tentamos (e não veio dado / não deu
        # pra casar); não insiste toda rodada.
        ja_carimbada = AgendaPartida.detalhe.has_key("lol_backfill_em")  # noqa: W601
        decidida = or_(
            AgendaPartida.vitoria_a.is_not(None),
            AgendaPartida.placar_a.is_not(None),
        )
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
                    AgendaPartida.inicio_previsto.between(
                        agora - BACKFILL_JANELA, agora - timedelta(minutes=45)
                    ),
                    decidida,
                    or_(
                        AgendaPartida.detalhe.is_(None),
                        and_(func.not_(tem_mapas), func.not_(ja_carimbada)),
                    ),
                )
                .order_by(AgendaPartida.inicio_previsto.desc())
                .limit(POR_RODADA_BACKFILL)
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
        ao_vivo = self._candidatos()
        backfill = self._candidatos_backfill()
        if not ao_vivo and not backfill:
            return []

        cliente = self._cliente()
        registros: list[RawRecord] = []
        try:
            if ao_vivo:
                agenda = cliente.get_json(
                    f"{ESPORTS_API}/getSchedule",
                    params={"hl": "en-US"},
                    headers={"x-api-key": CHAVE_API},
                )
                eventos = (
                    (agenda or {})
                    .get("data", {})
                    .get("schedule", {})
                    .get("events", [])
                )
                indice = self._indice_schedule(eventos)
                for id_agenda, nome_a, nome_b, inicio in ao_vivo:
                    reg = self._coletar_match(
                        cliente, indice, id_agenda, nome_a, nome_b, inicio, False
                    )
                    if reg is not None:
                        registros.append(reg)

            if backfill:
                indice_c = self._indice_completos(cliente)
                for id_agenda, nome_a, nome_b, inicio in backfill:
                    reg = self._coletar_match(
                        cliente, indice_c, id_agenda, nome_a, nome_b, inicio, True
                    )
                    registros.append(
                        reg
                        if reg is not None
                        else RawRecord(
                            fonte=self.fonte,
                            endpoint="/match-backfill",
                            identificador=str(id_agenda),
                            payload={"sem_dados": True},
                        )
                    )
        finally:
            cliente.close()
        return registros

    def _coletar_match(
        self,
        cliente: RateLimitedClient,
        indice: dict[Any, dict[str, Any]],
        id_agenda: int,
        nome_a: str,
        nome_b: str,
        inicio: datetime,
        backfill: bool,
    ) -> RawRecord | None:
        match_id = self._achar_match_id(indice, nome_a, nome_b, inicio)
        if match_id is None:
            return None
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
            return None

        dados_evento = (evento or {}).get("data", {}).get("event") or {}
        jogos = ((dados_evento.get("match") or {}).get("games")) or []
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=timezone.utc)
        janelas: dict[str, Any] = {}
        for jogo in jogos:
            gid = jogo.get("id")
            if not gid:
                continue
            if backfill:
                if jogo.get("state") != "completed":
                    continue
                janela = _frame_final(
                    cliente, gid, inicio, jogo.get("number") or 1
                )
            else:
                if jogo.get("state") not in ("inProgress", "completed"):
                    continue
                janela = _buscar_janela(cliente, gid)
            if janela is not None:
                janelas[gid] = janela

        if backfill and not janelas:
            return None
        return RawRecord(
            fonte=self.fonte,
            endpoint="/match-backfill" if backfill else "/match",
            identificador=str(id_agenda),
            payload={
                "nome_a": nome_a,
                "nome_b": nome_b,
                "evento": dados_evento,
                "janelas": janelas,
            },
        )

    def _indice_completos(
        self, cliente: RateLimitedClient
    ) -> dict[Any, dict[str, Any]]:
        """`{(par de times normalizados, dia) -> evento}` das partidas já
        encerradas das ligas tier 1. Caro de montar — cacheado 1h no processo."""
        agora = datetime.now(timezone.utc)
        cache = _indice_completos_cache
        if cache.get("indice") is not None and agora - cache["em"] < _TTL_INDICE_COMPLETOS:
            return cache["indice"]

        indice: dict[Any, dict[str, Any]] = {}
        try:
            ligas_resp = cliente.get_json(
                f"{ESPORTS_API}/getLeagues",
                params={"hl": "en-US"},
                headers={"x-api-key": CHAVE_API},
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("getLeagues (backfill) falhou", extra={"erro": str(exc)})
            return cache.get("indice") or {}

        limite_torneio = (agora.date() - timedelta(days=20)).isoformat()
        for liga in (ligas_resp or {}).get("data", {}).get("leagues") or []:
            if (liga.get("slug") or "").lower() not in LIGAS_TIER1:
                continue
            try:
                tresp = cliente.get_json(
                    f"{ESPORTS_API}/getTournamentsForLeague",
                    params={"hl": "en-US", "leagueId": liga.get("id")},
                    headers={"x-api-key": CHAVE_API},
                )
            except Exception:  # noqa: BLE001
                continue
            ligas_t = (tresp or {}).get("data", {}).get("leagues") or []
            torneios = ligas_t[0].get("tournaments") if ligas_t else []
            for t in torneios or []:
                tid = t.get("id")
                if not tid or (t.get("endDate") or "") < limite_torneio:
                    continue
                try:
                    cresp = cliente.get_json(
                        f"{ESPORTS_API}/getCompletedEvents",
                        params={"hl": "en-US", "tournamentId": tid},
                        headers={"x-api-key": CHAVE_API},
                    )
                except Exception:  # noqa: BLE001
                    continue
                eventos = (
                    (cresp or {})
                    .get("data", {})
                    .get("schedule", {})
                    .get("events", [])
                ) or []
                for chave, ev in self._indice_schedule(eventos).items():
                    indice.setdefault(chave, ev)

        cache["indice"] = indice
        cache["em"] = agora
        return indice

    # -- parse -----------------------------------------------------------

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoLolEsports:
        itens: list[DetalheLol] = []
        for registro in registros:
            if not isinstance(registro.payload, dict):
                continue
            backfill = registro.endpoint == "/match-backfill"
            if registro.payload.get("sem_dados"):
                # partida de backfill sem dado na lolesports — só carimba pra
                # não tentar de novo toda rodada.
                itens.append(
                    DetalheLol(int(registro.identificador), {}, backfill=True)
                )
                continue
            detalhe = _montar_detalhe(
                registro.payload.get("evento") or {},
                registro.payload.get("janelas") or {},
                registro.payload.get("nome_a") or "",
                registro.payload.get("nome_b") or "",
            )
            if detalhe and (detalhe.get("mapas") or detalhe.get("mapas_resultado")):
                itens.append(
                    DetalheLol(int(registro.identificador), detalhe, backfill=backfill)
                )
            elif backfill:
                itens.append(
                    DetalheLol(int(registro.identificador), {}, backfill=True)
                )
        return ResultadoLolEsports(itens=itens)

    def load(self, dados: ResultadoLolEsports) -> int:
        if not dados.itens:
            return 0
        agora_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        linhas_fato: list[tuple[int, dict[str, Any]]] = []
        atualizadas = 0
        with session_scope() as sessao:
            for item in dados.itens:
                existente = sessao.execute(
                    select(AgendaPartida.detalhe).where(
                        AgendaPartida.id == item.id_agenda
                    )
                ).scalar()

                if item.backfill:
                    novo = dict(existente or {})
                    gerado = item.detalhe or {}
                    if gerado.get("mapas"):
                        novo["mapas"] = gerado["mapas"]
                    if not novo.get("mapas_resultado") and gerado.get("mapas_resultado"):
                        novo["mapas_resultado"] = gerado["mapas_resultado"]
                    if not novo.get("placar_serie") and gerado.get("placar_serie"):
                        novo["placar_serie"] = gerado["placar_serie"]
                    novo.setdefault("fonte", gerado.get("fonte") or "lolesports")
                    if not novo.get("status") and gerado.get("status"):
                        novo["status"] = gerado["status"]
                    novo["lol_backfill_em"] = agora_iso
                else:
                    # Preserva os canais que outra fonte (PandaScore) já tinha
                    # gravado, quando a lolesports não trouxe os seus.
                    novo = dict(item.detalhe)
                    if not novo.get("streams") and (existente or {}).get("streams"):
                        novo["streams"] = existente["streams"]

                sessao.execute(
                    AgendaPartida.__table__.update()
                    .where(AgendaPartida.id == item.id_agenda)
                    .values(detalhe=novo)
                )
                atualizadas += 1
                for linha in _linhas_fato(novo):
                    linhas_fato.append((item.id_agenda, linha))

            gravadas = _gravar_fato_jogador(sessao, linhas_fato)

        logger.info(
            "detalhe de LoL carregado",
            extra={"partidas": atualizadas, "linhas_jogador": gravadas},
        )
        return atualizadas


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


def _frame_final(
    cliente: RateLimitedClient,
    gid: str,
    inicio_match: datetime,
    jogo_numero: int,
) -> dict[str, Any] | None:
    """O frame FINAL de um jogo já encerrado. O feed guarda o histórico por
    ~1-2 semanas; pedindo `startingTime` perto do fim provável do jogo ele
    devolve a janela terminando no frame de pós-jogo (K/D/A/ouro reais)."""
    teto = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=20)
    base = inicio_match + timedelta(minutes=(jogo_numero - 1) * 50 + 45)
    for extra in (timedelta(0), timedelta(minutes=25), timedelta(minutes=50)):
        alvo = min(base + extra, teto)
        alvo = alvo.replace(second=alvo.second - alvo.second % 10)
        try:
            dados = cliente.get_json(
                f"{FEED}/window/{gid}",
                params={"startingTime": alvo.strftime("%Y-%m-%dT%H:%M:%SZ")},
            )
        except Exception:  # noqa: BLE001
            continue
        frames = (dados or {}).get("frames") or []
        if not frames:
            continue
        ultimo = frames[-1]
        ouro = ((ultimo.get("blueTeam") or {}).get("totalGold")) or 0
        if ouro <= 0:
            continue
        if ultimo.get("gameState") == "finished" or extra == timedelta(minutes=50):
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
                        "posicao": posicao,
                        "time_a": rotulo_a,
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
                "id_externo": pm.get("esportsPlayerId"),
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


# ---------------------------------------------------------------------------
# fato_lol_jogador_partida — scoreboard por jogador/jogo
# ---------------------------------------------------------------------------


def _linhas_fato(detalhe: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai as linhas por jogador dos `mapas` do detalhe, só dos jogos já
    encerrados. `vitoria` sai do `mapas_resultado` (que quando vem da
    PandaScore já traz o vencedor real de cada jogo)."""
    vit_por_pos: dict[int, bool] = {}
    status_por_pos: dict[int, str | None] = {}
    for mr in detalhe.get("mapas_resultado") or []:
        pos = mr.get("posicao")
        if pos is None:
            continue
        status_por_pos[pos] = mr.get("status")
        if mr.get("vitoria_a") is not None:
            vit_por_pos[pos] = bool(mr["vitoria_a"])

    linhas: list[dict[str, Any]] = []
    for mapa in detalhe.get("mapas") or []:
        pos = mapa.get("posicao")
        if not pos:
            continue
        if status_por_pos.get(pos, "encerrado") != "encerrado":
            continue
        time_a = mapa.get("time_a")
        vit_a = vit_por_pos.get(pos)
        for j in mapa.get("jogadores") or []:
            ext = j.get("id_externo")
            if not ext:
                continue
            vitoria: bool | None = None
            if vit_a is not None and time_a is not None:
                vitoria = vit_a if j.get("time") == time_a else (not vit_a)
            campeao = j.get("campeao")
            linhas.append(
                {
                    "id_externo": str(ext),
                    "jogo_numero": int(pos),
                    "campeao": (str(campeao)[:48] if campeao else None),
                    "k": j.get("k"),
                    "d": j.get("d"),
                    "a": j.get("a"),
                    "cs": j.get("cs"),
                    "ouro": j.get("ouro"),
                    "nivel": j.get("nivel"),
                    "vitoria": vitoria,
                }
            )
    return linhas


def _gravar_fato_jogador(
    sessao, linhas: list[tuple[int, dict[str, Any]]]
) -> int:
    if not linhas:
        return 0
    id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == JOGO))
    if id_jogo is None:
        return 0
    externos = {linha["id_externo"] for _, linha in linhas}
    mapa_jogador = {
        ext: idj
        for idj, ext in sessao.execute(
            select(DimJogador.id_jogador, DimJogador.id_externo).where(
                DimJogador.id_jogo == id_jogo,
                DimJogador.id_externo.in_(externos),
            )
        )
    }
    agora = datetime.now(timezone.utc)
    registros: list[dict[str, Any]] = []
    for id_agenda, linha in linhas:
        id_jogador = mapa_jogador.get(linha["id_externo"])
        if id_jogador is None:
            continue
        registros.append(
            {
                "id_jogador": id_jogador,
                "id_agenda": id_agenda,
                "jogo_numero": linha["jogo_numero"],
                "campeao": linha["campeao"],
                "k": linha["k"],
                "d": linha["d"],
                "a": linha["a"],
                "cs": linha["cs"],
                "ouro": linha["ouro"],
                "nivel": linha["nivel"],
                "vitoria": linha["vitoria"],
                "coletado_em": agora,
            }
        )
    if not registros:
        return 0
    for lote in em_lotes(registros):
        stmt = pg_insert(FatoLolJogadorPartida).values(lote)
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_lol_jgp",
                set_={
                    "campeao": stmt.excluded.campeao,
                    "k": stmt.excluded.k,
                    "d": stmt.excluded.d,
                    "a": stmt.excluded.a,
                    "cs": stmt.excluded.cs,
                    "ouro": stmt.excluded.ouro,
                    "nivel": stmt.excluded.nivel,
                    "vitoria": stmt.excluded.vitoria,
                    "coletado_em": stmt.excluded.coletado_em,
                },
            )
        )
    return len(registros)
