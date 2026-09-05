"""Fase 19: trailers e capturas da pagina da loja

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-04

A ficha ja guardava a capa (`imagem_header`), que e uma imagem so e parada.
O carrossel do topo da ficha precisa da galeria inteira - o trailer e as
capturas que a propria pagina da loja mostra. Sao poucos itens por jogo e o
formato varia (video tem cartaz e titulo, imagem nao), entao vao como JSONB
numa coluna, nao numa tabela: nunca sao consultados por filtro, so lidos
inteiros junto com o resto da ficha.

Nada de rede pra preencher: o payload do `appdetails` ja tinha `movies` e
`screenshots` gravado em `data/raw/`, entao
`python cli.py collect steam --from-raw` reprocessa e preenche.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dim_jogo_steam",
        sa.Column("midias", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dim_jogo_steam", "midias")
