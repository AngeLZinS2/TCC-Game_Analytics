"""Fase 28: resumo de avaliacoes por IA (Groq)

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-11

A aba "Recepcao por jogo" (Recomendacoes por Reviews) mostrava as avaliacoes
individuais classificadas, mas ninguem sintetizava "o que a comunidade esta
dizendo" em texto corrido. `resumo_reviews.py` amostra avaliacoes de
`fato_avaliacao_steam`, pede pro Groq (GPT-OSS 120B, free) um resumo em
portugues + pontos positivos/negativos, e cacheia aqui - igual ao `itad_id`/
`menor_preco_historico` ja cacheados em `dim_jogo_steam` pra outras fontes
externas.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dim_jogo_steam", sa.Column("resumo_reviews_texto", sa.Text(), nullable=True)
    )
    op.add_column(
        "dim_jogo_steam",
        sa.Column("resumo_reviews_positivos", sa.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "dim_jogo_steam",
        sa.Column("resumo_reviews_negativos", sa.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "dim_jogo_steam",
        sa.Column("resumo_reviews_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dim_jogo_steam",
        sa.Column("resumo_reviews_modelo", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "dim_jogo_steam",
        sa.Column("resumo_reviews_avaliacoes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dim_jogo_steam", "resumo_reviews_avaliacoes")
    op.drop_column("dim_jogo_steam", "resumo_reviews_modelo")
    op.drop_column("dim_jogo_steam", "resumo_reviews_em")
    op.drop_column("dim_jogo_steam", "resumo_reviews_negativos")
    op.drop_column("dim_jogo_steam", "resumo_reviews_positivos")
    op.drop_column("dim_jogo_steam", "resumo_reviews_texto")
