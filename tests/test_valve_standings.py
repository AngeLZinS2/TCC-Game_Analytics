"""Testes do parser do Regional Standings da Valve.

Sem banco e sem rede: exercita `transform_valve_standings` sobre um recorte
real da tabela markdown (`tests/fixtures/valve_standings_global.md`), reduzido
para 8 linhas que cobrem os casos que importam - nome com prefixo/sufixo de
organizacao, sigla curta, nome repetido (line-up trocado), pontos nao-numerico
(W.O.).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from etl.transform_valve_standings import (
    data_do_arquivo,
    parse_standings,
    transformar,
)

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "valve_standings_global.md"
).read_text(encoding="utf-8")


@pytest.fixture
def resultado():
    return transformar(FIXTURE, nome_arquivo="standings_global_2026_08_03.md")


def test_extrai_uma_linha_por_time(resultado):
    # 8 linhas de dados no fixture, mas "Liquid" aparece 2x (line-up trocado)
    # e so a primeira - a mais bem colocada - entra.
    assert resultado.total == 7
    assert [l.posicao for l in resultado.linhas][:3] == [1, 2, 3]


def test_nome_e_pontos_do_topo(resultado):
    topo = resultado.linhas[0]
    assert topo.equipe_nome == "Spirit"
    assert topo.pontos == 2011
    assert topo.posicao == 1


def test_nome_repetido_fica_com_a_melhor_posicao(resultado):
    liquid = [l for l in resultado.linhas if l.equipe_nome == "Liquid"]
    assert len(liquid) == 1
    assert liquid[0].posicao == 32  # nao 251
    assert liquid[0].pontos == 1397


def test_pontos_nao_numerico_vira_none(resultado):
    waves = next(l for l in resultado.linhas if l.equipe_nome == "Time Waves")
    assert waves.pontos is None
    assert waves.posicao == 396


def test_data_vem_do_nome_do_arquivo(resultado):
    assert resultado.data_referencia == date(2026, 8, 3)


def test_data_do_arquivo_isolada():
    assert data_do_arquivo("standings_global_2025_01_06.md") == date(2025, 1, 6)
    assert data_do_arquivo("sem_data.md") is None


def test_data_cai_para_o_titulo_sem_nome_de_arquivo():
    # `### Standings as of 2026_08_03` dentro do markdown.
    r = transformar(FIXTURE, nome_arquivo="")
    assert r.data_referencia == date(2026, 8, 3)


def test_cabecalho_e_alinhamento_nao_viram_linha():
    r = parse_standings(FIXTURE)
    assert all(l.equipe_nome not in {"Team Name", ":-", ""} for l in r.linhas)


def test_markdown_vazio_nao_levanta():
    assert transformar("", nome_arquivo="x.md").total == 0
    assert transformar("   \n  \n", nome_arquivo="x.md").total == 0


def test_payload_nao_string_nao_levanta():
    assert transformar({"erro": "algo"}, nome_arquivo="x.md").total == 0
    assert transformar(None).total == 0
