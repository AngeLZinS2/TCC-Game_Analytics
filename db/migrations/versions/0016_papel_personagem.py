"""Fase 20: papel do personagem, e id_externo que cabe num uuid

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-05

`dim_personagem` sempre foi multi-jogo - o docstring do modelo diz que heroi
(Dota), campeao (LoL) e agente (Valorant) sao o mesmo conceito -, mas so tinha
nome. Para Valorant isso perde a informacao que mais importa na pergunta comum:
o agente e Duelista, Controlador, Iniciador ou Sentinela. Sem a coluna, "quais
agentes sao duelistas" nao teria resposta no banco mesmo com os 29 agentes
carregados.

Nula por padrao e nula continua no Dota: a OpenDota nao classifica heroi por
funcao de forma estavel (o mesmo heroi e carry num jogo e suporte no outro), e
inventar um papel fixo pra cada um seria dado nosso vestido de dado da fonte.

Junto vai o alargamento de `id_externo`: 32 caracteres cabiam no id inteiro
do heroi da OpenDota ("1", "112") e nao cabem no uuid de 36 do agente
("add6443a-41bd-e414-f6ad-e58d267f4e95"). A dimensao sempre foi multi-jogo;
a largura da coluna e que tinha sido dimensionada por uma fonte so.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dim_personagem", sa.Column("papel", sa.String(32), nullable=True))
    op.alter_column(
        "dim_personagem",
        "id_externo",
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Volta a 32 antes de perder a coluna: um id_externo maior que isso so
    # existe se agentes ja tiverem sido carregados, e ai o downgrade tem que
    # falhar alto em vez de truncar chave natural em silencio.
    op.alter_column(
        "dim_personagem",
        "id_externo",
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=False,
    )
    op.drop_column("dim_personagem", "papel")
