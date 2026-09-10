"""Parser do detalhe ao vivo de LoL (API oficial da LoL Esports).

Sem rede: um `getEventDetails` e um frame de `livestats/window` sintéticos,
minúsculos mas fiéis ao formato, exercitam o `_montar_detalhe` — que lado é o
nosso time A, o placar de série, o scoreboard por jogo e o status.
"""

from __future__ import annotations

from services.collectors.lolesports import (
    _linhas_fato,
    _montar_detalhe,
    _streams_do_evento,
)

_EVENTO = {
    "streams": [
        {"provider": "twitch", "parameter": "lck", "locale": "en-US"},
        {"provider": "youtube", "parameter": "abc123", "locale": "ko-KR"},
    ],
    "match": {
        "teams": [
            {"id": "T_A", "name": "Gen.G", "code": "GEN", "result": {"gameWins": 2}},
            {"id": "T_B", "name": "T1", "code": "T1", "result": {"gameWins": 1}},
        ],
        "games": [
            {
                "number": 1,
                "id": "G1",
                "state": "completed",
                "teams": [
                    {"id": "T_A", "side": "blue"},
                    {"id": "T_B", "side": "red"},
                ],
            },
            {
                "number": 2,
                "id": "G2",
                "state": "inProgress",
                "teams": [
                    {"id": "T_A", "side": "red"},
                    {"id": "T_B", "side": "blue"},
                ],
            },
            {"number": 3, "id": "G3", "state": "unstarted", "teams": []},
        ],
    },
}


def _janela(lado_a: str, kills_a: int, kills_b: int, gstate: str) -> dict:
    lado_b = "red" if lado_a == "blue" else "blue"
    return {
        "gameMetadata": {
            f"{lado_a}TeamMetadata": {
                "participantMetadata": [
                    {
                        "participantId": 1,
                        "summonerName": "GEN Kiin",
                        "championId": "Ksante",
                        "role": "top",
                    }
                ]
            },
            f"{lado_b}TeamMetadata": {
                "participantMetadata": [
                    {
                        "participantId": 6,
                        "summonerName": "T1 Zeus",
                        "championId": "Jax",
                        "role": "top",
                    }
                ]
            },
        },
        "frames": [
            {
                "gameState": gstate,
                f"{lado_a}Team": {
                    "totalKills": kills_a,
                    "totalGold": 50000,
                    "towers": 8,
                    "barons": 1,
                    "dragons": ["fire", "ocean"],
                    "participants": [
                        {
                            "participantId": 1,
                            "kills": 3,
                            "deaths": 1,
                            "assists": 7,
                            "creepScore": 240,
                            "totalGold": 12000,
                            "level": 16,
                        }
                    ],
                },
                f"{lado_b}Team": {
                    "totalKills": kills_b,
                    "totalGold": 44000,
                    "towers": 3,
                    "barons": 0,
                    "dragons": ["cloud"],
                    "participants": [
                        {
                            "participantId": 6,
                            "kills": 1,
                            "deaths": 3,
                            "assists": 2,
                            "creepScore": 210,
                            "totalGold": 10000,
                            "level": 15,
                        }
                    ],
                },
            }
        ],
    }


def test_monta_placar_status_e_scoreboard_do_lado_certo():
    janelas = {
        "G1": _janela("blue", 18, 9, "finished"),  # A é blue no jogo 1
        "G2": _janela("red", 5, 4, "in_game"),  # A é red no jogo 2
    }
    d = _montar_detalhe(_EVENTO, janelas, "Gen.G")

    assert d["fonte"] == "lolesports"
    assert d["status"] == "ao_vivo"  # jogo 2 in_game
    assert d["placar_serie"] == {"a": 2, "b": 1}

    j1, j2 = d["mapas"]
    assert j1["nome"] == "Jogo 1"
    # jogo 1: A venceu (18 x 9)
    assert j1["placar_a"] == 18 and j1["placar_b"] == 9
    assert j1["objetivos_a"]["torres"] == 8 and j1["objetivos_a"]["dragoes"] == 2
    p_a = j1["jogadores"][0]
    assert p_a["time"] == "Gen.G" and p_a["campeao"] == "Ksante"
    assert (p_a["k"], p_a["d"], p_a["a"], p_a["cs"]) == (3, 1, 7, 240)

    # jogo 2 (A é red): o placar_a tem que seguir sendo o do Gen.G
    assert j2["placar_a"] == 5 and j2["placar_b"] == 4

    res = {r["posicao"]: r for r in d["mapas_resultado"]}
    assert res[1]["vitoria_a"] is True and res[1]["status"] == "encerrado"
    assert res[3]["status"] == "em_breve"


def test_status_encerrada_quando_todos_os_jogos_fecharam():
    evento = {
        "match": {
            "teams": [
                {"id": "T_A", "name": "Gen.G", "result": {"gameWins": 2}},
                {"id": "T_B", "name": "T1", "result": {"gameWins": 0}},
            ],
            "games": [
                {"number": 1, "id": "G1", "state": "completed",
                 "teams": [{"id": "T_A", "side": "blue"}, {"id": "T_B", "side": "red"}]},
                {"number": 2, "id": "G2", "state": "completed",
                 "teams": [{"id": "T_A", "side": "blue"}, {"id": "T_B", "side": "red"}]},
                {"number": 3, "id": "G3", "state": "unneeded", "teams": []},
            ],
        }
    }
    janelas = {
        "G1": _janela("blue", 20, 5, "finished"),
        "G2": _janela("blue", 15, 8, "finished"),
    }
    d = _montar_detalhe(evento, janelas, "Gen.G")
    assert d["status"] == "encerrada"
    assert len(d["mapas"]) == 2


_EVENTO_BACKFILL = {
    "match": {
        "teams": [
            {"id": "111692118851466302", "name": "Karmine Corp", "code": "KC",
             "result": {"gameWins": 1}},
            {"id": "98767991926151025", "name": "G2 Esports", "code": "G2",
             "result": {"gameWins": 3}},
        ],
        "games": [
            {"number": 1, "id": "115548681803406304", "state": "completed",
             "teams": [
                 {"id": "111692118851466302", "side": "blue"},
                 {"id": "98767991926151025", "side": "red"},
             ]},
        ],
    }
}


def test_frame_final_do_feed_vira_scoreboard_por_jogador(carregar_fixture):
    """O frame final que o backfill puxa do `livestats` (fixture real) sai como
    `mapas[].jogadores` com K/D/A e o `id_externo` do jogador (esportsPlayerId)."""
    janela = carregar_fixture("lolesports_window_final")
    d = _montar_detalhe(
        _EVENTO_BACKFILL,
        {"115548681803406304": janela},
        "Karmine Corp",
        "G2 Esports",
    )

    assert d["placar_serie"] == {"a": 1, "b": 3}
    (mapa,) = d["mapas"]
    assert mapa["posicao"] == 1
    assert mapa["time_a"] == "Karmine Corp"

    canna = mapa["jogadores"][0]
    assert canna["id_externo"] == "103495716771322725"
    assert canna["time"] == "Karmine Corp"
    assert (canna["k"], canna["d"], canna["a"]) == (1, 2, 4)
    assert canna["cs"] == 304 and canna["ouro"] == 12642
    assert all(j.get("id_externo") for j in mapa["jogadores"])


def test_linhas_fato_resolve_vitoria_pelo_mapas_resultado():
    detalhe = {
        "mapas_resultado": [
            {"posicao": 1, "status": "encerrado", "vitoria_a": True},
            {"posicao": 2, "status": "ao_vivo", "vitoria_a": None},
        ],
        "mapas": [
            {
                "posicao": 1,
                "time_a": "Karmine Corp",
                "jogadores": [
                    {"id_externo": "1", "time": "Karmine Corp", "campeao": "Jayce",
                     "k": 3, "d": 1, "a": 5, "cs": 250, "ouro": 13000, "nivel": 16},
                    {"id_externo": "2", "time": "G2 Esports", "campeao": "Gnar",
                     "k": 1, "d": 4, "a": 2, "cs": 210, "ouro": 9000, "nivel": 14},
                ],
            },
            {
                "posicao": 2,
                "time_a": "Karmine Corp",
                "jogadores": [
                    {"id_externo": "1", "time": "Karmine Corp", "campeao": "Ksante",
                     "k": 0, "d": 0, "a": 0, "cs": 20, "ouro": 2500, "nivel": 4},
                ],
            },
        ],
    }

    linhas = _linhas_fato(detalhe)
    # jogo 2 ainda nao encerrou -> fora
    assert {l["jogo_numero"] for l in linhas} == {1}
    por_ext = {l["id_externo"]: l for l in linhas}
    assert por_ext["1"]["vitoria"] is True and por_ext["1"]["campeao"] == "Jayce"
    assert por_ext["2"]["vitoria"] is False
    assert por_ext["1"]["k"] == 3 and por_ext["2"]["d"] == 4


def test_streams_do_evento_monta_url_por_provedor():
    s = _streams_do_evento(_EVENTO)
    assert s[0] == {
        "url": "https://www.twitch.tv/lck",
        "nome": "lck",
        "plataforma": "twitch",
        "lingua": "EN",
        "principal": True,
    }
    assert s[1]["url"] == "https://www.youtube.com/watch?v=abc123"
    assert s[1]["lingua"] == "KO" and s[1]["principal"] is False
