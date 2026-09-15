"""Preco primeiro-partido da Steam: historico deduplicado + promocao (Fase 35).

Roda por app, a partir do MESMO preco que `transform_steam.py::parse_preco()`
ja extrai do `appdetails` - nao reimplementa parsing de preco, so consome o
que `SnapshotSteam` carrega (`preco_no_momento`, `preco_original`, `moeda`,
`desconto_percentual`).

Uma promocao NUNCA e inferida de agregado de catalogo - so abre na transicao
`desconto=0 -> desconto>0` observada NAQUELE app, atualiza a MESMA linha
enquanto segue ativa, e so fecha na transicao inversa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from config import Settings, get_settings
from models.models import HistoricoPrecoSteam, PromocaoSteam
from models.session import session_scope
from services.etl.transform_steam import ResultadoSteam, SnapshotSteam, truncar_janela

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ResumoPrecos:
    historico_inserido: int = 0
    promocoes_abertas: int = 0
    promocoes_atualizadas: int = 0
    promocoes_encerradas: int = 0


def _centavos(valor: Decimal | None) -> int | None:
    if valor is None:
        return None
    return int((valor * 100).to_integral_value())


def _processar_app(
    sessao: Session, snap: SnapshotSteam, pais: str, settings: Settings, agora: datetime
) -> ResumoPrecos:
    resumo = ResumoPrecos()
    if snap.preco_no_momento is None or not snap.moeda:
        return resumo

    app_id = snap.app_id
    moeda = snap.moeda
    preco_final = _centavos(snap.preco_no_momento)
    preco_original = _centavos(snap.preco_original) or preco_final
    desconto = snap.desconto_percentual or 0
    if preco_final is None:
        return resumo

    # --- Historico: so insere se o preco mudou de verdade desde a ultima
    # linha daquele (app_id, pais, moeda). A constraint em `janela_coleta`
    # (mesmo bucket horario do snapshot) e a rede de seguranca no Postgres.
    ultima = sessao.scalar(
        select(HistoricoPrecoSteam)
        .where(
            HistoricoPrecoSteam.app_id == app_id,
            HistoricoPrecoSteam.pais == pais,
            HistoricoPrecoSteam.moeda == moeda,
        )
        .order_by(desc(HistoricoPrecoSteam.registrado_em))
        .limit(1)
    )
    mudou = (
        ultima is None
        or ultima.preco_final != preco_final
        or ultima.desconto_percentual != desconto
    )
    if mudou:
        stmt = pg_insert(HistoricoPrecoSteam).values(
            app_id=app_id,
            pais=pais,
            moeda=moeda,
            preco_original=preco_original,
            preco_final=preco_final,
            desconto_percentual=desconto,
            janela_coleta=truncar_janela(agora, settings.snapshot_bucket_minutes),
            registrado_em=agora,
        )
        stmt = stmt.on_conflict_do_nothing(constraint="uq_historico_preco_app_janela")
        resultado = sessao.execute(stmt)
        if resultado.rowcount:
            resumo.historico_inserido = 1

    # --- Promocao: transicao real de desconto, nunca heuristica de catalogo.
    promo_ativa = sessao.scalar(
        select(PromocaoSteam).where(
            PromocaoSteam.app_id == app_id,
            PromocaoSteam.pais == pais,
            PromocaoSteam.ativa.is_(True),
        )
    )

    if desconto > 0:
        if promo_ativa is None:
            sessao.add(
                PromocaoSteam(
                    app_id=app_id,
                    pais=pais,
                    moeda=moeda,
                    preco_original=preco_original,
                    preco_final=preco_final,
                    desconto_percentual=desconto,
                    iniciada_em=agora,
                    ativa=True,
                )
            )
            resumo.promocoes_abertas = 1
            logger.info(
                "promocao iniciada",
                extra={"app_id": app_id, "desconto_percentual": desconto},
            )
        elif (
            promo_ativa.preco_final != preco_final
            or promo_ativa.desconto_percentual != desconto
        ):
            promo_ativa.preco_final = preco_final
            promo_ativa.preco_original = preco_original
            promo_ativa.desconto_percentual = desconto
            promo_ativa.atualizada_em = agora
            resumo.promocoes_atualizadas = 1
    elif promo_ativa is not None:
        promo_ativa.ativa = False
        promo_ativa.encerrada_em = agora
        promo_ativa.atualizada_em = agora
        resumo.promocoes_encerradas = 1
        logger.info("promocao encerrada", extra={"app_id": app_id})

    return resumo


def carregar(resultado: ResultadoSteam, settings: Settings | None = None) -> ResumoPrecos:
    """Processa historico + promocao para todo snapshot com preco desta carga."""
    if not resultado.snapshots:
        return ResumoPrecos()

    settings = settings or get_settings()
    pais = settings.steam_country.upper()
    agora = datetime.now(timezone.utc)
    total = ResumoPrecos()

    with session_scope() as sessao:
        for snap in resultado.snapshots:
            parcial = _processar_app(sessao, snap, pais, settings, agora)
            total.historico_inserido += parcial.historico_inserido
            total.promocoes_abertas += parcial.promocoes_abertas
            total.promocoes_atualizadas += parcial.promocoes_atualizadas
            total.promocoes_encerradas += parcial.promocoes_encerradas

    if total.historico_inserido or total.promocoes_abertas or total.promocoes_encerradas:
        logger.info(
            "carga de precos Steam concluida",
            extra={
                "historico_inserido": total.historico_inserido,
                "promocoes_abertas": total.promocoes_abertas,
                "promocoes_atualizadas": total.promocoes_atualizadas,
                "promocoes_encerradas": total.promocoes_encerradas,
            },
        )
    return total
