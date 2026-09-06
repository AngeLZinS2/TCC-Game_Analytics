"""Fase 24: detalhe por mapa e por jogador de uma partida da agenda

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-06

`agenda_partida` guarda o placar da serie (2-3) - quem venceu, nada sobre como.
Para Valorant o vlr.gg publica, em cada partida, o placar por mapa e a linha de
cada jogador (agente, ACS, K/D/A, ADR, HS%). A tela de detalhe da partida
mostra isso, como a do vlr.gg.

`detalhe` e JSONB e nao tabelas novas porque a forma e propria do jogo (um FPS
tatico tem ACS e first blood; um MOBA tem ouro por minuto) e o uso e exibicao,
nao agregacao - nada consulta "media de ACS de todos os jogos". O coletor
`vlr-detalhes` preenche so as partidas ja decididas que ainda estao com
`detalhe` nulo.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agenda_partida", sa.Column("detalhe", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("agenda_partida", "detalhe")
