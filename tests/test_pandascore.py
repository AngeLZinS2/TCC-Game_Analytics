"""Parser da PandaScore — a parte pura (sem rede, sem banco).

O que importa: uma partida decidida vira confronto com placar e vencedor; uma
por vir vira confronto sem resultado; TBD e cancelada saem fora; e o rótulo do
torneio junta liga + etapa do jeito que a tela mostra.
"""

from __future__ import annotations

from services.collectors.pandascore import (
    PandaScoreCollector,
    _canal_de_stream,
    _instante,
    _para_confronto,
    _rotulo_torneio,
    _streams_da_partida,
)


def _partida(**over):
    base = {
        "id": 1677001,
        "status": "finished",
        "begin_at": "2026-09-06T14:03:55Z",
        "scheduled_at": "2026-09-06T14:00:00Z",
        "number_of_games": 3,
        "winner_id": 100,
        "opponents": [
            {"opponent": {"id": 100, "name": "Team Spirit"}},
            {"opponent": {"id": 200, "name": "MOUZ"}},
        ],
        "results": [{"team_id": 100, "score": 3}, {"team_id": 200, "score": 1}],
        "league": {"name": "BLAST Open"},
        "tournament": {"name": "Playoffs"},
        "serie": {"full_name": "Fall 2026"},
    }
    base.update(over)
    return base


def test_decidida_traz_placar_e_vencedor():
    c = _para_confronto(_partida())
    assert c is not None
    assert (c.equipe_a_nome, c.equipe_b_nome) == ("Team Spirit", "MOUZ")
    assert (c.placar_a, c.placar_b) == (3, 1)
    assert c.vitoria_a is True
    assert c.formato == "Bo3"
    assert c.id_externo == "pandascore:1677001"
    assert c.torneio == "BLAST Open — Playoffs"


def test_escudo_e_sigla_vem_do_opponent():
    c = _para_confronto(
        _partida(
            opponents=[
                {"opponent": {"id": 100, "name": "Team Spirit", "image_url": "http://x/ts.png", "acronym": "TS"}},
                {"opponent": {"id": 200, "name": "MOUZ", "image_url": None, "acronym": ""}},
            ]
        )
    )
    assert c.equipe_a_logo == "http://x/ts.png"
    assert c.equipe_a_tag == "TS"
    assert c.equipe_b_logo is None
    assert c.equipe_b_tag is None


def test_vencedor_do_lado_b():
    c = _para_confronto(_partida(winner_id=200))
    assert c.vitoria_a is False


def test_por_vir_nao_tem_placar_nem_vitoria():
    c = _para_confronto(
        _partida(
            status="not_started",
            winner_id=None,
            begin_at=None,
            results=[{"team_id": 100, "score": 0}, {"team_id": 200, "score": 0}],
        )
    )
    assert c is not None
    assert c.placar_a is None and c.placar_b is None
    assert c.vitoria_a is None
    # cai no scheduled_at quando begin_at é nulo
    assert c.inicio_previsto.year == 2026


def test_tbd_e_descartada():
    assert _para_confronto(_partida(opponents=[{"opponent": {"id": 100, "name": "Spirit"}}])) is None
    assert _para_confronto(_partida(opponents=[])) is None


def test_cancelada_e_descartada():
    assert _para_confronto(_partida(status="canceled")) is None


def test_tier_fora_do_filtro_e_descartada():
    p = _partida(tournament={"name": "Open Qualifier", "tier": "d"})
    assert _para_confronto(p, {"s", "a", "b", "c"}) is None
    assert _para_confronto(p, None) is not None  # sem filtro, entra
    assert _para_confronto(p, {"d"}) is not None


def test_sem_horario_e_descartada():
    assert (
        _para_confronto(
            _partida(begin_at=None, scheduled_at=None, original_scheduled_at=None)
        )
        is None
    )


def test_rotulo_so_com_serie_quando_falta_liga_e_etapa():
    p = {"league": {"name": ""}, "tournament": {"name": ""}, "serie": {"full_name": "Season 12"}}
    assert _rotulo_torneio(p) == "Season 12"


def test_canal_de_stream_reconhece_plataforma_e_nome():
    assert _canal_de_stream("https://www.twitch.tv/PGL") == ("PGL", "twitch")
    assert _canal_de_stream("https://kick.com/fissure-cs") == ("fissure-cs", "kick")
    nome, plataforma = _canal_de_stream("https://exemplo.tv/live")
    assert plataforma == "other" and nome == "live"


def test_streams_da_partida_ordena_oficial_e_dedup():
    canais = _streams_da_partida(
        {
            "streams_list": [
                {"raw_url": "https://kick.com/fissure-a", "language": "en", "main": False},
                {"raw_url": "https://www.twitch.tv/PGL", "language": "en", "official": True},
                {"raw_url": "https://www.twitch.tv/PGL", "language": "en"},  # repetido
            ],
            "official_stream_url": None,
        }
    )
    assert [c["url"] for c in canais] == [
        "https://www.twitch.tv/PGL",
        "https://kick.com/fissure-a",
    ]
    assert canais[0]["principal"] is True and canais[0]["lingua"] == "EN"


def test_por_vir_carrega_os_canais_de_transmissao():
    c = _para_confronto(
        _partida(
            status="not_started",
            winner_id=None,
            streams_list=[{"raw_url": "https://www.twitch.tv/PGL", "official": True}],
        )
    )
    assert c is not None and c.streams and c.streams[0]["plataforma"] == "twitch"


def test_instante_normaliza_para_utc():
    dt = _instante(None, "", "2026-09-06T14:00:00Z")
    assert dt is not None and dt.tzinfo is not None


def test_jogo_desconhecido_recusa():
    import pytest

    with pytest.raises(ValueError):
        PandaScoreCollector(raw_storage=object(), jogo="pong")
