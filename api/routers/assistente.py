"""Endpoint do assistente de dados.

O modelo de linguagem e o unico componente do projeto que roda fora daqui, e o
unico que pode inventar. Por isso a resposta carrega os `blocos` de contexto que
foram usados: a tela mostra ao lado do texto, e todo numero pode ser conferido
contra a fonte sem sair da pagina.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.schemas import BlocoContexto, EntradaPergunta, RespostaAssistente
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
        tokens_entrada=resposta.tokens_entrada,
        tokens_saida=resposta.tokens_saida,
    )
