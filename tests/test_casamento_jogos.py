"""Normalizacao de titulo pro cruzamento Xbox -> Steam do resumo por IA."""

from __future__ import annotations

from services.etl.casamento_jogos import normalizar_titulo


def test_remove_sufixo_de_plataforma_entre_parenteses():
    assert normalizar_titulo("Grand Theft Auto V Enhanced (PC)") == normalizar_titulo(
        "Grand Theft Auto V"
    )


def test_remove_palavra_de_edicao_sem_parenteses():
    assert normalizar_titulo("Red Dead Redemption 2: Special Edition") == normalizar_titulo(
        "Red Dead Redemption 2"
    )


def test_ignora_acento_e_maiuscula():
    assert normalizar_titulo("Elden Ring") == normalizar_titulo("ELDEN RING")


def test_remove_trademark():
    assert normalizar_titulo("Forza Horizon 5™") == normalizar_titulo("Forza Horizon 5")


def test_titulos_de_jogos_diferentes_nao_batem():
    assert normalizar_titulo("Grand Theft Auto V") != normalizar_titulo(
        "Grand Theft Auto: San Andreas"
    )
    assert normalizar_titulo("Red Dead Redemption") != normalizar_titulo(
        "Red Dead Redemption 2"
    )


def test_vazio():
    assert normalizar_titulo("") == ""
    assert normalizar_titulo(None) == ""  # type: ignore[arg-type]
