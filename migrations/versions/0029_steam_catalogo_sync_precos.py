"""Fase 35: catalogo Steam completo com checkpoint, preco/promocao dedicados

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-15

O catalogo Steam monitorado (`dim_jogo_steam`) sempre foi um subconjunto
escolhido por popularidade/semente. Esta fase acrescenta o INDICE do
catalogo completo da Valve (`IStoreService/GetAppList`), com checkpoint de
verdade (sobrevive a restart) e sincronizacao incremental via
`price_change_number`, alem de duas entidades que faltavam: historico de
preco deduplicado por jogo e promocao com transicao ativa/encerrada real
(nunca inferida de heuristica de catalogo).

- `dim_app_steam_nome` (ja existia como cache de nome do Top 100 CCU) vira
  tambem o indice do catalogo completo: ganha `tipo`, `ultima_modificacao`,
  `numero_mudanca_preco` (o cursor de mudanca de preco da Valve) e
  `pendente_atualizacao_preco` - esta ultima E a fila de "precisa
  reprocessar preco", persistida no Postgres (sem Redis/Celery): marcada
  quando o sync incremental ve o `price_change_number` mudar (`!=`, nao so
  aumentar), zerada só depois que o `appdetails` daquele app_id já foi
  reprocessado com sucesso.
- `steam_sincronizacao`: checkpoint/estado por tipo de sync
  ("catalogo_inicial" | "catalogo_incremental" | "precos") - `last_appid`
  e os contadores sao gravados a cada execucao, nao só no final, entao um
  crash no meio perde no maximo 1 pagina do GetAppList (ate 50.000 apps),
  nunca o progresso ja persistido.
- `steam_historico_preco`: serie de preco por jogo, append-only. Dedup em
  DUAS camadas: a aplicacao so insere se o preco mudou de verdade desde a
  ultima linha, e a `UniqueConstraint` em (app_id, pais, moeda,
  janela_coleta) - mesmo bucket horario que `fato_snapshot_jogo_steam` ja
  usa (`truncar_janela()`) - funciona como rede de seguranca no proprio
  banco via `on_conflict_do_nothing`.
- `steam_promocoes`: uma promocao = uma transicao REAL de desconto
  observada num app (`desconto=0 -> desconto>0` abre, `desconto>0 ->
  desconto=0` fecha). O indice unico parcial `WHERE ativa` garante no
  proprio Postgres que nunca existe mais de uma promocao aberta por
  (app_id, pais) - nao so na logica do ETL.
- `steam_eventos`: schema completo para uma futura fonte oficial/curada de
  eventos (Summer Sale, Next Fest...). A Steam NAO tem endpoint publico
  para isso - a tabela fica criada e vazia nesta fase; nenhum coletor
  escreve nela ainda.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dim_app_steam_nome", sa.Column("tipo", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "dim_app_steam_nome",
        sa.Column("ultima_modificacao", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dim_app_steam_nome",
        sa.Column("numero_mudanca_preco", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "dim_app_steam_nome",
        sa.Column(
            "pendente_atualizacao_preco",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    op.create_table(
        "steam_sincronizacao",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tipo_sincronizacao", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_appid", sa.BigInteger(), nullable=True),
        sa.Column("ultimo_price_change_number", sa.BigInteger(), nullable=True),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "registros_processados", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "registros_criados", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "registros_atualizados", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "registros_falhos", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tipo_sincronizacao", name="uq_steam_sincronizacao_tipo"),
    )

    op.create_table(
        "steam_historico_preco",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("dim_jogo_steam.app_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pais", sa.String(length=2), nullable=False),
        sa.Column("moeda", sa.String(length=8), nullable=False),
        sa.Column("preco_original", sa.Integer(), nullable=True),
        sa.Column("preco_final", sa.Integer(), nullable=False),
        sa.Column("desconto_percentual", sa.Integer(), nullable=False),
        sa.Column("janela_coleta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registrado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "app_id", "pais", "moeda", "janela_coleta",
            name="uq_historico_preco_app_janela",
        ),
    )
    op.create_index(
        "ix_historico_preco_app", "steam_historico_preco",
        ["app_id", "pais", "moeda", "registrado_em"],
    )

    op.create_table(
        "steam_promocoes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("dim_jogo_steam.app_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pais", sa.String(length=2), nullable=False),
        sa.Column("moeda", sa.String(length=8), nullable=False),
        sa.Column("preco_original", sa.Integer(), nullable=False),
        sa.Column("preco_final", sa.Integer(), nullable=False),
        sa.Column("desconto_percentual", sa.Integer(), nullable=False),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_promocao_ativa_app_pais",
        "steam_promocoes",
        ["app_id", "pais"],
        unique=True,
        postgresql_where=sa.text("ativa"),
    )

    op.create_table(
        "steam_eventos",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("steam_event_id", sa.String(length=64), nullable=True),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("imagem_url", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("tipo_evento", sa.String(length=32), nullable=False),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encerrado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.UniqueConstraint("steam_event_id", name="uq_steam_eventos_steam_event_id"),
    )


def downgrade() -> None:
    op.drop_table("steam_eventos")
    op.drop_index("uq_promocao_ativa_app_pais", table_name="steam_promocoes")
    op.drop_table("steam_promocoes")
    op.drop_index("ix_historico_preco_app", table_name="steam_historico_preco")
    op.drop_table("steam_historico_preco")
    op.drop_table("steam_sincronizacao")
    op.drop_column("dim_app_steam_nome", "pendente_atualizacao_preco")
    op.drop_column("dim_app_steam_nome", "numero_mudanca_preco")
    op.drop_column("dim_app_steam_nome", "ultima_modificacao")
    op.drop_column("dim_app_steam_nome", "tipo")
