"""Contrato do painel admin: login por senha + token, e o gate nas rotas
protegidas. Sem sistema de contas - so uma senha (`ADMIN_SENHA`).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config import get_settings
from controllers.main import app
from controllers.routers import admin
from models.session import get_engine

SENHA_TESTE = "senha-de-teste-bem-forte"


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    try:
        with get_engine().connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - qualquer falha de conexao serve
        pytest.skip(f"Postgres indisponivel: {type(exc).__name__}")
    return TestClient(app)


@pytest.fixture
def com_senha(monkeypatch: pytest.MonkeyPatch):
    """Configura ADMIN_SENHA so pro escopo do teste, sem tocar no .env."""
    settings = get_settings().model_copy(update={"admin_senha": SENHA_TESTE})
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    return settings


def test_login_sem_senha_configurada_da_503(cliente: TestClient, monkeypatch):
    settings = get_settings().model_copy(update={"admin_senha": None})
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    resposta = cliente.post("/api/admin/login", json={"senha": "qualquer"})
    assert resposta.status_code == 503


def test_login_senha_errada_da_401(cliente: TestClient, com_senha):
    resposta = cliente.post("/api/admin/login", json={"senha": "errada"})
    assert resposta.status_code == 401


def test_login_senha_certa_devolve_token(cliente: TestClient, com_senha):
    resposta = cliente.post("/api/admin/login", json={"senha": SENHA_TESTE})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["token"]
    assert "." in corpo["token"]
    assert corpo["expira_em"]


def test_rota_protegida_sem_token_da_401(cliente: TestClient, com_senha):
    resposta = cliente.get("/api/admin/visao-geral")
    assert resposta.status_code == 401


def test_rota_protegida_com_token_de_outra_senha_da_401(cliente: TestClient, com_senha):
    resposta = cliente.get(
        "/api/admin/visao-geral",
        headers={"Authorization": "Bearer 9999999999.assinaturafalsa"},
    )
    assert resposta.status_code == 401


def test_rota_protegida_com_token_valido_funciona(cliente: TestClient, com_senha):
    token = cliente.post("/api/admin/login", json={"senha": SENHA_TESTE}).json()["token"]

    resposta = cliente.get(
        "/api/admin/visao-geral", headers={"Authorization": f"Bearer {token}"}
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    for chave in (
        "online_agora",
        "acessos_hoje",
        "acessos_mes",
        "acessos_ano",
        "buscas_hoje",
        "serie_acessos",
        "termos_mais_buscados",
    ):
        assert chave in corpo


def test_sistema_devolve_alguma_fonte(cliente: TestClient, com_senha):
    token = cliente.post("/api/admin/login", json={"senha": SENHA_TESTE}).json()["token"]
    resposta = cliente.get(
        "/api/admin/sistema", headers={"Authorization": f"Bearer {token}"}
    )
    assert resposta.status_code == 200
    assert resposta.json()["fonte"] in ("netdata", "local")


def test_banco_devolve_tamanho_e_tabelas(cliente: TestClient, com_senha):
    token = cliente.post("/api/admin/login", json={"senha": SENHA_TESTE}).json()["token"]
    resposta = cliente.get(
        "/api/admin/banco", headers={"Authorization": f"Bearer {token}"}
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["tamanho_texto"]
    assert isinstance(corpo["tabelas"], list)
    assert len(corpo["tabelas"]) > 0


def test_telemetria_acesso_e_204(cliente: TestClient):
    resposta = cliente.post(
        "/api/telemetria/acesso",
        json={"visitante_id": "visitante-de-teste-admin-py", "rota": "/"},
    )
    assert resposta.status_code == 204
