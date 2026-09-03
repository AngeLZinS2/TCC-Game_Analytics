"""Fase 11: metadados de equipe vindos do wikitexto da Liquipedia

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-03

A `dim_equipe` era preenchida so pela OpenDota, que da nome, tag e logo - nada
sobre QUEM e a equipe. Estas colunas vem do `{{Infobox team}}` da Liquipedia, e
entram por `teamid`, que e o mesmo identificador de `id_externo`.

`pagina_liquipedia` nao e enfeite: e a prova de procedencia. Uma linha com
regiao preenchida e sem pagina teria vindo de outro lugar, e a diferenca importa
quando alguem for conferir.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dim_equipe", sa.Column("regiao", sa.String(length=40), nullable=True))
    op.add_column("dim_equipe", sa.Column("pais", sa.String(length=80), nullable=True))
    # Nula, nao `True` por padrao: "nao sabemos" e diferente de "esta ativa", e
    # a maioria das equipes que ja estao na tabela nunca foi vista pela wiki.
    op.add_column("dim_equipe", sa.Column("ativa", sa.Boolean(), nullable=True))
    op.add_column("dim_equipe", sa.Column("criada_em", sa.Date(), nullable=True))
    op.add_column(
        "dim_equipe", sa.Column("pagina_liquipedia", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    for coluna in ("pagina_liquipedia", "criada_em", "ativa", "pais", "regiao"):
        op.drop_column("dim_equipe", coluna)
