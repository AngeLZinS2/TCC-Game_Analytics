"""Contrato da conta de usuario: gate por token do Firebase, upsert de
`dim_usuario`, e o historico de perguntas do Assistente de IA por conta.

Nao ha como emitir um ID token real do Firebase num teste - `verificar_token_firebase`
e trocada por um dublê (monkeypatch) que devolve claims fixas, do mesmo jeito
que `test_admin.py` troca `get_settings` pra nao depender de segredo real.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config import get_settings
from controllers.main import app
from controllers.routers import usuario
from models.session import get_engine
from services import cifra

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
    """Faz `verificar_token_firebase` devolver claims de uma conta de teste,
    com um uid novo a cada teste pra nao colidir com `dim_usuario` de outra
    rodada."""
    uid = f"uid-teste-{uuid.uuid4().hex[:12]}"
    claims = {"sub": uid, "email": "teste@playdb.local", "name": "Conta de Teste"}
    monkeypatch.setattr(usuario, "verificar_token_firebase", lambda *a, **k: claims)
    return claims


def test_perfil_sem_token_da_401(cliente: TestClient):
    resposta = cliente.get("/api/usuario/perfil")
    assert resposta.status_code == 401


def test_perfil_cria_conta_na_primeira_chamada(cliente: TestClient, com_usuario):
    resposta = cliente.get("/api/usuario/perfil", headers=CABECALHO)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["email"] == "teste@playdb.local"
    assert corpo["nome_exibicao"] == "Conta de Teste"
    assert corpo["total_perguntas_assistente"] == 0
    assert corpo["membro_desde"]


def test_perguntar_sem_token_da_401(cliente: TestClient):
    resposta = cliente.post("/api/assistente/perguntar", json={"pergunta": "oi"})
    assert resposta.status_code == 401


def test_historico_assistente_comeca_vazio(cliente: TestClient, com_usuario):
    resposta = cliente.get("/api/usuario/historico-assistente", headers=CABECALHO)
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_avaliar_pergunta_inexistente_da_404(cliente: TestClient, com_usuario):
    resposta = cliente.patch(
        "/api/usuario/historico-assistente/999999999",
        json={"util": True},
        headers=CABECALHO,
    )
    assert resposta.status_code == 404


def test_limpar_historico_vazio_nao_da_erro(cliente: TestClient, com_usuario):
    resposta = cliente.delete("/api/usuario/historico-assistente", headers=CABECALHO)
    assert resposta.status_code == 204


def test_perfil_comeca_sem_chave_ia_propria(cliente: TestClient, com_usuario):
    resposta = cliente.get("/api/usuario/perfil", headers=CABECALHO)
    corpo = resposta.json()
    assert corpo["tem_chave_ia_propria"] is False
    assert corpo["chave_ia_mascarada"] is None


def test_salvar_e_remover_chave_ia(cliente: TestClient, com_usuario):
    salvar = cliente.put(
        "/api/usuario/chave-ia",
        json={"chave": "sk-or-v1-chave-de-teste-nao-e-real-9999"},
        headers=CABECALHO,
    )
    assert salvar.status_code == 204

    perfil = cliente.get("/api/usuario/perfil", headers=CABECALHO).json()
    assert perfil["tem_chave_ia_propria"] is True
    assert perfil["chave_ia_mascarada"] == "••••9999"

    remover = cliente.delete("/api/usuario/chave-ia", headers=CABECALHO)
    assert remover.status_code == 204

    perfil2 = cliente.get("/api/usuario/perfil", headers=CABECALHO).json()
    assert perfil2["tem_chave_ia_propria"] is False
    assert perfil2["chave_ia_mascarada"] is None


def test_salvar_chave_curta_demais_da_422(cliente: TestClient, com_usuario):
    resposta = cliente.put(
        "/api/usuario/chave-ia", json={"chave": "abc"}, headers=CABECALHO
    )
    assert resposta.status_code == 422


def test_salvar_chave_sem_cifra_configurada_da_503(
    cliente: TestClient, com_usuario, monkeypatch: pytest.MonkeyPatch
):
    sem_cifra = get_settings().model_copy(update={"chave_cifra_secrets": None})
    monkeypatch.setattr(cifra, "get_settings", lambda: sem_cifra)
    resposta = cliente.put(
        "/api/usuario/chave-ia",
        json={"chave": "sk-or-v1-outra-chave-de-teste-000"},
        headers=CABECALHO,
    )
    assert resposta.status_code == 503
