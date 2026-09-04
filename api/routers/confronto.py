"""Endpoints da previsao de confronto entre equipes.

Responde "qual time tem mais chance de vencer, e por que" - a pergunta que se
faz ANTES da partida. O `/api/ml/...` responde a outra: durante a partida, com
o mapa em curso.

A resposta carrega os fatores que a explicam e o relatorio de validacao junto.
Com a amostra atual o modelo nao supera a taxa base, e esconder isso atras de
uma porcentagem bonita seria o mesmo erro que a tela de assistente evita.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    ConfrontoAgendado,
    EquipeConfronto,
    LigaConfronto,
    PrevisaoConfronto,
    RelatorioConfronto,
)
from ml import confronto as motor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml/confronto", tags=["ml"])


def _relatorio(jogo: str) -> dict[str, Any]:
    """O relatorio DAQUELE jogo.

    O argumento nao e enfeite: sem ele esta funcao devolvia sempre o arquivo do
    Dota 2, e `/relatorio?jogo=counterstrike` respondia com `"jogo": "dota2"`
    dentro do corpo - numero certo respondendo a pergunta errada.
    """
    relatorio = motor.carregar_relatorio(jogo)
    if relatorio is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"As forças das equipes de {jogo} não foram ajustadas. Rode "
                f"`python cli.py train-confronto --jogo {jogo}` depois de coletar "
                "partidas COM RESULTADO: para Dota 2 elas vêm da OpenDota; para "
                "os demais jogos vêm do ticker da Liquipedia "
                f"(`cli.py collect liquipedia --wiki {jogo}`, coletado ao longo "
                "do tempo, já que o ticker só guarda uma janela recente)."
            ),
        )
    return relatorio


def _para_schema(equipe: motor.Equipe) -> EquipeConfronto:
    return EquipeConfronto(
        id_equipe=equipe.id_equipe,
        nome=equipe.nome,
        tag=equipe.tag,
        logo_url=equipe.logo_url,
        partidas=equipe.partidas,
        vitorias=equipe.vitorias,
        winrate=round(equipe.winrate, 1),
        forca=round(equipe.forca, 4),
        # Arredondado aqui, nao na tela: GPM com tres casas decimais nao e
        # precisao, e ruido de media - "540,067 de ouro por minuto" sugere uma
        # exatidao que a medida nao tem.
        gpm_medio=round(equipe.gpm_medio) if equipe.gpm_medio is not None else None,
        xpm_medio=round(equipe.xpm_medio) if equipe.xpm_medio is not None else None,
        kda_medio=round(equipe.kda_medio, 2) if equipe.kda_medio is not None else None,
        duracao_media_segundos=(
            round(equipe.duracao_media_segundos)
            if equipe.duracao_media_segundos is not None
            else None
        ),
        posicao_ranking=equipe.posicao_ranking,
        pontos_ranking=equipe.pontos_ranking,
    )


@router.get("/relatorio", response_model=RelatorioConfronto)
def relatorio(jogo: str = "dota2") -> RelatorioConfronto:
    """Como as forcas foram ajustadas e o que a validacao temporal disse."""
    return RelatorioConfronto(**_relatorio(jogo))


@router.get("/ligas", response_model=list[LigaConfronto])
def listar_ligas(jogo: str = "dota2") -> list[LigaConfronto]:
    """Campeonatos presentes nos dados coletados."""
    _relatorio(jogo)
    return [LigaConfronto(**liga) for liga in motor.ligas(jogo)]


@router.get("/ranking", response_model=list[EquipeConfronto])
def listar_ranking(
    jogo: str = "dota2",
    liga: str | None = Query(None, description="restringe ao campeonato"),
    min_partidas: int = Query(
        1,
        ge=1,
        description=(
            "corte de amostra. Um time com uma vitoria em uma partida lidera "
            "qualquer ranking sem significar nada."
        ),
    ),
) -> list[EquipeConfronto]:
    """Equipes ordenadas por forca - a resposta a 'quem e o favorito'."""
    _relatorio(jogo)
    return [
        _para_schema(equipe)
        for equipe in motor.ranking(jogo, liga)
        if equipe.partidas >= min_partidas
    ]


@router.get("/prever", response_model=PrevisaoConfronto)
def prever(
    equipe_a: int = Query(..., description="id da equipe do lado A"),
    equipe_b: int = Query(..., description="id da equipe do lado B"),
    jogo: str = "dota2",
) -> PrevisaoConfronto:
    """Probabilidade de a equipe A vencer a B, com os fatores por tras."""
    relatorio_atual = _relatorio(jogo)

    try:
        previsao = motor.prever(equipe_a, equipe_b, jogo)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PrevisaoConfronto(
        equipe_a=_para_schema(previsao.equipe_a),
        equipe_b=_para_schema(previsao.equipe_b),
        probabilidade_a=previsao.probabilidade_a,
        probabilidade_b=previsao.probabilidade_b,
        contribuicao_forca=previsao.contribuicao_forca,
        contribuicao_lado=previsao.contribuicao_lado,
        confrontos_diretos=previsao.confrontos_diretos,
        vitorias_diretas_a=previsao.vitorias_diretas_a,
        fatores=[
            {
                "rotulo": fator.rotulo,
                "valor_a": fator.valor_a,
                "valor_b": fator.valor_b,
                "diferenca": fator.diferenca,
                "unidade": fator.unidade,
                "peso_no_modelo": fator.peso_no_modelo,
            }
            for fator in previsao.fatores
        ],
        validacao=relatorio_atual["validacao"],
    )


@router.get("/agenda", response_model=list[ConfrontoAgendado])
def listar_agenda(
    jogo: str = "dota2",
    limite: int = Query(40, ge=1, le=200),
    apenas_com_previsao: bool = Query(False),
) -> list[ConfrontoAgendado]:
    """Proximos confrontos do calendario, com a previsao de cada um.

    Por padrao devolve tambem os que nao tem previsao: escondê-los daria a
    impressao de que a agenda e menor do que e, e o motivo ("time sem historico
    coletado") diz onde a coleta precisa crescer.

    **Nao exige modelo ajustado**, ao contrario dos outros endpoints deste
    router: o calendario vem da Liquipedia e existe para os 66 jogos com agenda,
    enquanto o ajuste so existe para os que tem partidas com resultado. Exigir o
    relatorio aqui devolvia 503 para um calendario que estava completo no banco.
    """
    return [
        ConfrontoAgendado(
            id_externo=confronto.id_externo,
            equipe_a_nome=confronto.equipe_a_nome,
            equipe_b_nome=confronto.equipe_b_nome,
            inicio_previsto=confronto.inicio_previsto,
            torneio=confronto.torneio,
            formato=confronto.formato,
            probabilidade_a=confronto.probabilidade_a,
            equipe_a=_para_schema(confronto.equipe_a) if confronto.equipe_a else None,
            equipe_b=_para_schema(confronto.equipe_b) if confronto.equipe_b else None,
            motivo_sem_previsao=confronto.motivo_sem_previsao,
        )
        for confronto in motor.agenda(jogo, limite)
        if not apenas_com_previsao or confronto.probabilidade_a is not None
    ]
