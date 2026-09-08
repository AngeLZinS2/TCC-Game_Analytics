"""Fase 25: usuarios simultaneos da Steam (numero da plataforma, nao a soma)

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-08

A home mostrava "jogadores simultaneos na Steam" somando o ultimo snapshot dos
~48 jogos monitorados - o que responde outra pergunta ("quantos estao nos jogos
que a gente acompanha"), nao "quantos usuarios a Steam tem online agora".

A Valve publica o numero real da plataforma em
`valvesoftware.com/en/about/stats` (JSON: `users_online`, `users_ingame`). Esta
tabela guarda um snapshot por coleta - serie temporal, para a home mostrar a
variacao e um sparkline como faz com o resto.

O Top 100 mais jogados nao ganha tabela: vem ao vivo do
`ISteamChartsService` a cada request (com cache curto no endpoint).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fato_steam_online",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        # `users_online` da Valve: conectados a Steam neste instante.
        sa.Column("usuarios_online", sa.Integer(), nullable=False),
        # `users_ingame`: subconjunto que esta dentro de um jogo.
        sa.Column("usuarios_em_jogo", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_fato_steam_online_coletado_em", "fato_steam_online", ["coletado_em"]
    )

    # Cache de nome por app_id, SEM FK e SEM relacao com `dim_jogo_steam`. O
    # Top 100 mais jogados inclui apps que a gente nao monitora; a tela so
    # precisa do nome deles, nao de um registro de dimensao inteiro. Tabela
    # propria para nao arriscar um join com linha de dimensao pela metade.
    op.create_table(
        "dim_app_steam_nome",
        sa.Column("app_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("visto_em", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dim_app_steam_nome")
    op.drop_index("ix_fato_steam_online_coletado_em", table_name="fato_steam_online")
    op.drop_table("fato_steam_online")
