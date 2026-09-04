"""Fase 18: tempo pra zerar (HowLongToBeat)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-04

O HLTB nao tem appid da Steam - o casamento e por nome, cacheado igual ao
`itad_id`. Uma linha basta (nao ha "oferta por loja" aqui, so tres tempos por
jogo), entao e so coluna nova em `dim_jogo_steam`, sem tabela propria.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_COLUNAS = [
    ("hltb_id", sa.String(length=40)),
    ("hltb_nome", sa.Text()),
    ("hltb_horas_historia", sa.Numeric(6, 1)),
    ("hltb_horas_extras", sa.Numeric(6, 1)),
    ("hltb_horas_completista", sa.Numeric(6, 1)),
    ("coletado_tempo_em", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    for nome, tipo in _COLUNAS:
        op.add_column("dim_jogo_steam", sa.Column(nome, tipo, nullable=True))


def downgrade() -> None:
    for nome, _tipo in reversed(_COLUNAS):
        op.drop_column("dim_jogo_steam", nome)
