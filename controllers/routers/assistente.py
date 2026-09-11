"""Endpoint do assistente de dados.

O modelo de linguagem e o unico componente do projeto que roda fora daqui, e o
unico que pode inventar. Por isso a resposta carrega os `blocos` de contexto que
foram usados: a tela mostra ao lado do texto, e todo numero pode ser conferido
contra a fonte sem sair da pagina.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from controllers.routers.usuario import UsuarioAtual, exigir_usuario
from models.models import DimUsuario, FatoPerguntaAssistente
from models.session import get_db, session_scope
from services.cifra import decifrar
from views.schemas import (
    BlocoContexto,
    FonteWeb,
    EntradaPergunta,
    JogoAoVivo,
    JogoRecomendado,
    MenorPrecoHistorico,
    OfertaLoja,
    PontoSerieAssistente,
    RespostaAssistente,
    SerieAssistente,
)
from config import get_settings
from services.ml.assistente import AssistenteIndisponivel, perguntar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistente", tags=["assistente"])


def _registrar_pergunta(id_usuario: int, pergunta: str) -> None:
    """Grava a pergunta no historico da conta - melhor esforco, como
    `registrar_busca` em `telemetria.py`: falhar aqui nao pode derrubar uma
    resposta que ja chegou pro usuario."""
    try:
        with session_scope() as sessao:
            sessao.add(
                FatoPerguntaAssistente(
                    id_usuario=id_usuario,
                    pergunta=pergunta,
                    criado_em=datetime.now(timezone.utc),
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "gravar pergunta no historico falhou",
            extra={"erro": f"{type(exc).__name__}: {exc}"},
        )


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


@router.get("/saude")
def saude() -> dict[str, object]:
    """Telemetria em tempo real das chamadas ao OpenRouter.

    O `/auth/key` do provedor nao devolve quanto falta da cota gratis (so
    custo em dolar, que fica 0 pra modelo `:free`), entao o unico jeito de
    saber "esta rate-limited agora" e observar as nossas proprias chamadas -
    `telemetria_assistente` guarda as ultimas em memoria. A tela usa isto pra
    explicar um 429 na hora em vez de parecer bug nosso.
    """
    from services.ml import telemetria_assistente

    settings = get_settings()
    return {
        "configurado": bool(settings.openrouter_api_key),
        "modelo": settings.openrouter_model,
        **telemetria_assistente.resumo(),
    }


@router.post("/perguntar", response_model=RespostaAssistente)
def responder(
    entrada: EntradaPergunta,
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> RespostaAssistente:
    """Responde uma pergunta sobre os dados coletados.

    Exige conta (Fase 31) - a pergunta entra no historico pessoal, visivel em
    "Perfil". Quem cadastrou chave propria (Fase 33/34 - OpenRouter,
    Anthropic ou Google) usa ELA aqui, em vez da compartilhada do site. 503
    quando falta chave (nem a compartilhada, nem a propria) ou o provedor
    recusa - sao estados esperados, e a tela mostra a instrucao em vez de um
    erro generico.
    """
    chave_cifrada, provedor_pessoal, modelo_pessoal = sessao.execute(
        select(
            DimUsuario.chave_ia_cifrada,
            DimUsuario.chave_ia_provedor,
            DimUsuario.chave_ia_modelo,
        ).where(DimUsuario.id_usuario == usuario.id_usuario)
    ).one()
    chave_pessoal = decifrar(chave_cifrada) if chave_cifrada else None

    try:
        resposta = perguntar(
            entrada.pergunta,
            chave_pessoal=chave_pessoal,
            provedor_pessoal=provedor_pessoal,
            modelo_pessoal=modelo_pessoal,
        )
    except AssistenteIndisponivel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _registrar_pergunta(usuario.id_usuario, resposta.pergunta)

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
            imagem_fundo=j.imagem_fundo,
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
        fontes_web=[
            FonteWeb(url=f["url"], titulo=f["titulo"]) for f in resposta.fontes_web
        ],
        recomendacoes=[
            JogoRecomendado(
                app_id=j.app_id,
                nome=j.nome,
                generos=j.generos,
                nota_avaliacoes=j.nota_avaliacoes,
                jogadores_simultaneos=j.jogadores_simultaneos,
                imagem_header=j.imagem_header,
                preco=j.preco,
                moeda=j.moeda,
                gratuito=j.gratuito,
            )
            for j in resposta.recomendacoes
        ],
        jogo_ao_vivo=jogo_ao_vivo,
        series=[
            SerieAssistente(
                chave=s.chave,
                titulo=s.titulo,
                unidade=s.unidade,
                itens=[
                    PontoSerieAssistente(
                        rotulo=i.rotulo, valor=i.valor, detalhe=i.detalhe
                    )
                    for i in s.itens
                ],
            )
            for s in resposta.series
        ],
        tokens_entrada=resposta.tokens_entrada,
        tokens_saida=resposta.tokens_saida,
        usando_chave_propria=resposta.usando_chave_propria,
        provedor_ia=resposta.provedor_ia,
    )
