"""Fase 33: chave de IA pessoal por conta

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-11

Quem tem sua propria chave do OpenRouter pode cadastrar - o Assistente de IA
passa a usar ELA pras perguntas dessa conta, em vez da chave compartilhada do
site (que tem cota unica pra todo mundo sem chave propria). Guardada cifrada
(Fernet, `services/cifra.py`), nunca em texto puro - o backend so decifra na
hora de montar o header `Authorization` da chamada ao OpenRouter.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dim_usuario",
        sa.Column("openrouter_api_key_cifrada", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dim_usuario", "openrouter_api_key_cifrada")
