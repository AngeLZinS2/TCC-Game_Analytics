"""Fase 34: chave de IA pessoal aceita Anthropic e Google, alem do OpenRouter

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-11

A coluna nascia especifica do OpenRouter (`openrouter_api_key_cifrada`,
migration 0027) - vira generica (`chave_ia_cifrada`) porque a mesma conta
pode guardar chave de qualquer um dos tres provedores agora. `chave_ia_provedor`
("openrouter"/"anthropic"/"google") diz qual, e `chave_ia_modelo` guarda o
modelo escolhido (o OpenRouter ja da acesso a Claude/Gemini - a novidade
maior e deixar ESCOLHER o modelo, nao so trocar a chave).

Sem dado de producao pra migrar (feature ainda nao deployada) - renomear em
vez de manter as duas colunas.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "dim_usuario",
        "openrouter_api_key_cifrada",
        new_column_name="chave_ia_cifrada",
    )
    op.add_column(
        "dim_usuario", sa.Column("chave_ia_provedor", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "dim_usuario", sa.Column("chave_ia_modelo", sa.String(length=120), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("dim_usuario", "chave_ia_modelo")
    op.drop_column("dim_usuario", "chave_ia_provedor")
    op.alter_column(
        "dim_usuario",
        "chave_ia_cifrada",
        new_column_name="openrouter_api_key_cifrada",
    )
