"""Carga da varredura completa de ofertas Steam (Fase 35.1).

Duas responsabilidades, nesta ordem:

1. Garantir que todo app_id encontrado tenha uma linha minima em
   `dim_jogo_steam` (nome + imagem) - so INSERT, nunca UPDATE: um app que ja
   tem ficha completa (Fase 16, `appdetails`) nao pode ter recursos,
   plataformas, idiomas etc. apagados so porque esta varredura so conhece
   nome + imagem.
2. Alimentar o MESMO loader de preco/promocao que o fluxo monitorado ja usa
   (`load_steam_precos.py`) - reaproveita abertura/atualizacao de promocao,
   nao reimplementa a logica de transicao.

Encerrar uma promocao ausente da varredura so acontece quando ela terminou
por completo (`completa=True`) - uma varredura interrompida por erro nao
pode ser lida como "essas ofertas acabaram", so como "nao chegamos la".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import Settings, get_settings
from models.models import DimJogoSteam, DimTagSteam, PromocaoSteam
from models.session import session_scope
from services.etl.lotes import em_lotes
from services.etl.load_steam_precos import carregar as carregar_precos
from services.etl.transform_steam import ResultadoSteam, SnapshotSteam, truncar_janela
from services.etl.transform_steam_ofertas import LinhaOfertaSteam

logger = logging.getLogger(__name__)

#: A Steam so expoe moeda pelo `cc` da chamada, nunca no HTML de busca. O
#: projeto usa um unico pais (`STEAM_COUNTRY`) - `BR` e o unico valor real
#: hoje; os demais so pra nao quebrar se o pais mudar no `.env`.
_MOEDA_POR_PAIS = {
    "br": "BRL",
    "us": "USD",
    "ar": "ARS",
    "pt": "EUR",
}


def _imagem_header(app_id: int) -> str:
    # Mesmo CDN que `header_image` do `appdetails` resolve hoje - sem o `?t=`
    # (cache-buster da Steam), que nao e exigido pra a imagem carregar.
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"


@dataclass(slots=True)
class ResumoOfertasSteam:
    apps_novos: int = 0
    historico_inserido: int = 0
    promocoes_abertas: int = 0
    promocoes_atualizadas: int = 0
    promocoes_encerradas: int = 0
    tags_no_dicionario: int = 0
    apps_com_tags: int = 0
    apps_com_tipo: int = 0


def _upsert_ficha_minima(sessao, linhas: list[LinhaOfertaSteam]) -> int:
    """So INSERT - nunca sobrescreve uma ficha (Fase 16) ja existente."""
    valores = [
        {
            "app_id": linha.app_id,
            "nome": linha.nome,
            "tipo": linha.tipo,
            "imagem_header": _imagem_header(linha.app_id),
        }
        for linha in linhas
    ]
    inseridos = 0
    for lote in em_lotes(valores):
        stmt = pg_insert(DimJogoSteam).values(lote)
        stmt = stmt.on_conflict_do_nothing(index_elements=["app_id"])
        resultado = sessao.execute(stmt)
        # DB-API: rowcount pode vir -1 quando o driver nao sabe informar
        # (visto ao vivo em 2026-09-15, sem afetar o INSERT em si - so a
        # contagem no log). `max(..., 0)` evita que um -1 corrompa a soma.
        inseridos += max(resultado.rowcount or 0, 0)
    return inseridos


def _upsert_tags(sessao, tags: dict[int, str]) -> int:
    """O dicionario id -> nome das tags. Sobrescreve o nome (a Steam pode
    renomear uma tag), mas nunca apaga: uma tag some do dicionario popular
    sem deixar de existir nos apps que ja a tem."""
    if not tags:
        return 0
    valores = [{"tag_id": tag_id, "nome": nome} for tag_id, nome in tags.items()]
    for lote in em_lotes(valores):
        stmt = pg_insert(DimTagSteam).values(lote)
        stmt = stmt.on_conflict_do_update(
            index_elements=["tag_id"],
            set_={"nome": stmt.excluded.nome, "atualizado_em": func.now()},
        )
        sessao.execute(stmt)
    return len(valores)


def _atualizar_tags_dos_apps(sessao, linhas: list[LinhaOfertaSteam]) -> int:
    """Grava as tags da Steam nos apps da varredura.

    Separado do upsert de ficha porque a regra e outra: a ficha nunca e
    sobrescrita (`DO NOTHING`), mas a TAG precisa ser atualizada - os ~18 mil
    apps que a varredura anterior criou entraram sem tag nenhuma, e sem isto
    o filtro de genero nasceria vazio para todos eles.

    E um upsert com `set_` de UMA coluna, nao um `UPDATE ... WHERE` em lote:
    o segundo parecia mais direto, mas o SQLAlchemy recusa executemany com
    criterio WHERE ("bulk synchronize of persistent objects not supported"),
    e derrubava a carga inteira. Aqui o `ON CONFLICT` ja e o proprio criterio,
    e `set_` garante que so `tags_steam` e tocado - nenhum campo de ficha.
    """
    com_tags = [linha for linha in linhas if linha.tags]
    if not com_tags:
        return 0

    valores = [
        {
            "app_id": linha.app_id,
            "nome": linha.nome,
            "imagem_header": _imagem_header(linha.app_id),
            "tags_steam": linha.tags,
        }
        for linha in com_tags
    ]
    for lote in em_lotes(valores):
        stmt = pg_insert(DimJogoSteam).values(lote)
        stmt = stmt.on_conflict_do_update(
            index_elements=["app_id"],
            set_={"tags_steam": stmt.excluded.tags_steam},
        )
        sessao.execute(stmt)
    return len(com_tags)


def _atualizar_tipos(sessao, linhas: list[LinhaOfertaSteam]) -> int:
    """Grava `tipo` (jogo/DLC) nos apps que a varredura ja conhecia.

    O `_upsert_ficha_minima` acima so acerta o tipo de app NOVO: os ~19 mil
    que a varredura anterior criou (antes da separacao por `category1`)
    entraram com `tipo` nulo, e sem isto a tela de Ofertas - que agora so
    mostra `tipo = 'game'` - nasceria vazia pra todos eles.

    O `where` protege a ficha completa: quando o `appdetails` ja preencheu o
    tipo, ele manda. As duas fontes concordam no vocabulario ("game"/"dlc"),
    entao isto e desempate de procedencia, nao de valor - o `appdetails` e
    quem olhou o app, a varredura so sabe em qual filtro ele apareceu.
    """
    valores = [
        {
            "app_id": linha.app_id,
            "nome": linha.nome,
            "tipo": linha.tipo,
            "imagem_header": _imagem_header(linha.app_id),
        }
        for linha in linhas
    ]
    atualizados = 0
    for lote in em_lotes(valores):
        stmt = pg_insert(DimJogoSteam).values(lote)
        stmt = stmt.on_conflict_do_update(
            index_elements=["app_id"],
            set_={"tipo": stmt.excluded.tipo},
            where=DimJogoSteam.coletado_ficha_em.is_(None),
        )
        sessao.execute(stmt)
        atualizados += len(lote)
    return atualizados


def carregar(
    linhas: list[LinhaOfertaSteam],
    completa: bool,
    tags: dict[int, str] | None = None,
    settings: Settings | None = None,
) -> ResumoOfertasSteam:
    resumo = ResumoOfertasSteam()
    if not linhas:
        return resumo

    # A varredura pagina por `start`/`count` sobre uma lista que a Steam
    # reordena entre uma pagina e outra, entao o mesmo app reaparece em duas
    # paginas - medido: 19.393 linhas para ~18.000 apps distintos. Deduplicar
    # aqui, e nao em cada consumidor, porque:
    #   * `ON CONFLICT DO UPDATE` recusa duas linhas com a mesma chave no
    #     MESMO comando ("cannot affect row a second time") e derrubava a
    #     carga inteira;
    #   * sem isso o mesmo preco era processado duas vezes no historico.
    # Fica a ULTIMA ocorrencia: paginas mais tarde sao leitura mais recente.
    linhas = list({linha.app_id: linha for linha in linhas}.values())

    settings = settings or get_settings()
    pais = settings.steam_country.upper()
    moeda = _MOEDA_POR_PAIS.get(settings.steam_country.lower(), pais)
    agora = datetime.now(timezone.utc)

    with session_scope() as sessao:
        resumo.apps_novos = _upsert_ficha_minima(sessao, linhas)
        resumo.apps_com_tipo = _atualizar_tipos(sessao, linhas)
        resumo.tags_no_dicionario = _upsert_tags(sessao, tags or {})
        resumo.apps_com_tags = _atualizar_tags_dos_apps(sessao, linhas)

    snapshots = [
        SnapshotSteam(
            app_id=linha.app_id,
            janela_coleta=truncar_janela(agora, settings.snapshot_bucket_minutes),
            data_coleta=agora,
            preco_no_momento=Decimal(linha.preco_final_centavos) / 100,
            preco_original=Decimal(linha.preco_original_centavos) / 100,
            moeda=moeda,
            desconto_percentual=linha.desconto_percentual,
        )
        for linha in linhas
    ]
    resultado_precos = carregar_precos(ResultadoSteam(snapshots=snapshots), settings=settings)
    resumo.historico_inserido = resultado_precos.historico_inserido
    resumo.promocoes_abertas = resultado_precos.promocoes_abertas
    resumo.promocoes_atualizadas = resultado_precos.promocoes_atualizadas

    if completa:
        ids_na_varredura = {linha.app_id for linha in linhas}
        with session_scope() as sessao:
            ativas = sessao.scalars(
                select(PromocaoSteam).where(
                    PromocaoSteam.ativa.is_(True),
                    PromocaoSteam.pais == pais,
                )
            )
            for promo in ativas:
                if promo.app_id in ids_na_varredura:
                    continue
                promo.ativa = False
                promo.encerrada_em = agora
                promo.atualizada_em = agora
                resumo.promocoes_encerradas += 1

    logger.info(
        "carga de ofertas Steam concluida",
        extra={
            "apps_novos": resumo.apps_novos,
            "historico_inserido": resumo.historico_inserido,
            "promocoes_abertas": resumo.promocoes_abertas,
            "promocoes_atualizadas": resumo.promocoes_atualizadas,
            "promocoes_encerradas": resumo.promocoes_encerradas,
            "tags_no_dicionario": resumo.tags_no_dicionario,
            "apps_com_tags": resumo.apps_com_tags,
            "apps_com_tipo": resumo.apps_com_tipo,
            "completa": completa,
        },
    )
    return resumo
