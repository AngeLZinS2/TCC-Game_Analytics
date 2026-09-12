"""Testes do catalogo de modelos do seletor do Perfil.

Nao ha rede aqui: a lista do OpenRouter e testada contra uma resposta
fabricada, porque o que precisa valer nao e "qual modelo existe hoje" (isso
muda toda semana) e sim a CURADORIA - o que entra, o que fica de fora, e em
que ordem.
"""

from __future__ import annotations

import pytest

from services.ml import modelos_ia


@pytest.fixture(autouse=True)
def _cache_limpo():
    """O cache e de processo e vive uma hora - sem limpar, o primeiro teste
    contamina os outros."""
    modelos_ia._cache["em"] = 0.0
    modelos_ia._cache["itens"] = []
    yield
    modelos_ia._cache["em"] = 0.0
    modelos_ia._cache["itens"] = []


class _RespostaFalsa:
    def __init__(self, dados):
        self._dados = dados

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": self._dados}


def _com_resposta(monkeypatch, dados):
    monkeypatch.setattr(
        modelos_ia.requests, "get", lambda *a, **k: _RespostaFalsa(dados)
    )


def test_modelos_diretos_nao_levam_prefixo_do_openrouter():
    """O id muda de caminho: no OpenRouter e "anthropic/claude-sonnet-5", na
    API direta da Anthropic e "claude-sonnet-5". Mandar um pelo outro da
    "modelo nao encontrado" na hora da pergunta, nao no cadastro - era
    exatamente o erro que o seletor existe para evitar."""
    for modelo in modelos_ia.listar("anthropic"):
        assert "/" not in modelo.id
    for modelo in modelos_ia.listar("google"):
        assert "/" not in modelo.id

    ids_anthropic = {m.id for m in modelos_ia.listar("anthropic")}
    assert "claude-sonnet-5" in ids_anthropic


def test_openrouter_cura_a_lista(monkeypatch):
    _com_resposta(
        monkeypatch,
        [
            {"id": "algum/modelo:free", "name": "Algum: Modelo (free)"},
            {"id": "anthropic/claude-sonnet-5", "name": "Anthropic: Claude Sonnet 5"},
            # `:batch` e assincrono - nao serve para pergunta interativa.
            {"id": "anthropic/claude-sonnet-5:batch", "name": "Anthropic: Sonnet (batch)"},
            # Familia fora da curadoria: nao entra (senao sao 400+ opcoes).
            {"id": "obscuro/modelo-x", "name": "Obscuro: Modelo X"},
        ],
    )

    modelos = modelos_ia.listar("openrouter")
    ids = [m.id for m in modelos]

    assert "algum/modelo:free" in ids
    assert "anthropic/claude-sonnet-5" in ids
    assert "anthropic/claude-sonnet-5:batch" not in ids
    assert "obscuro/modelo-x" not in ids
    # Gratuitos primeiro - e a opcao que mais gente vai querer.
    assert modelos[0].gratuito is True
    assert modelos[0].grupo == "Gratuitos"


def test_nome_da_opcao_nao_repete_familia_nem_o_free(monkeypatch):
    _com_resposta(
        monkeypatch, [{"id": "algum/modelo:free", "name": "Algum: Modelo VL (free)"}]
    )

    modelo = modelos_ia.listar("openrouter")[0]

    # O grupo ja diz a familia e o selo ja diz que e gratis - repetir os dois
    # no rotulo so gasta a largura do select.
    assert modelo.nome == "Modelo VL"


def test_falha_da_api_devolve_fallback_em_vez_de_select_vazio(monkeypatch):
    def _explode(*a, **k):
        raise modelos_ia.requests.RequestException("sem rede")

    monkeypatch.setattr(modelos_ia.requests, "get", _explode)

    modelos = modelos_ia.listar("openrouter")

    assert modelos, "select vazio deixaria a pessoa sem como escolher modelo"
    assert all(m.id for m in modelos)


def test_catalogo_traz_os_tres_provedores(monkeypatch):
    _com_resposta(monkeypatch, [{"id": "anthropic/claude-sonnet-5", "name": "x"}])

    catalogo = modelos_ia.catalogo()

    assert set(catalogo) == {"openrouter", "anthropic", "google"}
    assert all(catalogo.values())
