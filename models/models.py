"""Modelos SQLAlchemy.

Dois dominios de dados convivem no mesmo banco, mas NAO compartilham schema:

  * dominio "catalogo/mercado" (Steam)  -> Fase 1
  * dominio "partidas" (esports)        -> Fase 2+ (star schema)

Tabela `raw_data` e transversal: registra todo payload bruto recebido de
qualquer fonte, permitindo reprocessar o ETL sem rechamar as APIs.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Transversal
# ---------------------------------------------------------------------------


class RawData(Base):
    """Manifesto dos payloads brutos gravados em disco.

    O JSON fica no filesystem (`data/raw/...`) porque cresce rapido; aqui
    guardamos apenas o ponteiro + metadados, o que torna barato responder
    "o que ja foi coletado?" e "de onde veio esta linha do fato?".
    """

    __tablename__ = "raw_data"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fonte: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    identificador: Mapped[str] = mapped_column(String(128), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(Text, nullable=False)
    hash_payload: Mapped[str] = mapped_column(String(64), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    registrado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "fonte", "endpoint", "identificador", "coletado_em",
            name="uq_raw_data_coleta",
        ),
        Index("ix_raw_data_fonte_coletado_em", "fonte", "coletado_em"),
    )


# ---------------------------------------------------------------------------
# Dominio catalogo / mercado (Steam)
# ---------------------------------------------------------------------------


class DimJogoSteam(Base):
    """Dimensao de jogo do catalogo Steam (atributos que mudam pouco)."""

    __tablename__ = "dim_jogo_steam"

    app_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(32))
    desenvolvedora: Mapped[str | None] = mapped_column(Text)
    publicadora: Mapped[str | None] = mapped_column(Text)
    data_lancamento: Mapped[date | None] = mapped_column(Date)
    data_lancamento_texto: Mapped[str | None] = mapped_column(String(64))
    generos: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    gratuito: Mapped[bool | None] = mapped_column()
    preco_atual: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    moeda: Mapped[str | None] = mapped_column(String(8))
    nota_metacritic: Mapped[int | None] = mapped_column(Integer)

    # --- Ficha do jogo (Fase 16) ------------------------------------------
    # Tudo abaixo ja vinha no payload de `appdetails` que o coletor sempre
    # gravou - so nao era extraido. Reprocessar do raw preenche sem rede.

    #: Recursos da Steam ("Conquistas", "Cartas colecionaveis", "Nuvem",
    #: "Suporte total a controle"...). Sao os `categories` do appdetails.
    recursos: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    #: Subconjunto de {"windows", "mac", "linux"}.
    plataformas: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    #: Idiomas de interface/legenda suportados.
    idiomas: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    #: Idiomas com audio dublado (subconjunto de `idiomas`).
    idiomas_com_audio: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    #: Idade minima declarada na loja (`required_age`).
    faixa_etaria: Mapped[int | None] = mapped_column(Integer)
    #: Descritores de conteudo da Steam (violencia, nudez...).
    descritores_conteudo: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    #: Classificacao por orgao: {"esrb": "M", "pegi": "18", "dejus": "18"...}.
    classificacoes: Mapped[dict | None] = mapped_column(JSONB)
    #: "full", "partial" ou nulo (`controller_support`).
    suporte_controle: Mapped[str | None] = mapped_column(String(16))
    #: Quantas conquistas o jogo tem (`achievements.total`).
    conquistas_total: Mapped[int | None] = mapped_column(Integer)
    #: As conquistas em destaque, com icone: [{"nome": ..., "icone": ...}].
    conquistas_destaque: Mapped[list | None] = mapped_column(JSONB)
    #: Total de recomendacoes positivas que a loja exibe (`recommendations`).
    analises_totais: Mapped[int | None] = mapped_column(Integer)
    #: app_ids das DLCs.
    dlc_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    site_oficial: Mapped[str | None] = mapped_column(Text)
    imagem_header: Mapped[str | None] = mapped_column(Text)
    #: `release_date.coming_soon` - lancado ou ainda por vir.
    em_breve: Mapped[bool | None] = mapped_column(Boolean)
    #: Requisitos minimos de PC, ja em texto puro (o payload vem em HTML).
    requisitos_minimos: Mapped[str | None] = mapped_column(Text)
    #: Requisitos recomendados. Nulo no jogo que nao publica (a Steam so traz
    #: `minimum` para varios) - a tela esconde a aba nesse caso.
    requisitos_recomendados: Mapped[str | None] = mapped_column(Text)
    #: Trailers e capturas da pagina da loja, na ordem do carrossel da ficha:
    #: [{"tipo": "video"|"imagem", "url", "cartaz", "titulo"}]. Video em HLS -
    #: a Steam nao publica mais mp4/webm direto (ver `_parse_midias`).
    midias: Mapped[list | None] = mapped_column(JSONB)

    # --- SteamSpy (Fase 16) ---------------------------------------------
    #: Faixa de donos estimada ("1,000,000 .. 2,000,000"). O plano gratuito
    #: do SteamSpy so da faixa, nunca numero exato - e proposital nao fingir
    #: precisao aqui.
    donos_estimados: Mapped[str | None] = mapped_column(String(48))
    tempo_jogo_medio_min: Mapped[int | None] = mapped_column(Integer)
    tempo_jogo_mediano_min: Mapped[int | None] = mapped_column(Integer)
    #: Tags da comunidade com contagem de votos: {"RPG": 1240, ...}.
    tags_comunidade: Mapped[dict | None] = mapped_column(JSONB)

    coletado_ficha_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # --- Comparacao de preco (Fase 17, IsThereAnyDeal) ------------------
    #: UUID do jogo no ITAD, achado uma vez por Steam appid e cacheado.
    #: `""` (string vazia) = ja procurado e NAO existe no ITAD - o marcador
    #: que evita repetir a busca a cada rodada.
    itad_id: Mapped[str | None] = mapped_column(String(40))
    #: O menor preco que o jogo JA teve em qualquer loja acompanhada - o
    #: numero que responde "compro agora ou espero a proxima promo?".
    menor_preco_historico: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    menor_preco_historico_loja: Mapped[str | None] = mapped_column(String(60))
    menor_preco_historico_moeda: Mapped[str | None] = mapped_column(String(8))
    menor_preco_historico_em: Mapped[date | None] = mapped_column(Date)
    coletado_preco_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Tempo pra zerar (Fase 18, HowLongToBeat) ------------------------
    #: Id do jogo no HLTB, achado por nome (nao ha appid la) e cacheado.
    #: `""` = ja procurado e nenhum candidato bateu com confianca suficiente.
    hltb_id: Mapped[str | None] = mapped_column(String(40))
    #: Nome como aparece no HLTB - existe pra conferir que o casamento por
    #: nome achou o jogo certo (Steam e HLTB nao compartilham nenhum id).
    hltb_nome: Mapped[str | None] = mapped_column(Text)
    hltb_horas_historia: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    hltb_horas_extras: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    hltb_horas_completista: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    coletado_tempo_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Resumo de avaliacoes por IA (Fase 28, Groq) ---------------------
    #: Texto corrido (2-4 frases) sintetizando a recepcao, gerado a partir de
    #: uma amostra de `fato_avaliacao_steam`. `None` = ainda nao resumido ou
    #: avaliacoes de menos (`resumo_reviews_minimo_avaliacoes`).
    resumo_reviews_texto: Mapped[str | None] = mapped_column(Text)
    resumo_reviews_positivos: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    resumo_reviews_negativos: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    resumo_reviews_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Qual modelo gerou - transparencia (a tela mostra "resumo por IA, via <modelo>").
    resumo_reviews_modelo: Mapped[str | None] = mapped_column(String(80))
    #: Quantas avaliacoes entraram na amostra - contexto de quao robusto e o resumo.
    resumo_reviews_avaliacoes: Mapped[int | None] = mapped_column(Integer)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    snapshots: Mapped[list["FatoSnapshotJogoSteam"]] = relationship(
        back_populates="jogo", cascade="all, delete-orphan"
    )
    noticias: Mapped[list["NoticiaJogoSteam"]] = relationship(
        back_populates="jogo", cascade="all, delete-orphan"
    )
    ofertas: Mapped[list["OfertaJogoSteam"]] = relationship(
        back_populates="jogo", cascade="all, delete-orphan"
    )


class NoticiaJogoSteam(Base):
    """Noticia / patch note oficial de um jogo (`ISteamNews/GetNewsForApp`).

    O SteamDB mostra o changelog de cada jogo; esta e a versao possivel sem
    conectar como cliente Steam: os posts do "Community Announcements" e do
    feed oficial, que e onde estudio publica as notas de atualizacao.

    `gid` e o id da noticia na Steam - unico por jogo, e o que da idempotencia:
    recoletar nao duplica, so acrescenta o que e novo.
    """

    __tablename__ = "dim_jogo_steam_noticia"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("dim_jogo_steam.app_id", ondelete="CASCADE"), nullable=False
    )
    gid: Mapped[str] = mapped_column(String(32), nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    autor: Mapped[str | None] = mapped_column(String(120))
    feed: Mapped[str | None] = mapped_column(String(120))
    publicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Corpo em texto puro, cortado - a lista da tela nao quer o BBCode inteiro.
    resumo: Mapped[str | None] = mapped_column(Text)
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    jogo: Mapped["DimJogoSteam"] = relationship(back_populates="noticias")

    __table_args__ = (
        UniqueConstraint("app_id", "gid", name="uq_noticia_app_gid"),
        Index("ix_noticia_app_data", "app_id", "publicado_em"),
    )


class OfertaJogoSteam(Base):
    """Preco atual de um jogo numa loja, via IsThereAnyDeal (Fase 17).

    Uma linha por (jogo, loja): o preco que AQUELA loja pede agora, o preco
    cheio e o desconto. A tela ordena por preco e marca a mais barata - e
    responde "esta mais barato fora da Steam?".

    `menor_preco_historico` do jogo mora em `dim_jogo_steam`, nao aqui: e um
    numero por jogo, nao por loja.
    """

    __tablename__ = "oferta_jogo_steam"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("dim_jogo_steam.app_id", ondelete="CASCADE"), nullable=False
    )
    loja_id: Mapped[int] = mapped_column(Integer, nullable=False)
    loja: Mapped[str] = mapped_column(String(60), nullable=False)
    preco: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    #: Preco cheio (sem desconto). Igual a `preco` quando nao ha promo.
    preco_normal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    desconto: Mapped[int | None] = mapped_column(Integer)
    moeda: Mapped[str | None] = mapped_column(String(8))
    url: Mapped[str | None] = mapped_column(Text)
    #: "Steam", "GOG", "DRM-free"... o que a loja entrega. Ajuda a nao
    #: comparar chave de Steam com copia DRM-free como se fossem a mesma coisa.
    drm: Mapped[str | None] = mapped_column(String(120))
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    jogo: Mapped["DimJogoSteam"] = relationship(back_populates="ofertas")

    __table_args__ = (
        UniqueConstraint("app_id", "loja_id", name="uq_oferta_app_loja"),
    )


class FatoSnapshotJogoSteam(Base):
    """Serie temporal por jogo: uma linha por (app_id, janela de coleta).

    `janela_coleta` e o timestamp truncado em SNAPSHOT_BUCKET_MINUTES. Ele
    existe para dar idempotencia: reexecutar o coletor dentro da mesma janela
    faz upsert na mesma linha em vez de duplicar a serie.
    """

    __tablename__ = "fato_snapshot_jogo_steam"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("dim_jogo_steam.app_id", ondelete="CASCADE"), nullable=False
    )
    janela_coleta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    data_coleta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    jogadores_simultaneos: Mapped[int | None] = mapped_column(Integer)
    nota_avaliacoes: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    numero_avaliacoes: Mapped[int | None] = mapped_column(Integer)
    avaliacoes_positivas: Mapped[int | None] = mapped_column(Integer)
    avaliacoes_negativas: Mapped[int | None] = mapped_column(Integer)
    classificacao_steam: Mapped[str | None] = mapped_column(String(64))
    preco_no_momento: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    moeda: Mapped[str | None] = mapped_column(String(8))
    desconto_percentual: Mapped[int | None] = mapped_column(Integer)

    jogo: Mapped[DimJogoSteam] = relationship(back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint("app_id", "janela_coleta", name="uq_snapshot_app_janela"),
        Index("ix_snapshot_janela", "janela_coleta"),
    )


class FatoSteamOnline(Base):
    """Usuarios simultaneos da PLATAFORMA Steam - o numero que a Valve publica.

    Diferente de `fato_snapshot_jogo_steam`, que e por jogo: aqui e um numero
    so, da Steam inteira, vindo de `valvesoftware.com/en/about/stats`. Serie
    temporal (uma linha por coleta) para a home mostrar a variacao.
    """

    __tablename__ = "fato_steam_online"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: `users_online` da Valve: conectados a Steam neste instante.
    usuarios_online: Mapped[int] = mapped_column(Integer, nullable=False)
    #: `users_ingame`: o subconjunto que esta dentro de um jogo.
    usuarios_em_jogo: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_fato_steam_online_coletado_em", "coletado_em"),)


class DimAppSteamNome(Base):
    """Nome por app_id, sem relacao com `dim_jogo_steam`.

    O Top 100 mais jogados traz apps que nao sao monitorados; a tela so quer o
    nome deles. Tabela separada para o join da home nao esbarrar numa linha de
    dimensao pela metade.
    """

    __tablename__ = "dim_app_steam_nome"

    app_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    visto_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class FatoAvaliacaoSteam(Base):
    """Uma linha por avaliacao escrita na Steam - o grao do dominio de texto.

    O `fato_snapshot_jogo_steam` guarda o RESUMO das avaliacoes (quantas
    positivas, a nota); ele responde "como o publico avalia o jogo". Esta tabela
    guarda cada avaliacao individual, com o texto - e o que permite treinar um
    classificador em vez de so plotar a nota agregada.

    `recomendado` e o polegar do proprio autor. E rotulo de verdade, dado de
    graca pela fonte: nenhuma anotacao manual entra no treino de sentimento.
    """

    __tablename__ = "fato_avaliacao_steam"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("dim_jogo_steam.app_id", ondelete="CASCADE"), nullable=False
    )
    #: `recommendationid` da Steam. E a chave natural que da idempotencia.
    id_externo: Mapped[str] = mapped_column(String(32), nullable=False)

    idioma: Mapped[str | None] = mapped_column(String(32))
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    recomendado: Mapped[bool] = mapped_column(nullable=False)

    criada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Minutos, como a Steam devolve - converter na carga perderia precisao.
    minutos_jogados: Mapped[int | None] = mapped_column(Integer)
    votos_uteis: Mapped[int | None] = mapped_column(Integer)
    votos_engracados: Mapped[int | None] = mapped_column(Integer)

    compra_na_steam: Mapped[bool | None] = mapped_column()
    recebido_de_graca: Mapped[bool | None] = mapped_column()
    acesso_antecipado: Mapped[bool | None] = mapped_column()

    __table_args__ = (
        UniqueConstraint("app_id", "id_externo", name="uq_avaliacao_app_externo"),
        Index("ix_avaliacao_idioma", "idioma"),
        Index("ix_avaliacao_recomendado", "recomendado"),
    )


# ---------------------------------------------------------------------------
# Dominio catalogo Xbox (Fase 26) - vitrine de loja
# ---------------------------------------------------------------------------
#
# Espelha `dim_jogo_steam` + `fato_snapshot_jogo_steam`, mas raso de proposito:
# nao ha CCU publico, nao ha texto de avaliacao em API gratuita da Microsoft. O
# que a loja da e ficha + preco + se o jogo esta no Game Pass - e e isso que
# estas tabelas guardam. Fonte: `catalog.gamepass.com` (a lista do GP) e
# `displaycatalog.mp.microsoft.com` (a ficha), ambos publicos e NAO-oficiais,
# fixados no mercado BR. Sem FK para o dominio Steam nem para o esports.


class DimJogoXbox(Base):
    """Dimensao de jogo da Xbox Store (atributos que mudam pouco)."""

    __tablename__ = "dim_jogo_xbox"

    #: `ProductId` do Microsoft Store (alfanumerico, ex. "9NKX70BBCDRN"). Chave
    #: natural da fonte, nao um substituto.
    product_id: Mapped[str] = mapped_column(String(64), primary_key=True, autoincrement=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    #: `ProductType` da Microsoft ("Game", "Durable"...). Guardado para filtrar.
    tipo: Mapped[str | None] = mapped_column(String(32))
    desenvolvedora: Mapped[str | None] = mapped_column(Text)
    publicadora: Mapped[str | None] = mapped_column(Text)
    data_lancamento: Mapped[date | None] = mapped_column(Date)
    #: `OriginalReleaseDate` como veio, quando nao parseia para `date`.
    data_lancamento_texto: Mapped[str | None] = mapped_column(String(64))
    #: `Properties.Categories` da Microsoft - o equivalente aos generos.
    generos: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    gratuito: Mapped[bool | None] = mapped_column(Boolean)
    #: Preco de venda no mercado BR na ultima coleta (o historico vai no snapshot).
    preco_atual: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    #: Preco cheio (MSRP) - igual a `preco_atual` quando nao ha promo.
    preco_normal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    moeda: Mapped[str | None] = mapped_column(String(8))
    desconto_percentual: Mapped[int | None] = mapped_column(Integer)
    #: Idade minima (`MarketProperties[0].MinimumUserAge`).
    faixa_etaria: Mapped[int | None] = mapped_column(Integer)
    #: Arte larga (SuperHeroArt), para o topo da ficha.
    imagem_header: Mapped[str | None] = mapped_column(Text)
    #: Arte quadrada (Poster/BoxArt), para a lista.
    imagem_capa: Mapped[str | None] = mapped_column(Text)
    #: Link da pagina na Microsoft Store.
    url_loja: Mapped[str | None] = mapped_column(Text)
    #: `ShortDescription` da loja - o texto curto da ficha.
    descricao: Mapped[str | None] = mapped_column(Text)

    #: Nota da Microsoft Store (0.0-5.0), agregada de sempre (`UsageData.AllTime`).
    #: E o unico sinal de "o publico gostou?" que a API gratuita da - nao ha
    #: texto de avaliacao individual como na Steam.
    nota: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    numero_avaliacoes: Mapped[int | None] = mapped_column(Integer)
    #: Nota dos ultimos 7 dias (`UsageData.7Days`) - o "esta melhorando/piorando".
    nota_recente: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    #: Recursos (`Properties.Attributes`) ja traduzidos: "4K", "HDR", "Co-op
    #: online", "Otimizado p/ Series X|S"... So os conhecidos; ruido e descartado.
    recursos: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    #: O jogo tem conquistas? (flag `XblAchievements`). A LISTA de conquistas
    #: exige conta Xbox Live autenticada, entao aqui e so o sim/nao.
    tem_conquistas: Mapped[bool | None] = mapped_column(Boolean)
    #: Classificacao indicativa preferindo a DJCTQ (Brasil): "14", "18", "L"...
    classificacao_etaria: Mapped[str | None] = mapped_column(String(16))
    #: Descritores de conteudo ja traduzidos ("Violencia", "Drogas"...).
    descritores_conteudo: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    #: Trailers e capturas da ficha, para a tela de detalhe:
    #: [{"tipo": "imagem"|"video", "url", "cartaz"}].
    midias: Mapped[list | None] = mapped_column(JSONB)

    #: Estado atual: o jogo esta no catalogo do Game Pass agora? (o historico de
    #: entra/sai fica no snapshot).
    no_game_pass: Mapped[bool | None] = mapped_column(Boolean)
    #: Primeira vez que o vimos no Game Pass - so preenche, nunca reescreve.
    game_pass_desde: Mapped[date | None] = mapped_column(Date)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    snapshots: Mapped[list["FatoSnapshotJogoXbox"]] = relationship(
        back_populates="jogo", cascade="all, delete-orphan"
    )


class FatoSnapshotJogoXbox(Base):
    """Serie temporal por jogo do Xbox: uma linha por (product_id, janela).

    Mesmo desenho de `fato_snapshot_jogo_steam`: `janela_coleta` truncada em
    `snapshot_bucket_minutes` da idempotencia - recoletar dentro da janela e um
    upsert, nao uma linha nova. O que a vitrine acompanha aqui e preco e a
    presenca no Game Pass ao longo do tempo.
    """

    __tablename__ = "fato_snapshot_jogo_xbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("dim_jogo_xbox.product_id", ondelete="CASCADE"), nullable=False
    )
    janela_coleta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    data_coleta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    preco_no_momento: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    preco_normal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    moeda: Mapped[str | None] = mapped_column(String(8))
    desconto_percentual: Mapped[int | None] = mapped_column(Integer)
    no_game_pass: Mapped[bool | None] = mapped_column(Boolean)
    #: Nota da Store no momento da coleta - para a serie de satisfacao no tempo.
    nota: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    numero_avaliacoes: Mapped[int | None] = mapped_column(Integer)
    nota_recente: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))

    jogo: Mapped[DimJogoXbox] = relationship(back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint("product_id", "janela_coleta", name="uq_snapshot_xbox_janela"),
        Index("ix_snapshot_xbox_janela", "janela_coleta"),
    )


# ---------------------------------------------------------------------------
# Dominio partidas (esports) - star schema
# ---------------------------------------------------------------------------
#
# As dimensoes sao compartilhadas entre Dota 2, LoL e Valorant, com `id_jogo`
# como discriminador. As chaves sao substitutas (inteiros gerados aqui) e o id
# vindo da API fica em `id_externo` - e isso que permite os tres jogos
# conviverem sem colisao, ja que um account_id da Steam e um puuid da Riot nao
# compartilham espaco de nomes.


class DimJogo(Base):
    __tablename__ = "dim_jogo"

    id_jogo: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    nome: Mapped[str] = mapped_column(String(64), nullable=False)


class DimJogador(Base):
    __tablename__ = "dim_jogador"

    id_jogador: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    id_jogo: Mapped[int] = mapped_column(ForeignKey("dim_jogo.id_jogo"), nullable=False)
    id_externo: Mapped[str] = mapped_column(String(64), nullable=False)
    nome: Mapped[str | None] = mapped_column(Text)
    regiao: Mapped[str | None] = mapped_column(String(32))

    # --- Elenco profissional (Fase 27, LoL Esports) ---------------------
    #: Rota do jogador (top/jungle/mid/bottom/support). Nula no Dota (a
    #: OpenDota nao classifica jogador por funcao de forma estavel).
    papel: Mapped[str | None] = mapped_column(String(32))
    #: Nome civil ("Changdong Kim") quando a fonte publica.
    nome_completo: Mapped[str | None] = mapped_column(Text)
    imagem: Mapped[str | None] = mapped_column(Text)
    #: Time atual do jogador. So o elenco (LoL Esports) preenche; a linha de
    #: `fato_partida_jogador` continua sendo a fonte de "quem jogou onde".
    id_equipe: Mapped[int | None] = mapped_column(ForeignKey("dim_equipe.id_equipe"))

    __table_args__ = (
        UniqueConstraint("id_jogo", "id_externo", name="uq_jogador_jogo_externo"),
    )


class DimPersonagem(Base):
    """Heroi (Dota), campeao (LoL) e agente (Valorant) sao o mesmo conceito."""

    __tablename__ = "dim_personagem"

    id_personagem: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_jogo: Mapped[int] = mapped_column(ForeignKey("dim_jogo.id_jogo"), nullable=False)
    #: 64 e nao 32 porque a chave natural muda de forma com a fonte: o heroi da
    #: OpenDota e um inteiro ("112"), o agente do Valorant e um uuid de 36.
    id_externo: Mapped[str] = mapped_column(String(64), nullable=False)
    nome: Mapped[str] = mapped_column(String(64), nullable=False)
    nome_interno: Mapped[str | None] = mapped_column(String(64))
    #: Funcao dentro do time, como a FONTE do jogo classifica - "Duelista",
    #: "Sentinela". Nula no Dota de proposito: a OpenDota nao classifica heroi
    #: por funcao de forma estavel (o mesmo heroi e carry num jogo e suporte no
    #: outro), e fixar um papel aqui seria dado nosso vestido de dado da fonte.
    papel: Mapped[str | None] = mapped_column(String(32))
    #: O que NAO muda: lore, retrato, icone e as habilidades. Formato proprio
    #: do jogo (agente tem habilidade por slot; heroi de Dota tem outra coisa),
    #: por isso JSONB. Nulo enquanto a fonte estatica nao foi coletada.
    metadados: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("id_jogo", "id_externo", name="uq_personagem_jogo_externo"),
    )


class FatoEstatisticaPersonagem(Base):
    """Agregado por personagem, com as metricas que o esporte dele usa.

    Grao diferente de `fato_partida_jogador`: la e uma linha por jogador por
    partida (so a OpenDota entrega isso, e so para Dota); aqui e "este agente,
    nesta janela, teve estes numeros", que e como o OP.GG publica Valorant e
    League - centenas de milhares de partidas resumidas.

    `metricas` e JSONB porque cada esporte mede o que valoriza: taxa de
    headshot e dano por round num tatico, ouro e experiencia por minuto num
    MOBA, taxa de banimento em League. Uma coluna por metrica exigiria
    migration a cada esporte novo e encheria a tabela de nulo. Quem da sentido
    as chaves e `api/vocabulario_esports.py`.
    """

    __tablename__ = "fato_estatistica_personagem"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_personagem: Mapped[int] = mapped_column(
        ForeignKey("dim_personagem.id_personagem"), nullable=False
    )
    janela_coleta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: Quem publicou o numero - "opgg" hoje. Nao e nossa medicao.
    fonte: Mapped[str] = mapped_column(String(32), nullable=False)
    partidas: Mapped[int | None] = mapped_column(BigInteger)
    vitorias: Mapped[int | None] = mapped_column(BigInteger)
    metricas: Mapped[dict] = mapped_column(JSONB, nullable=False)
    #: `""` = o agregado geral do personagem. Um nome de mapa = o recorte
    #: daquele mapa (`valorant_list_agent_statistics?map_id=`). Os dois convivem
    #: por janela de coleta. NOT NULL para nao cair na semantica de NULL
    #: distinto num indice unico (ver migration 0018).
    mapa: Mapped[str] = mapped_column(String(48), nullable=False, server_default="")

    __table_args__ = (
        UniqueConstraint(
            "id_personagem",
            "janela_coleta",
            "mapa",
            name="uq_estatistica_personagem_janela",
        ),
        Index("ix_estatistica_personagem_janela", "id_personagem", "janela_coleta"),
    )


class DimEquipe(Base):
    """Equipes profissionais, compartilhadas entre os jogos.

    Existe pela mesma razao de `dim_jogador`: o time e uma entidade que
    reaparece em muitas partidas, e repetir nome e logo em cada linha de fato
    desnormalizaria o que o star schema existe para normalizar.

    Nem toda partida tem equipe. A OpenDota so preenche `radiant_team` quando a
    partida esta ligada a um time cadastrado - em qualificatorias abertas e
    comum vir vazio. Por isso as FKs em `dim_partida` sao nulas.
    """

    __tablename__ = "dim_equipe"

    id_equipe: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_jogo: Mapped[int] = mapped_column(ForeignKey("dim_jogo.id_jogo"), nullable=False)
    #: A identidade da equipe NA FONTE, e ela muda de forma por jogo.
    #:
    #: Em Dota 2 e o `team_id` numerico, que a OpenDota e a Liquipedia usam em
    #: comum - foi ele que permitiu ligar as duas sem casar nome com nome. Nas
    #: outras wikis esse campo simplesmente NAO EXISTE no infobox (medido em
    #: counterstrike, valorant, leagueoflegends e rocketleague), e a identidade
    #: passa a ser o titulo da pagina, que a MediaWiki garante unico por wiki.
    #:
    #: Semantica mista numa coluna so incomoda, mas a unicidade e por
    #: `(id_jogo, id_externo)`: cada jogo tem UM esquema de identidade, e
    #: nenhuma consulta compara id entre jogos diferentes.
    id_externo: Mapped[str] = mapped_column(String(200), nullable=False)

    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    tag: Mapped[str | None] = mapped_column(String(32))
    logo_url: Mapped[str | None] = mapped_column(Text)

    #: Metadados do `{{Infobox team}}` da Liquipedia, ligados por `teamid`, que
    #: e o mesmo numero de `id_externo`. Nulos enquanto a equipe nao aparecer
    #: na wiki - o que e a regra para times de qualificatoria aberta.
    regiao: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(80))
    #: Nulo = a wiki nunca falou desta equipe. Nao confundir com `False`, que
    #: seria a wiki dizendo que ela foi dissolvida.
    ativa: Mapped[bool | None] = mapped_column(Boolean)
    criada_em: Mapped[date | None] = mapped_column(Date)
    #: A pagina de onde os campos acima vieram - procedencia conferivel.
    pagina_liquipedia: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        UniqueConstraint("id_jogo", "id_externo", name="uq_equipe_jogo_externo"),
    )


class AgendaPartida(Base):
    """Confrontos que a Liquipedia listou - futuros OU ja concluidos.

    O nome e um resquicio da Fase 10, quando so o futuro importava. A pagina
    que alimenta esta tabela (`Liquipedia:Matches`) e um TICKER, nao uma
    agenda pura: ela mostra uma janela recente que inclui confrontos ja
    decididos, e a Fase 13 passou a capturar o resultado deles em vez de
    descarta-lo. Por isso a tabela guarda os dois tipos de linha juntos, e o
    que os separa e `vitoria_a`: `NULL` = ainda sem resultado (e e o que a
    tela "Proximos Confrontos" filtra por `inicio_previsto >= agora`); `True`
    ou `False` = confronto decidido, e e ESSA a fonte que alimenta o ajuste de
    forcas (Bradley-Terry) para todo jogo que nao e Dota 2 - a OpenDota so
    cobre Dota, e sem esta tabela os outros 72 jogos do catalogo nunca
    teriam uma partida COM RESULTADO para treinar em cima.

    Nao e um fato no sentido classico (a granularidade e "o que a Liquipedia
    afirmou", nao "o que aconteceu na partida minuto a minuto" - isso a
    OpenDota da, so para Dota). Mas para Bradley-Terry, que so precisa de
    quem venceu, esse grao basta.

    `id_equipe_a/b` sao nulas ate a reconciliacao encontrar o time na dimensao.
    A Liquipedia escreve "Power Rangers" e a OpenDota cadastra "_PowerRangers";
    guardar o nome COMO VEIO (`equipe_a_nome`) alem da FK e o que permite
    mostrar o confronto mesmo sem previsao, em vez de esconder a partida.
    """

    __tablename__ = "agenda_partida"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_jogo: Mapped[int] = mapped_column(ForeignKey("dim_jogo.id_jogo"), nullable=False)
    #: Hash de (times, horario) - a Liquipedia nao expoe id de partida.
    id_externo: Mapped[str] = mapped_column(String(32), nullable=False)

    equipe_a_nome: Mapped[str] = mapped_column(String(120), nullable=False)
    equipe_b_nome: Mapped[str] = mapped_column(String(120), nullable=False)
    id_equipe_a: Mapped[int | None] = mapped_column(
        ForeignKey("dim_equipe.id_equipe")
    )
    id_equipe_b: Mapped[int | None] = mapped_column(
        ForeignKey("dim_equipe.id_equipe")
    )

    inicio_previsto: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    torneio: Mapped[str | None] = mapped_column(Text)
    formato: Mapped[str | None] = mapped_column(String(16))
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    #: `NULL` = sem resultado publicado ainda (e o estado normal de um
    #: confronto futuro). Ver o docstring da classe.
    vitoria_a: Mapped[bool | None] = mapped_column(Boolean)
    placar_a: Mapped[int | None] = mapped_column(Integer)
    placar_b: Mapped[int | None] = mapped_column(Integer)
    #: Placar por mapa e linha de cada jogador (agente, ACS, K/D/A, ADR, HS%),
    #: quando a fonte publica - hoje so Valorant, do vlr.gg. `None` fora disso e
    #: para partida ainda nao decidida. Formato: `{mapas: [{nome, placar_a,
    #: placar_b, jogadores: [{nome, time, agente, acs, k, d, a, adr, hs}]}]}`.
    detalhe: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("id_jogo", "id_externo", name="uq_agenda_jogo_externo"),
        Index("ix_agenda_inicio", "inicio_previsto"),
    )


class RankingExterno(Base):
    """Ranking de equipes publicado por um terceiro, com data de referencia.

    A previsao de confronto (`ml/confronto.py`) estima a forca de cada time SO
    a partir dos confrontos que coletamos. Isso deixa o time com pouco
    historico preso perto de 50% - correto quando nao se sabe nada, mas em
    Counter-Strike a Valve publica um ranking oficial (`counter-strike_
    regional_standings` no GitHub, cadencia mensal, ~400 times com pontuacao)
    que ja sabe algo. Guardar essa pontuacao aqui permite usa-la como PRIOR do
    Bradley-Terry: um time #6 no ranking da Valve com duas partidas coletadas
    nao deveria ter forca ~0.

    `data_referencia` e a data do snapshot (a Valve publica um por mes). Guardar
    todos os snapshots - nao so o ultimo - e o que permite o prior ser
    point-in-time na validacao walk-forward: prever uma partida de julho usa o
    ranking de julho, nao o de hoje.

    `id_equipe` e nula ate a reconciliacao casar o nome publicado com
    `dim_equipe` - mesmo padrao de `agenda_partida`.
    """

    __tablename__ = "ranking_externo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: Quem publicou o ranking. Hoje so `"valve"`; a coluna existe para o dia
    #: em que houver uma segunda fonte sem precisar de outra tabela.
    fonte: Mapped[str] = mapped_column(String(20), nullable=False)
    id_jogo: Mapped[int] = mapped_column(ForeignKey("dim_jogo.id_jogo"), nullable=False)
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False)

    id_equipe: Mapped[int | None] = mapped_column(ForeignKey("dim_equipe.id_equipe"))
    #: O nome COMO O RANKING ESCREVEU - guardado alem da FK para a
    #: reconciliacao poder melhorar depois sem recoletar.
    equipe_nome: Mapped[str] = mapped_column(String(120), nullable=False)

    posicao: Mapped[int] = mapped_column(Integer, nullable=False)
    #: A pontuacao que o metodo da fonte atribuiu. `NULL` se a fonte so
    #: publica ordem, sem numero.
    pontos: Mapped[int | None] = mapped_column(Integer)
    #: Vitorias/derrotas de serie no split. Preenchido por fontes que publicam
    #: a tabela de classificacao (LoL Esports), nao so a ordem.
    vitorias: Mapped[int | None] = mapped_column(Integer)
    derrotas: Mapped[int | None] = mapped_column(Integer)
    #: `"global"` ou uma regiao. A Valve publica os dois; guardamos o global.
    regiao: Mapped[str | None] = mapped_column(String(20))

    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "fonte",
            "id_jogo",
            "data_referencia",
            "regiao",
            "equipe_nome",
            name="uq_ranking_externo_snapshot",
        ),
        Index("ix_ranking_externo_lookup", "fonte", "id_jogo", "data_referencia"),
    )


class DimTempo(Base):
    """Dimensao de calendario. `id_tempo` e a data no formato AAAAMMDD."""

    __tablename__ = "dim_tempo"

    id_tempo: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )
    data: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    ano: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    dia: Mapped[int] = mapped_column(Integer, nullable=False)
    trimestre: Mapped[int] = mapped_column(Integer, nullable=False)
    semana: Mapped[int] = mapped_column(Integer, nullable=False)
    dia_da_semana: Mapped[int] = mapped_column(Integer, nullable=False)
    nome_dia: Mapped[str] = mapped_column(String(16), nullable=False)


class DimPartida(Base):
    __tablename__ = "dim_partida"

    id_partida: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    id_jogo: Mapped[int] = mapped_column(ForeignKey("dim_jogo.id_jogo"), nullable=False)
    id_externo: Mapped[str] = mapped_column(String(64), nullable=False)
    id_tempo: Mapped[int | None] = mapped_column(ForeignKey("dim_tempo.id_tempo"))
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duracao_segundos: Mapped[int | None] = mapped_column(Integer)
    modo: Mapped[str | None] = mapped_column(String(48))
    tipo_partida: Mapped[str | None] = mapped_column(String(16))
    patch: Mapped[str | None] = mapped_column(String(16))
    liga_nome: Mapped[str | None] = mapped_column(Text)
    liga_id_externo: Mapped[str | None] = mapped_column(String(32))
    #: `tier` da liga na fonte: premium, professional, amateur.
    liga_tier: Mapped[str | None] = mapped_column(String(24))

    # Lado A e radiant no Dota, blue no LoL, atacante no Valorant - a mesma
    # convencao de `fato_minuto_partida`. Nulas quando a fonte nao cadastrou o
    # time, o que e comum em qualificatoria aberta.
    id_equipe_lado_a: Mapped[int | None] = mapped_column(
        ForeignKey("dim_equipe.id_equipe")
    )
    id_equipe_lado_b: Mapped[int | None] = mapped_column(
        ForeignKey("dim_equipe.id_equipe")
    )

    __table_args__ = (
        UniqueConstraint("id_jogo", "id_externo", name="uq_partida_jogo_externo"),
        Index("ix_partida_data_inicio", "data_inicio"),
        Index("ix_partida_equipes", "id_equipe_lado_a", "id_equipe_lado_b"),
    )


class FatoPartidaJogador(Base):
    """Uma linha por jogador por partida - o grao do dominio de partidas.

    As metricas sao as que existem nos tres jogos. `pontos_objetivo` e a
    normalizacao generica de objetivos (torres/Roshan no Dota, torres/dragoes
    no LoL, spikes no Valorant), e o que e exclusivo de um jogo vai para
    `metricas_extras` em vez de virar coluna que os outros nunca preenchem.
    """

    __tablename__ = "fato_partida_jogador"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_partida: Mapped[int] = mapped_column(
        ForeignKey("dim_partida.id_partida", ondelete="CASCADE"), nullable=False
    )
    id_jogo: Mapped[int] = mapped_column(ForeignKey("dim_jogo.id_jogo"), nullable=False)
    # Nulo quando a API anonimiza o jogador (comum em partidas publicas).
    id_jogador: Mapped[int | None] = mapped_column(ForeignKey("dim_jogador.id_jogador"))
    id_personagem: Mapped[int | None] = mapped_column(
        ForeignKey("dim_personagem.id_personagem")
    )
    id_tempo: Mapped[int | None] = mapped_column(ForeignKey("dim_tempo.id_tempo"))

    equipe: Mapped[str | None] = mapped_column(String(16))
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    vitoria: Mapped[bool | None] = mapped_column()

    kills: Mapped[int | None] = mapped_column(Integer)
    deaths: Mapped[int | None] = mapped_column(Integer)
    assists: Mapped[int | None] = mapped_column(Integer)
    dano_causado: Mapped[int | None] = mapped_column(Integer)
    dano_recebido: Mapped[int | None] = mapped_column(Integer)
    economia: Mapped[int | None] = mapped_column(Integer)
    economia_por_minuto: Mapped[int | None] = mapped_column(Integer)
    experiencia_por_minuto: Mapped[int | None] = mapped_column(Integer)
    pontos_objetivo: Mapped[int | None] = mapped_column(Integer)
    last_hits: Mapped[int | None] = mapped_column(Integer)
    denies: Mapped[int | None] = mapped_column(Integer)
    nivel: Mapped[int | None] = mapped_column(Integer)
    funcao: Mapped[str | None] = mapped_column(String(32))
    duracao_partida_segundos: Mapped[int | None] = mapped_column(Integer)
    metricas_extras: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("id_partida", "slot", name="uq_fato_partida_slot"),
        Index("ix_fato_jogo_personagem", "id_jogo", "id_personagem"),
    )


class FatoLolJogadorPartida(Base):
    """Uma linha por jogador por jogo de uma serie de LoL profissional.

    Grao parecido com `fato_partida_jogador`, mas de LoL Esports e ligado a
    `agenda_partida` (nao ha `dim_partida` de LoL - so Dota tem). Alimentado
    pelo backfill do `lolesports.py`: quando uma serie decidida ainda esta na
    janela de retencao do feed `livestats`, o frame final de cada jogo da
    campeao/K/D/A/CS/ouro/nivel por jogador. E o que faz a aba Jogadores
    funcionar para LoL, agregando estas linhas.
    """

    __tablename__ = "fato_lol_jogador_partida"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_jogador: Mapped[int] = mapped_column(
        ForeignKey("dim_jogador.id_jogador"), nullable=False
    )
    id_agenda: Mapped[int] = mapped_column(
        ForeignKey("agenda_partida.id", ondelete="CASCADE"), nullable=False
    )
    #: 1..5 - qual jogo da serie.
    jogo_numero: Mapped[int] = mapped_column(Integer, nullable=False)

    campeao: Mapped[str | None] = mapped_column(String(48))
    k: Mapped[int | None] = mapped_column(Integer)
    d: Mapped[int | None] = mapped_column(Integer)
    a: Mapped[int | None] = mapped_column(Integer)
    cs: Mapped[int | None] = mapped_column(Integer)
    ouro: Mapped[int | None] = mapped_column(Integer)
    nivel: Mapped[int | None] = mapped_column(Integer)
    vitoria: Mapped[bool | None] = mapped_column(Boolean)

    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "id_jogador", "id_agenda", "jogo_numero", name="uq_lol_jgp"
        ),
        Index("ix_lol_jgp_agenda", "id_agenda"),
        Index("ix_lol_jgp_jogador", "id_jogador"),
    )


class FatoMinutoPartida(Base):
    """Uma linha por minuto de partida - o grao que o modelo de previsao consome.

    O `fato_partida_jogador` guarda o placar FINAL de cada jogador; ele responde
    "como a partida terminou". Este fato responde outra pergunta: "como a partida
    estava indo no minuto N". Sao granularidades diferentes, e forcar as duas na
    mesma tabela obrigaria a repetir o estado do mapa em cada uma das dez linhas
    de jogador.

    O ponto de vista e sempre o do **lado A** (radiant no Dota, blue no LoL,
    atacante no Valorant): `vantagem_economia` positiva significa lado A na
    frente. Guardar a diferenca em vez dos dois totais e o que mantem a tabela
    util quando a fonte so publica o saldo, que e o caso da OpenDota.
    """

    __tablename__ = "fato_minuto_partida"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_partida: Mapped[int] = mapped_column(
        ForeignKey("dim_partida.id_partida", ondelete="CASCADE"), nullable=False
    )
    id_jogo: Mapped[int] = mapped_column(ForeignKey("dim_jogo.id_jogo"), nullable=False)

    minuto: Mapped[int] = mapped_column(Integer, nullable=False)

    vantagem_economia: Mapped[int | None] = mapped_column(Integer)
    vantagem_experiencia: Mapped[int | None] = mapped_column(Integer)

    # Acumulados ATE o minuto, nao o que aconteceu nele: o modelo preve a partir
    # do estado do mapa, e o estado e cumulativo.
    torres_perdidas_lado_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    torres_perdidas_lado_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    objetivos_maiores_lado_a: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    objetivos_maiores_lado_b: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # O rotulo. Fica desnormalizado aqui de proposito: e o alvo do treino, e
    # buscá-lo por join em cada leitura do dataset custaria caro sem ganho.
    vitoria_lado_a: Mapped[bool | None] = mapped_column()

    __table_args__ = (
        UniqueConstraint("id_partida", "minuto", name="uq_minuto_partida"),
        Index("ix_minuto_jogo", "id_jogo", "minuto"),
    )


# ---------------------------------------------------------------------------
# Telemetria do site (Fase 30) - painel admin
# ---------------------------------------------------------------------------


class FatoAcessoSite(Base):
    """Uma linha por pageview/heartbeat do frontend (`POST /api/telemetria/acesso`).

    `visitante_id` e um UUID gerado no navegador e guardado no localStorage -
    identifica o MESMO visitante entre paginas/sessoes sem cookie nem dado
    pessoal (nao e IP, nao e nome, nao e email). E o que permite contar
    "visitantes unicos" alem de "acessos" simples.
    """

    __tablename__ = "fato_acesso_site"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    visitante_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rota: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_acesso_site_criado_em", "criado_em"),
        Index("ix_acesso_site_visitante", "visitante_id"),
    )


class FatoBusca(Base):
    """Uma linha por busca no catalogo (Steam ou Xbox) - `fonte` distingue qual."""

    __tablename__ = "fato_busca"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fonte: Mapped[str] = mapped_column(String(20), nullable=False)
    termo: Mapped[str] = mapped_column(String(200), nullable=False)
    resultados: Mapped[int | None] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_busca_criado_em", "criado_em"),)


# ---------------------------------------------------------------------------
# Contas de usuario (Fase 31) - Firebase Auth
# ---------------------------------------------------------------------------


class DimUsuario(Base):
    """Perfil local minimo de uma conta Firebase.

    O Firebase e quem cria a conta e verifica a senha - esta linha so guarda o
    suficiente pra ligar o `firebase_uid` (o `sub` do ID token) a dados
    proprios do PlayDB, como o historico de perguntas ao assistente. Criada
    sob demanda (upsert) na primeira requisicao autenticada, nao num fluxo de
    cadastro separado.
    """

    __tablename__ = "dim_usuario"

    id_usuario: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    firebase_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    nome_exibicao: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ultimo_acesso: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Chave de IA da propria conta, cifrada (Fernet) - `None` usa a chave
    #: compartilhada do site (OpenRouter). Nunca fica em texto puro no banco
    #: nem sai numa resposta de API (ver `services/cifra.py`).
    chave_ia_cifrada: Mapped[str | None] = mapped_column(Text)
    #: "openrouter" | "anthropic" | "google" - qual API a chave acima abre.
    chave_ia_provedor: Mapped[str | None] = mapped_column(String(20))
    #: Modelo escolhido nesse provedor (ex. "anthropic/claude-sonnet-4.5" no
    #: OpenRouter, "claude-sonnet-5" na Anthropic direta). `None` usa o
    #: padrao do provedor.
    chave_ia_modelo: Mapped[str | None] = mapped_column(String(120))

    __table_args__ = (UniqueConstraint("firebase_uid", name="uq_usuario_firebase_uid"),)


class FatoPerguntaAssistente(Base):
    """Uma pergunta feita ao Assistente de IA, ligada a conta de quem perguntou."""

    __tablename__ = "fato_pergunta_assistente"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_usuario.id_usuario", ondelete="CASCADE"), nullable=False
    )
    pergunta: Mapped[str] = mapped_column(Text, nullable=False)
    util: Mapped[bool | None] = mapped_column(Boolean)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_pergunta_assistente_usuario", "id_usuario", "criado_em"),)


# ---------------------------------------------------------------------------
# Favoritos (Fase 32)
# ---------------------------------------------------------------------------


class UsuarioJogoFavorito(Base):
    """Um jogo (Steam ou Xbox) que a conta quer acompanhar.

    `jogo_id` e sempre texto (mesmo pra Steam, cujo `app_id` e inteiro) pra
    nao precisar de duas colunas nullable por fonte. Sem FK pro catalogo: um
    favorito sobrevive ao jogo sair do catalogo coletado.
    """

    __tablename__ = "usuario_jogo_favorito"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_usuario.id_usuario", ondelete="CASCADE"), nullable=False
    )
    fonte: Mapped[str] = mapped_column(String(10), nullable=False)
    jogo_id: Mapped[str] = mapped_column(String(64), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_usuario", "fonte", "jogo_id", name="uq_usuario_jogo_favorito"),
        Index("ix_jogo_favorito_usuario", "id_usuario"),
    )


class UsuarioEquipeFavorita(Base):
    """Um time (`dim_equipe`) que a conta quer acompanhar.

    A dimensao de equipe ja e por jogo (o mesmo time em CS e Valorant sao
    linhas diferentes), entao favoritar aqui e implicitamente "esse time
    NESSE jogo".
    """

    __tablename__ = "usuario_equipe_favorita"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_usuario.id_usuario", ondelete="CASCADE"), nullable=False
    )
    id_equipe: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_equipe.id_equipe", ondelete="CASCADE"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_usuario", "id_equipe", name="uq_usuario_equipe_favorita"),
        Index("ix_equipe_favorita_usuario", "id_usuario"),
    )
