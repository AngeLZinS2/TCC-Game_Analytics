"""Parse do coletor de usuarios simultaneos da Steam.

Sem rede nem banco: so o `parse` sobre RawRecord's montados na mao. Protege
contra a regressao que travou o coletor em producao - a Valve trocou o
`/en/about/stats` (que devolvia `{users_online: ...}`) por `[]` e o
`dados.get(...)` estourava `AttributeError`. Agora o dado vem do WebSocket
como dict e o `parse` ignora qualquer coisa que nao seja dict.
"""

from __future__ import annotations

from services.collectors.base import RawRecord
from services.collectors.steam_online import (
    ENDPOINT_PLATAFORMA,
    ENDPOINT_TOP100,
    SteamOnlineCollector,
)


class _StorageFake:
    def salvar_muitos(self, registros):  # noqa: D401 - stub
        return len(list(registros))


def _reg(identificador: str, payload) -> RawRecord:
    return RawRecord(
        fonte="steam_online",
        endpoint="x",
        identificador=identificador,
        payload=payload,
    )


def _coletor() -> SteamOnlineCollector:
    return SteamOnlineCollector(raw_storage=_StorageFake())


def test_parse_stats_do_socket_como_dict():
    registros = [
        _reg(ENDPOINT_PLATAFORMA, {"users_online": 23832610, "users_ingame": 6310893}),
        _reg(
            ENDPOINT_TOP100,
            {"response": {"ranks": [{"appid": 730}, {"appid": 570}, {"foo": 1}]}},
        ),
    ]
    r = _coletor().parse(registros)
    assert r.usuarios_online == 23832610
    assert r.usuarios_em_jogo == 6310893
    assert r.top_app_ids == [730, 570]
    assert r.total == 1


def test_parse_stats_como_string_json():
    """Back-compat: se algum dia o payload voltar a ser texto."""
    r = _coletor().parse(
        [_reg(ENDPOINT_PLATAFORMA, '{"users_online": "1,234,567", "users_ingame": 42}')]
    )
    assert r.usuarios_online == 1234567
    assert r.usuarios_em_jogo == 42


def test_parse_lista_vazia_nao_estoura():
    """O bug de producao: `/en/about/stats` passou a devolver `[]`."""
    r = _coletor().parse([_reg(ENDPOINT_PLATAFORMA, [])])
    assert r.usuarios_online is None
    assert r.usuarios_em_jogo is None
    assert r.total == 0


def test_parse_sem_registro_de_plataforma():
    """So o Top 100 veio (socket fora do ar) - nao quebra, so nao grava snapshot."""
    r = _coletor().parse(
        [_reg(ENDPOINT_TOP100, {"response": {"ranks": [{"appid": 730}]}})]
    )
    assert r.usuarios_online is None
    assert r.top_app_ids == [730]
