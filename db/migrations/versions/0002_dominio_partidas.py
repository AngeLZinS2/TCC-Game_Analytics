"""Fase 2: dominio partidas (star schema de esports)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Semeado aqui porque sao valores fechados do dominio, nao dados coletados.
JOGOS = [
    {"codigo": "dota2", "nome": "Dota 2"},
    {"codigo": "lol", "nome": "League of Legends"},
    {"codigo": "valorant", "nome": "Valorant"},
]


def upgrade() -> None:
    dim_jogo = op.create_table(
        "dim_jogo",
        sa.Column("id_jogo", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("codigo", sa.String(length=16), nullable=False),
        sa.Column("nome", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id_jogo"),
        sa.UniqueConstraint("codigo"),
    )
    op.bulk_insert(dim_jogo, JOGOS)

    op.create_table(
        "dim_tempo",
        sa.Column("id_tempo", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("dia", sa.Integer(), nullable=False),
        sa.Column("trimestre", sa.Integer(), nullable=False),
        sa.Column("semana", sa.Integer(), nullable=False),
        sa.Column("dia_da_semana", sa.Integer(), nullable=False),
        sa.Column("nome_dia", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id_tempo"),
        sa.UniqueConstraint("data"),
    )

    op.create_table(
        "dim_jogador",
        sa.Column("id_jogador", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_jogo", sa.Integer(), nullable=False),
        sa.Column("id_externo", sa.String(length=64), nullable=False),
        sa.Column("nome", sa.Text(), nullable=True),
        sa.Column("regiao", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["id_jogo"], ["dim_jogo.id_jogo"]),
        sa.PrimaryKeyConstraint("id_jogador"),
        sa.UniqueConstraint("id_jogo", "id_externo", name="uq_jogador_jogo_externo"),
    )

    op.create_table(
        "dim_personagem",
        sa.Column("id_personagem", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_jogo", sa.Integer(), nullable=False),
        sa.Column("id_externo", sa.String(length=32), nullable=False),
        sa.Column("nome", sa.String(length=64), nullable=False),
        sa.Column("nome_interno", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["id_jogo"], ["dim_jogo.id_jogo"]),
        sa.PrimaryKeyConstraint("id_personagem"),
        sa.UniqueConstraint("id_jogo", "id_externo", name="uq_personagem_jogo_externo"),
    )

    op.create_table(
        "dim_partida",
        sa.Column("id_partida", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_jogo", sa.Integer(), nullable=False),
        sa.Column("id_externo", sa.String(length=64), nullable=False),
        sa.Column("id_tempo", sa.Integer(), nullable=True),
        sa.Column("data_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duracao_segundos", sa.Integer(), nullable=True),
        sa.Column("modo", sa.String(length=48), nullable=True),
        sa.Column("tipo_partida", sa.String(length=16), nullable=True),
        sa.Column("patch", sa.String(length=16), nullable=True),
        sa.Column("liga_nome", sa.Text(), nullable=True),
        sa.Column("liga_id_externo", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["id_jogo"], ["dim_jogo.id_jogo"]),
        sa.ForeignKeyConstraint(["id_tempo"], ["dim_tempo.id_tempo"]),
        sa.PrimaryKeyConstraint("id_partida"),
        sa.UniqueConstraint("id_jogo", "id_externo", name="uq_partida_jogo_externo"),
    )
    op.create_index("ix_partida_data_inicio", "dim_partida", ["data_inicio"])

    op.create_table(
        "fato_partida_jogador",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_partida", sa.BigInteger(), nullable=False),
        sa.Column("id_jogo", sa.Integer(), nullable=False),
        sa.Column("id_jogador", sa.BigInteger(), nullable=True),
        sa.Column("id_personagem", sa.Integer(), nullable=True),
        sa.Column("id_tempo", sa.Integer(), nullable=True),
        sa.Column("equipe", sa.String(length=16), nullable=True),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("vitoria", sa.Boolean(), nullable=True),
        sa.Column("kills", sa.Integer(), nullable=True),
        sa.Column("deaths", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("dano_causado", sa.Integer(), nullable=True),
        sa.Column("dano_recebido", sa.Integer(), nullable=True),
        sa.Column("economia", sa.Integer(), nullable=True),
        sa.Column("economia_por_minuto", sa.Integer(), nullable=True),
        sa.Column("experiencia_por_minuto", sa.Integer(), nullable=True),
        sa.Column("pontos_objetivo", sa.Integer(), nullable=True),
        sa.Column("last_hits", sa.Integer(), nullable=True),
        sa.Column("denies", sa.Integer(), nullable=True),
        sa.Column("nivel", sa.Integer(), nullable=True),
        sa.Column("funcao", sa.String(length=32), nullable=True),
        sa.Column("duracao_partida_segundos", sa.Integer(), nullable=True),
        sa.Column("metricas_extras", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id_partida"], ["dim_partida.id_partida"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["id_jogo"], ["dim_jogo.id_jogo"]),
        sa.ForeignKeyConstraint(["id_jogador"], ["dim_jogador.id_jogador"]),
        sa.ForeignKeyConstraint(["id_personagem"], ["dim_personagem.id_personagem"]),
        sa.ForeignKeyConstraint(["id_tempo"], ["dim_tempo.id_tempo"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_partida", "slot", name="uq_fato_partida_slot"),
    )
    op.create_index(
        "ix_fato_jogo_personagem",
        "fato_partida_jogador",
        ["id_jogo", "id_personagem"],
    )


def downgrade() -> None:
    op.drop_index("ix_fato_jogo_personagem", table_name="fato_partida_jogador")
    op.drop_table("fato_partida_jogador")
    op.drop_index("ix_partida_data_inicio", table_name="dim_partida")
    op.drop_table("dim_partida")
    op.drop_table("dim_personagem")
    op.drop_table("dim_jogador")
    op.drop_table("dim_tempo")
    op.drop_table("dim_jogo")
