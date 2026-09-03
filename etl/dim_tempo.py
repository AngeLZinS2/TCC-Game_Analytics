"""Dimensao de calendario, compartilhada por todos os jogos.

A chave e a propria data no formato AAAAMMDD (ex.: 20260902), o que dispensa
uma consulta de lookup: o ETL calcula a chave direto do timestamp da partida.
As linhas sao criadas sob demanda, so para as datas que aparecem na coleta.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import DimTempo

NOMES_DIA = (
    "segunda-feira",
    "terca-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sabado",
    "domingo",
)


def chave_para_data(chave: int) -> date:
    """20260902 -> date(2026, 9, 2)."""
    return datetime.strptime(str(chave), "%Y%m%d").date()


def linha_tempo(dia: date) -> dict[str, object]:
    """Monta a linha completa da dimensao a partir de uma data."""
    return {
        "id_tempo": int(dia.strftime("%Y%m%d")),
        "data": dia,
        "ano": dia.year,
        "mes": dia.month,
        "dia": dia.day,
        "trimestre": (dia.month - 1) // 3 + 1,
        "semana": dia.isocalendar().week,
        "dia_da_semana": dia.isoweekday(),
        "nome_dia": NOMES_DIA[dia.weekday()],
    }


def garantir_dim_tempo(sessao: Session, chaves: Iterable[int | None]) -> int:
    """Cria as linhas de calendario que ainda nao existem.

    Idempotente: chaves ja presentes sao ignoradas (ON CONFLICT DO NOTHING).
    """
    unicas = sorted({chave for chave in chaves if chave})
    if not unicas:
        return 0

    linhas = [linha_tempo(chave_para_data(chave)) for chave in unicas]
    stmt = pg_insert(DimTempo).values(linhas).on_conflict_do_nothing(
        index_elements=["id_tempo"]
    )
    sessao.execute(stmt)
    return len(linhas)
