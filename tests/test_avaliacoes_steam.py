"""Testes do parser de avaliacoes da Steam - a base do modelo de sentimento.

O contrato que importa aqui e o do ROTULO: `voted_up` e o polegar do autor, e e
com ele que o classificador e treinado. Se a Steam renomear esse campo, o parser
tem que devolver lista vazia em vez de silenciosamente rotular tudo como
negativo - o que produziria um modelo treinado em ruido sem nenhum erro visivel.
"""

from __future__ import annotations

from datetime import timezone

from etl.transform_steam import parse_avaliacoes

APP_ID = 570


def _payload(*reviews: dict) -> dict:
    return {"success": 1, "query_summary": {"num_reviews": len(reviews)}, "reviews": list(reviews)}


def _review(**campos) -> dict:
    base = {
        "recommendationid": "1",
        "review": "um texto de avaliacao com tamanho suficiente",
        "voted_up": True,
        "language": "english",
        "timestamp_created": 1_756_000_000,
        "votes_up": 3,
        "votes_funny": 1,
        "steam_purchase": True,
        "received_for_free": False,
        "written_during_early_access": False,
        "author": {"playtime_forever": 1200},
    }
    base.update(campos)
    return base


def test_campos_mapeados_da_avaliacao():
    (avaliacao,) = parse_avaliacoes(_payload(_review()), APP_ID)

    assert avaliacao.app_id == APP_ID
    assert avaliacao.id_externo == "1"
    assert avaliacao.idioma == "english"
    assert avaliacao.recomendado is True
    assert avaliacao.minutos_jogados == 1200
    assert avaliacao.votos_uteis == 3
    assert avaliacao.votos_engracados == 1
    assert avaliacao.compra_na_steam is True
    assert avaliacao.criada_em is not None
    assert avaliacao.criada_em.tzinfo == timezone.utc


def test_polegar_para_baixo_vira_rotulo_negativo():
    (avaliacao,) = parse_avaliacoes(_payload(_review(voted_up=False)), APP_ID)
    assert avaliacao.recomendado is False


def test_rotulo_ausente_ou_nao_booleano_descarta_a_linha():
    """Sem rotulo nao ha o que treinar - e chutar um seria pior que descartar."""
    assert parse_avaliacoes(_payload(_review(voted_up=None)), APP_ID) == []
    assert parse_avaliacoes(_payload(_review(voted_up="true")), APP_ID) == []
    sem_campo = _review()
    del sem_campo["voted_up"]
    assert parse_avaliacoes(_payload(sem_campo), APP_ID) == []


def test_avaliacao_sem_texto_nao_entra():
    """Da para votar sem escrever; uma linha vazia nao ensina nada ao modelo."""
    assert parse_avaliacoes(_payload(_review(review="")), APP_ID) == []
    assert parse_avaliacoes(_payload(_review(review="   ")), APP_ID) == []


def test_texto_e_normalizado_nas_pontas():
    (avaliacao,) = parse_avaliacoes(_payload(_review(review="  bom jogo  ")), APP_ID)
    assert avaliacao.texto == "bom jogo"


def test_sem_recommendationid_descarta():
    """Sem chave natural o upsert nao teria como ser idempotente."""
    sem_id = _review()
    del sem_id["recommendationid"]
    assert parse_avaliacoes(_payload(sem_id), APP_ID) == []


def test_autor_ausente_nao_levanta():
    sem_autor = _review()
    del sem_autor["author"]
    (avaliacao,) = parse_avaliacoes(_payload(sem_autor), APP_ID)
    assert avaliacao.minutos_jogados is None


def test_payload_de_resumo_puro_nao_gera_avaliacao():
    """E o formato antigo, com `num_per_page=0`: existe resumo e nao ha lista."""
    assert parse_avaliacoes({"success": 1, "query_summary": {}}, APP_ID) == []
    assert parse_avaliacoes({"success": 1, "reviews": []}, APP_ID) == []


def test_payload_invalido_nao_levanta():
    assert parse_avaliacoes(None, APP_ID) == []
    assert parse_avaliacoes({"success": 2, "reviews": [_review()]}, APP_ID) == []
    assert parse_avaliacoes({"success": 1, "reviews": ["nao e dicionario"]}, APP_ID) == []


def test_varias_avaliacoes_preservam_a_ordem_da_pagina():
    payload = _payload(
        _review(recommendationid="10"),
        _review(recommendationid="11", voted_up=False),
        _review(recommendationid="12"),
    )
    assert [a.id_externo for a in parse_avaliacoes(payload, APP_ID)] == ["10", "11", "12"]
