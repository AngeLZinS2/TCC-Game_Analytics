"""Carga dos confrontos de Valorant do vlr.gg em `agenda_partida`.

Mesma tabela do ticker da Liquipedia e dos confrontos de LoL do OP.GG. O que e
proprio daqui e a reconciliacao: o vlr.gg nomeia os times ("LOUD", "NRG"), e a
wiki ja povoou `dim_equipe` de Valorant com esses mesmos nomes. Entao aqui NAO
se cria um universo de times paralelo - reconcilia-se pela escada de casamento
de `etl/load_liquipedia` (exato, normalizado, sem enfeites), e so o que sobra
sem par entra como `dim_equipe` novo, com `id_externo` `vlr:<nome>`.

Sem isso, "LOUD" da Liquipedia e "LOUD" do vlr.gg seriam duas linhas na
dimensao, e a forca de um time se partiria em dois no Bradley-Terry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from collectors.vlr import JOGO, ResultadoVlr
from db.models import AgendaPartida, DimEquipe, DimJogo
from db.session import session_scope
from etl.load_liquipedia import _mapa_de_equipes, _resolver, normalizar

logger = logging.getLogger(__name__)


class JogoNaoCadastradoError(RuntimeError):
    """dim_jogo e semeada pelas migrations; sem ela nada pode ser carregado."""


def carregar(resultado: ResultadoVlr) -> int:
    """Persiste os confrontos, reconciliando os times. Devolve quantos entraram."""
    if not resultado.confrontos:
        return 0

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == JOGO))
        if id_jogo is None:
            raise JogoNaoCadastradoError(
                f"jogo {JOGO!r} ausente em dim_jogo - rode `python cli.py init-db`"
            )

        mapa = _mapa_de_equipes(sessao, id_jogo)

        # Times que a escada nao casou: nascem em dim_equipe com id `vlr:<nome>`.
        # Quando o `liquipedia-times` passar de novo, ele casa pelo nome e so
        # acrescenta regiao/pais - nao duplica.
        sem_par = sorted(
            {
                nome
                for c in resultado.confrontos
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
                            "id_externo": f"vlr:{normalizar(nome)}"[:200],
                            "nome": nome[:120],
                        }
                        for nome in sem_par
                    ]
                )
                .on_conflict_do_nothing(constraint="uq_equipe_jogo_externo")
            )
            sessao.flush()
            mapa = _mapa_de_equipes(sessao, id_jogo)
            logger.info(
                "equipes de valorant criadas do vlr.gg",
                extra={"quantidade": len(sem_par)},
            )

        agora = datetime.now(timezone.utc)
        linhas = [
            {
                "id_jogo": id_jogo,
                "id_externo": c.id_externo,
                "equipe_a_nome": c.equipe_a_nome,
                "equipe_b_nome": c.equipe_b_nome,
                "id_equipe_a": _resolver(c.equipe_a_nome, mapa),
                "id_equipe_b": _resolver(c.equipe_b_nome, mapa),
                "inicio_previsto": c.inicio_previsto,
                "torneio": c.torneio,
                "formato": c.formato,
                "coletado_em": agora,
                "vitoria_a": c.vitoria_a,
                "placar_a": c.placar_a,
                "placar_b": c.placar_b,
            }
            for c in resultado.confrontos
        ]

        stmt = pg_insert(AgendaPartida).values(linhas)
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_agenda_jogo_externo",
                set_={
                    # A linha nasce como "por vir" (placar nulo) e vira resultado
                    # na rodada seguinte, no lugar - por isso UPDATE, nao ignore.
                    "inicio_previsto": stmt.excluded.inicio_previsto,
                    "torneio": stmt.excluded.torneio,
                    "formato": stmt.excluded.formato,
                    "id_equipe_a": stmt.excluded.id_equipe_a,
                    "id_equipe_b": stmt.excluded.id_equipe_b,
                    "coletado_em": stmt.excluded.coletado_em,
                    "vitoria_a": stmt.excluded.vitoria_a,
                    "placar_a": stmt.excluded.placar_a,
                    "placar_b": stmt.excluded.placar_b,
                },
            )
        )

    logger.info("confrontos de valorant do vlr.gg carregados", extra={"confrontos": len(linhas)})
    return len(linhas)
