"""Agenda e resultados de esports via API da PandaScore.

A PandaScore é um provedor consolidado de dado de esports (13 jogos, id de
partida estável, cobertura desde 2014). O plano gratuito ("Schedules, Results &
Context", 1000 req/hora) entrega o que a tela "Partidas" precisa: confronto por
vir e confronto decidido com placar de série, torneio, formato e horário em UTC
de verdade — sem raspar HTML.

**Por que existe.** A agenda de CS vinha do `hltv.org` (bloqueado por Cloudflare,
só passa com `curl_cffi`) e do ticker esparso da Liquipedia. A PandaScore troca
o scraping frágil por uma API só, e o mesmo coletor serve LoL, CoD e outros
quando quiser — muda o slug do jogo.

**O que o free tier NÃO dá.** Estatística por jogador/mapa (KDA, gold, rounds) —
isso é o plano Historical, pago e caro. Para Valorant o detalhe por mapa
continua vindo do `vlr-detalhes`; para Dota, da OpenDota.

**Volume.** CS tem ~90 mil partidas decididas, a maioria de qualifier aberto
(tier c/d). O coletor filtra por TORNEIO: pega os torneios tier s/a/b (major a
regional) que estão rolando, por vir ou terminaram há pouco, e só as partidas
deles. São ~6-8 chamadas por rodada.

**Onde cai no schema.** `agenda_partida` (`carregar_agenda`), como vlr/hltv/
Liquipedia. `id_externo = pandascore:<match_id>`; times reconciliados por nome
contra o `dim_equipe` que a wiki já povoou, os que não casam entram com
`id_externo` `ps:<nome>`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings

logger = logging.getLogger(__name__)

#: prefixo de rota da PandaScore (`/{jogo}/matches`) -> código em `dim_jogo`.
#: Atenção: a rota NÃO é o slug do videogame — CoD é `cod-mw` no catálogo mas
#: `codmw` na URL.
JOGOS_PANDASCORE: dict[str, str] = {
    "csgo": "counterstrike",
    "lol": "leagueoflegends",
    "dota2": "dota2",
    "valorant": "valorant",
    "codmw": "callofduty",
    "ow": "overwatch",
    "r6siege": "rainbowsix",
    "rl": "rocketleague",
}

#: Quantos torneios recentes puxar de cada lista. 20 cobre a janela relevante.
TORNEIOS_POR_LISTA = 20

#: Teto de páginas por lista — proteção, não deve ser atingido (a agenda de CS
#: da PandaScore tem ~300 partidas por vir, 3 páginas).
MAX_PAGINAS = 4
PARTIDAS_POR_PAGINA = 100


class SemChavePandaScoreError(RuntimeError):
    """`PANDASCORE_API_KEY` não configurada — o coletor não tem o que fazer."""


@dataclass
class ConfrontoPandaScore:
    id_externo: str
    equipe_a_nome: str
    equipe_b_nome: str
    inicio_previsto: datetime
    torneio: str | None
    formato: str | None
    vitoria_a: bool | None
    placar_a: int | None
    placar_b: int | None
    # A PandaScore traz escudo e sigla de todo time — vira `dim_equipe.logo_url`
    # / `tag` no `carregar_agenda`, inclusive backfill dos que já existiam sem.
    equipe_a_logo: str | None = None
    equipe_b_logo: str | None = None
    equipe_a_tag: str | None = None
    equipe_b_tag: str | None = None


@dataclass
class ResultadoPandaScore:
    jogo_codigo: str
    confrontos: list[ConfrontoPandaScore] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.confrontos)


def _instante(*candidatos: str | None) -> datetime | None:
    """Primeiro ISO-8601 que decodificar, como datetime aware em UTC."""
    for texto in candidatos:
        if not texto:
            continue
        try:
            dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _rotulo_torneio(partida: dict[str, Any]) -> str | None:
    """`{league:BLAST Open, tournament:Playoffs}` -> `BLAST Open — Playoffs`."""
    liga = ((partida.get("league") or {}).get("name") or "").strip()
    etapa = ((partida.get("tournament") or {}).get("name") or "").strip()
    serie = ((partida.get("serie") or {}).get("full_name") or "").strip()

    partes = [p for p in (liga, etapa) if p and p.lower() not in {"tbd", "unknown"}]
    if not partes and serie:
        partes = [serie]
    return " — ".join(partes) or None


def _para_confronto(
    partida: dict[str, Any], tiers: set[str] | None = None
) -> ConfrontoPandaScore | None:
    """Uma partida da PandaScore -> `ConfrontoPandaScore`, ou `None` se não serve.

    Descarta: tier fora do filtro, sem os dois times definidos (TBD), cancelada,
    e sem horário.
    """
    status = partida.get("status")
    if status == "canceled":
        return None

    if tiers is not None:
        tier = (partida.get("tournament") or {}).get("tier")
        if tier not in tiers:
            return None

    times = [
        o["opponent"]
        for o in (partida.get("opponents") or [])
        if isinstance(o, dict) and o.get("opponent")
    ]
    if len(times) < 2:
        return None
    a, b = times[0], times[1]
    nome_a = (a.get("name") or "").strip()
    nome_b = (b.get("name") or "").strip()
    if not nome_a or not nome_b:
        return None

    inicio = _instante(
        partida.get("begin_at"),
        partida.get("scheduled_at"),
        partida.get("original_scheduled_at"),
    )
    if inicio is None:
        return None

    decidida = status == "finished"
    placar = {
        r.get("team_id"): r.get("score")
        for r in (partida.get("results") or [])
        if isinstance(r, dict)
    }
    placar_a = placar.get(a.get("id")) if decidida else None
    placar_b = placar.get(b.get("id")) if decidida else None

    vitoria_a: bool | None = None
    vencedor = partida.get("winner_id")
    if decidida and vencedor:
        vitoria_a = vencedor == a.get("id")

    nog = partida.get("number_of_games")
    formato = f"Bo{nog}" if isinstance(nog, int) and nog > 0 else None

    def _sigla(time: dict[str, Any]) -> str | None:
        sig = (time.get("acronym") or "").strip()
        return sig[:32] or None

    return ConfrontoPandaScore(
        id_externo=f"pandascore:{partida['id']}",
        equipe_a_nome=nome_a[:120],
        equipe_b_nome=nome_b[:120],
        inicio_previsto=inicio,
        torneio=_rotulo_torneio(partida),
        formato=formato,
        vitoria_a=vitoria_a,
        placar_a=placar_a,
        placar_b=placar_b,
        equipe_a_logo=a.get("image_url") or None,
        equipe_b_logo=b.get("image_url") or None,
        equipe_a_tag=_sigla(a),
        equipe_b_tag=_sigla(b),
    )


class PandaScoreCollector(BaseCollector[ResultadoPandaScore]):
    """Agenda + resultados de um jogo, via PandaScore.

    `jogo` é o slug da PandaScore (`csgo`, `lol`, ...). O código em `dim_jogo`
    sai do mapa `JOGOS_PANDASCORE`.
    """

    fonte = "pandascore"

    def __init__(
        self,
        raw_storage: Any,
        jogo: str = "csgo",
        settings: Settings | None = None,
    ) -> None:
        super().__init__(raw_storage)
        if jogo not in JOGOS_PANDASCORE:
            raise ValueError(
                f"jogo {jogo!r} não mapeado — conhecidos: {sorted(JOGOS_PANDASCORE)}"
            )
        self.jogo = jogo
        self.jogo_codigo = JOGOS_PANDASCORE[jogo]
        self.settings = settings or get_settings()
        self.client: RateLimitedClient | None = None

    @property
    def _base(self) -> str:
        return self.settings.pandascore_base_url.rstrip("/")

    def _cliente(self) -> RateLimitedClient:
        if self.client is None:
            self.client = RateLimitedClient(
                nome="pandascore",
                intervalo_minimo=self.settings.pandascore_rate_limit_seconds,
                max_retries=self.settings.http_max_retries,
                timeout=self.settings.http_timeout_seconds,
            )
        return self.client

    def _get(self, caminho: str, **params: Any) -> Any:
        cliente = self._cliente()
        return cliente.get_json(
            f"{self._base}/{self.jogo}/{caminho}",
            params=params,
            headers={"Authorization": f"Bearer {self.settings.pandascore_api_key}"},
        )

    def _ids_de_torneios(self) -> list[int]:
        """Torneios do tier configurado que estão rolando ou fecharam há pouco.

        Só para os RESULTADOS: as partidas por vir vêm da lista direta
        (`matches/upcoming`), que não some no volume tier c/d porque o filtro
        de tier é aplicado no `parse`.
        """
        tier = self.settings.pandascore_tiers
        ids: list[int] = []
        listas = (
            ("tournaments/running", {"sort": "begin_at"}),
            ("tournaments/past", {"sort": "-end_at"}),
        )
        for caminho, extra in listas:
            try:
                torneios = self._get(
                    caminho,
                    **{"filter[tier]": tier, "per_page": TORNEIOS_POR_LISTA, **extra},
                )
            except Exception as exc:  # noqa: BLE001 - uma lista fora não leva as outras
                self.logger.warning(
                    "lista de torneios da PandaScore falhou",
                    extra={"caminho": caminho, "erro": f"{type(exc).__name__}: {exc}"},
                )
                continue
            for t in torneios or []:
                if isinstance(t, dict) and isinstance(t.get("id"), int):
                    ids.append(t["id"])
        # dedup preservando ordem
        return list(dict.fromkeys(ids))

    def collect(self) -> list[RawRecord]:
        if not self.settings.pandascore_api_key:
            raise SemChavePandaScoreError(
                "PANDASCORE_API_KEY não configurada. Chave gratuita em "
                "https://pandascore.co/ e no .env."
            )

        registros: list[RawRecord] = []

        # 1. Próximas partidas: a lista direta, todos os tiers. O `parse` corta
        #    pelo tier — assim uma partida tier-c de uma série em andamento não
        #    depende do torneio dela estar no top-20.
        registros += self._paginar(
            "matches/upcoming",
            {"sort": "begin_at"},
            rotulo="upcoming",
        )

        # 2. Resultados: só as partidas decididas dos torneios do tier
        #    configurado — o histórico recente sem filtro é 99% qualifier aberto.
        ids = self._ids_de_torneios()
        if ids:
            registros += self._paginar(
                "matches",
                {
                    "filter[tournament_id]": ",".join(str(i) for i in ids),
                    "filter[status]": "finished",
                    "sort": "-end_at",
                },
                rotulo="resultados",
            )
        return registros

    def _paginar(
        self, caminho: str, params: dict[str, Any], *, rotulo: str
    ) -> list[RawRecord]:
        """Segue as páginas de um endpoint de lista até esvaziar ou o teto."""
        registros: list[RawRecord] = []
        for pagina in range(1, MAX_PAGINAS + 1):
            try:
                lote = self._get(
                    caminho, **params, per_page=PARTIDAS_POR_PAGINA, page=pagina
                )
            except Exception as exc:  # noqa: BLE001 - uma página fora não leva as outras
                self.logger.warning(
                    "página da PandaScore falhou",
                    extra={
                        "caminho": caminho,
                        "pagina": pagina,
                        "erro": f"{type(exc).__name__}: {exc}",
                    },
                )
                break
            if not lote:
                break
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=f"{self.jogo}/{caminho}",
                    identificador=f"{self.jogo}:{rotulo}:{pagina}",
                    payload=lote,
                )
            )
            if len(lote) < PARTIDAS_POR_PAGINA:
                break
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoPandaScore:
        tiers = {
            t.strip().lower()
            for t in self.settings.pandascore_tiers.split(",")
            if t.strip()
        } or None
        vistos: set[str] = set()
        confrontos: list[ConfrontoPandaScore] = []
        for registro in registros:
            partidas: Iterable[Any] = (
                registro.payload if isinstance(registro.payload, list) else []
            )
            for partida in partidas:
                if not isinstance(partida, dict) or "id" not in partida:
                    continue
                confronto = _para_confronto(partida, tiers)
                if confronto is None or confronto.id_externo in vistos:
                    continue
                vistos.add(confronto.id_externo)
                confrontos.append(confronto)
        return ResultadoPandaScore(jogo_codigo=self.jogo_codigo, confrontos=confrontos)

    def load(self, dados: ResultadoPandaScore) -> int:
        from etl.load_agenda import carregar_agenda

        return carregar_agenda(
            dados.jogo_codigo, dados.confrontos, prefixo_equipe="ps"
        )

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
