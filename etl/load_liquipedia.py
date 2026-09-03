"""Carga da agenda de partidas, com reconciliacao de nomes de equipe.

A parte dificil nao e o INSERT, e o casamento. A Liquipedia escreve
"Power Rangers"; a OpenDota cadastrou "_PowerRangers". "Pipsqueak+4" contra
"Pipsqueak + 4". Nao ha chave comum entre as duas fontes - so o nome, escrito
por pessoas diferentes.

A estrategia e uma escada, do mais seguro para o mais frouxo:

1. **Nome exato.** Barato e sem risco.
2. **Nome normalizado** - minusculo, sem acento, sem pontuacao, sem espacos.
   Resolve "_PowerRangers" e "Pipsqueak + 4" de uma vez.
3. **Nome sem os enfeites**: o sufixo entre parenteses que a Liquipedia usa
   para desambiguar pagina ("DYNASTY (stack)", "Crescent (Chinese team)") e os
   sufixos de organizacao ("Direborn Esports" -> "DIREBORN").
4. **Apelidos declarados a mao** (`APELIDOS`), para o que sobrar: abreviacoes e
   times renomeados.

O que nao casar fica com FK nula, e a partida aparece na tela sem previsao. E
melhor que o contrario: casar por similaridade aproximada produziria confronto
entre o time errado, e uma previsao confiante sobre a dupla errada e pior que
nenhuma previsao.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import AgendaPartida, DimEquipe, DimJogo
from db.session import session_scope
from etl.lotes import em_lotes
from etl.transform_liquipedia import ResultadoAgenda

logger = logging.getLogger(__name__)

#: O jogo a que a agenda pertence. A pagina coletada e a wiki de Dota 2.
JOGO = "dota2"

#: Sufixos de organizacao que aparecem num lado e nao no outro. So entram na
#: TERCEIRA tentativa, e so quando o resultado nao colide com outro time - sem
#: essa checagem, "Team Spirit" e "Team Spirit Academy" virariam o mesmo.
SUFIXOS_ORGANIZACAO = ("esports", "esport", "gaming", "club", "team")

#: Casos que a normalizacao nao resolve: abreviacao, rebranding, nome de
#: organizacao contra nome de line-up. Cresce quando alguem olha os nao
#: casados e reconhece um par - por isso fica aqui, versionado, e nao numa
#: tabela editavel sem rastro.
APELIDOS: dict[str, str] = {
    # liquipedia (normalizado) -> nome como esta em dim_equipe
}


def normalizar(nome: str) -> str:
    """Minusculo, sem acento e sem nada que nao seja letra ou numero.

    "_PowerRangers", "Power Rangers" e "power-rangers" viram a mesma chave.
    Agressivo de proposito: nomes de time de esports variam em pontuacao e
    espaco com muito mais frequencia do que colidem de verdade.
    """
    sem_acento = unicodedata.normalize("NFKD", nome.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", sem_acento)


def _sem_enfeites(nome: str) -> str:
    """Tira o desambiguador da wiki e o sufixo de organizacao.

    "DYNASTY (stack)" -> "dynasty"; "Direborn Esports" -> "direborn". O
    parentese e metadado da Liquipedia (ela desambigua paginas homonimas
    assim), nao parte do nome que o time usa.
    """
    sem_parenteses = re.sub(r"\s*\([^)]*\)\s*", " ", nome)
    chave = normalizar(sem_parenteses)

    for sufixo in SUFIXOS_ORGANIZACAO:
        if chave.endswith(sufixo) and len(chave) > len(sufixo) + 2:
            return chave[: -len(sufixo)]
    return chave


def _mapa_de_equipes(sessao: Session, id_jogo: int) -> dict[str, int]:
    """Todas as formas de escrever um time -> o id dele na dimensao."""
    mapa: dict[str, int] = {}
    colisoes: set[str] = set()

    for id_equipe, nome, tag in sessao.execute(
        select(DimEquipe.id_equipe, DimEquipe.nome, DimEquipe.tag).where(
            DimEquipe.id_jogo == id_jogo
        )
    ):
        mapa.setdefault(nome, id_equipe)
        mapa.setdefault(normalizar(nome), id_equipe)
        # A tag ("SpiritAc") so entra se nao colidir com outro time - duas
        # equipes com a mesma sigla nao sao raras, e um casamento errado aqui
        # produziria previsao sobre a dupla errada.
        if tag:
            chave = normalizar(tag)
            if chave and chave not in mapa:
                mapa[chave] = id_equipe

        # Mesma regra da tag: so entra se nao colidir. "Team Spirit" e
        # "Team Spirit Academy" reduzem para chaves diferentes, mas duas
        # organizacoes homonimas reduziriam para a mesma - e ai e melhor nao
        # casar nenhuma das duas do que casar a errada.
        enfeitado = _sem_enfeites(nome)
        if enfeitado and enfeitado not in mapa:
            mapa[enfeitado] = id_equipe
        elif enfeitado and mapa.get(enfeitado) != id_equipe:
            colisoes.add(enfeitado)

    # Chave ambigua nao serve para casar nada.
    for chave in colisoes:
        mapa.pop(chave, None)

    return mapa


def _resolver(nome: str, mapa: dict[str, int]) -> int | None:
    """Escada de casamento: exato, normalizado, apelido."""
    if nome in mapa:
        return mapa[nome]

    chave = normalizar(nome)
    if chave in mapa:
        return mapa[chave]

    enfeitado = _sem_enfeites(nome)
    if enfeitado and enfeitado != chave and enfeitado in mapa:
        return mapa[enfeitado]

    apelido = APELIDOS.get(chave)
    if apelido:
        return mapa.get(apelido) or mapa.get(normalizar(apelido))

    return None


def carregar(resultado: ResultadoAgenda) -> int:
    """Persiste a agenda, resolvendo as equipes contra a dimensao."""
    if not resultado.partidas:
        return 0

    agora = datetime.now(timezone.utc)

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == JOGO))
        if id_jogo is None:
            raise RuntimeError(
                f"jogo {JOGO!r} ausente em dim_jogo - rode `cli.py init-db`"
            )

        mapa = _mapa_de_equipes(sessao, id_jogo)

        linhas = []
        nao_casados: set[str] = set()

        for partida in resultado.partidas:
            id_a = _resolver(partida.equipe_a_nome, mapa)
            id_b = _resolver(partida.equipe_b_nome, mapa)

            for nome, id_equipe in (
                (partida.equipe_a_nome, id_a),
                (partida.equipe_b_nome, id_b),
            ):
                if id_equipe is None:
                    nao_casados.add(nome)

            linhas.append(
                {
                    "id_jogo": id_jogo,
                    "id_externo": partida.id_externo,
                    "equipe_a_nome": partida.equipe_a_nome,
                    "equipe_b_nome": partida.equipe_b_nome,
                    "id_equipe_a": id_a,
                    "id_equipe_b": id_b,
                    "inicio_previsto": partida.inicio_previsto,
                    "torneio": partida.torneio,
                    "formato": partida.formato,
                    "coletado_em": agora,
                }
            )

        # Dedup por `id_externo` ANTES do upsert.
        #
        # `ON CONFLICT DO UPDATE` recusa dois registros com a mesma chave no
        # MESMO comando (`CardinalityViolation`), e isso acontece de verdade:
        # a agenda e coletada de hora em hora, `ler_ultima_coleta` devolve
        # todos os payloads da janela, e o mesmo confronto aparece em varios
        # deles com o mesmo id (sha1 de times+horario). Fica a ultima
        # ocorrencia, que e a leitura mais recente do mesmo confronto.
        unicas: dict[str, dict] = {}
        for linha in linhas:
            unicas[linha["id_externo"]] = linha

        for lote in em_lotes(list(unicas.values())):
            stmt = pg_insert(AgendaPartida).values(lote)
            atualizaveis = {
                coluna: stmt.excluded[coluna]
                for coluna in lote[0]
                if coluna not in ("id_jogo", "id_externo")
            }
            sessao.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_agenda_jogo_externo", set_=atualizaveis
                )
            )

    com_previsao = sum(
        1 for l in linhas if l["id_equipe_a"] and l["id_equipe_b"]
    )
    logger.info(
        "agenda carregada",
        extra={
            "partidas": len(linhas),
            "com_as_duas_equipes_casadas": com_previsao,
            "nomes_nao_casados": len(nao_casados),
        },
    )
    if nao_casados:
        # Em nivel de debug e de proposito: a lista e longa e esperada. Quem
        # for melhorar a reconciliacao liga o debug e ve os candidatos.
        logger.debug(
            "nomes sem equipe correspondente",
            extra={"nomes": sorted(nao_casados)[:40]},
        )

    return len(linhas)
