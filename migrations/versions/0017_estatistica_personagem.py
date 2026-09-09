"""Fase 21: estatistica agregada por personagem, com metricas por esporte

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-05

Cada esporte mede o que o proprio jogo valoriza. Dota fala de ouro e
experiencia por minuto; Valorant e Counter-Strike falam de taxa de headshot e
dano por round; League fala de taxa de banimento e de rota. Ate aqui a tela de
personagens so sabia falar Dota, porque so `fato_partida_jogador` (OpenDota)
existia - e as colunas GPM/XPM/KDA estavam escritas nela.

Esta tabela guarda o AGREGADO por personagem, que e o grao em que as outras
fontes publicam: o OP.GG nao entrega partida a partida de Valorant, entrega
"este agente, nestas centenas de milhares de partidas, teve estes numeros".

`metricas` e JSONB de proposito. Uma coluna por metrica obrigaria uma migration
a cada esporte novo e deixaria a tabela cheia de nulo - `hs_percentual` nunca
teria valor em Dota, `ouro_por_minuto` nunca teria em Valorant. O que da
sentido as chaves e o vocabulario em `api/vocabulario_esports.py`, que diz por
jogo quais existem, como se chamam e como se formatam.

Historico por `janela_coleta`: o mesmo agente coletado semana a semana permite
ver o meta se mexendo, e e o mesmo padrao de `fato_snapshot_jogo_steam`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fato_estatistica_personagem",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "id_personagem",
            sa.Integer(),
            sa.ForeignKey("dim_personagem.id_personagem"),
            nullable=False,
        ),
        sa.Column("janela_coleta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fonte", sa.String(32), nullable=False),
        sa.Column("partidas", sa.BigInteger(), nullable=True),
        sa.Column("vitorias", sa.BigInteger(), nullable=True),
        sa.Column("metricas", JSONB(), nullable=False),
        sa.UniqueConstraint(
            "id_personagem", "janela_coleta", name="uq_estatistica_personagem_janela"
        ),
    )
    op.create_index(
        "ix_estatistica_personagem_janela",
        "fato_estatistica_personagem",
        ["id_personagem", "janela_coleta"],
    )


def downgrade() -> None:
    op.drop_index("ix_estatistica_personagem_janela", "fato_estatistica_personagem")
    op.drop_table("fato_estatistica_personagem")
