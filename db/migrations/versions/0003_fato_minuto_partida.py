"""Fase 6: fato minuto a minuto (base do modelo de previsao)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fato_minuto_partida",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_partida", sa.BigInteger(), nullable=False),
        sa.Column("id_jogo", sa.Integer(), nullable=False),
        sa.Column("minuto", sa.Integer(), nullable=False),
        sa.Column("vantagem_economia", sa.Integer(), nullable=True),
        sa.Column("vantagem_experiencia", sa.Integer(), nullable=True),
        sa.Column(
            "torres_perdidas_lado_a",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "torres_perdidas_lado_b",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "objetivos_maiores_lado_a",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "objetivos_maiores_lado_b",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("vitoria_lado_a", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id_partida"], ["dim_partida.id_partida"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["id_jogo"], ["dim_jogo.id_jogo"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_partida", "minuto", name="uq_minuto_partida"),
    )
    op.create_index("ix_minuto_jogo", "fato_minuto_partida", ["id_jogo", "minuto"])


def downgrade() -> None:
    op.drop_index("ix_minuto_jogo", table_name="fato_minuto_partida")
    op.drop_table("fato_minuto_partida")
