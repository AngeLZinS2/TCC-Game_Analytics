"""Testes do parsing do catalogo completo da Steam (Fase 35).

A fixture e uma pagina real de `GetAppList` (reduzida a 5 apps), com um app
sintetico de nome vazio para testar o descarte. `last_appid`/`concluido`
saem do formato da resposta - nenhum estado extra precisa ser simulado.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.collectors.base import RawRecord
from services.etl.transform_steam_catalogo import (
    FONTE,
    transformar,
)

MOMENTO = datetime(2026, 9, 15, 3, 51, 0, tzinfo=timezone.utc)


def _pagina(payload, identificador="catalogo_inicial-0") -> RawRecord:
    return RawRecord(
        fonte=FONTE,
        endpoint="getapplist",
        identificador=identificador,
        payload=payload,
        coletado_em=MOMENTO,
    )


def test_sem_fase_devolve_sem_execucao():
    """`fase=None` e o tick no-op do passo incremental (ainda nao venceu o
    intervalo) - `collect()` nem tenta a rede, e nada e persistido."""
    assert transformar([], None).fase == "sem_execucao"
    assert transformar([], None).total == 0


def test_fase_com_registros_vazios_preserva_a_fase():
    """Uma pagina que falhou (`collect()` sem RawRecord) ainda carrega a
    fase - `load_steam_catalogo.py` grava o checkpoint mesmo sem apps novos,
    so sem avancar `last_appid`."""
    resultado = transformar([], "catalogo_inicial")
    assert resultado.fase == "catalogo_inicial"
    assert resultado.total == 0
    assert resultado.last_appid is None
    assert resultado.concluido is False


def test_parse_pagina_real_descarta_app_sem_nome(carregar_fixture):
    payload = carregar_fixture("steam_getapplist_pagina")
    resultado = transformar([_pagina(payload)], "catalogo_inicial")

    # 5 apps na fixture, 1 com nome vazio -> 4 linhas validas.
    assert resultado.total == 4
    assert {linha.app_id for linha in resultado.linhas} == {10, 70, 220, 400}
    assert 620 not in {linha.app_id for linha in resultado.linhas}


def test_parse_extrai_last_modified_e_price_change_number(carregar_fixture):
    payload = carregar_fixture("steam_getapplist_pagina")
    resultado = transformar([_pagina(payload)], "catalogo_inicial")

    cs = next(l for l in resultado.linhas if l.app_id == 10)
    assert cs.nome == "Counter-Strike"
    assert cs.numero_mudanca_preco == 20123456
    assert cs.ultima_modificacao == datetime.fromtimestamp(1704067200, tz=timezone.utc)


def test_last_appid_e_concluido_vem_da_ultima_pagina(carregar_fixture):
    payload = carregar_fixture("steam_getapplist_pagina")
    resultado = transformar([_pagina(payload)], "catalogo_inicial")

    assert resultado.last_appid == 620  # ultimo appid da pagina, mesmo descartado
    assert resultado.concluido is False  # have_more_results=true na fixture
    assert resultado.paginas_processadas == 1


def test_have_more_results_false_marca_concluido():
    payload = {
        "apps": [{"appid": 999, "name": "Fim do Catalogo", "last_modified": 1, "price_change_number": 1}],
        "have_more_results": False,
        "last_appid": 999,
    }
    resultado = transformar([_pagina(payload)], "catalogo_inicial")
    assert resultado.concluido is True


def test_concluido_reflete_so_a_ultima_pagina_processada():
    """Duas paginas: a primeira diz que tem mais, a segunda que acabou."""
    pagina1 = {
        "apps": [{"appid": 1, "name": "A", "last_modified": 1, "price_change_number": 1}],
        "have_more_results": True,
        "last_appid": 1,
    }
    pagina2 = {
        "apps": [{"appid": 2, "name": "B", "last_modified": 1, "price_change_number": 1}],
        "have_more_results": False,
        "last_appid": 2,
    }
    resultado = transformar(
        [_pagina(pagina1, "p1"), _pagina(pagina2, "p2")], "catalogo_incremental"
    )
    assert resultado.concluido is True
    assert resultado.last_appid == 2
    assert resultado.total == 2


def test_pagina_sem_apps_nao_quebra():
    payload = {"apps": [], "have_more_results": False, "last_appid": 0}
    resultado = transformar([_pagina(payload)], "catalogo_inicial")
    assert resultado.total == 0
    assert resultado.concluido is True
    assert resultado.last_appid is None
