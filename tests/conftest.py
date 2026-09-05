from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Permite `import etl.transform_steam` rodando pytest da raiz do projeto.
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def carregar_fixture():
    def _carregar(nome: str):
        return json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))

    return _carregar


@pytest.fixture
def sem_opgg(monkeypatch):
    """Finge que o servidor do OP.GG esta fora do ar.

    Os testes de roteamento de contexto sao deterministas e sem rede por
    principio (ver o docstring de test_assistente.py). O bloco de elenco passou
    a consultar uma fonte externa, e sem esta fixture a suite inteira dependeria
    de um servico de terceiro estar no ar - alem de gastar uma chamada por
    teste num servico gratuito.
    """
    from collectors import opgg_mcp

    def fora_do_ar():
        raise opgg_mcp.OpggIndisponivel("desligado no teste")

    monkeypatch.setattr(opgg_mcp, "estatisticas_agentes_valorant", fora_do_ar)
