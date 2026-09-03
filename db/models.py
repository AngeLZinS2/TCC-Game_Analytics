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
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    snapshots: Mapped[list["FatoSnapshotJogoSteam"]] = relationship(
        back_populates="jogo", cascade="all, delete-orphan"
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
    codigo: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
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
    id_externo: Mapped[str] = mapped_column(String(32), nullable=False)
    nome: Mapped[str] = mapped_column(String(64), nullable=False)
    nome_interno: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("id_jogo", "id_externo", name="uq_personagem_jogo_externo"),
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
    #: `team_id` da fonte.
    id_externo: Mapped[str] = mapped_column(String(32), nullable=False)

    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    tag: Mapped[str | None] = mapped_column(String(32))
    logo_url: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("id_jogo", "id_externo", name="uq_equipe_jogo_externo"),
    )


class AgendaPartida(Base):
    """Confrontos que ainda vao acontecer, vindos da Liquipedia.

    Nao e um fato: nada foi medido ainda. E o calendario que permite a tela de
    previsao falar de partidas futuras em vez de so simular confrontos
    hipoteticos.

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

    __table_args__ = (
        UniqueConstraint("id_jogo", "id_externo", name="uq_agenda_jogo_externo"),
        Index("ix_agenda_inicio", "inicio_previsto"),
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
