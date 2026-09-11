"""Fase 32: favoritar jogos e times

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-11

Duas tabelas, ambas por conta (`dim_usuario`):

- `usuario_jogo_favorito`: um jogo (Steam ou Xbox) que a pessoa quer
  acompanhar. `jogo_id` e string porque as duas fontes tem chave natural de
  tipo diferente (app_id inteiro na Steam, product_id alfanumerico na Xbox) -
  guardar como texto evita duas colunas nullable. Sem FK pra
  `dim_jogo_steam`/`dim_jogo_xbox`: favoritar precisa sobreviver mesmo que o
  jogo saia do catalogo coletado (ex. Xbox removeu da loja).
- `usuario_equipe_favorita`: um time (`dim_equipe.id_equipe`) - a dimensao ja
  e por jogo (o mesmo time em CS e Valorant sao linhas diferentes), entao
  favoritar aqui e implicitamente favoritar "esse time NESSE jogo".
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuario_jogo_favorito",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "id_usuario",
            sa.Integer(),
            sa.ForeignKey("dim_usuario.id_usuario", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fonte", sa.String(length=10), nullable=False),
        sa.Column("jogo_id", sa.String(length=64), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_usuario_jogo_favorito",
        "usuario_jogo_favorito",
        ["id_usuario", "fonte", "jogo_id"],
    )
    op.create_index(
        "ix_jogo_favorito_usuario", "usuario_jogo_favorito", ["id_usuario"]
    )

    op.create_table(
        "usuario_equipe_favorita",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "id_usuario",
            sa.Integer(),
            sa.ForeignKey("dim_usuario.id_usuario", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "id_equipe",
            sa.Integer(),
            sa.ForeignKey("dim_equipe.id_equipe", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_usuario_equipe_favorita",
        "usuario_equipe_favorita",
        ["id_usuario", "id_equipe"],
    )
    op.create_index(
        "ix_equipe_favorita_usuario", "usuario_equipe_favorita", ["id_usuario"]
    )


def downgrade() -> None:
    op.drop_index("ix_equipe_favorita_usuario", table_name="usuario_equipe_favorita")
    op.drop_constraint(
        "uq_usuario_equipe_favorita", "usuario_equipe_favorita", type_="unique"
    )
    op.drop_table("usuario_equipe_favorita")

    op.drop_index("ix_jogo_favorito_usuario", table_name="usuario_jogo_favorito")
    op.drop_constraint(
        "uq_usuario_jogo_favorito", "usuario_jogo_favorito", type_="unique"
    )
    op.drop_table("usuario_jogo_favorito")
