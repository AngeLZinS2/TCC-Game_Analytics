"""Fase 31: contas de usuario (Firebase Auth) + historico do assistente por conta

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-11

O site ganha conta de verdade via Firebase Authentication (e-mail + senha) -
senha e verificacao de credencial ficam inteiramente do lado do Firebase, o
backend nunca ve nem guarda senha nenhuma. Duas telas passam a exigir login:
"Perfil" e "Assistente de IA".

- `dim_usuario`: perfil local minimo, uma linha por conta Firebase. Criado sob
  demanda (upsert) na primeira requisicao autenticada que chega - nao existe
  fluxo de "cadastro" separado no backend, o Firebase e quem cria a conta.
  `firebase_uid` e o identificador estavel (`claims["sub"]` do ID token).
- `fato_pergunta_assistente`: uma linha por pergunta feita ao assistente,
  ligada a conta. Substitui o historico que ate aqui vivia so no localStorage
  do navegador (`assistente/historico.ts`) - a mesma pergunta que a tela ja
  perguntava confirmando com o usuario ("guardar por conta?").
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dim_usuario",
        sa.Column("id_usuario", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("firebase_uid", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("nome_exibicao", sa.String(length=200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_acesso", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_usuario_firebase_uid", "dim_usuario", ["firebase_uid"]
    )

    op.create_table(
        "fato_pergunta_assistente",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "id_usuario",
            sa.Integer(),
            sa.ForeignKey("dim_usuario.id_usuario", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pergunta", sa.Text(), nullable=False),
        sa.Column("util", sa.Boolean(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_pergunta_assistente_usuario",
        "fato_pergunta_assistente",
        ["id_usuario", "criado_em"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pergunta_assistente_usuario", table_name="fato_pergunta_assistente"
    )
    op.drop_table("fato_pergunta_assistente")

    op.drop_constraint("uq_usuario_firebase_uid", "dim_usuario", type_="unique")
    op.drop_table("dim_usuario")
