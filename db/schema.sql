-- ---------------------------------------------------------------------------
-- Referencia de leitura do schema. A FONTE DA VERDADE sao as migrations
-- Alembic em db/migrations/versions/ (aplicadas com `python cli.py init-db`).
-- Este arquivo existe para consulta rapida e para anexar na monografia.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- Transversal: manifesto dos payloads brutos
-- ===========================================================================

CREATE TABLE raw_data (
    id              BIGSERIAL PRIMARY KEY,
    fonte           VARCHAR(32)  NOT NULL,   -- steam | opendota | riot | valorant
    endpoint        VARCHAR(128) NOT NULL,
    identificador   VARCHAR(128) NOT NULL,   -- app_id, match_id, puuid...
    caminho_arquivo TEXT         NOT NULL,   -- relativo a RAW_DATA_DIR
    hash_payload    VARCHAR(64)  NOT NULL,   -- sha256 do arquivo
    tamanho_bytes   INTEGER      NOT NULL,
    coletado_em     TIMESTAMPTZ  NOT NULL,
    registrado_em   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_raw_data_coleta
        UNIQUE (fonte, endpoint, identificador, coletado_em)
);

CREATE INDEX ix_raw_data_fonte_coletado_em ON raw_data (fonte, coletado_em);

-- ===========================================================================
-- Dominio catalogo / mercado (Steam) -- Fase 1
-- ===========================================================================

CREATE TABLE dim_jogo_steam (
    app_id                INTEGER PRIMARY KEY,
    nome                  TEXT        NOT NULL,
    tipo                  VARCHAR(32),          -- game | dlc | demo ...
    desenvolvedora        TEXT,
    publicadora           TEXT,
    data_lancamento       DATE,                 -- NULL quando nao parseavel
    data_lancamento_texto VARCHAR(64),          -- ex.: "Q3 2026", "Coming soon"
    generos               TEXT[],
    gratuito              BOOLEAN,
    preco_atual           NUMERIC(10, 2),
    moeda                 VARCHAR(8),
    nota_metacritic       INTEGER,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Serie temporal por jogo. `janela_coleta` = data_coleta truncada em
-- SNAPSHOT_BUCKET_MINUTES; e a chave de idempotencia do upsert.
CREATE TABLE fato_snapshot_jogo_steam (
    id                    BIGSERIAL PRIMARY KEY,
    app_id                INTEGER     NOT NULL
        REFERENCES dim_jogo_steam (app_id) ON DELETE CASCADE,
    janela_coleta         TIMESTAMPTZ NOT NULL,
    data_coleta           TIMESTAMPTZ NOT NULL,
    jogadores_simultaneos INTEGER,
    nota_avaliacoes       NUMERIC(5, 2),   -- % de avaliacoes positivas
    numero_avaliacoes     INTEGER,
    avaliacoes_positivas  INTEGER,
    avaliacoes_negativas  INTEGER,
    classificacao_steam   VARCHAR(64),     -- ex.: "Very Positive"
    preco_no_momento      NUMERIC(10, 2),
    moeda                 VARCHAR(8),
    desconto_percentual   INTEGER,
    CONSTRAINT uq_snapshot_app_janela UNIQUE (app_id, janela_coleta)
);

CREATE INDEX ix_snapshot_janela ON fato_snapshot_jogo_steam (janela_coleta);

-- ===========================================================================
-- Dominio partidas (esports) -- Fase 2
--
-- Star schema compartilhado por Dota 2, LoL e Valorant. As chaves sao
-- substitutas e o id vindo da API fica em `id_externo`: e isso que permite os
-- tres jogos conviverem sem colisao de identificadores.
-- ===========================================================================

CREATE TABLE dim_jogo (
    id_jogo SERIAL PRIMARY KEY,
    codigo  VARCHAR(16) NOT NULL UNIQUE,   -- dota2 | lol | valorant
    nome    VARCHAR(64) NOT NULL
);

CREATE TABLE dim_tempo (
    id_tempo      INTEGER PRIMARY KEY,     -- AAAAMMDD, ex.: 20260902
    data          DATE        NOT NULL UNIQUE,
    ano           INTEGER     NOT NULL,
    mes           INTEGER     NOT NULL,
    dia           INTEGER     NOT NULL,
    trimestre     INTEGER     NOT NULL,
    semana        INTEGER     NOT NULL,
    dia_da_semana INTEGER     NOT NULL,
    nome_dia      VARCHAR(16) NOT NULL
);

CREATE TABLE dim_jogador (
    id_jogador BIGSERIAL PRIMARY KEY,
    id_jogo    INTEGER     NOT NULL REFERENCES dim_jogo (id_jogo),
    id_externo VARCHAR(64) NOT NULL,       -- account_id, puuid...
    nome       TEXT,
    regiao     VARCHAR(32),
    CONSTRAINT uq_jogador_jogo_externo UNIQUE (id_jogo, id_externo)
);

-- Heroi (Dota), campeao (LoL) e agente (Valorant): mesmo conceito.
CREATE TABLE dim_personagem (
    id_personagem SERIAL PRIMARY KEY,
    id_jogo       INTEGER     NOT NULL REFERENCES dim_jogo (id_jogo),
    id_externo    VARCHAR(32) NOT NULL,
    nome          VARCHAR(64) NOT NULL,
    nome_interno  VARCHAR(64),
    CONSTRAINT uq_personagem_jogo_externo UNIQUE (id_jogo, id_externo)
);

CREATE TABLE dim_partida (
    id_partida       BIGSERIAL PRIMARY KEY,
    id_jogo          INTEGER     NOT NULL REFERENCES dim_jogo (id_jogo),
    id_externo       VARCHAR(64) NOT NULL,   -- match_id
    id_tempo         INTEGER     REFERENCES dim_tempo (id_tempo),
    data_inicio      TIMESTAMPTZ,
    duracao_segundos INTEGER,
    modo             VARCHAR(48),
    tipo_partida     VARCHAR(16),            -- profissional | publica
    patch            VARCHAR(16),
    liga_nome        TEXT,
    liga_id_externo  VARCHAR(32),
    CONSTRAINT uq_partida_jogo_externo UNIQUE (id_jogo, id_externo)
);

CREATE INDEX ix_partida_data_inicio ON dim_partida (data_inicio);

-- Grao: um jogador dentro de uma partida.
-- As colunas sao as metricas que existem nos tres jogos. O que e exclusivo de
-- um deles vai para `metricas_extras`, em vez de virar coluna que os outros
-- nunca preencheriam.
CREATE TABLE fato_partida_jogador (
    id                       BIGSERIAL PRIMARY KEY,
    id_partida               BIGINT  NOT NULL
        REFERENCES dim_partida (id_partida) ON DELETE CASCADE,
    id_jogo                  INTEGER NOT NULL REFERENCES dim_jogo (id_jogo),
    id_jogador               BIGINT  REFERENCES dim_jogador (id_jogador),
    id_personagem            INTEGER REFERENCES dim_personagem (id_personagem),
    id_tempo                 INTEGER REFERENCES dim_tempo (id_tempo),
    equipe                   VARCHAR(16),   -- radiant | dire (lado no mapa)
    slot                     INTEGER NOT NULL,
    vitoria                  BOOLEAN,
    kills                    INTEGER,
    deaths                   INTEGER,
    assists                  INTEGER,
    dano_causado             INTEGER,
    dano_recebido            INTEGER,
    economia                 INTEGER,
    economia_por_minuto      INTEGER,
    experiencia_por_minuto   INTEGER,
    pontos_objetivo          INTEGER,       -- torres + Roshan (Dota)
    last_hits                INTEGER,
    denies                   INTEGER,
    nivel                    INTEGER,
    funcao                   VARCHAR(32),
    duracao_partida_segundos INTEGER,
    metricas_extras          JSONB,
    CONSTRAINT uq_fato_partida_slot UNIQUE (id_partida, slot)
);

CREATE INDEX ix_fato_jogo_personagem
    ON fato_partida_jogador (id_jogo, id_personagem);

-- ===========================================================================
-- fato_evento_partida (timeline granular) -- fora do escopo da Fase 2
-- ===========================================================================
