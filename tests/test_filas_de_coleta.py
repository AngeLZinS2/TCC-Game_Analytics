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
from sqlalchemy import select, text

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
