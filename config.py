"""Configuracao central do projeto, lida de variaveis de ambiente / .env.

Nenhuma chave de API e hardcoded: tudo passa por aqui.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 55432
    postgres_db: str = "gaming_analytics"
    postgres_user: str = "gaming"
    postgres_password: str = "gaming"

    # --- Chaves de API (opcionais nesta fase) ---
    steam_api_key: str | None = None
    riot_api_key: str | None = None
    valorant_api_key: str | None = None
    # Opcional: sem chave o OpenDota ja permite ~3.000 chamadas/dia.
    opendota_api_key: str | None = None

    # --- API / dashboard ---
    # Origens liberadas no CORS, separadas por virgula. O Vite sobe em 5173
    # (dev) e 4173 (preview do build).
    cors_origins: str = "http://localhost:5173,http://localhost:4173"

    # --- Logging ---
    log_level: str = "INFO"
    log_format: str = "json"

    # --- Armazenamento bruto ---
    raw_data_dir: Path = Path("data/raw")

    # --- Rate limiting (segundos entre chamadas por host) ---
    steam_store_rate_limit_seconds: float = 1.5
    steam_api_rate_limit_seconds: float = 0.5
    steam_spy_rate_limit_seconds: float = 1.0
    # OpenDota: 60 requisicoes por minuto -> 1,05s de folga entre chamadas.
    opendota_rate_limit_seconds: float = 1.05

    # --- Steam ---
    #: Quantas avaliacoes escritas pedir por jogo (0 traz so o resumo agregado).
    #: Cabe numa chamada so ate 100 - acima disso a Steam pagina por cursor, e
    #: paginar gastaria o mesmo balde de rate limit do appdetails.
    steam_reviews_por_app: int = Field(default=100, ge=0, le=100)

    #: Quantas paginas de avaliacoes puxar por jogo. A Steam pagina por cursor;
    #: cada pagina e uma requisicao no mesmo balde do appdetails, entao subir
    #: isso multiplica o custo da coleta pelo numero de jogos monitorados.
    steam_reviews_paginas: int = Field(default=1, ge=1, le=20)

    # --- Liquipedia (agenda de partidas) ---
    #: A politica da Liquipedia pede 2s entre chamadas a `action=parse`.
    #: O padrao aqui e 3 para dar folga - um bloqueio por excesso atinge o IP,
    #: nao a chave, e derrubaria todo mundo na mesma rede.
    liquipedia_rate_limit_seconds: float = Field(default=3.0, gt=0)
    #: A Liquipedia exige um User-Agent que identifique o projeto e um contato.
    #: UA generico e motivo declarado de bloqueio nos termos de uso deles.
    liquipedia_user_agent: str = (
        "GamingAnalyticsTCC/0.1 (projeto academico; "
        "https://github.com/ - contato no repositorio)"
    )

    # --- Agendador de coleta ---
    #: Intervalo entre coletas da Steam, em minutos.
    #:
    #: O padrao e 60 porque a JANELA do snapshot e horaria: `truncar_janela`
    #: arredonda o momento da coleta para a hora, e `(app_id, janela_coleta)` e
    #: unico. Coletar de 30 em 30 minutos nao dobraria a serie - a segunda
    #: coleta cairia na mesma janela e viraria um UPDATE da primeira. O
    #: intervalo acompanha o grao do fato; mudar um sem o outro so gasta rede.
    agendador_steam_minutos: int = Field(default=60, ge=5)

    #: Intervalo entre coletas de partidas profissionais, em minutos.
    #:
    #: Partidas terminam ao longo do dia e a OpenDota so as publica depois de
    #: encerradas, entao nao ha janela a respeitar - o limite aqui e a cortesia
    #: com a API publica. Seis horas cobrem um dia de campeonato em quatro
    #: passadas.
    agendador_opendota_minutos: int = Field(default=360, ge=5)

    #: Intervalo entre leituras da agenda de partidas futuras, em minutos.
    #:
    #: O calendario de campeonato muda em dias, nao em minutos, e a Liquipedia
    #: bloqueia por IP quem abusa. Duas vezes ao dia e generoso para o dado e
    #: barato para eles.
    agendador_liquipedia_minutos: int = Field(default=720, ge=5)

    #: Intervalo entre leituras das paginas de equipe da Liquipedia, em minutos.
    #:
    #: Uma vez por dia. Equipe nao nasce e nao muda de regiao de hora em hora -
    #: o que muda e a lista, quando um time novo ganha pagina na wiki. Uma
    #: rodada sao ~23 chamadas e ~70 segundos, entao diario e barato para eles.
    agendador_equipes_minutos: int = Field(default=1440, ge=60)

    #: Quantas wikis coletar equipes por rodada do agendador.
    #:
    #: Nao da para varrer as 71 de uma vez: o Counter-Strike sozinho tem 1.410
    #: equipes e leva 97 segundos; as 71 juntas passariam de uma hora e meia de
    #: chamadas seguidas a um servico publico e gratuito. O rodizio pega as
    #: proximas N a cada rodada e volta ao inicio - uma varredura completa leva
    #: cerca de uma semana, que e rapido para um dado que muda em meses.
    agendador_equipes_por_rodada: int = Field(default=10, ge=1, le=80)

    #: Quantas partidas pedir por rodada do agendador.
    agendador_opendota_limite: int = Field(default=100, ge=1, le=500)

    #: Coletar uma vez logo que o agendador sobe, em vez de esperar o intervalo.
    #:
    #: Seguro por construcao: a coleta da Steam e upsert na janela horaria e a
    #: da OpenDota pula partidas ja existentes. Um restart nao duplica nada - no
    #: pior caso repete uma chamada de rede.
    agendador_rodar_ao_iniciar: bool = True

    # --- Assistente (OpenRouter) ---
    #: Sem chave, o endpoint do assistente responde 503 com a instrucao. E um
    #: estado esperado: o resto do projeto funciona sem LLM nenhum.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    #: Modelo do OpenRouter. O padrao e gratuito e responde bem em portugues.
    openrouter_model: str = "minimax/minimax-m3:free"
    openrouter_timeout_seconds: float = Field(default=60.0, gt=0)

    steam_country: str = "br"
    steam_language: str = "english"

    # --- ETL ---
    snapshot_bucket_minutes: int = Field(default=60, ge=1, le=1440)

    http_timeout_seconds: float = 30.0
    http_max_retries: int = 5

    @property
    def database_url(self) -> str:
        """URL SQLAlchemy usando o driver psycopg (v3)."""
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins_lista(self) -> list[str]:
        return [origem.strip() for origem in self.cors_origins.split(",") if origem.strip()]

    @property
    def raw_data_path(self) -> Path:
        """Diretorio de payloads brutos, sempre resolvido a partir da raiz."""
        path = self.raw_data_dir
        if not path.is_absolute():
            path = BASE_DIR / path
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
