"""Fase 0/1: tabela raw_data + dominio catalogo/mercado (Steam)

Revision ID: 0001
Revises:
Create Date: 2026-09-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_data",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fonte", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=128), nullable=False),
        sa.Column("identificador", sa.String(length=128), nullable=False),
        sa.Column("caminho_arquivo", sa.Text(), nullable=False),
        sa.Column("hash_payload", sa.String(length=64), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "registrado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fonte", "endpoint", "identificador", "coletado_em",
            name="uq_raw_data_coleta",
        ),
    )
    op.create_index(
        "ix_raw_data_fonte_coletado_em", "raw_data", ["fonte", "coletado_em"]
    )

    op.create_table(
        "dim_jogo_steam",
        sa.Column("app_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=True),
        sa.Column("desenvolvedora", sa.Text(), nullable=True),
        sa.Column("publicadora", sa.Text(), nullable=True),
        sa.Column("data_lancamento", sa.Date(), nullable=True),
        sa.Column("data_lancamento_texto", sa.String(length=64), nullable=True),
        sa.Column("generos", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("gratuito", sa.Boolean(), nullable=True),
        sa.Column("preco_atual", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("moeda", sa.String(length=8), nullable=True),
        sa.Column("nota_metacritic", sa.Integer(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("app_id"),
    )

    op.create_table(
        "fato_snapshot_jogo_steam",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("janela_coleta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_coleta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("jogadores_simultaneos", sa.Integer(), nullable=True),
        sa.Column("nota_avaliacoes", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("numero_avaliacoes", sa.Integer(), nullable=True),
        sa.Column("avaliacoes_positivas", sa.Integer(), nullable=True),
        sa.Column("avaliacoes_negativas", sa.Integer(), nullable=True),
        sa.Column("classificacao_steam", sa.String(length=64), nullable=True),
        sa.Column("preco_no_momento", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("moeda", sa.String(length=8), nullable=True),
        sa.Column("desconto_percentual", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_id"], ["dim_jogo_steam.app_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", "janela_coleta", name="uq_snapshot_app_janela"),
    )
    op.create_index("ix_snapshot_janela", "fato_snapshot_jogo_steam", ["janela_coleta"])


def downgrade() -> None:
    op.drop_index("ix_snapshot_janela", table_name="fato_snapshot_jogo_steam")
    op.drop_table("fato_snapshot_jogo_steam")
    op.drop_table("dim_jogo_steam")
    op.drop_index("ix_raw_data_fonte_coletado_em", table_name="raw_data")
    op.drop_table("raw_data")
