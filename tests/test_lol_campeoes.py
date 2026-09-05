"""Testes do parser da notacao do OP.GG e da normalizacao dos campeoes.

Sem rede: o que se testa e o `parse`, que e funcao pura. E ai que mora a
corretude - um campeao normalizado errado vira estatistica colada no campeao
errado, que e pior do que tela vazia.
"""

from __future__ import annotations

import json as json_module

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


# --- videos de habilidade do Valorant (ficha oficial da Riot) ---

from collectors.valorant_agentes import _casar_video, _chave_habilidade, _extrair_videos, _slug_riot


def test_slug_riot_cobre_os_nomes_torto():
    """A URL da ficha da Riot deriva do nome - "KAY/O" e o caso que quebra."""
    assert _slug_riot("KAY/O") == "kay-o"
    assert _slug_riot("Chamber") == "chamber"
    assert _slug_riot("Nunu & Willump") == "nunu-willump"


def test_chave_habilidade_tira_o_que_a_riot_poe_alem_do_nome():
    """A valorant-api entrega o nome limpo; a ficha da Riot enfeita."""
    assert _chave_habilidade("Q - Predador Explosivo") == _chave_habilidade("Predador Explosivo")
    assert _chave_habilidade("Enseada (Fumaça de Enseada)") == _chave_habilidade("Enseada")
    assert _chave_habilidade("Nebulosa/Dissipar") == _chave_habilidade("Nebulosa")


def test_casar_video_aceita_nome_contido():
    videos = {"formaastraldivisacosmica": "http://x/a.mp4", "nebulosa": "http://x/b.mp4"}
    # "Forma Astral" (valorant-api) casa com "Forma Astral/Divisão Cósmica" (Riot)
    assert _casar_video("Forma Astral", videos) == "http://x/a.mp4"
    # Casamento exato ainda ganha
    assert _casar_video("Nebulosa", videos) == "http://x/b.mp4"
    # Nada parecido -> None, nao um chute
    assert _casar_video("Muralha de Fogo", videos) is None


def test_extrair_videos_de_next_data_minimo():
    """A blade de habilidade e a unica `iconTab`; o texto do header muda com o
    idioma e por isso NAO e usado no filtro."""
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json_module.dumps(
            {
                "props": {
                    "pageProps": {
                        "page": {
                            "blades": [
                                {"type": "characterMasthead"},
                                {
                                    "type": "iconTab",
                                    "header": {"title": "Habilidades Especiais"},
                                    "groups": [
                                        {
                                            "content": {
                                                "title": "C - Chama",
                                                "media": {
                                                    "sources": [
                                                        {
                                                            "src": "https://cmsassets.rgpub.io/x/y.mp4",
                                                            "type": "video/mp4",
                                                        }
                                                    ]
                                                },
                                            }
                                        }
                                    ],
                                },
                            ]
                        }
                    }
                }
            }
        )
        + "</script>"
    )
    videos = _extrair_videos(html)
    assert videos == {"chama": "https://cmsassets.rgpub.io/x/y.mp4"}


def test_extrair_videos_devolve_vazio_se_a_forma_mudar():
    assert _extrair_videos("<html>sem next data</html>") == {}
    assert _extrair_videos('<script id="__NEXT_DATA__">nao e json</script>') == {}


# --- dado estatico: LoL (Data Dragon) e Dota (datafeed da Valve) ---

from collectors.lol_campeoes import _limpar_html, _metadados_ddragon
from collectors.dota_herois import _limpar as _limpar_dota, _normalizar_heroi


def test_metadados_ddragon_monta_habilidades_com_slot():
    payload = {
        "versao": "16.17.1",
        "data": {
            "Ahri": {
                "image": {"full": "Ahri.png"},
                "lore": "A ligação de Ahri...",
                "passive": {
                    "name": "Furto de Essência",
                    "description": "Ahri se cura.<br>Depois...",
                    "image": {"full": "Ahri_SoulEater2.png"},
                },
                "spells": [
                    {"name": "Orbe da Ilusão", "description": "d", "image": {"full": "AhriQ.png"}},
                    {"name": "Fogo de Raposa", "description": "d", "image": {"full": "AhriW.png"}},
                    {"name": "Encanto", "description": "d", "image": {"full": "AhriE.png"}},
                    {"name": "Ímpeto Espiritual", "description": "d", "image": {"full": "AhriR.png"}},
                ],
            }
        },
    }
    meta = _metadados_ddragon(payload)["Ahri"]

    slots = [h["slot"] for h in meta["habilidades"]]
    assert slots == ["Passiva", "Q", "W", "E", "R"]
    assert meta["habilidades"][1]["icone"].endswith("/img/spell/AhriQ.png")
    assert meta["descricao"].startswith("A ligação de Ahri")
    # `<br>` virou espaco, sem tag sobrando
    assert "<" not in meta["habilidades"][0]["descricao"]


def test_limpar_html_tira_placeholder_de_template():
    assert _limpar_html("Envenena o alvo %i:OnHit% ao contato") == (
        "Envenena o alvo … ao contato"
    )


def test_normalizar_heroi_dota_casa_por_id_e_limpa_o_texto():
    bruto = {
        "id": 14,
        "name": "npc_dota_hero_pudge",
        "name_loc": "Pudge",
        "bio_loc": "Nos Campos da Carnificina...",
        "abilities": [
            {
                "name": "pudge_meat_hook",
                "name_loc": "Gancho de Carne",
                "desc_loc": "Em inglês: <b><font color='#F2A93E'>Meat Hook</font></b>\n \nLança um gancho.",
            },
            {"name": "generic_hidden", "name_loc": "x", "desc_loc": "y"},
        ],
    }
    heroi = _normalizar_heroi(bruto)

    # id_externo e o id numerico da Valve - o mesmo de `dim_personagem` no Dota.
    assert heroi["id_externo"] == "14"
    assert heroi["nome_interno"] == "npc_dota_hero_pudge"
    habs = heroi["metadados"]["habilidades"]
    # `generic_hidden` (slot vazio) nao entra.
    assert len(habs) == 1
    assert habs[0]["nome"] == "Gancho de Carne"
    # o prefixo "Em inglês: ... </b>" saiu, sobrou so o texto pt-BR.
    assert habs[0]["descricao"] == "Lança um gancho."
    assert habs[0]["icone"].endswith("/abilities/pudge_meat_hook.png")


def test_limpar_dota_tira_token_de_atributo():
    assert _limpar_dota("Ganha %damage_stat_bonus_pct%%% de dano") == "Ganha … de dano"
    # Tokens em CamelCase (contagem de cargas) tambem somem.
    assert _limpar_dota("consome uma das %AbilityCharges% cargas") == "consome uma das … cargas"
