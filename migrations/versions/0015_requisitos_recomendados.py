"""Fase 19: requisitos recomendados, separados dos minimos

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-05

A ficha guardava so `pc_requirements.minimum`. A tela passou a separar as duas
abas - minimo e recomendado -, e para isso o recomendado precisa existir no
banco. Nem todo jogo publica: dos 30 no `data/raw/`, 21 tem recomendado e 9
so tem minimo, entao a coluna e nula com frequencia e a aba some quando for.

Sem rede pra preencher: o `pc_requirements` inteiro ja estava no payload do
appdetails, entao `python cli.py collect steam --from-raw` reprocessa.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dim_jogo_steam", sa.Column("requisitos_recomendados", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("dim_jogo_steam", "requisitos_recomendados")
