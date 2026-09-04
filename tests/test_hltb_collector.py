"""Teste da normalizacao de nome usada na busca do HLTB.

So a parte pura (sem rede, sem banco): simbolos de marca colados numa palavra
("Legends™") fazem a busca inteira do HLTB voltar vazia - `_normalizar_busca`
e o que evita isso.
"""

from __future__ import annotations

from collectors.hltb_collector import _normalizar_busca


def test_remove_simbolos_de_marca_colados_na_palavra():
    assert _normalizar_busca("Apex Legends™") == "Apex Legends"
    assert _normalizar_busca("Rocket League®") == "Rocket League"
    assert _normalizar_busca("Copyright© Game") == "Copyright Game"


def test_colapsa_espaco_que_sobra_da_remocao():
    assert _normalizar_busca("A™ B") == "A B"


def test_nome_sem_simbolo_fica_igual():
    assert _normalizar_busca("Hades") == "Hades"


def test_normaliza_espacos_extras_tambem_sem_simbolo():
    assert _normalizar_busca("  Dota   2  ") == "Dota 2"
