"""Testes do parser da notacao do OP.GG e da normalizacao dos campeoes.

Sem rede: o que se testa e o `parse`, que e funcao pura. E ai que mora a
corretude - um campeao normalizado errado vira estatistica colada no campeao
errado, que e pior do que tela vazia.
"""

from __future__ import annotations

from collectors.base import RawRecord
from collectors.lol_campeoes import CampeoesLolCollector
from collectors.opgg_mcp import analisar_notacao_compacta

ELENCO = """class LolListChampions: lang,data
class Data: champions
class Champion: champion_id,key,name,release_date

LolListChampions("pt_BR",Data([Champion(1,"Annie","Annie","2010-07-13"),\
Champion(60001,"Jade_Annie","Annie","2010-07-13"),\
Champion(20,"Nunu","Nunu & Willump","2009-09-02")]))"""

MID = """class LolListLaneMetaChampions: data
class Data: positions
class Positions: mid
class Mid: champion,is_rip,play,win,kill,win_rate,pick_rate,role_rate,ban_rate,kda,tier,rank,rank_prev,rank_prev_patch

LolListLaneMetaChampions(Data(Positions([Mid("Annie",false,100,60,500,0.6,0.09,0.8,0.03,2.5,1,1,1,2)])))"""

TOP = MID.replace("mid", "top").replace("Mid(", "Top(").replace("class Mid:", "class Top:")


def _registro(identificador: str, payload: str) -> RawRecord:
    return RawRecord(
        fonte="lol_campeoes", endpoint="x", identificador=identificador, payload=payload
    )


def test_parser_le_a_ordem_declarada_no_cabecalho():
    """O cabecalho e o que torna a notacao parseavel sem chutar posicao.

    Se o OP.GG acrescentar um campo, ele aparece com o nome certo em vez de
    deslocar os nossos em silencio.
    """
    linhas = analisar_notacao_compacta(MID, "Mid")

    assert len(linhas) == 1
    assert linhas[0]["champion"] == "Annie"
    assert linhas[0]["is_rip"] is False
    assert linhas[0]["win_rate"] == 0.6
    assert linhas[0]["tier"] == 1


def test_parser_respeita_nome_com_caractere_especial():
    """`split(",")` quebraria em "Nunu & Willump" e afins."""
    nomes = [c["name"] for c in analisar_notacao_compacta(ELENCO, "Champion")]
    assert "Nunu & Willump" in nomes


def test_parser_devolve_vazio_para_classe_ausente():
    """Mudanca de forma do outro lado deixa quem chama SEM dado, nao com dado
    errado."""
    assert analisar_notacao_compacta(MID, "Adc") == []


def test_variante_de_modo_nao_substitui_o_campeao_canonico():
    """O bug real: a fonte devolve 236 linhas para 173 campeoes.

    Sessenta e tres sao variantes de modo com o MESMO nome exibido e id 60000+
    ("Jade_Annie", 60001). Um dicionario por nome ficava com a ULTIMA, e a
    Annie do banco virava `Jade_Annie` com id 60001 - nome certo, identidade
    errada, e a estatistica da rota colava no registro errado.
    """
    coletor = CampeoesLolCollector(raw_storage=None)
    campeoes = coletor.parse([_registro("elenco", ELENCO)])

    annie = next(c for c in campeoes if c["nome"] == "Annie")
    assert annie["id_externo"] == "1"
    assert annie["nome_interno"] == "Annie"
    # A variante nao vira um segundo campeao de mesmo nome.
    assert sum(1 for c in campeoes if c["nome"] == "Annie") == 1


def test_rota_principal_e_a_de_maior_presenca():
    """Um campeao nao tem "um" desempenho - tem um por rota.

    A media entre rotas descreveria um campeao que ninguem joga; a escolhida e
    aquela onde ele mais aparece (`role_rate`).
    """
    coletor = CampeoesLolCollector(raw_storage=None)
    top = TOP.replace("0.8,", "0.2,")  # mesma Annie, com presenca menor no topo

    campeoes = coletor.parse(
        [_registro("elenco", ELENCO), _registro("rota:MID", MID), _registro("rota:TOP", top)]
    )

    annie = next(c for c in campeoes if c["nome"] == "Annie")
    assert annie["papel"] == "Meio"
    assert annie["metricas"]["role_rate"] == 80.0


def test_taxas_viram_pontos_percentuais():
    """A fonte publica fracao (0.09); a tela mostra 9,0%."""
    coletor = CampeoesLolCollector(raw_storage=None)
    campeoes = coletor.parse([_registro("elenco", ELENCO), _registro("rota:MID", MID)])

    metricas = next(c for c in campeoes if c["nome"] == "Annie")["metricas"]
    assert metricas["pick_rate"] == 9.0
    assert metricas["ban_rate"] == 3.0
    # KDA e tier nao sao taxa e passam direto.
    assert metricas["kda"] == 2.5
    assert metricas["tier"] == 1


def test_campeao_sem_estatistica_entra_sem_metrica():
    """Sem rota coletada ele existe no elenco e nao ganha numero inventado."""
    coletor = CampeoesLolCollector(raw_storage=None)
    campeoes = coletor.parse([_registro("elenco", ELENCO)])

    nunu = next(c for c in campeoes if c["nome"] == "Nunu & Willump")
    assert "metricas" not in nunu
    assert "papel" not in nunu
