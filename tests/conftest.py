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
