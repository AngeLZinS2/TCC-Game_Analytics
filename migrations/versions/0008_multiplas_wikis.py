"""Fase 12: espaco para as 73 wikis da Liquipedia

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-03

Duas colunas ficaram apertadas quando o projeto deixou de ser so Dota 2.

`dim_jogo.codigo` era `String(16)`, e `leagueoflegends` tem exatamente 15
caracteres - passava raspando. Um codigo novo da Liquipedia estouraria a coluna
no meio de uma coleta.

`dim_equipe.id_externo` era `String(32)`, dimensionada para o `team_id` numerico
da OpenDota. Fora da wiki de Dota 2 **nao existe `teamid` no infobox** - foi
medido: em counterstrike, valorant, leagueoflegends e rocketleague o
`{{Infobox team}}` traz `name`, `region`, `location`, `created` e `disbanded`, e
mais nada. Nessas wikis a identidade da equipe passa a ser o TITULO DA PAGINA,
que a MediaWiki garante unico por wiki. Titulo nao cabe em 32 caracteres.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "dim_jogo",
        "codigo",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "dim_equipe",
        "id_externo",
        existing_type=sa.String(length=32),
        type_=sa.String(length=200),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Truncaria dado real: os titulos de pagina passam de 32 caracteres.
    op.alter_column(
        "dim_equipe",
        "id_externo",
        existing_type=sa.String(length=200),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "dim_jogo",
        "codigo",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
