"""Fase 9: equipes profissionais (base da previsao de confronto)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dim_equipe",
        sa.Column("id_equipe", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_jogo", sa.Integer(), nullable=False),
        sa.Column("id_externo", sa.String(length=32), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("tag", sa.String(length=32), nullable=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["id_jogo"], ["dim_jogo.id_jogo"]),
        sa.PrimaryKeyConstraint("id_equipe"),
        sa.UniqueConstraint("id_jogo", "id_externo", name="uq_equipe_jogo_externo"),
    )

    op.add_column("dim_partida", sa.Column("liga_tier", sa.String(length=24), nullable=True))
    op.add_column("dim_partida", sa.Column("id_equipe_lado_a", sa.Integer(), nullable=True))
    op.add_column("dim_partida", sa.Column("id_equipe_lado_b", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_partida_equipe_a", "dim_partida", "dim_equipe",
        ["id_equipe_lado_a"], ["id_equipe"],
    )
    op.create_foreign_key(
        "fk_partida_equipe_b", "dim_partida", "dim_equipe",
        ["id_equipe_lado_b"], ["id_equipe"],
    )
    op.create_index(
        "ix_partida_equipes", "dim_partida", ["id_equipe_lado_a", "id_equipe_lado_b"]
    )


def downgrade() -> None:
    op.drop_index("ix_partida_equipes", table_name="dim_partida")
    op.drop_constraint("fk_partida_equipe_b", "dim_partida", type_="foreignkey")
    op.drop_constraint("fk_partida_equipe_a", "dim_partida", type_="foreignkey")
    op.drop_column("dim_partida", "id_equipe_lado_b")
    op.drop_column("dim_partida", "id_equipe_lado_a")
    op.drop_column("dim_partida", "liga_tier")
    op.drop_table("dim_equipe")
