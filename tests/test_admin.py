"""Contrato do painel admin: mesma conta do site (Firebase), autorizada por
uma lista de uids (`ADMIN_FIREBASE_UIDS`) - nao ha senha propria.

Nao ha como emitir um ID token real do Firebase num teste -
`verificar_token_firebase` e trocada por um dublê (monkeypatch), do mesmo
jeito que `test_usuario.py` faz.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config import get_settings
from controllers.main import app
from controllers.routers import admin, usuario
from models.session import get_engine

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
    """Conta logada comum, sem acesso ao painel - uid novo a cada teste."""
    uid = f"uid-teste-{uuid.uuid4().hex[:12]}"
    claims = {"sub": uid, "email": "teste@playdb.local", "name": "Conta de Teste"}
    monkeypatch.setattr(usuario, "verificar_token_firebase", lambda *a, **k: claims)
    return claims


@pytest.fixture
def com_admin(com_usuario, monkeypatch: pytest.MonkeyPatch):
    """A mesma conta de `com_usuario`, agora na lista de administradores."""
    settings = get_settings().model_copy(update={"admin_firebase_uids": com_usuario["sub"]})
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    return com_usuario


def test_rota_protegida_sem_token_da_401(cliente: TestClient):
    resposta = cliente.get("/api/admin/visao-geral")
    assert resposta.status_code == 401


def test_rota_protegida_sem_admin_configurado_da_503(cliente: TestClient, com_usuario, monkeypatch):
    settings = get_settings().model_copy(update={"admin_firebase_uids": None})
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    resposta = cliente.get("/api/admin/visao-geral", headers=CABECALHO)
    assert resposta.status_code == 503


def test_rota_protegida_conta_fora_da_lista_da_403(cliente: TestClient, com_usuario, monkeypatch):
    settings = get_settings().model_copy(update={"admin_firebase_uids": "outro-uid-qualquer"})
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    resposta = cliente.get("/api/admin/visao-geral", headers=CABECALHO)
    assert resposta.status_code == 403


def test_eu_sou_admin_sem_token_da_401(cliente: TestClient):
    resposta = cliente.get("/api/admin/eu-sou-admin")
    assert resposta.status_code == 401


def test_eu_sou_admin_conta_comum_devolve_falso(cliente: TestClient, com_usuario):
    resposta = cliente.get("/api/admin/eu-sou-admin", headers=CABECALHO)
    assert resposta.status_code == 200
    assert resposta.json() == {"admin": False}


def test_eu_sou_admin_conta_admin_devolve_verdadeiro(cliente: TestClient, com_admin):
    resposta = cliente.get("/api/admin/eu-sou-admin", headers=CABECALHO)
    assert resposta.status_code == 200
    assert resposta.json() == {"admin": True}


def test_rota_protegida_com_conta_admin_funciona(cliente: TestClient, com_admin):
    resposta = cliente.get("/api/admin/visao-geral", headers=CABECALHO)
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


def test_sistema_devolve_alguma_fonte(cliente: TestClient, com_admin):
    resposta = cliente.get("/api/admin/sistema", headers=CABECALHO)
    assert resposta.status_code == 200
    assert resposta.json()["fonte"] in ("netdata", "local")


def test_contas_devolve_total_e_lista_sem_dado_pessoal(cliente: TestClient, com_admin):
    resposta = cliente.get("/api/admin/contas", headers=CABECALHO)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo["total"], int)
    assert corpo["total"] >= 1
    assert isinstance(corpo["contas"], list)
    assert len(corpo["contas"]) >= 1
    for conta in corpo["contas"]:
        # so nome + data de criacao - nunca e-mail nem uid (LGPD).
        assert set(conta.keys()) == {"nome_exibicao", "criado_em"}


def test_banco_devolve_tamanho_e_tabelas(cliente: TestClient, com_admin):
    resposta = cliente.get("/api/admin/banco", headers=CABECALHO)
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
