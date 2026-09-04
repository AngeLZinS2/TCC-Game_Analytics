"""Fase 15: ranking externo de equipes (Valve Regional Standings)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-03

O Bradley-Terry de `ml/confronto.py` so sabe o que os confrontos coletados
dizem. Em Counter-Strike a Valve publica um ranking oficial - aberto, no
GitHub, cadencia mensal, ~400 times com pontuacao - que serve de PRIOR: um
time no topo do ranking com pouco historico proprio nao deveria cair pra 50%.

`data_referencia` guarda a data de cada snapshot mensal. Manter todos - e nao
so o ultimo - e o que permite o prior ser point-in-time na validacao
walk-forward.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ranking_externo",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fonte", sa.String(length=20), nullable=False),
        sa.Column(
            "id_jogo",
            sa.Integer(),
            sa.ForeignKey("dim_jogo.id_jogo"),
            nullable=False,
        ),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column(
            "id_equipe",
            sa.Integer(),
            sa.ForeignKey("dim_equipe.id_equipe"),
            nullable=True,
        ),
        sa.Column("equipe_nome", sa.String(length=120), nullable=False),
        sa.Column("posicao", sa.Integer(), nullable=False),
        sa.Column("pontos", sa.Integer(), nullable=True),
        sa.Column("regiao", sa.String(length=20), nullable=True),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "fonte",
            "id_jogo",
            "data_referencia",
            "regiao",
            "equipe_nome",
            name="uq_ranking_externo_snapshot",
        ),
    )
    op.create_index(
        "ix_ranking_externo_lookup",
        "ranking_externo",
        ["fonte", "id_jogo", "data_referencia"],
    )


def downgrade() -> None:
    op.drop_index("ix_ranking_externo_lookup", table_name="ranking_externo")
    op.drop_table("ranking_externo")
