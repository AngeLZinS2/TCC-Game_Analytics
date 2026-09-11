"""Contrato de favoritos: jogos (Steam/Xbox) e times de esports, por conta.

Usa jogos/times que ja existem no banco local (coletados de verdade) pra
testar o enriquecimento - sem Postgres com catalogo populado, os testes que
precisam disso pulam em vez de falhar.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from controllers.main import app
from controllers.routers import usuario
from models.models import DimEquipe, DimJogoSteam
from models.session import get_engine, session_scope

CABECALHO = {"Authorization": "Bearer token-de-teste"}


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    try:
        with get_engine().connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - qualquer falha de conexao serve
        pytest.skip(f"Postgres indisponivel: {type(exc).__name__}")
    return TestClient(app)


@pytest.fixture
def com_usuario(monkeypatch: pytest.MonkeyPatch):
    uid = f"uid-teste-{uuid.uuid4().hex[:12]}"
    claims = {"sub": uid, "email": "teste@playdb.local", "name": "Conta de Teste"}
    monkeypatch.setattr(usuario, "verificar_token_firebase", lambda *a, **k: claims)
    return claims


def test_jogos_sem_token_da_401(cliente: TestClient):
    resposta = cliente.get("/api/usuario/favoritos/jogos")
    assert resposta.status_code == 401


def test_equipes_sem_token_da_401(cliente: TestClient):
    resposta = cliente.get("/api/usuario/favoritos/equipes")
    assert resposta.status_code == 401


def test_favoritar_e_listar_jogo_steam(cliente: TestClient, com_usuario):
    with session_scope() as sessao:
        app_id = sessao.execute(select(DimJogoSteam.app_id).limit(1)).scalar_one_or_none()
    if app_id is None:
        pytest.skip("catalogo Steam local vazio")

    resposta = cliente.post(
        "/api/usuario/favoritos/jogos",
        json={"fonte": "steam", "jogo_id": str(app_id)},
        headers=CABECALHO,
    )
    assert resposta.status_code == 204

    listagem = cliente.get("/api/usuario/favoritos/jogos", headers=CABECALHO)
    assert listagem.status_code == 200
    corpo = listagem.json()
    assert len(corpo) == 1
    assert corpo[0]["fonte"] == "steam"
    assert corpo[0]["jogo_id"] == str(app_id)
    assert "promocao_ativa" in corpo[0]

    # Favoritar de novo nao duplica (idempotente).
    cliente.post(
        "/api/usuario/favoritos/jogos",
        json={"fonte": "steam", "jogo_id": str(app_id)},
        headers=CABECALHO,
    )
    listagem2 = cliente.get("/api/usuario/favoritos/jogos", headers=CABECALHO)
    assert len(listagem2.json()) == 1

    remocao = cliente.delete(
        f"/api/usuario/favoritos/jogos/steam/{app_id}", headers=CABECALHO
    )
    assert remocao.status_code == 204
    assert cliente.get("/api/usuario/favoritos/jogos", headers=CABECALHO).json() == []


def test_desfavoritar_jogo_inexistente_da_404(cliente: TestClient, com_usuario):
    resposta = cliente.delete(
        "/api/usuario/favoritos/jogos/steam/999999999", headers=CABECALHO
    )
    assert resposta.status_code == 404


def test_favoritar_equipe_inexistente_da_404(cliente: TestClient, com_usuario):
    resposta = cliente.post(
        "/api/usuario/favoritos/equipes",
        json={"id_equipe": 999999999},
        headers=CABECALHO,
    )
    assert resposta.status_code == 404


def test_favoritar_e_listar_equipe(cliente: TestClient, com_usuario):
    with session_scope() as sessao:
        id_equipe = sessao.execute(select(DimEquipe.id_equipe).limit(1)).scalar_one_or_none()
    if id_equipe is None:
        pytest.skip("nenhuma equipe coletada localmente")

    resposta = cliente.post(
        "/api/usuario/favoritos/equipes",
        json={"id_equipe": id_equipe},
        headers=CABECALHO,
    )
    assert resposta.status_code == 204

    listagem = cliente.get("/api/usuario/favoritos/equipes", headers=CABECALHO)
    assert listagem.status_code == 200
    corpo = listagem.json()
    assert len(corpo) == 1
    assert corpo[0]["id_equipe"] == id_equipe
    assert "proxima_partida" in corpo[0]

    remocao = cliente.delete(
        f"/api/usuario/favoritos/equipes/{id_equipe}", headers=CABECALHO
    )
    assert remocao.status_code == 204
    assert cliente.get("/api/usuario/favoritos/equipes", headers=CABECALHO).json() == []
