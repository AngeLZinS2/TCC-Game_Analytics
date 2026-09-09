"""Fase 22: detalhe do personagem - metadados estaticos e estatistica por mapa

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-05

Para a tela de detalhe do agente (o equivalente de op.gg/valorant/agents/<nome>)
faltavam duas coisas:

1. `dim_personagem.metadados` (JSONB): a parte que NAO muda - descricao/lore,
   retrato, icone, e as quatro habilidades com nome, texto e icone. Vem da
   valorant-api.com, que o coletor de agentes ja consulta e ate agora
   descartava. JSONB e nao colunas porque o formato e proprio do jogo: um
   agente tem habilidades por slot, um heroi de Dota tem outra coisa.

2. `fato_estatistica_personagem.mapa`: o OP.GG publica a estatistica do agente
   TAMBEM por mapa (`valorant_list_agent_statistics?map_id=`), e e esse recorte
   que da profundidade a tela - Chamber e forte em Ascent e fraco em Fracture,
   e a media esconde isso. String vazia = o agregado geral (as linhas que ja
   existem entram como `''`); um nome de mapa = o recorte daquele mapa.

`mapa` e NOT NULL DEFAULT '' de proposito: `NULL` num indice unico e tratado
como distinto no Postgres < 15, e ai duas linhas "gerais" do mesmo personagem
na mesma janela passariam. O sentinela `''` evita depender da versao.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dim_personagem", sa.Column("metadados", JSONB(), nullable=True)
    )

    op.add_column(
        "fato_estatistica_personagem",
        sa.Column(
            "mapa", sa.String(48), nullable=False, server_default=""
        ),
    )
    op.drop_constraint(
        "uq_estatistica_personagem_janela",
        "fato_estatistica_personagem",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_estatistica_personagem_janela",
        "fato_estatistica_personagem",
        ["id_personagem", "janela_coleta", "mapa"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_estatistica_personagem_janela",
        "fato_estatistica_personagem",
        type_="unique",
    )
    op.execute("DELETE FROM fato_estatistica_personagem WHERE mapa <> ''")
    op.drop_column("fato_estatistica_personagem", "mapa")
    op.create_unique_constraint(
        "uq_estatistica_personagem_janela",
        "fato_estatistica_personagem",
        ["id_personagem", "janela_coleta"],
    )
    op.drop_column("dim_personagem", "metadados")
