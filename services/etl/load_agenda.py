"""Carga genérica de confrontos em `agenda_partida`, para qualquer fonte.

O `load_vlr` já fazia isto para Valorant; quando o HLTV entrou (CS), a lógica
— reconciliar times contra `dim_equipe`, criar os que faltam, upsert por
`id_externo` — era idêntica, só mudava o jogo e o prefixo do id. Ficou aqui,
parametrizada.

`confrontos` é qualquer iterável de objetos com os atributos: `id_externo`,
`equipe_a_nome`, `equipe_b_nome`, `inicio_previsto`, `torneio`, `formato`,
`vitoria_a`, `placar_a`, `placar_b`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Protocol

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.models import AgendaPartida, DimEquipe, DimJogo
from models.session import session_scope
from services.etl.load_liquipedia import _mapa_de_equipes, _resolver, normalizar

logger = logging.getLogger(__name__)


class JogoNaoCadastradoError(RuntimeError):
    """dim_jogo é semeada pelas migrations; sem ela nada pode ser carregado."""


class ConfrontoAgenda(Protocol):
    id_externo: str
    equipe_a_nome: str
    equipe_b_nome: str
    inicio_previsto: datetime
    torneio: str | None
    formato: str | None
    vitoria_a: bool | None
    placar_a: int | None
    placar_b: int | None
    # Opcionais — a PandaScore preenche, vlr/hltv não. Lidos com `getattr`.
    # equipe_a_logo / equipe_b_logo / equipe_a_tag / equipe_b_tag


def _preencher_escudos(
    sessao,
    id_jogo: int,
    mapa: dict[str, int],
    meta_time: dict[str, tuple[str | None, str | None]],
) -> None:
    """Preenche `logo_url` (e `tag` se nula) dos times que estão sem.

    Só toca em nulo — um escudo já gravado (da wiki, do OP.GG) manda. É o que
    faz a agenda de CS/LoL/CoD aparecer com escudo mesmo nos times que a
    PandaScore criou antes de eu passar a guardar a imagem.
    """
    if not meta_time:
        return

    sem_logo = {
        id_equipe
        for (id_equipe,) in sessao.execute(
            select(DimEquipe.id_equipe).where(
                DimEquipe.id_jogo == id_jogo, DimEquipe.logo_url.is_(None)
            )
        )
    }
    if not sem_logo:
        return

    ja_feito: set[int] = set()
    for nome, (logo, tag) in meta_time.items():
        if not logo:
            continue
        id_equipe = _resolver(nome, mapa)
        if id_equipe is None or id_equipe not in sem_logo or id_equipe in ja_feito:
            continue
        ja_feito.add(id_equipe)
        valores: dict = {"logo_url": logo}
        if tag:
            valores["tag"] = func.coalesce(DimEquipe.tag, tag)
        sessao.execute(
            update(DimEquipe)
            .where(DimEquipe.id_equipe == id_equipe)
            .values(**valores)
        )

    if ja_feito:
        logger.info(
            "escudos preenchidos na agenda",
            extra={"id_jogo": id_jogo, "quantidade": len(ja_feito)},
        )


def _detalhe(c: ConfrontoAgenda) -> dict | None:
    """`{status, streams, placar_serie, mapas_resultado}` para
    `agenda_partida.detalhe`, se a fonte trouxe.

    Só a PandaScore preenche esses campos (o resto usa `getattr`, que devolve
    `None`). Sem nenhum deles, retorna `None` e o `coalesce` do upsert preserva
    o que já estava (inclusive o detalhe rico do `vlr_detalhes`).
    """
    status = getattr(c, "status", None)
    streams = getattr(c, "streams", None)
    placar_serie = getattr(c, "placar_serie", None)
    mapas = getattr(c, "mapas", None)
    if not status and not streams and not placar_serie and not mapas:
        return None
    d: dict = {"fonte": "pandascore"}
    if status:
        d["status"] = status
    if streams:
        d["streams"] = streams
    if placar_serie:
        d["placar_serie"] = placar_serie
    if mapas:
        d["mapas_resultado"] = mapas
    return d


def carregar_agenda(
    jogo_codigo: str,
    confrontos: Iterable[ConfrontoAgenda],
    *,
    prefixo_equipe: str,
) -> int:
    """Persiste os confrontos, reconciliando os times. Devolve quantos entraram.

    `prefixo_equipe` é o que vai no `id_externo` de um time que não casou com a
    dimensão (ex.: `"vlr"`, `"hltv"`) — mantém a origem legível sem duplicar o
    time quando outra fonte já o tinha criado.
    """
    confrontos = list(confrontos)
    if not confrontos:
        return 0

    with session_scope() as sessao:
        id_jogo = sessao.scalar(
            select(DimJogo.id_jogo).where(DimJogo.codigo == jogo_codigo)
        )
        if id_jogo is None:
            raise JogoNaoCadastradoError(
                f"jogo {jogo_codigo!r} ausente em dim_jogo - rode `python cli.py init-db`"
            )

        mapa = _mapa_de_equipes(sessao, id_jogo)

        # Escudo e sigla que a fonte trouxe, por nome de time. A PandaScore
        # manda os dois em toda partida; vlr/hltv não mandam nada (getattr).
        meta_time: dict[str, tuple[str | None, str | None]] = {}
        for c in confrontos:
            for nome, logo, tag in (
                (
                    c.equipe_a_nome,
                    getattr(c, "equipe_a_logo", None),
                    getattr(c, "equipe_a_tag", None),
                ),
                (
                    c.equipe_b_nome,
                    getattr(c, "equipe_b_logo", None),
                    getattr(c, "equipe_b_tag", None),
                ),
            ):
                if nome and nome not in meta_time and (logo or tag):
                    meta_time[nome] = (logo, tag)

        sem_par = sorted(
            {
                nome
                for c in confrontos
                for nome in (c.equipe_a_nome, c.equipe_b_nome)
                if _resolver(nome, mapa) is None and nome.strip()
            }
        )
        if sem_par:
            sessao.execute(
                pg_insert(DimEquipe)
                .values(
                    [
                        {
                            "id_jogo": id_jogo,
                            "id_externo": f"{prefixo_equipe}:{normalizar(nome)}"[:200],
                            "nome": nome[:120],
                            "logo_url": meta_time.get(nome, (None, None))[0],
                            "tag": meta_time.get(nome, (None, None))[1],
                        }
                        for nome in sem_par
                    ]
                )
                .on_conflict_do_nothing(constraint="uq_equipe_jogo_externo")
            )
            sessao.flush()
            mapa = _mapa_de_equipes(sessao, id_jogo)
            logger.info(
                "equipes criadas da agenda",
                extra={"jogo": jogo_codigo, "quantidade": len(sem_par)},
            )

        # Backfill: time que já existia sem escudo ganha o da fonte agora.
        _preencher_escudos(sessao, id_jogo, mapa, meta_time)

        agora = datetime.now(timezone.utc)
        linhas = [
            {
                "id_jogo": id_jogo,
                "id_externo": c.id_externo,
                "equipe_a_nome": c.equipe_a_nome[:120],
                "equipe_b_nome": c.equipe_b_nome[:120],
                "id_equipe_a": _resolver(c.equipe_a_nome, mapa),
                "id_equipe_b": _resolver(c.equipe_b_nome, mapa),
                "inicio_previsto": c.inicio_previsto,
                "torneio": c.torneio,
                "formato": c.formato,
                "coletado_em": agora,
                "vitoria_a": c.vitoria_a,
                "placar_a": c.placar_a,
                "placar_b": c.placar_b,
                # `status` (running/not_started) e a live oficial — só a
                # PandaScore preenche; vlr/hltv/Liquipedia deixam nulo.
                "detalhe": _detalhe(c),
            }
            for c in confrontos
        ]

        stmt = pg_insert(AgendaPartida).values(linhas)
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_agenda_jogo_externo",
                set_={
                    "inicio_previsto": stmt.excluded.inicio_previsto,
                    "torneio": stmt.excluded.torneio,
                    "formato": stmt.excluded.formato,
                    "id_equipe_a": stmt.excluded.id_equipe_a,
                    "id_equipe_b": stmt.excluded.id_equipe_b,
                    "coletado_em": stmt.excluded.coletado_em,
                    "vitoria_a": stmt.excluded.vitoria_a,
                    "placar_a": stmt.excluded.placar_a,
                    "placar_b": stmt.excluded.placar_b,
                    # `coalesce`: se esta rodada não trouxe `detalhe` (fonte que
                    # não preenche, ou payload sem stream), o que já estava fica.
                    "detalhe": func.coalesce(
                        stmt.excluded.detalhe, AgendaPartida.detalhe
                    ),
                },
            )
        )

    logger.info(
        "agenda carregada",
        extra={"jogo": jogo_codigo, "confrontos": len(linhas)},
    )
    return len(linhas)
