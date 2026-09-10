"""Fase 26: catalogo Xbox (vitrine de loja) - dim_jogo_xbox + snapshot

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-09

A tela "Jogos da Steam" virou "Catalogo de Jogos" com abas por loja. A aba
Xbox precisa de um lugar para guardar o catalogo do Game Pass + a ficha de
cada jogo (nome, capa, preco, se esta no GP), coletado periodicamente do
mercado BR.

Duas tabelas, espelhando o par Steam (`dim_jogo_steam` + `fato_snapshot_jogo_steam`)
mas rasas: a Microsoft nao publica CCU nem texto de avaliacao em API gratuita.

- `dim_jogo_xbox`: PK `product_id` (o Store ID alfanumerico), ficha + preco
  atual + `no_game_pass` / `game_pass_desde` + o que mais a resposta da Store
  ja traz: `descricao`, `nota` / `numero_avaliacoes` / `nota_recente` (estrela
  0-5 da Store), `recursos` (4K, HDR, co-op...), `tem_conquistas`,
  `classificacao_etaria` + `descritores_conteudo`, `midias`.
- `fato_snapshot_jogo_xbox`: serie por (product_id, janela_coleta) de preco,
  presenca no Game Pass e nota (satisfacao no tempo). `janela_coleta` truncada
  em `snapshot_bucket_minutes` = chave de idempotencia (uq_snapshot_xbox_janela).

Sem FK para o dominio Steam nem para o esports. Fonte: `catalog.gamepass.com`
+ `displaycatalog.mp.microsoft.com`, publicos e nao-oficiais, atras do
kill-switch `xbox_enabled`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dim_jogo_xbox",
        sa.Column("product_id", sa.String(length=64), primary_key=True, autoincrement=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=True),
        sa.Column("desenvolvedora", sa.Text(), nullable=True),
        sa.Column("publicadora", sa.Text(), nullable=True),
        sa.Column("data_lancamento", sa.Date(), nullable=True),
        sa.Column("data_lancamento_texto", sa.String(length=64), nullable=True),
        sa.Column("generos", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("gratuito", sa.Boolean(), nullable=True),
        sa.Column("preco_atual", sa.Numeric(10, 2), nullable=True),
        sa.Column("preco_normal", sa.Numeric(10, 2), nullable=True),
        sa.Column("moeda", sa.String(length=8), nullable=True),
        sa.Column("desconto_percentual", sa.Integer(), nullable=True),
        sa.Column("faixa_etaria", sa.Integer(), nullable=True),
        sa.Column("imagem_header", sa.Text(), nullable=True),
        sa.Column("imagem_capa", sa.Text(), nullable=True),
        sa.Column("url_loja", sa.Text(), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("nota", sa.Numeric(3, 1), nullable=True),
        sa.Column("numero_avaliacoes", sa.Integer(), nullable=True),
        sa.Column("nota_recente", sa.Numeric(3, 1), nullable=True),
        sa.Column("recursos", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("tem_conquistas", sa.Boolean(), nullable=True),
        sa.Column("classificacao_etaria", sa.String(length=16), nullable=True),
        sa.Column("descritores_conteudo", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("midias", postgresql.JSONB(), nullable=True),
        sa.Column("no_game_pass", sa.Boolean(), nullable=True),
        sa.Column("game_pass_desde", sa.Date(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "fato_snapshot_jogo_xbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.String(length=64),
            sa.ForeignKey("dim_jogo_xbox.product_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("janela_coleta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_coleta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preco_no_momento", sa.Numeric(10, 2), nullable=True),
        sa.Column("preco_normal", sa.Numeric(10, 2), nullable=True),
        sa.Column("moeda", sa.String(length=8), nullable=True),
        sa.Column("desconto_percentual", sa.Integer(), nullable=True),
        sa.Column("no_game_pass", sa.Boolean(), nullable=True),
        sa.Column("nota", sa.Numeric(3, 1), nullable=True),
        sa.Column("numero_avaliacoes", sa.Integer(), nullable=True),
        sa.Column("nota_recente", sa.Numeric(3, 1), nullable=True),
        sa.UniqueConstraint(
            "product_id", "janela_coleta", name="uq_snapshot_xbox_janela"
        ),
    )
    op.create_index(
        "ix_snapshot_xbox_janela", "fato_snapshot_jogo_xbox", ["janela_coleta"]
    )


def downgrade() -> None:
    op.drop_index("ix_snapshot_xbox_janela", table_name="fato_snapshot_jogo_xbox")
    op.drop_table("fato_snapshot_jogo_xbox")
    op.drop_table("dim_jogo_xbox")
