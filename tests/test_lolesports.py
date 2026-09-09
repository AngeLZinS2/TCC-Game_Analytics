"""Parser do detalhe ao vivo de LoL (API oficial da LoL Esports).

Sem rede: um `getEventDetails` e um frame de `livestats/window` sintéticos,
minúsculos mas fiéis ao formato, exercitam o `_montar_detalhe` — que lado é o
nosso time A, o placar de série, o scoreboard por jogo e o status.
"""

from __future__ import annotations

from collectors.lolesports import _montar_detalhe, _streams_do_evento

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
