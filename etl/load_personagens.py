"""Carga de personagens e da estatistica agregada deles, para qualquer jogo.

Nasceu de duplicacao: o carregador dos agentes de Valorant e o dos campeoes de
League fariam exatamente as mesmas duas coisas - upsert em `dim_personagem` e
snapshot em `fato_estatistica_personagem` -, mudando so o codigo do jogo. Duas
copias divergiriam no dia em que uma ganhasse um campo e a outra nao.

O que E especifico de cada jogo fica no coletor: quais metricas existem, como
elas se chamam e de que bruto saem. Aqui so entra o que ja chegou pronto.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import DimJogo, DimPersonagem, FatoEstatisticaPersonagem
from db.session import session_scope

logger = logging.getLogger(__name__)


class JogoNaoCadastradoError(RuntimeError):
    """dim_jogo e semeada pelas migrations; sem ela nada pode ser carregado."""


def carregar(jogo: str, personagens: list[dict[str, Any]], fonte: str) -> int:
    """Grava o elenco e, para quem veio com numero, o snapshot dele.

    Devolve quantos personagens entraram na dimensao. `fonte` marca de onde as
    metricas vieram - nao e medicao nossa, e a tela precisa poder dizer isso.
    """
    if not personagens:
        return 0

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == jogo))
        if id_jogo is None:
            raise JogoNaoCadastradoError(
                f"jogo {jogo!r} ausente em dim_jogo - rode `python cli.py init-db`"
            )

        elenco = [
            {
                "id_jogo": id_jogo,
                "id_externo": p["id_externo"],
                "nome": p["nome"],
                "nome_interno": p.get("nome_interno"),
                "papel": p.get("papel"),
            }
            for p in personagens
        ]
        stmt = pg_insert(DimPersonagem).values(elenco)
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_personagem_jogo_externo",
                set_={
                    "nome": stmt.excluded.nome,
                    "nome_interno": stmt.excluded.nome_interno,
                    "papel": stmt.excluded.papel,
                },
            )
        )

        _snapshot(sessao, id_jogo, personagens, fonte)

    logger.info(
        "personagens carregados", extra={"jogo": jogo, "personagens": len(elenco)}
    )
    return len(elenco)


def _snapshot(
    sessao, id_jogo: int, personagens: list[dict[str, Any]], fonte: str
) -> int:
    """As metricas de quem veio COM numero.

    Personagem sem metrica nao vira linha de zeros: a diferenca entre "a fonte
    nao publicou" e "e zero" e exatamente o que a tela precisa poder dizer.

    A janela e truncada na hora, como `fato_snapshot_jogo_steam` - duas coletas
    na mesma hora viram um UPDATE, e a serie fica com o grao que a coleta tem.
    """
    com_numero = [p for p in personagens if p.get("metricas")]
    if not com_numero:
        return 0

    chaves = {
        id_externo: id_personagem
        for id_externo, id_personagem in sessao.execute(
            select(DimPersonagem.id_externo, DimPersonagem.id_personagem).where(
                DimPersonagem.id_jogo == id_jogo
            )
        )
    }

    janela = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    linhas = [
        {
            "id_personagem": chaves[p["id_externo"]],
            "janela_coleta": janela,
            "fonte": fonte,
            "partidas": p.get("partidas"),
            "vitorias": p.get("vitorias"),
            "metricas": p["metricas"],
        }
        for p in com_numero
        if p["id_externo"] in chaves
    ]
    if not linhas:
        return 0

    stmt = pg_insert(FatoEstatisticaPersonagem).values(linhas)
    sessao.execute(
        stmt.on_conflict_do_update(
            constraint="uq_estatistica_personagem_janela",
            set_={
                "partidas": stmt.excluded.partidas,
                "vitorias": stmt.excluded.vitorias,
                "metricas": stmt.excluded.metricas,
            },
        )
    )
    return len(linhas)
