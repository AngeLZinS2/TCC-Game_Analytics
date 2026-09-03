"""Fase 10: agenda de partidas futuras (Liquipedia)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agenda_partida",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_jogo", sa.Integer(), nullable=False),
        sa.Column("id_externo", sa.String(length=32), nullable=False),
        sa.Column("equipe_a_nome", sa.String(length=120), nullable=False),
        sa.Column("equipe_b_nome", sa.String(length=120), nullable=False),
        sa.Column("id_equipe_a", sa.Integer(), nullable=True),
        sa.Column("id_equipe_b", sa.Integer(), nullable=True),
        sa.Column("inicio_previsto", sa.DateTime(timezone=True), nullable=False),
        sa.Column("torneio", sa.Text(), nullable=True),
        sa.Column("formato", sa.String(length=16), nullable=True),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["id_jogo"], ["dim_jogo.id_jogo"]),
        sa.ForeignKeyConstraint(["id_equipe_a"], ["dim_equipe.id_equipe"]),
        sa.ForeignKeyConstraint(["id_equipe_b"], ["dim_equipe.id_equipe"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_jogo", "id_externo", name="uq_agenda_jogo_externo"),
    )
    op.create_index("ix_agenda_inicio", "agenda_partida", ["inicio_previsto"])


def downgrade() -> None:
    op.drop_index("ix_agenda_inicio", table_name="agenda_partida")
    op.drop_table("agenda_partida")
