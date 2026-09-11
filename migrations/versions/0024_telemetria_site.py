"""Fase 30: telemetria do site (acessos + buscas) - painel admin

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-11

O painel admin (`/admin`) precisa de "quantos acessos o site teve" e "quantas
buscas" com granularidade dia/mes/ano - e serie no tempo, entao precisa de uma
linha por evento, nao um contador que reseta. Duas tabelas novas:

- `fato_acesso_site`: uma linha por pageview/heartbeat que o frontend manda
  (`POST /api/telemetria/acesso`, em `App.tsx` no mount + troca de rota +
  intervalo). `visitante_id` e um UUID gerado no navegador e guardado no
  localStorage - identifica o MESMO visitante sem cookie nem PII (nao e nome,
  email, IP). O mesmo evento tambem alimenta "quem esta online agora" (em
  memoria, `services/ml/telemetria_site.py` - nao precisa de tabela).
- `fato_busca`: uma linha por busca no catalogo (Steam ou Xbox), gravada nos
  proprios endpoints `/api/steam/catalogo` e `/api/xbox/catalogo`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fato_acesso_site",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("visitante_id", sa.String(length=64), nullable=False),
        sa.Column("rota", sa.String(length=200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_acesso_site_criado_em", "fato_acesso_site", ["criado_em"]
    )
    op.create_index(
        "ix_acesso_site_visitante", "fato_acesso_site", ["visitante_id"]
    )

    op.create_table(
        "fato_busca",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fonte", sa.String(length=20), nullable=False),
        sa.Column("termo", sa.String(length=200), nullable=False),
        sa.Column("resultados", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_busca_criado_em", "fato_busca", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_busca_criado_em", table_name="fato_busca")
    op.drop_table("fato_busca")

    op.drop_index("ix_acesso_site_visitante", table_name="fato_acesso_site")
    op.drop_index("ix_acesso_site_criado_em", table_name="fato_acesso_site")
    op.drop_table("fato_acesso_site")
