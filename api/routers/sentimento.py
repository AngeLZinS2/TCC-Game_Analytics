"""Endpoints do modelo de sentimento sobre o texto das avaliacoes da Steam.

Router separado do `ml.py` de proposito: o modelo de previsao de partida le do
star schema de esports, este le do dominio de catalogo. Sao os dois dominios que
o projeto mantem separados desde o ETL, e juntar os endpoints num arquivo so
comecaria a apaga-los.

A tela distingue duas coisas que parecem a mesma:

* **Previsao** - o que o modelo diz sobre um texto (`/classificar`, e a coluna
  de probabilidade em `/avaliacoes`).
* **Observacao** - o que os autores de fato votaram (`/panorama`). Nao passa
  pelo modelo: sao contagens sobre `recomendado`.

Misturar as duas daria ao modelo credito por um dado que veio observado.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Integer, func, or_, select
from sqlalchemy.orm import Session

from api.schemas import (
    AspectoSentimento,
    AvaliacaoClassificada,
    ComparacaoSentimento,
    EntradaSentimento,
    JogoSentimento,
    PanoramaSentimento,
    PontoSentimentoDia,
    ResultadoSentimento,
)
from db.models import DimJogoSteam, FatoAvaliacaoSteam
from db.session import get_db
from ml import sentimento

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml/sentimento", tags=["ml"])

#: Modelos carregados, por (chave, mtime). O mtime invalida o cache sozinho
#: quando o treino roda de novo.
_CACHE: dict[tuple[str, float], Any] = {}


def _relatorio() -> dict[str, Any]:
    relatorio = sentimento.carregar_metricas()
    if relatorio is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Nenhum modelo de sentimento treinado. "
                "Rode `python cli.py train-sentimento`."
            ),
        )
    return relatorio


def _modelo(chave: str | None) -> tuple[str, Any]:
    relatorio = _relatorio()
    escolhida = chave or relatorio["modelo_ativo"]

    conhecidas = {m["chave"] for m in relatorio["modelos"]}
    if escolhida not in conhecidas:
        raise HTTPException(
            status_code=404,
            detail=f"modelo {escolhida!r} nao existe. Disponiveis: {sorted(conhecidas)}",
        )

    caminho = sentimento.PASTA / f"sentimento_{escolhida}.joblib"
    chave_cache = (escolhida, caminho.stat().st_mtime if caminho.exists() else 0.0)

    if chave_cache not in _CACHE:
        _CACHE.clear()
        _CACHE[chave_cache] = sentimento.carregar_modelo(escolhida)

    return escolhida, _CACHE[chave_cache]


@router.get("/comparacao", response_model=ComparacaoSentimento)
def comparacao() -> ComparacaoSentimento:
    """O relatorio do ultimo `cli.py train-sentimento`."""
    return ComparacaoSentimento(**_relatorio())


@router.post("/classificar", response_model=ResultadoSentimento)
def classificar(
    entrada: EntradaSentimento,
    modelo: str | None = Query(None, description="chave do modelo; padrao e o ativo"),
) -> ResultadoSentimento:
    """Classifica um texto avulso como recomendacao positiva ou negativa."""
    chave, estimador = _modelo(modelo)
    probabilidade = float(estimador.predict_proba([entrada.texto])[0, 1])

    return ResultadoSentimento(
        modelo=chave,
        probabilidade_positiva=round(probabilidade, 4),
        rotulo="positiva" if probabilidade >= 0.5 else "negativa",
        caracteres=len(entrada.texto),
        # O modelo nunca viu textos tao curtos no treino; a resposta sai, mas a
        # tela precisa poder avisar que ali ela vale menos.
        curto=len(entrada.texto) < sentimento.MINIMO_CARACTERES,
    )


@router.get("/avaliacoes", response_model=list[AvaliacaoClassificada])
def avaliacoes_classificadas(
    sessao: Session = Depends(get_db),
    app_id: int | None = Query(None),
    apenas_erros: bool = Query(False, description="so onde o modelo discordou do autor"),
    limite: int = Query(20, ge=1, le=100),
    modelo: str | None = Query(None),
) -> list[AvaliacaoClassificada]:
    """Avaliacoes reais com a previsao do modelo ao lado do rotulo verdadeiro.

    `apenas_erros` e o filtro que importa: mostrar so acertos transformaria a
    tela num folheto. O erro e onde da para ver o que o modelo nao aprendeu -
    sarcasmo, review misturando idiomas, elogio escrito com palavrao.
    """
    relatorio = _relatorio()
    chave, estimador = _modelo(modelo)

    consulta = (
        select(
            FatoAvaliacaoSteam.id_externo,
            FatoAvaliacaoSteam.texto,
            FatoAvaliacaoSteam.recomendado,
            FatoAvaliacaoSteam.criada_em,
            FatoAvaliacaoSteam.minutos_jogados,
            FatoAvaliacaoSteam.votos_uteis,
            DimJogoSteam.nome,
            DimJogoSteam.app_id,
        )
        .join(DimJogoSteam, DimJogoSteam.app_id == FatoAvaliacaoSteam.app_id)
        .where(
            FatoAvaliacaoSteam.idioma == relatorio["idioma"],
            func.length(FatoAvaliacaoSteam.texto) >= sentimento.MINIMO_CARACTERES,
        )
        .order_by(FatoAvaliacaoSteam.criada_em.desc().nullslast())
    )
    if app_id is not None:
        consulta = consulta.where(FatoAvaliacaoSteam.app_id == app_id)

    # Com o filtro de erro ligado busca muito mais linhas do que o limite: os
    # erros sao a minoria, e cortar antes de classificar devolveria quase nada.
    linhas = sessao.execute(
        consulta.limit(limite * 12 if apenas_erros else limite)
    ).all()
    if not linhas:
        return []

    probabilidades = estimador.predict_proba([linha[1] for linha in linhas])[:, 1]

    classificadas: list[AvaliacaoClassificada] = []
    for linha, probabilidade in zip(linhas, probabilidades):
        previsto = bool(probabilidade >= 0.5)
        if apenas_erros and previsto == bool(linha[2]):
            continue

        classificadas.append(
            AvaliacaoClassificada(
                id_externo=linha[0],
                texto=linha[1],
                recomendado=linha[2],
                criada_em=linha[3],
                minutos_jogados=linha[4],
                votos_uteis=linha[5],
                jogo=linha[6],
                app_id=linha[7],
                probabilidade_positiva=round(float(probabilidade), 4),
                acertou=previsto == bool(linha[2]),
                modelo=chave,
            )
        )
        if len(classificadas) >= limite:
            break

    return classificadas


@router.get("/panorama", response_model=PanoramaSentimento)
def panorama(
    sessao: Session = Depends(get_db),
    app_id: int | None = Query(None),
) -> PanoramaSentimento:
    """Recortes do rotulo VERDADEIRO: por jogo, por dia e por aspecto.

    Nada aqui passa pelo modelo - sao contagens sobre `recomendado`.

    O recorte por aspecto sai de uma lista de palavras (`ml.sentimento.ASPECTOS`),
    nao de um classificador: "entre as avaliacoes que mencionam desempenho,
    quantas recomendam". E um filtro transparente, e a tela diz isso; chamar de
    "analise de sentimento por aspecto" seria vender um modelo inexistente.
    """
    filtros = [func.length(FatoAvaliacaoSteam.texto) >= sentimento.MINIMO_CARACTERES]
    if app_id is not None:
        filtros.append(FatoAvaliacaoSteam.app_id == app_id)

    positivas = func.sum(func.cast(FatoAvaliacaoSteam.recomendado, Integer))

    por_jogo = [
        JogoSentimento(
            app_id=linha[0],
            jogo=linha[1],
            avaliacoes=linha[2],
            positivas=int(linha[3] or 0),
            percentual_positivo=round(100 * float(linha[3] or 0) / linha[2], 1),
        )
        for linha in sessao.execute(
            select(
                DimJogoSteam.app_id,
                DimJogoSteam.nome,
                func.count().label("n"),
                positivas,
            )
            .join(FatoAvaliacaoSteam, FatoAvaliacaoSteam.app_id == DimJogoSteam.app_id)
            .where(*filtros)
            .group_by(DimJogoSteam.app_id, DimJogoSteam.nome)
            .order_by(func.count().desc())
        )
    ]

    dia = func.date_trunc("day", FatoAvaliacaoSteam.criada_em).label("dia")
    por_dia = [
        PontoSentimentoDia(
            dia=linha[0].date(),
            avaliacoes=linha[1],
            positivas=int(linha[2] or 0),
            percentual_positivo=round(100 * float(linha[2] or 0) / linha[1], 1),
        )
        for linha in sessao.execute(
            select(dia, func.count(), positivas)
            .where(*filtros, FatoAvaliacaoSteam.criada_em.is_not(None))
            .group_by(dia)
            .order_by(dia)
        )
    ]

    aspectos: list[AspectoSentimento] = []
    for nome, termos in sentimento.ASPECTOS.items():
        mencao = or_(*[FatoAvaliacaoSteam.texto.ilike(f"%{t}%") for t in termos])
        linha = sessao.execute(
            select(func.count(), positivas).where(*filtros, mencao)
        ).first()

        total = linha[0] if linha else 0
        if not total:
            continue

        aspectos.append(
            AspectoSentimento(
                aspecto=nome,
                termos=list(termos),
                avaliacoes=total,
                positivas=int(linha[1] or 0),
                percentual_positivo=round(100 * float(linha[1] or 0) / total, 1),
            )
        )

    aspectos.sort(key=lambda aspecto: aspecto.percentual_positivo, reverse=True)

    geral = sessao.execute(select(func.count(), positivas).where(*filtros)).first()

    return PanoramaSentimento(
        avaliacoes=geral[0] if geral else 0,
        positivas=int(geral[1] or 0) if geral else 0,
        por_jogo=por_jogo,
        por_dia=por_dia,
        aspectos=aspectos,
    )
