"""API FastAPI.

Expoe os dois dominios de dados para o dashboard React (`dashboard/`):

    /api/visao-geral      contagens transversais
    /api/steam/...        catalogo / mercado
    /api/partidas/...     star schema de partidas
    /api/ml/sentimento/.. classificacao do texto das avaliacoes
    /api/assistente/...   perguntas em linguagem natural sobre os dados
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.routers import (
    assistente,
    catalogo,
    confronto,
    dota,
    meta,
    sentimento,
    steam,
)
from config import get_settings
from db.session import get_engine
from logging_config import configurar_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configurar_logging(settings.log_level, settings.log_format)
    yield


app = FastAPI(
    title="Gaming Analytics API",
    description="Coleta e analise de dados de esports (Dota 2, LoL, Valorant) e do catalogo Steam.",
    version="0.2.0",
    lifespan=lifespan,
)

# O dashboard roda em outra origem (Vite em :5173), entao precisa de CORS.
# As origens permitidas vem do .env - nada de "*" fixo no codigo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_lista,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(steam.router)
app.include_router(catalogo.router)
app.include_router(dota.router)
app.include_router(sentimento.router)
app.include_router(confronto.router)
app.include_router(assistente.router)


@app.get("/", tags=["meta"])
def raiz() -> dict[str, str]:
    return {"servico": "gaming-analytics", "docs": "/docs"}


@app.get("/health", tags=["meta"])
def health() -> dict[str, object]:
    """Confirma que a API sobe E que o Postgres responde."""
    try:
        with get_engine().connect() as conexao:
            conexao.execute(text("SELECT 1"))
        banco_ok = True
        detalhe = None
    except Exception as exc:  # noqa: BLE001 - health nunca deve levantar
        banco_ok = False
        detalhe = f"{type(exc).__name__}: {exc}"

    return {"status": "ok" if banco_ok else "degradado", "banco": banco_ok, "erro": detalhe}
