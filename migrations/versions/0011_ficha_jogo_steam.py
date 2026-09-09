"""Fase 16: ficha do jogo estilo SteamDB

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-04

A tela de detalhe do jogo mostrava nome, generos, preco e a serie de
jogadores. O `appdetails` que o coletor SEMPRE gravou traz muito mais e nada
disso era extraido: recursos da Steam, plataformas, idiomas, faixa etaria,
classificacoes, numero de conquistas, DLCs, requisitos. Reprocessar os
payloads em disco preenche tudo sem uma chamada de rede.

Alem disso: SteamSpy por app (donos estimados, tempo de jogo, tags da
comunidade) e as noticias / patch notes oficiais (`ISteamNews`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_COLUNAS = [
    ("recursos", sa.ARRAY(sa.Text())),
    ("plataformas", sa.ARRAY(sa.Text())),
    ("idiomas", sa.ARRAY(sa.Text())),
    ("idiomas_com_audio", sa.ARRAY(sa.Text())),
    ("faixa_etaria", sa.Integer()),
    ("descritores_conteudo", sa.ARRAY(sa.Text())),
    ("classificacoes", JSONB()),
    ("suporte_controle", sa.String(length=16)),
    ("conquistas_total", sa.Integer()),
    ("conquistas_destaque", JSONB()),
    ("analises_totais", sa.Integer()),
    ("dlc_ids", sa.ARRAY(sa.Integer())),
    ("site_oficial", sa.Text()),
    ("imagem_header", sa.Text()),
    ("em_breve", sa.Boolean()),
    ("requisitos_minimos", sa.Text()),
    ("donos_estimados", sa.String(length=48)),
    ("tempo_jogo_medio_min", sa.Integer()),
    ("tempo_jogo_mediano_min", sa.Integer()),
    ("tags_comunidade", JSONB()),
    ("coletado_ficha_em", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    for nome, tipo in _COLUNAS:
        op.add_column("dim_jogo_steam", sa.Column(nome, tipo, nullable=True))

    op.create_table(
        "dim_jogo_steam_noticia",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("dim_jogo_steam.app_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gid", sa.String(length=32), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("autor", sa.String(length=120), nullable=True),
        sa.Column("feed", sa.String(length=120), nullable=True),
        sa.Column("publicado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("app_id", "gid", name="uq_noticia_app_gid"),
    )
    op.create_index(
        "ix_noticia_app_data", "dim_jogo_steam_noticia", ["app_id", "publicado_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_noticia_app_data", table_name="dim_jogo_steam_noticia")
    op.drop_table("dim_jogo_steam_noticia")
    for nome, _tipo in reversed(_COLUNAS):
        op.drop_column("dim_jogo_steam", nome)
