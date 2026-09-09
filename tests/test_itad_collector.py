"""Coleta de preco sob demanda do ITAD.

A parte que da pra testar sem rede nem banco: o `ItadCollector` aceitando uma
lista de `app_ids` (o caminho da busca sob demanda) e o helper do `/coletar`
sendo best-effort quando nao ha `ITAD_API_KEY`.
"""

from __future__ import annotations

import pytest

from services.collectors.itad_collector import ItadCollector, SemChaveItadError


class _StorageFake:
    def salvar_muitos(self, registros):  # noqa: D401 - stub
        return len(list(registros))


def test_app_ids_fica_guardado_como_lista():
    coletor = ItadCollector(raw_storage=_StorageFake(), app_ids=(10, 20, 30))
    assert coletor.app_ids == [10, 20, 30]


def test_sem_app_ids_o_alvo_e_o_catalogo_inteiro():
    coletor = ItadCollector(raw_storage=_StorageFake())
    assert coletor.app_ids is None


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
