"""Busca no catalogo completo da Steam e coleta sob demanda.

O `/api/steam/jogos` responde sobre o que ESTA no banco - os jogos que a coleta
ja trouxe. Este router responde sobre o que existe na Steam, que sao ~200 mil
apps, e permite trazer um deles para dentro na hora.

**Uma correcao importante sobre a chave.** A `STEAM_API_KEY` nao habilita nada
disto: a busca da loja (`storesearch`), o `appdetails` e o `appreviews` sao
todos publicos e sem chave. A chave serve para endpoints autenticados de dados
de JOGADOR (inventario, biblioteca, amigos), que este projeto nao usa. Ela fica
configurada para fases futuras.

**Por que a busca precisa coletar.** Achar um jogo na Steam da os dados que a
Steam publica - nome, nota agregada, preco. Mas as telas de recomendacao vivem
das avaliacoes com TEXTO, e essas so existem depois de coletadas. Sem a coleta
sob demanda, buscar um jogo novo mostraria a ficha e mais nada: nem tendencia,
nem aspectos, nem avaliacao classificada. Por isso `/coletar`.

**Preco nas outras lojas e resumo por IA.** O `/coletar` tambem dispara, na
mesma chamada, a coleta do ITAD e o resumo por IA (Groq) para esse app -
senao o painel "Onde comprar" e o "Resumo por IA" ficariam vazios ate a
rodada em lote (horas depois, e so quando o jogo entrasse na fila). Os dois
sao best-effort: se ITAD/Groq falharem ou nao tiverem chave, a coleta da
Steam ja esta feita e a resposta volta mesmo assim.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from views.schemas import CandidatoJogo, EntradaColeta, ResumoColeta
from services.collectors import steam_loja
from controllers.routers.telemetria import registrar_busca
from config import get_settings
from models.models import DimJogoSteam, FatoAvaliacaoSteam
from models.session import get_db, session_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/steam", tags=["steam"])

#: Paginas de avaliacoes numa coleta sob demanda.
#:
#: Menos que o padrao da coleta em lote: aqui alguem esta esperando na tela.
#: Tres paginas (~300 avaliacoes) levam uns 6 segundos e ja dao amostra para a
#: tendencia e os aspectos; dez levariam 20 e a pessoa acharia que travou.
PAGINAS_SOB_DEMANDA = 3


def _coletar_preco_sob_demanda(app_id: int) -> None:
    """Puxa o preco do ITAD para um app recem-coletado. Best-effort.

    Roda depois da coleta da Steam, na mesma requisicao: quem buscou um jogo
    novo quer o painel "Onde comprar" preenchido agora, nao na proxima rodada
    em lote. Sao ~2 chamadas (lookup do jogo + os dois lotes), ~2 segundos.

    Nunca levanta: sem `ITAD_API_KEY`, jogo gratuito ou ITAD fora do ar, a
    coleta da Steam ja aconteceu e a resposta do `/coletar` nao muda.
    """
    from services.collectors.itad_collector import ItadCollector
    from services.etl.raw_storage import RawStorage

    settings = get_settings()
    if not settings.itad_api_key:
        return

    storage = RawStorage(settings.raw_data_path, registrar_no_banco=True)
    coletor = ItadCollector(
        raw_storage=storage, settings=settings, app_ids=[app_id]
    )
    try:
        coletor.run(carregar=True)
    except Exception as exc:  # noqa: BLE001 - preco e acessorio, nao derruba a coleta
        logger.warning(
            "coleta de preco sob demanda falhou",
            extra={"app_id": app_id, "erro": f"{type(exc).__name__}: {exc}"},
        )
    finally:
        coletor.close()


def _gerar_resumo_sob_demanda(app_id: int) -> None:
    """Gera o resumo por IA (Groq) para um app recem-coletado. Best-effort.

    Roda na mesma requisicao do `/coletar`: as ~300 avaliacoes que acabaram de
    entrar (`PAGINAS_SOB_DEMANDA`) ja bastam pro minimo do resumo
    (`resumo_reviews_minimo_avaliacoes`, padrao 15) - sem isto o "Resumo por
    IA" so apareceria quando o jogo entrasse na fila do agendador (a cada 2h,
    6 por rodada), o que pode levar dias pra um catalogo grande.

    `app_ids=[app_id]` restringe a UM jogo: mesmo que o coletor normalmente
    processe varios por rodada, aqui e so essa chamada ao Groq (poucos
    segundos), nao um lote.

    Nunca levanta: sem `GROQ_API_KEY`, avaliacoes de menos, ou Groq fora do
    ar, a coleta da Steam ja aconteceu e a resposta do `/coletar` nao muda.
    """
    from services.collectors.resumo_reviews import ResumoReviewsCollector
    from services.etl.raw_storage import RawStorage

    settings = get_settings()
    if not settings.groq_api_key:
        return

    storage = RawStorage(settings.raw_data_path, registrar_no_banco=True)
    coletor = ResumoReviewsCollector(
        raw_storage=storage, settings=settings, app_ids=[app_id]
    )
    try:
        coletor.run(carregar=True)
    except Exception as exc:  # noqa: BLE001 - resumo e acessorio, nao derruba a coleta
        logger.warning(
            "resumo por IA sob demanda falhou",
            extra={"app_id": app_id, "erro": f"{type(exc).__name__}: {exc}"},
        )
    finally:
        coletor.close()


@router.get("/catalogo", response_model=list[CandidatoJogo])
def buscar_catalogo(
    termo: str = Query(..., min_length=2, max_length=100),
    sessao: Session = Depends(get_db),
) -> list[CandidatoJogo]:
    """Busca no catalogo da Steam, marcando o que ja foi coletado.

    O campo `coletado` e o que a tela usa para decidir entre mostrar as
    estatisticas ou oferecer o botao de coletar.
    """
    # `buscar` devolve lista vazia tanto para "nada casa" quanto para "a loja
    # nao respondeu". Aqui os dois casos tem a mesma resposta - uma busca sem
    # resultado - entao nao vale distinguir com um 502.
    itens = steam_loja.buscar(termo, limite=20)
    if not itens:
        registrar_busca("steam", termo, 0)
        return []

    app_ids = [int(item["id"]) for item in itens]

    # Uma consulta so para saber quais desses ja estao no banco, e com quantas
    # avaliacoes - N consultas dentro do laco seriam N idas ao Postgres.
    coletados = {
        linha[0]: linha[1]
        for linha in sessao.execute(
            select(DimJogoSteam.app_id, func.count(FatoAvaliacaoSteam.id))
            .outerjoin(
                FatoAvaliacaoSteam, FatoAvaliacaoSteam.app_id == DimJogoSteam.app_id
            )
            .where(DimJogoSteam.app_id.in_(app_ids))
            .group_by(DimJogoSteam.app_id)
        )
    }

    candidatos: list[CandidatoJogo] = []
    for item in itens:
        app_id = item.get("id")
        nome = item.get("name")
        if not isinstance(app_id, int) or not nome:
            continue

        preco = item.get("price") if isinstance(item.get("price"), dict) else {}
        candidatos.append(
            CandidatoJogo(
                app_id=app_id,
                nome=nome,
                tipo=item.get("type"),
                preco_centavos=preco.get("final"),
                moeda=preco.get("currency"),
                coletado=app_id in coletados,
                avaliacoes_coletadas=coletados.get(app_id, 0),
                imagem=item.get("tiny_image") or None,
            )
        )

    registrar_busca("steam", termo, len(candidatos))
    return candidatos


@router.post("/coletar", response_model=ResumoColeta)
def coletar(entrada: EntradaColeta) -> ResumoColeta:
    """Coleta um jogo da Steam agora, com o texto das avaliacoes.

    E o unico endpoint do projeto que ESCREVE chamando uma API externa. Roda de
    forma sincrona, e nao em fila, porque quem clicou esta esperando o resultado
    na tela - a Steam sao ~6 segundos, + preco/resumo por IA best-effort no
    fim (mais uns segundos cada, nunca minutos: so este app, nao um lote).
    """
    # Import tardio: o coletor arrasta requests, o ETL e o storage, e os outros
    # endpoints deste router nao precisam de nada disso.
    from services.collectors.steam_collector import SteamCollector
    from services.etl.raw_storage import RawStorage

    settings = get_settings()
    settings = settings.model_copy(
        update={"steam_reviews_paginas": PAGINAS_SOB_DEMANDA}
    )

    storage = RawStorage(settings.raw_data_path, registrar_no_banco=True)
    coletor = SteamCollector(
        raw_storage=storage, app_ids=[entrada.app_id], settings=settings
    )

    try:
        execucao = coletor.run(carregar=True)
    except Exception as exc:  # noqa: BLE001 - a tela precisa da mensagem
        logger.warning(
            "coleta sob demanda falhou",
            extra={"app_id": entrada.app_id, "erro": f"{type(exc).__name__}: {exc}"},
        )
        raise HTTPException(
            status_code=502, detail=f"a coleta falhou: {type(exc).__name__}"
        ) from exc
    finally:
        coletor.close()

    if not execucao.sucesso:
        raise HTTPException(
            status_code=502, detail=execucao.erro or "a coleta nao foi concluida"
        )

    # `registros_carregados` conta dimensao + snapshot + avaliacoes juntos; a
    # tela quer saber quantas AVALIACOES entraram, que e o que ela vai mostrar.
    with session_scope() as sessao:
        avaliacoes = sessao.scalar(
            select(func.count())
            .select_from(FatoAvaliacaoSteam)
            .where(FatoAvaliacaoSteam.app_id == entrada.app_id)
        )
        nome = sessao.scalar(
            select(DimJogoSteam.nome).where(DimJogoSteam.app_id == entrada.app_id)
        )

    if nome is None:
        # A Steam responde 200 com `success: false` para app inexistente ou
        # regionalmente indisponivel; o ETL descarta e nada e gravado.
        raise HTTPException(
            status_code=404,
            detail=(
                f"o app {entrada.app_id} nao devolveu dados de loja. "
                "Pode ser DLC, pacote, ou indisponivel nesta regiao."
            ),
        )

    # O jogo entrou no banco: agora preco nas outras lojas + resumo por IA,
    # best-effort os dois.
    _coletar_preco_sob_demanda(entrada.app_id)
    _gerar_resumo_sob_demanda(entrada.app_id)

    return ResumoColeta(
        app_id=entrada.app_id,
        nome=nome,
        avaliacoes_coletadas=int(avaliacoes or 0),
        registros_brutos=execucao.registros_coletados,
        segundos=round(execucao.duracao_segundos, 2),
    )

