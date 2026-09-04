"""Testes do parser de bracket de torneio da Liquipedia.

A fixture e um bloco real de `BLAST/Open/2026/Fall`, reduzido (as imagens de
logo saem, o parser nunca as le). Cobre os tres casos que decidem tudo: lado A
venceu, lado B venceu, e um confronto ainda sem definicao (TBD).

Errar a extracao de vencedor aqui e o pior erro silencioso que este projeto
pode cometer: ele nao levanta excecao, so inverte o rotulo de treino do
Bradley-Terry, e o modelo aprenderia o oposto do que aconteceu sem que nada na
tela ou no log denunciasse isso.
"""

from __future__ import annotations

from datetime import timezone

import pytest

from etl.transform_liquipedia_bracket import parse_bracket, transformar


@pytest.fixture(scope="module")
def payload(carregar_fixture):
    return carregar_fixture("liquipedia_bracket")


@pytest.fixture(scope="module")
def confrontos(payload):
    return {p.equipe_a_nome: p for p in transformar(payload, "BLAST/Open/2026/Fall").partidas}


def test_extrai_os_confrontos_decididos(confrontos):
    assert set(confrontos) == {"Team Spirit", "DENDELE CS"}


def test_lado_a_vencedor(confrontos):
    """Time Spirit (lado A) venceu DENDELE CS 2:0 - bloco real do bracket."""
    partida = confrontos["Team Spirit"]
    assert partida.equipe_b_nome == "DENDELE CS"
    assert partida.vitoria_a is True
    assert (partida.placar_a, partida.placar_b) == (2, 0)
    assert partida.formato == "Bo3"
    assert partida.torneio == "BLAST/Open/2026/Fall"


def test_lado_b_vencedor(confrontos):
    """DENDELE CS (lado A nesta linha) perdeu para Aurora Gaming (lado B).

    Sem este caso, um parser que so soubesse ler "o primeiro opponent venceu"
    passaria despercebido - e inverteria o rotulo de toda partida em que quem
    ganha e o segundo opponent do bloco.
    """
    partida = confrontos["DENDELE CS"]
    assert partida.equipe_b_nome == "Aurora Gaming"
    assert partida.vitoria_a is False
    assert (partida.placar_a, partida.placar_b) == (0, 2)


def test_confronto_com_tbd_e_descartado(payload):
    """Um lado do bracket ainda sem time definido nao vira confronto."""
    nomes_a = {p.equipe_a_nome for p in transformar(payload, "x").partidas}
    nomes_b = {p.equipe_b_nome for p in transformar(payload, "x").partidas}
    assert "TBD" not in nomes_a | nomes_b


def test_horario_vira_datetime_em_utc(confrontos):
    for partida in confrontos.values():
        assert partida.inicio_previsto.tzinfo == timezone.utc


def test_id_externo_e_estavel_entre_execucoes(payload):
    primeira = {p.id_externo for p in transformar(payload, "BLAST/Open/2026/Fall").partidas}
    segunda = {p.id_externo for p in transformar(payload, "BLAST/Open/2026/Fall").partidas}
    assert primeira == segunda
    assert len(primeira) == 2


def test_torneio_vem_de_fora_nao_do_html(payload):
    """O bracket nao repete o nome do torneio em cada partida - a pagina
    inteira ja e um torneio so, entao o nome vem de quem chamou `transformar`."""
    r1 = transformar(payload, "BLAST/Open/2026/Fall")
    r2 = transformar(payload, "Outro Torneio Qualquer")
    assert all(p.torneio == "BLAST/Open/2026/Fall" for p in r1.partidas)
    assert all(p.torneio == "Outro Torneio Qualquer" for p in r2.partidas)


def test_html_vazio_devolve_lista_vazia():
    assert parse_bracket("", "x") == []
    assert parse_bracket("<div>nada aqui</div>", "x") == []


def test_payload_de_erro_da_api_nao_levanta():
    assert transformar({"error": {"code": "missingtitle"}}, "x").total == 0
    assert transformar(None, "x").total == 0
    assert transformar({"parse": {}}, "x").total == 0


def test_confronto_sem_vencedor_marcado_e_descartado():
    """Nenhum dos dois lados marcado como vencedor = ainda nao aconteceu.

    O bracket futuro ja vem do ticker (Fase 10) - este parser so acrescenta
    resultado, e sem vencedor nao ha resultado para acrescentar.
    """
    html = (
        '<div class="brkts-match">'
        '<span data-timestamp="1788436800"></span>'
        '<div aria-label="A" class="brkts-opponent-entry"></div>'
        '<div aria-label="B" class="brkts-opponent-entry"></div>'
        "</div>"
    )
    assert parse_bracket(html, "x") == []


def test_os_dois_lados_marcados_e_descartado():
    """Contradicao da propria fonte - a mesma postura do parser do ticker."""
    html = (
        '<div class="brkts-match">'
        '<span data-timestamp="1788436800"></span>'
        '<div aria-label="A" class="brkts-opponent-entry">'
        '<div class="brkts-opponent-win"></div></div>'
        '<div aria-label="B" class="brkts-opponent-entry">'
        '<div class="brkts-opponent-win"></div></div>'
        "</div>"
    )
    assert parse_bracket(html, "x") == []


def test_placar_nao_numerico_vira_none():
    """W.O. ou abandono aparecem como texto, nao inteiro - vira None."""
    html = (
        '<div class="brkts-match">'
        '<span data-timestamp="1788436800"></span>'
        '<div aria-label="A" class="brkts-opponent-entry">'
        '<div class="brkts-opponent-win"></div>'
        '<div class="brkts-opponent-score-inner">W</div></div>'
        '<div aria-label="B" class="brkts-opponent-entry">'
        '<div class="brkts-opponent-score-inner">FF</div></div>'
        "</div>"
    )
    partidas = parse_bracket(html, "x")
    assert partidas[0].vitoria_a is True
    assert (partidas[0].placar_a, partidas[0].placar_b) == (None, None)
