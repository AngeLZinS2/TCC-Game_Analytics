"""Fase 35.2: tags da Steam nas ofertas (filtro de genero/categoria)

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-15

A varredura de ofertas (Fase 35.1) trouxe ~18 mil promocoes, mas as linhas
de `dim_jogo_steam` que ela cria tem so nome e imagem - genero e categoria
vem do `appdetails`, que essas linhas nunca tiveram. Medido: 67 das 17.985
ofertas ativas tinham genero. Um filtro de genero sobre isso devolveria
quase nada.

O dado que faltava ja vinha junto e era descartado: cada linha do HTML de
`/search/results/?specials=1` carrega `data-ds-tagids` - as tags da Steam
daquele app. Passam a ser guardadas, sem UMA requisicao a mais na varredura.

- `dim_jogo_steam.tags_steam`: os ids das tags (nao os nomes). Id e
  neutro de idioma; o nome muda conforme o `l=` da coleta, e congelar
  "Ação" numa coluna deixaria a tela em ingles/espanhol mostrando
  portugues.
- `dim_tag_steam`: o dicionario id -> nome, preenchido de
  `store.steampowered.com/tagdata/populartags/<idioma>` (publico, uma
  requisicao por varredura). Separado de `generos`/`recursos` de
  proposito: aquelas sao a taxonomia do `appdetails` (genero de loja e
  recurso), estas sao as tags votadas pela comunidade. Misturar as duas
  corromperia o filtro de genero do Catalogo, que depende do `appdetails`.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dim_jogo_steam",
        sa.Column("tags_steam", postgresql.ARRAY(sa.Integer()), nullable=True),
    )

    op.create_table(
        "dim_tag_steam",
        sa.Column("tag_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # O filtro pergunta "quais ofertas tem a tag X" - `ANY(tags_steam)` sobre
    # 18 mil linhas sem indice vira varredura sequencial a cada troca de
    # dropdown. GIN e o indice de array do Postgres.
    op.create_index(
        "ix_dim_jogo_steam_tags",
        "dim_jogo_steam",
        ["tags_steam"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_dim_jogo_steam_tags", table_name="dim_jogo_steam")
    op.drop_table("dim_tag_steam")
    op.drop_column("dim_jogo_steam", "tags_steam")
