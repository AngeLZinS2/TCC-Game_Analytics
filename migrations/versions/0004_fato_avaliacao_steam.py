"""Fase 7: avaliacoes individuais da Steam (base do modelo de sentimento)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fato_avaliacao_steam",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("id_externo", sa.String(length=32), nullable=False),
        sa.Column("idioma", sa.String(length=32), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("recomendado", sa.Boolean(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("minutos_jogados", sa.Integer(), nullable=True),
        sa.Column("votos_uteis", sa.Integer(), nullable=True),
        sa.Column("votos_engracados", sa.Integer(), nullable=True),
        sa.Column("compra_na_steam", sa.Boolean(), nullable=True),
        sa.Column("recebido_de_graca", sa.Boolean(), nullable=True),
        sa.Column("acesso_antecipado", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_id"], ["dim_jogo_steam.app_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", "id_externo", name="uq_avaliacao_app_externo"),
    )
    op.create_index("ix_avaliacao_idioma", "fato_avaliacao_steam", ["idioma"])
    op.create_index("ix_avaliacao_recomendado", "fato_avaliacao_steam", ["recomendado"])


def downgrade() -> None:
    op.drop_index("ix_avaliacao_recomendado", table_name="fato_avaliacao_steam")
    op.drop_index("ix_avaliacao_idioma", table_name="fato_avaliacao_steam")
    op.drop_table("fato_avaliacao_steam")
