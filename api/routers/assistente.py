"""Endpoint do assistente de dados.

O modelo de linguagem e o unico componente do projeto que roda fora daqui, e o
unico que pode inventar. Por isso a resposta carrega os `blocos` de contexto que
foram usados: a tela mostra ao lado do texto, e todo numero pode ser conferido
contra a fonte sem sair da pagina.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.schemas import (
    BlocoContexto,
    EntradaPergunta,
    JogoAoVivo,
    JogoRecomendado,
    MenorPrecoHistorico,
    OfertaLoja,
    RespostaAssistente,
)
from config import get_settings
from ml.assistente import AssistenteIndisponivel, perguntar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistente", tags=["assistente"])


@router.get("/status")
def status() -> dict[str, object]:
    """Se o assistente esta configurado, e com qual modelo.

    A tela consulta isto antes de mostrar o campo de pergunta: sem chave, ela
    explica o que falta em vez de deixar o usuario escrever e receber erro.
    """
    settings = get_settings()
    return {
        "configurado": bool(settings.openrouter_api_key),
        "modelo": settings.openrouter_model,
        "provedor": "OpenRouter",
    }


@router.post("/perguntar", response_model=RespostaAssistente)
def responder(entrada: EntradaPergunta) -> RespostaAssistente:
    """Responde uma pergunta sobre os dados coletados.

    503 quando falta chave ou o provedor recusa - sao estados esperados, e a
    tela mostra a instrucao em vez de um erro generico.
    """
    try:
        resposta = perguntar(entrada.pergunta)
    except AssistenteIndisponivel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    jogo_ao_vivo = None
    if resposta.jogo_ao_vivo is not None:
        j = resposta.jogo_ao_vivo
        # Mesmo criterio de `api/routers/steam.py`: ordena por preco, marca a
        # primeira como "melhor" - so faz sentido com pelo menos uma oferta.
        ofertas_ordenadas = sorted(j.ofertas, key=lambda o: o.preco)
        jogo_ao_vivo = JogoAoVivo(
            app_id=j.app_id,
            nome=j.nome,
            imagem_header=j.imagem_header,
            generos=j.generos,
            desenvolvedora=j.desenvolvedora,
            preco_atual=j.preco_atual,
            moeda=j.moeda,
            gratuito=j.gratuito,
            no_nosso_banco=j.no_nosso_banco,
            ofertas=[
                OfertaLoja(
                    loja=o.loja,
                    preco=o.preco,
                    preco_normal=o.preco_normal,
                    desconto=o.desconto,
                    moeda=o.moeda,
                    url=o.url,
                    drm=o.drm,
                    melhor=(i == 0),
                )
                for i, o in enumerate(ofertas_ordenadas)
            ],
            menor_historico=(
                MenorPrecoHistorico(
                    preco=j.menor_historico.preco,
                    loja=j.menor_historico.loja,
                    moeda=j.menor_historico.moeda,
                    data=j.menor_historico.data,
                )
                if j.menor_historico is not None
                else None
            ),
        )

    return RespostaAssistente(
        pergunta=resposta.pergunta,
        resposta=resposta.resposta,
        modelo=resposta.modelo,
        blocos=[
            BlocoContexto(
                chave=b.chave, titulo=b.titulo, conteudo=b.conteudo, fonte=b.fonte
            )
            for b in resposta.blocos
        ],
        recomendacoes=[
            JogoRecomendado(
                app_id=j.app_id,
                nome=j.nome,
                generos=j.generos,
                nota_avaliacoes=j.nota_avaliacoes,
                jogadores_simultaneos=j.jogadores_simultaneos,
                preco=j.preco,
                moeda=j.moeda,
                gratuito=j.gratuito,
            )
            for j in resposta.recomendacoes
        ],
        jogo_ao_vivo=jogo_ao_vivo,
        tokens_entrada=resposta.tokens_entrada,
        tokens_saida=resposta.tokens_saida,
    )
