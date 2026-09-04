"""Fase 17: comparacao de preco (IsThereAnyDeal)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-04

O painel de detalhe mostra o preco na Steam. Um jogo pago pode estar em
promocao em outra loja (Nuuvem, GOG, Fanatical...). O IsThereAnyDeal agrega o
preco atual de ~33 lojas por Steam appid; este par de mudancas guarda o
resultado: `oferta_jogo_steam` (uma linha por loja) e o menor preco historico
em `dim_jogo_steam`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_COLUNAS = [
    ("itad_id", sa.String(length=40)),
    ("menor_preco_historico", sa.Numeric(10, 2)),
    ("menor_preco_historico_loja", sa.String(length=60)),
    ("menor_preco_historico_moeda", sa.String(length=8)),
    ("menor_preco_historico_em", sa.Date()),
    ("coletado_preco_em", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    for nome, tipo in _COLUNAS:
        op.add_column("dim_jogo_steam", sa.Column(nome, tipo, nullable=True))

    op.create_table(
        "oferta_jogo_steam",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("dim_jogo_steam.app_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("loja_id", sa.Integer(), nullable=False),
        sa.Column("loja", sa.String(length=60), nullable=False),
        sa.Column("preco", sa.Numeric(10, 2), nullable=False),
        sa.Column("preco_normal", sa.Numeric(10, 2), nullable=True),
        sa.Column("desconto", sa.Integer(), nullable=True),
        sa.Column("moeda", sa.String(length=8), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("drm", sa.String(length=120), nullable=True),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("app_id", "loja_id", name="uq_oferta_app_loja"),
    )


def downgrade() -> None:
    op.drop_table("oferta_jogo_steam")
    for nome, _tipo in reversed(_COLUNAS):
        op.drop_column("dim_jogo_steam", nome)
