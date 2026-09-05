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


@pytest.mark.parametrize("jogo", ["dota2", "valorant", "leagueoflegends"])
def test_personagens_honram_ordenar_por(cliente: TestClient, jogo: str) -> None:
    """A lista tem que voltar na ordem pedida, nos DOIS caminhos.

    O caminho agregado (Valorant, LoL) ignorava `ordenar_por` e devolvia sempre
    por numero de partidas. A tela de Herois assume a lista ja ordenada por
    winrate e mostrava "maior winrate: Kai'Sa 49,4%" (a mais jogada) contra uma
    tabela liderada por outro campeao a 52,7% - a contradicao que o usuario
    achou.
    """
    por_wr = cliente.get(
        "/api/partidas/personagens",
        params={"jogo": jogo, "ordenar_por": "winrate", "limite": 200},
    ).json()
    if len(por_wr) < 2:
        pytest.skip(f"{jogo} sem personagem suficiente")

    winrates = [p["winrate"] for p in por_wr]
    assert winrates == sorted(winrates, reverse=True)

    por_vol = cliente.get(
        "/api/partidas/personagens",
        params={"jogo": jogo, "ordenar_por": "partidas", "limite": 200},
    ).json()
    partidas = [p["partidas"] for p in por_vol]
    assert partidas == sorted(partidas, reverse=True)
    # E os dois recortes contem o mesmo conjunto - so a ordem muda.
    assert {p["id_personagem"] for p in por_wr} == {p["id_personagem"] for p in por_vol}


def test_detalhe_da_partida_traz_as_duas_equipes(cliente: TestClient) -> None:
    partidas = cliente.get("/api/partidas", params={"limite": 1}).json()
    if not partidas:
        pytest.skip("nenhuma partida coletada")

    corpo = cliente.get(f"/api/partidas/{partidas[0]['id_partida']}").json()
    equipes = {jogador["equipe"] for jogador in corpo["jogadores"]}
    assert equipes == {"radiant", "dire"}
    # O vencedor sai do fato; se ha vitorioso, ele e uma das duas equipes.
    assert corpo["partida"]["vencedor"] in {"radiant", "dire", None}


def test_resumo_de_confrontos_responde_no_grao_do_calendario(
    cliente: TestClient,
) -> None:
    """A tela de Partidas lia so `dim_partida`, que existe apenas para Dota 2.

    Os outros treze esportes abriam a pagina inteira zerada - zero partidas,
    zero jogadores, duracao nula, graficos vazios - tendo confronto, equipe,
    torneio e placar no banco. Este endpoint responde no grao que eles tem: a
    serie, nao a partida dentro dela.
    """
    resposta = cliente.get("/api/partidas/resumo-confrontos", params={"jogo": "valorant"})

    assert resposta.status_code == 200
    corpo = resposta.json()

    # O que a fonte publica.
    assert corpo["decididos"] >= 0
    assert corpo["equipes"] >= 0
    assert set(corpo) >= {
        "decididos", "futuros", "equipes", "torneios",
        "vitorias_lado_a", "winrate_lado_a", "por_formato", "por_dia",
    }
    # O que ela NAO publica nao aparece disfarcado de zero: nao ha campo de
    # duracao nem de jogador neste resumo, e isso e a diferenca entre "nao
    # temos" e "e zero".
    assert "duracao_media_segundos" not in corpo
    assert "jogadores_distintos" not in corpo


def test_resumo_de_confrontos_de_jogo_inexistente_nao_estoura(
    cliente: TestClient,
) -> None:
    """Jogo sem linha em `agenda_partida` devolve zeros, nao 500.

    A tela pede este resumo para QUALQUER jogo do seletor, inclusive um
    recem-cadastrado sem coleta - e um estado normal, nao um erro.
    """
    resposta = cliente.get(
        "/api/partidas/resumo-confrontos", params={"jogo": "jogo-que-nao-existe"}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["decididos"] == 0
    assert corpo["winrate_lado_a"] is None
    assert corpo["por_formato"] == []


def test_perfil_declara_o_vocabulario_de_cada_esporte(cliente: TestClient) -> None:
    """Um MOBA e um tatico nao compartilham estatistica.

    A tela desenhava "KDA / GPM / XPM" fixo - o vocabulario do Dota. Pedir ouro
    por minuto de um agente de Valorant e pedir um numero que o jogo nao produz,
    e a coluna vazia sugeriria dado faltando quando ele nem existe naquele
    esporte.
    """
    dota = cliente.get("/api/partidas/perfil", params={"jogo": "dota2"}).json()
    valorant = cliente.get("/api/partidas/perfil", params={"jogo": "valorant"}).json()

    assert dota["substantivo_plural"] == "heróis"
    assert valorant["substantivo_plural"] == "agentes"

    rotulos_dota = {m["rotulo"] for m in dota["metricas"]}
    rotulos_valorant = {m["rotulo"] for m in valorant["metricas"]}
    assert {"GPM", "XPM"} <= rotulos_dota
    assert {"HS%", "ADR", "ACS"} <= rotulos_valorant
    # Ouro por minuto nao existe num tatico, e headshot nao existe num MOBA.
    assert "GPM" not in rotulos_valorant
    assert "HS%" not in rotulos_dota


def test_perfil_sem_fonte_nao_inventa_metrica(cliente: TestClient) -> None:
    """Counter-Strike mede HS% e ADR no mundo real - nos nao os coletamos.

    Um perfil vazio faz a tela dizer o que falta. Herdar as metricas de outro
    esporte renderizaria colunas que nunca teriam valor, e uma coluna sempre
    vazia se le como "o dado sumiu", nao como "esta fonte nao existe aqui".
    """
    corpo = cliente.get(
        "/api/partidas/perfil", params={"jogo": "counterstrike"}
    ).json()

    assert corpo["metricas"] == []
    assert corpo["fonte"] == ""
    # E o gate da ordenacao acompanha: sem reagregacao no banco, a pilula de
    # ordenar nao reordena nada.
    assert corpo["ordenavel"] is False


def test_perfil_de_jogo_desconhecido_cai_num_padrao_neutro(
    cliente: TestClient,
) -> None:
    """Nada de assumir MOBA: o padrao nao tem metrica nenhuma."""
    corpo = cliente.get("/api/partidas/perfil", params={"jogo": "xadrez-3d"}).json()

    assert corpo["substantivo_plural"] == "personagens"
    assert corpo["metricas"] == []


def test_icone_do_personagem_sai_da_cdn_de_cada_jogo() -> None:
    """A tabela mostrava quadrado cinza com a inicial para agente e campeao: o
    componente so sabia derivar o caminho da CDN da Valve do `npc_dota_hero_*`.
    Cada jogo tem a sua."""
    from api.routers.dota import _icone_personagem

    assert _icone_personagem(
        "dota2", "npc_dota_hero_razor", None
    ) == (
        "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/"
        "heroes/icons/razor.png"
    )
    assert _icone_personagem("leagueoflegends", "MonkeyKing", None) == (
        "https://cdn.communitydragon.org/latest/champion/MonkeyKing/square"
    )
    assert (
        _icone_personagem("valorant", "Deadeye", {"icone": "http://x/chamber.png"})
        == "http://x/chamber.png"
    )
    # Sem base para derivar -> `None`, e a tela cai no quadrado com a inicial.
    assert _icone_personagem("dota2", None, None) is None
    assert _icone_personagem("leagueoflegends", None, None) is None
    assert _icone_personagem("valorant", "Deadeye", None) is None


@pytest.mark.parametrize("jogo", ["dota2", "leagueoflegends", "valorant"])
def test_lista_de_personagens_traz_icone(cliente: TestClient, jogo: str) -> None:
    lista = cliente.get(
        "/api/partidas/personagens", params={"jogo": jogo, "limite": 5}
    ).json()
    if not lista:
        pytest.skip(f"{jogo} sem personagem")
    for p in lista:
        assert "icone" in p
        if p["icone"] is not None:
            assert p["icone"].startswith("https://")


def test_detalhe_de_personagem_inexistente_e_404(cliente: TestClient) -> None:
    assert cliente.get("/api/partidas/personagens/99999999").status_code == 404


def test_detalhe_de_personagem_junta_estatico_e_numeros(cliente: TestClient) -> None:
    """A ficha completa: quem e (da API do jogo) + como vai (do OP.GG).

    O que uma fonte nao der fica nulo, nao vira zero - por isso os asserts sao
    de forma, nao de valor: o teste roda contra o banco de dev, que pode ter ou
    nao ter cada fonte coletada.
    """
    lista = cliente.get(
        "/api/partidas/personagens", params={"jogo": "valorant", "limite": 1}
    ).json()
    if not lista:
        pytest.skip("nenhum agente de valorant coletado")

    corpo = cliente.get(
        f"/api/partidas/personagens/{lista[0]['id_personagem']}"
    ).json()

    assert corpo["jogo"] == "valorant"
    assert corpo["nome"] == lista[0]["nome"]
    # O perfil vem junto - a tela usa as mesmas colunas da lista.
    assert {"HS%", "ADR", "ACS"} <= {m["rotulo"] for m in corpo["perfil"]["metricas"]}
    # Habilidades: ou tem a lista completa, ou nenhuma - nunca meia.
    for hab in corpo["habilidades"]:
        assert hab["nome"]
    # Por mapa: ordenado do melhor winrate ao pior, e cada linha carrega as
    # metricas do mesmo vocabulario.
    winrates = [m["winrate"] for m in corpo["por_mapa"]]
    assert winrates == sorted(winrates, reverse=True)
    for mapa in corpo["por_mapa"]:
        assert mapa["mapa"]
        assert 0.0 <= mapa["winrate"] <= 100.0
