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

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert

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
                "metadados": p.get("metadados"),
            }
            for p in personagens
        ]
        stmt = pg_insert(DimPersonagem).values(elenco)
        atualizaveis = {
            "nome": stmt.excluded.nome,
            "nome_interno": stmt.excluded.nome_interno,
            "papel": stmt.excluded.papel,
        }
        # So mexe em `metadados` quando esta coleta trouxe algum: uma fonte que
        # nao tem a parte estatica (o elenco da OpenDota, um dia) nao pode apagar
        # o que outra ja gravou.
        #
        # E MESCLA (`||`), nao substitui: a chave `guia` (build do OP.GG) as
        # vezes falta - o OP.GG devolve, sob carga, uma resposta vazia para
        # alguns campeoes. Substituir apagaria o guia bom da rodada anterior.
        # Com a mescla, as chaves que a coleta trouxe (lore, habilidades) sao
        # atualizadas e a `guia` que faltou nesta rodada permanece. A cobertura
        # so cresce entre rodadas.
        if any(p.get("metadados") for p in personagens):
            atual = func.coalesce(
                DimPersonagem.metadados, text("'{}'::jsonb")
            ).cast(JSONB)
            atualizaveis["metadados"] = atual.op("||")(
                pg_insert(DimPersonagem).excluded.metadados
            )
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_personagem_jogo_externo", set_=atualizaveis
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
    """As metricas de quem veio COM numero - o agregado geral e o de cada mapa.

    Personagem sem metrica nao vira linha de zeros: a diferenca entre "a fonte
    nao publicou" e "e zero" e exatamente o que a tela precisa poder dizer.

    A janela e truncada na hora, como `fato_snapshot_jogo_steam` - duas coletas
    na mesma hora viram um UPDATE, e a serie fica com o grao que a coleta tem.
    """
    chaves = {
        id_externo: id_personagem
        for id_externo, id_personagem in sessao.execute(
            select(DimPersonagem.id_externo, DimPersonagem.id_personagem).where(
                DimPersonagem.id_jogo == id_jogo
            )
        )
    }

    janela = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    linhas: list[dict[str, Any]] = []

    for p in personagens:
        id_personagem = chaves.get(p["id_externo"])
        if id_personagem is None:
            continue

        if p.get("metricas"):
            linhas.append(
                {
                    "id_personagem": id_personagem,
                    "janela_coleta": janela,
                    "fonte": fonte,
                    "mapa": "",  # `""` = o agregado geral
                    "partidas": p.get("partidas"),
                    "vitorias": p.get("vitorias"),
                    "metricas": p["metricas"],
                }
            )

        for recorte in p.get("por_mapa") or []:
            if not recorte.get("metricas"):
                continue
            linhas.append(
                {
                    "id_personagem": id_personagem,
                    "janela_coleta": janela,
                    "fonte": fonte,
                    "mapa": recorte["mapa"][:48],
                    "partidas": recorte.get("partidas"),
                    "vitorias": recorte.get("vitorias"),
                    "metricas": recorte["metricas"],
                }
            )

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
