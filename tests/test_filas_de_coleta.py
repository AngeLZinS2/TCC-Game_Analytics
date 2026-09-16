"""As filas que o agendador alimenta nao podem incluir stub de oferta.

A varredura de ofertas (Fase 35.1) cria uma linha em `dim_jogo_steam` por
oferta ativa - so nome, imagem e tags, sem ficha. O banco saiu de ~90 linhas
para ~20 mil, e tres filas de coleta recorrente foram junto sem ninguem
notar, porque o agendador estava parado na epoca:

* a tarefa `steam` (`appdetails` + avaliacoes de cada monitorado) passou a
  pedir 20.079 apps a ~3s cada: 16,7 HORAS de passada, numa tarefa agendada
  a cada 60 minutos. Medido ao vivo na VPS em 2026-09-16, com o log em
  `posicao: 14, total: 20079`;
* a fila do ITAD casava com stub por `gratuito IS NULL`;
* a do HowLongToBeat, por `hltb_id IS NULL`.

O criterio e o mesmo dos routers: `coletado_ficha_em` diz quem tem ficha de
verdade. O stub ja tem preco pela propria varredura, de hora em hora - e e
so o que a tela de Ofertas mostra dele. Ele entra nas filas quando alguem
abrir a ficha e a coleta sob demanda rodar.

Sem Postgres o modulo inteiro e pulado (mesmo motivo de `test_api.py`).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from models.models import DimJogoSteam
from models.session import get_engine, session_scope


@pytest.fixture(scope="module", autouse=True)
def exige_postgres() -> None:
    try:
        with get_engine().connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - qualquer falha de conexao serve
        pytest.skip(f"Postgres indisponivel: {type(exc).__name__}")


def _stubs_no_banco() -> int:
    with session_scope() as sessao:
        return sessao.scalar(
            select(DimJogoSteam.app_id)
            .where(DimJogoSteam.coletado_ficha_em.is_(None))
            .limit(1)
        ) is not None


def _sem_ficha(app_ids: list[int]) -> list[int]:
    if not app_ids:
        return []
    with session_scope() as sessao:
        return list(
            sessao.scalars(
                select(DimJogoSteam.app_id).where(
                    DimJogoSteam.app_id.in_(app_ids),
                    DimJogoSteam.coletado_ficha_em.is_(None),
                )
            )
        )


def test_monitorados_do_agendador_so_tem_ficha() -> None:
    """A fila da tarefa `steam` - a que custava 16,7 horas por passada."""
    from agendador import _apps_monitorados

    intrusos = _sem_ficha(_apps_monitorados())
    assert intrusos == [], f"{len(intrusos)} stub(s) na fila da coleta Steam"


def test_fila_do_itad_so_tem_ficha() -> None:
    from services.collectors.itad_collector import jogos_para_preco

    intrusos = _sem_ficha([app_id for app_id, _ in jogos_para_preco()])
    assert intrusos == [], f"{len(intrusos)} stub(s) na fila do ITAD"


def test_fila_do_hltb_so_tem_ficha() -> None:
    from services.collectors.hltb_collector import jogos_para_tempo

    intrusos = _sem_ficha([app_id for app_id, _ in jogos_para_tempo()])
    assert intrusos == [], f"{len(intrusos)} stub(s) na fila do HowLongToBeat"


def test_a_premissa_do_teste_vale() -> None:
    """Sem stub no banco os tres testes acima passariam por vacuidade.

    Este fixa que o banco de teste tem de fato o caso que eles protegem - se
    parar de ter, sao eles que precisam de outro cenario, nao o codigo.
    """
    assert _stubs_no_banco(), "banco sem stub: os testes acima nao provam nada"


# --- O "nao achei" do HLTB nao pode ser definitivo ---------------------------


def test_hltb_revalida_o_marcador_de_nao_achado() -> None:
    """`hltb_id = ""` volta pra fila depois da janela de revalidacao.

    Sem isto o marcador era DEFINITIVO, e custava dado real em dois casos:
    lancamento coletado antes de existir no HLTB nunca teria tempo, e jogo
    marcado antes de uma melhoria na busca tambem nao. O segundo aconteceu:
    "Apex Legends™" ficou sem tempo mesmo depois da limpeza de ™/®/©, apesar
    de a busca passar a encontra-lo (`count=2`, conferido ao vivo).

    Compara a fila com e sem a janela em vez de fixar um numero: o banco de
    teste muda, a REGRA nao.
    """
    from services.collectors.hltb_collector import jogos_para_tempo

    with session_scope() as sessao:
        marcados = sessao.scalar(
            select(func.count())
            .select_from(DimJogoSteam)
            .where(DimJogoSteam.hltb_id == "")
        )
    if not marcados:
        pytest.skip("banco sem jogo marcado como 'nao achei no HLTB'")

    sem_janela = {app_id for app_id, _ in jogos_para_tempo()}
    # Janela de 0 dia: todo marcado ja venceu, entao todos voltam.
    com_janela = {app_id for app_id, _ in jogos_para_tempo(revalidar_vazios_dias=0)}

    assert com_janela > sem_janela, (
        "a janela de revalidacao nao trouxe nenhum 'nao achei' de volta"
    )
    assert len(com_janela - sem_janela) == marcados


def test_hltb_sem_janela_nao_repete_quem_ja_foi_achado() -> None:
    """O complemento: quem TEM tempo nunca volta, com ou sem janela.

    Diferente do ITAD (que rebusca preco toda rodada), aqui o id e os tempos
    saem da mesma chamada - jogo achado nao tem o que atualizar, e rebusca-lo
    seria trafego a toa num site que nem API oficial tem.
    """
    from services.collectors.hltb_collector import jogos_para_tempo

    with session_scope() as sessao:
        achados = set(
            sessao.scalars(
                select(DimJogoSteam.app_id).where(
                    DimJogoSteam.hltb_id.is_not(None), DimJogoSteam.hltb_id != ""
                )
            )
        )
    if not achados:
        pytest.skip("banco sem jogo com tempo do HLTB")

    na_fila = {app_id for app_id, _ in jogos_para_tempo(revalidar_vazios_dias=0)}
    assert na_fila & achados == set()


# --- A regra tem UM dono ------------------------------------------------------


def test_ninguem_reescreve_o_criterio_na_mao() -> None:
    """`com_ficha()`/`sem_ficha()` sao os unicos donos da regra.

    Os testes acima cobrem as tres filas que existiam quando o bug apareceu.
    Este cobre a PROXIMA - a fila que alguem ainda vai escrever, e que nenhum
    teste enumerado pegaria. O criterio nasceu espalhado (dez consultas com o
    mesmo `coletado_ficha_em IS NOT NULL` copiado), e foi assim que tres
    delas esqueceram dele.

    Escrever o predicado na mao volta a permitir esquecer; usar o helper faz
    a regra ser uma coisa so, que da pra achar e mudar num lugar.
    """
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parent.parent
    ignorados = {"tests", "migrations", ".git", "node_modules", "dashboard"}
    infratores = []

    for arquivo in raiz.rglob("*.py"):
        if any(parte in ignorados for parte in arquivo.parts):
            continue
        # O proprio model define o helper - e o unico lugar onde a coluna
        # pode ser comparada diretamente.
        if arquivo.name == "models.py" and arquivo.parent.name == "models":
            continue
        texto = arquivo.read_text(encoding="utf-8")
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if "coletado_ficha_em.is_" in linha:
                infratores.append(f"{arquivo.relative_to(raiz)}:{numero}")

    assert infratores == [], (
        "use DimJogoSteam.com_ficha()/sem_ficha() em vez de comparar a coluna "
        f"direto: {infratores}"
    )
