"""Telemetria em memoria das chamadas ao OpenRouter - o que alimenta o painel
"Status da API" do Assistente de Dados.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import services.ml.telemetria_assistente as telemetria


def _limpar():
    with telemetria._lock:
        telemetria._historico.clear()


def test_sem_chamadas_resumo_vazio():
    _limpar()
    r = telemetria.resumo()
    assert r["total_recente"] == 0
    assert r["taxa_sucesso"] is None
    assert r["rate_limited_recente"] is False
    assert r["ultima_chamada_em"] is None
    assert r["chamadas"] == []


def test_registrar_sucesso_e_falha_conta_taxa():
    _limpar()
    telemetria.registrar(sucesso=True, status_http=200, erro=None, duracao_ms=800)
    telemetria.registrar(
        sucesso=False, status_http=500, erro="deu ruim", duracao_ms=100
    )
    r = telemetria.resumo()
    assert r["total_recente"] == 2
    assert r["sucessos_recente"] == 1
    assert r["taxa_sucesso"] == 0.5
    assert r["ultima_chamada_sucesso"] is False
    assert r["ultima_chamada_erro"] == "deu ruim"


def test_429_marca_rate_limited():
    _limpar()
    telemetria.registrar(
        sucesso=False,
        status_http=429,
        erro="temporarily rate-limited upstream",
        duracao_ms=300,
    )
    r = telemetria.resumo()
    assert r["rate_limited_recente"] is True
    assert r["chamadas"][0]["rate_limited"] is True
    assert r["chamadas"][0]["status_http"] == 429


def test_429_antigo_fora_da_janela_nao_conta():
    _limpar()
    velha = telemetria._Chamada(
        quando=datetime.now(timezone.utc) - timedelta(minutes=30),
        sucesso=False,
        status_http=429,
        erro="rate limit",
        duracao_ms=200,
    )
    with telemetria._lock:
        telemetria._historico.append(velha)
    r = telemetria.resumo()
    assert r["rate_limited_recente"] is False


def test_chamadas_mais_recente_primeiro():
    _limpar()
    telemetria.registrar(sucesso=True, status_http=200, erro=None, duracao_ms=1)
    telemetria.registrar(sucesso=False, status_http=429, erro="x", duracao_ms=2)
    r = telemetria.resumo()
    assert r["chamadas"][0]["status_http"] == 429
    assert r["chamadas"][1]["status_http"] == 200


def test_historico_tem_teto():
    _limpar()
    for _ in range(telemetria.MAX_HISTORICO + 10):
        telemetria.registrar(sucesso=True, status_http=200, erro=None, duracao_ms=1)
    assert len(telemetria._historico) == telemetria.MAX_HISTORICO


def test_erro_longo_e_truncado():
    _limpar()
    telemetria.registrar(
        sucesso=False, status_http=500, erro="x" * 500, duracao_ms=1
    )
    r = telemetria.resumo()
    assert len(r["chamadas"][0]["erro"]) == 200
