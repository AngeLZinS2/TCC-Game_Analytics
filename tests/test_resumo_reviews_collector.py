"""Coleta do resumo de avaliacoes por IA - a parte que da pra testar sem rede
nem banco: erro sem chave, `app_ids` guardado, montagem do prompt.
"""

from __future__ import annotations

import pytest

from services.collectors.resumo_reviews import (
    ResumoReviewsCollector,
    SemChaveGroqError,
    _prompt_avaliacoes,
)


class _StorageFake:
    def salvar_muitos(self, registros):  # noqa: D401 - stub
        return len(list(registros))


def test_app_ids_fica_guardado_como_lista():
    coletor = ResumoReviewsCollector(raw_storage=_StorageFake(), app_ids=(10, 20))
    assert coletor.app_ids == [10, 20]


def test_sem_app_ids_o_alvo_e_o_catalogo_inteiro():
    coletor = ResumoReviewsCollector(raw_storage=_StorageFake())
    assert coletor.app_ids is None


def test_collect_sem_chave_recusa():
    coletor = ResumoReviewsCollector(raw_storage=_StorageFake(), app_ids=[730])
    coletor.settings = coletor.settings.model_copy(update={"groq_api_key": None})
    with pytest.raises(SemChaveGroqError):
        coletor.collect()


def test_prompt_avaliacoes_rotula_recomendacao():
    prompt = _prompt_avaliacoes([("Otimo jogo, recomendo muito", True), ("Cheio de bugs", False)])
    linhas = prompt.splitlines()
    assert linhas[0].startswith("[RECOMENDA]")
    assert linhas[1].startswith("[NAO RECOMENDA]")


def test_prompt_avaliacoes_apara_texto_longo():
    texto = "a" * 500
    prompt = _prompt_avaliacoes([(texto, True)])
    # "[RECOMENDA] " (12 chars) + ate 320 chars do texto.
    assert len(prompt) <= 12 + 320
