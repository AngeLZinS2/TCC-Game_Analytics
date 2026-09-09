"""Carga do snapshot de usuarios simultaneos + refresh do cache de nomes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from services.collectors.steam_loja import ficha
from services.collectors.steam_online import ResultadoSteamOnline
from models.models import DimAppSteamNome, DimJogoSteam, FatoSteamOnline
from models.session import session_scope

logger = logging.getLogger(__name__)

#: Teto de nomes a resolver por rodada. Depois da primeira, o Top 100 muda
#: devagar e quase nada cai aqui; o teto so limita o pior caso.
MAX_RESOLVER = 40


def carregar(resultado: ResultadoSteamOnline) -> int:
    gravados = 0
    with session_scope() as sessao:
        if resultado.usuarios_online is not None and resultado.usuarios_em_jogo is not None:
            sessao.add(
                FatoSteamOnline(
                    coletado_em=resultado.coletado_em,
                    usuarios_online=resultado.usuarios_online,
                    usuarios_em_jogo=resultado.usuarios_em_jogo,
                )
            )
            gravados += 1

        _resolver_nomes(sessao, resultado.top_app_ids)

    logger.info(
        "usuarios simultaneos da Steam gravados",
        extra={
            "online": resultado.usuarios_online,
            "em_jogo": resultado.usuarios_em_jogo,
            "top": len(resultado.top_app_ids),
        },
    )
    return gravados


def _resolver_nomes(sessao, app_ids: list[int]) -> None:
    """Preenche `dim_app_steam_nome` para os app_ids do Top 100 sem nome ainda."""
    if not app_ids:
        return

    ja_no_cache = set(
        sessao.scalars(
            select(DimAppSteamNome.app_id).where(DimAppSteamNome.app_id.in_(app_ids))
        )
    )
    ja_na_dimensao = set(
        sessao.scalars(
            select(DimJogoSteam.app_id).where(DimJogoSteam.app_id.in_(app_ids))
        )
    )
    pendentes = [
        a for a in app_ids if a not in ja_no_cache and a not in ja_na_dimensao
    ][:MAX_RESOLVER]

    agora = datetime.now(timezone.utc)
    for app_id in pendentes:
        dados = ficha(app_id)
        nome = (dados or {}).get("name")
        if not isinstance(nome, str) or not nome.strip():
            continue
        sessao.execute(
            pg_insert(DimAppSteamNome)
            .values(app_id=app_id, nome=nome.strip()[:200], visto_em=agora)
            .on_conflict_do_update(
                index_elements=["app_id"],
                set_={"nome": nome.strip()[:200], "visto_em": agora},
            )
        )

    if pendentes:
        logger.info("nomes de app resolvidos", extra={"quantidade": len(pendentes)})
