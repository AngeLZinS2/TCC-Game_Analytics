"""Presenca em memoria (\"quem esta no site agora\") - o que alimenta
`online_agora` no painel admin.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import services.ml.telemetria_site as telemetria


def _limpar():
    with telemetria._lock:
        telemetria._ultimo_visto.clear()


def test_sem_ninguem_online_agora_e_zero():
    _limpar()
    assert telemetria.online_agora() == 0


def test_registrar_presenca_conta_visitante_unico():
    _limpar()
    telemetria.registrar_presenca("visitante-a")
    telemetria.registrar_presenca("visitante-b")
    telemetria.registrar_presenca("visitante-a")  # heartbeat de novo, nao duplica
    assert telemetria.online_agora() == 2


def test_visitante_fora_da_janela_nao_conta():
    _limpar()
    with telemetria._lock:
        telemetria._ultimo_visto["visitante-velho"] = datetime.now(
            timezone.utc
        ) - timedelta(minutes=10)
    assert telemetria.online_agora() == 0


def test_visitante_vazio_e_ignorado():
    _limpar()
    telemetria.registrar_presenca("")
    assert telemetria.online_agora() == 0
