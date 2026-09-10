"""Coleta do catalogo Xbox - a parte testavel sem rede nem banco.

O `XboxCollector` aceitando uma lista de `product_ids` (o caminho da coleta sob
demanda), a semente sendo lida do disco, e a tarefa do agendador so entrando
quando `xbox_enabled`.
"""

from __future__ import annotations

from services.collectors.xbox_collector import (
    XboxCollector,
    carregar_produtos_semente,
    _ids_da_sigl,
)


class _StorageFake:
    def salvar_muitos(self, registros):  # noqa: D401 - stub
        return len(list(registros))


def test_product_ids_fica_guardado_como_lista():
    coletor = XboxCollector(raw_storage=_StorageFake(), product_ids=("A", "B", "C"))
    assert coletor.product_ids == ["A", "B", "C"]


def test_sem_product_ids_o_alvo_e_game_pass_mais_banco():
    coletor = XboxCollector(raw_storage=_StorageFake())
    assert coletor.product_ids is None


def test_semente_do_disco_traz_ids_de_verdade():
    semente = carregar_produtos_semente()
    assert semente
    assert all(isinstance(x, str) and x for x in semente)


def test_ids_da_sigl_pula_o_metadado():
    payload = [
        {"siglId": "abc", "title": "Todos os jogos"},
        {"id": "9AAA"},
        {"id": "9BBB"},
        {"naoTemId": True},
    ]
    assert _ids_da_sigl(payload) == ["9AAA", "9BBB"]


def test_ids_da_sigl_tolera_payload_invalido():
    assert _ids_da_sigl(None) == []
    assert _ids_da_sigl({}) == []
