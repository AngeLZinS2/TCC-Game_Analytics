"""Testes de contrato da API.

Diferente dos testes de transform, estes precisam de um Postgres de pe: as
consultas usam recursos que so existem no Postgres (DISTINCT ON, unnest,
percentile_cont), entao trocar por SQLite testaria outro SQL que nao o que
roda em producao. Sem banco, o modulo inteiro e pulado.

O que se verifica aqui e o *contrato* com o dashboard: as chaves que cada tela
le. Um campo renomeado no backend quebra a tela em silencio - o teste faz esse
erro aparecer antes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app
from db.session import get_engine


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    try:
        with get_engine().connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - qualquer falha de conexao serve
        pytest.skip(f"Postgres indisponivel: {type(exc).__name__}")
    return TestClient(app)


def test_health_confirma_o_banco(cliente: TestClient) -> None:
    corpo = cliente.get("/health").json()
    assert corpo["status"] == "ok"
    assert corpo["banco"] is True


def test_visao_geral_traz_os_dois_dominios(cliente: TestClient) -> None:
    resposta = cliente.get("/api/visao-geral")
    assert resposta.status_code == 200

    corpo = resposta.json()
    for campo in ("jogos_steam", "snapshots_steam", "partidas", "jogadores"):
        assert isinstance(corpo[campo], int)
    assert isinstance(corpo["coletas"], list)


def test_lista_de_jogos_vem_com_o_snapshot_achatado(cliente: TestClient) -> None:
    corpo = cliente.get("/api/steam/jogos", params={"limite": 5}).json()
    assert isinstance(corpo, list)
    if not corpo:
        pytest.skip("catalogo Steam vazio")

    jogo = corpo[0]
    # A dimensao e o fato chegam na mesma linha - e disso que a tabela vive.
    for campo in ("app_id", "nome", "generos", "jogadores_simultaneos"):
        assert campo in jogo
    assert isinstance(jogo["generos"], list)


def test_ordenacao_por_jogadores_e_decrescente(cliente: TestClient) -> None:
    corpo = cliente.get(
        "/api/steam/jogos", params={"ordenar_por": "jogadores", "limite": 10}
    ).json()
    valores = [j["jogadores_simultaneos"] for j in corpo if j["jogadores_simultaneos"]]
    assert valores == sorted(valores, reverse=True)


def test_jogo_inexistente_da_404(cliente: TestClient) -> None:
    assert cliente.get("/api/steam/jogos/1").status_code == 404


def test_jogo_desconhecido_da_404(cliente: TestClient) -> None:
    assert cliente.get("/api/partidas/resumo", params={"jogo": "xadrez"}).status_code == 404


def test_resumo_de_partidas_tem_o_histograma(cliente: TestClient) -> None:
    corpo = cliente.get("/api/partidas/resumo").json()
    assert isinstance(corpo["partidas"], int)
    assert isinstance(corpo["distribuicao_duracao"], list)
    for faixa in corpo["distribuicao_duracao"]:
        assert {"rotulo", "minuto_inicial", "partidas"} <= faixa.keys()


def test_winrate_por_personagem_fica_entre_0_e_100(cliente: TestClient) -> None:
    corpo = cliente.get(
        "/api/partidas/personagens", params={"min_partidas": 1, "limite": 50}
    ).json()
    if not corpo:
        pytest.skip("nenhuma partida coletada")

    for heroi in corpo:
        assert 0.0 <= heroi["winrate"] <= 100.0
        assert heroi["vitorias"] <= heroi["partidas"]


def test_min_partidas_corta_a_cauda(cliente: TestClient) -> None:
    """O corte tem que reduzir (ou manter) o conjunto, nunca aumenta-lo."""
    solto = cliente.get("/api/partidas/personagens", params={"min_partidas": 1}).json()
    apertado = cliente.get("/api/partidas/personagens", params={"min_partidas": 15}).json()
    assert len(apertado) <= len(solto)
    for heroi in apertado:
        assert heroi["partidas"] >= 15


def test_detalhe_da_partida_traz_as_duas_equipes(cliente: TestClient) -> None:
    partidas = cliente.get("/api/partidas", params={"limite": 1}).json()
    if not partidas:
        pytest.skip("nenhuma partida coletada")

    corpo = cliente.get(f"/api/partidas/{partidas[0]['id_partida']}").json()
    equipes = {jogador["equipe"] for jogador in corpo["jogadores"]}
    assert equipes == {"radiant", "dire"}
    # O vencedor sai do fato; se ha vitorioso, ele e uma das duas equipes.
    assert corpo["partida"]["vencedor"] in {"radiant", "dire", None}
