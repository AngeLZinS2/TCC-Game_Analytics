"""Coleta de preco sob demanda do ITAD.

A parte que da pra testar sem rede nem banco: o `ItadCollector` aceitando uma
lista de `app_ids` (o caminho da busca sob demanda) e o helper do `/coletar`
sendo best-effort quando nao ha `ITAD_API_KEY`.
"""

from __future__ import annotations

import pytest

from services.collectors.base import RawRecord
from services.collectors.itad_collector import ItadCollector, SemChaveItadError
from services.etl.transform_itad import ENDPOINT_LOOKUP, ENDPOINT_PRECOS


class _StorageFake:
    def salvar_muitos(self, registros):  # noqa: D401 - stub
        return len(list(registros))


def test_app_ids_fica_guardado_como_lista():
    coletor = ItadCollector(raw_storage=_StorageFake(), app_ids=(10, 20, 30))
    assert coletor.app_ids == [10, 20, 30]


def test_sem_app_ids_o_alvo_e_o_catalogo_inteiro():
    coletor = ItadCollector(raw_storage=_StorageFake())
    assert coletor.app_ids is None


def test_parse_sintetiza_lookup_dos_jogos_ja_conhecidos():
    """O buraco que travava o lote: em regime estavel `collect` nao faz nenhum
    `lookup` (todo jogo ja tem `itad_id`), e sem lookup o `transformar` nao
    liga o UUID do `prices` a um appid. O `parse` sintetiza esses lookups em
    memoria a partir de `_uuids_cacheados`."""
    uuid = "018d937f-5a2b-72c1-9e00-abc123456789"
    coletor = ItadCollector(raw_storage=_StorageFake())
    coletor._uuids_cacheados = {1245620: uuid}

    registros = [
        RawRecord(
            fonte="itad",
            endpoint=ENDPOINT_PRECOS,
            identificador="lote-1-1",
            payload=[{"id": uuid, "deals": [
                {"shop": {"id": 61, "name": "Nuuvem"},
                 "price": {"amount": 149.99, "currency": "BRL"},
                 "regular": {"amount": 249.9, "currency": "BRL"}, "cut": 40}
            ]}],
        ),
    ]
    resultado = coletor.parse(registros)
    assert resultado.total == 1
    assert resultado.jogos[0].app_id == 1245620
    assert resultado.jogos[0].ofertas[0].loja == "Nuuvem"


def test_parse_nao_duplica_lookup_real():
    """Se o jogo teve `lookup` de verdade nesta rodada, o sintetico nao entra."""
    uuid = "018d937f-5a2b-72c1-9e00-abc123456789"
    coletor = ItadCollector(raw_storage=_StorageFake())
    coletor._uuids_cacheados = {1245620: uuid}
    registros = [
        RawRecord(fonte="itad", endpoint=ENDPOINT_LOOKUP, identificador="1245620",
                  payload={"found": True, "game": {"id": uuid}}),
        RawRecord(fonte="itad", endpoint=ENDPOINT_PRECOS, identificador="lote-1-1",
                  payload=[{"id": uuid, "deals": []}]),
    ]
    resultado = coletor.parse(registros)
    assert resultado.total == 1


def test_collect_sem_chave_recusa():
    coletor = ItadCollector(raw_storage=_StorageFake(), app_ids=[730])
    coletor.settings = coletor.settings.model_copy(update={"itad_api_key": None})
    with pytest.raises(SemChaveItadError):
        coletor.collect()


def test_preco_sob_demanda_sem_chave_nao_toca_no_coletor(monkeypatch):
    """Sem `ITAD_API_KEY` o helper do `/coletar` sai sem tocar em storage/rede."""
    from controllers.routers import catalogo

    class _StubSettings:
        itad_api_key = None

    monkeypatch.setattr(catalogo, "get_settings", lambda: _StubSettings())

    def _proibido(*_a, **_k):  # pragma: no cover - nao deve ser chamado
        raise AssertionError("ItadCollector nao deveria ser instanciado sem chave")

    monkeypatch.setattr("services.collectors.itad_collector.ItadCollector", _proibido)

    catalogo._coletar_preco_sob_demanda(730)  # nao levanta
