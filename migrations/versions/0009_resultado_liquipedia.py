"""Fase 13: resultado dos confrontos da Liquipedia

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-03

`agenda_partida` sempre guardou qualquer bloco da pagina `Liquipedia:Matches`
com horario valido - passado ou futuro, porque o parser nunca filtrou por
tempo. So que o resultado (quem venceu, o placar) era descartado: a pagina e
um ticker que mostra confrontos ja decididos, mas ninguem lia essa parte.

Medido no dia desta migration: 722 linhas na tabela, 614 ja no passado,
espalhadas por 13 jogos - dado real, ja coletado, parado sem uso porque
faltavam estas tres colunas.

O motivo de importar: e a UNICA fonte de partida-com-resultado que o projeto
tem para qualquer jogo que nao seja Dota 2. A OpenDota (`dim_partida` /
`fato_partida_jogador`) so cobre Dota. Sem isto, o ajuste de forcas
(Bradley-Terry, `ml/confronto.py`) nunca teria dado para treinar em
Counter-Strike, VALORANT, ou qualquer um dos outros 70 jogos do catalogo.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agenda_partida", sa.Column("vitoria_a", sa.Boolean(), nullable=True))
    op.add_column("agenda_partida", sa.Column("placar_a", sa.Integer(), nullable=True))
    op.add_column("agenda_partida", sa.Column("placar_b", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("agenda_partida", "placar_b")
    op.drop_column("agenda_partida", "placar_a")
    op.drop_column("agenda_partida", "vitoria_a")
