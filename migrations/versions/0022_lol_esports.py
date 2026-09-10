"""Fase 27: LoL Esports - ranking oficial, elencos e stats de partida

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-09

O LoL profissional tinha agenda/resultado (OP.GG + PandaScore free), mas tres
buracos: sem stats por jogo (campeao/KDA/ouro), sem ranking oficial (LCK/LPL/
LEC), sem elenco (time -> jogador). Tudo vem da API oficial gratuita
`esports-api.lolesports.com` + `feed.lolesports.com/livestats`.

- `ranking_externo` ganha `vitorias`/`derrotas`: as ligas de LoL publicam a
  tabela de classificacao (V-D por split), nao um rating. O router repassa isso
  em `EquipeRankingOficial.vitorias/derrotas` (que ja existiam no schema, so o
  ranking derivado de confronto preenchia).
- `dim_jogador` ganha `papel`/`nome_completo`/`imagem`/`id_equipe`: o elenco
  profissional que o `getTeams` entrega, sem home ate agora.
- `fato_lol_jogador_partida` (novo): uma linha por jogador por jogo de uma serie
  decidida de LoL, ligada a `agenda_partida` (nao ha `dim_partida` de LoL). O
  backfill do `lolesports.py` grava a partir do frame final do feed; a aba
  Jogadores agrega dai.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ranking_externo", sa.Column("vitorias", sa.Integer(), nullable=True)
    )
    op.add_column(
        "ranking_externo", sa.Column("derrotas", sa.Integer(), nullable=True)
    )

    op.add_column("dim_jogador", sa.Column("papel", sa.String(length=32), nullable=True))
    op.add_column("dim_jogador", sa.Column("nome_completo", sa.Text(), nullable=True))
    op.add_column("dim_jogador", sa.Column("imagem", sa.Text(), nullable=True))
    op.add_column(
        "dim_jogador",
        sa.Column(
            "id_equipe",
            sa.Integer(),
            sa.ForeignKey("dim_equipe.id_equipe"),
            nullable=True,
        ),
    )

    op.create_table(
        "fato_lol_jogador_partida",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "id_jogador",
            sa.BigInteger(),
            sa.ForeignKey("dim_jogador.id_jogador"),
            nullable=False,
        ),
        sa.Column(
            "id_agenda",
            sa.BigInteger(),
            sa.ForeignKey("agenda_partida.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("jogo_numero", sa.Integer(), nullable=False),
        sa.Column("campeao", sa.String(length=48), nullable=True),
        sa.Column("k", sa.Integer(), nullable=True),
        sa.Column("d", sa.Integer(), nullable=True),
        sa.Column("a", sa.Integer(), nullable=True),
        sa.Column("cs", sa.Integer(), nullable=True),
        sa.Column("ouro", sa.Integer(), nullable=True),
        sa.Column("nivel", sa.Integer(), nullable=True),
        sa.Column("vitoria", sa.Boolean(), nullable=True),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "id_jogador", "id_agenda", "jogo_numero", name="uq_lol_jgp"
        ),
    )
    op.create_index(
        "ix_lol_jgp_agenda", "fato_lol_jogador_partida", ["id_agenda"]
    )
    op.create_index(
        "ix_lol_jgp_jogador", "fato_lol_jogador_partida", ["id_jogador"]
    )


def downgrade() -> None:
    op.drop_index("ix_lol_jgp_jogador", table_name="fato_lol_jogador_partida")
    op.drop_index("ix_lol_jgp_agenda", table_name="fato_lol_jogador_partida")
    op.drop_table("fato_lol_jogador_partida")

    op.drop_column("dim_jogador", "id_equipe")
    op.drop_column("dim_jogador", "imagem")
    op.drop_column("dim_jogador", "nome_completo")
    op.drop_column("dim_jogador", "papel")

    op.drop_column("ranking_externo", "derrotas")
    op.drop_column("ranking_externo", "vitorias")
