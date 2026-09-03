"""Testes do armazenamento bruto (sem banco: registrar_no_banco=False)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from collectors.base import RawRecord
from etl.raw_storage import RawStorage

MOMENTO = datetime(2026, 9, 2, 14, 37, 12, tzinfo=timezone.utc)


def _registro(app_id: int = 570) -> RawRecord:
    return RawRecord(
        fonte="steam",
        endpoint="appdetails",
        identificador=str(app_id),
        payload={"570": {"success": True, "data": {"name": "Dota 2"}}},
        coletado_em=MOMENTO,
    )


def test_salva_com_envelope_auto_descritivo(tmp_path):
    storage = RawStorage(tmp_path, registrar_no_banco=False)
    caminho = storage.salvar(_registro())

    assert caminho.exists()
    assert caminho.parent == tmp_path / "steam" / "appdetails" / "2026-09-02"
    # Nome de arquivo valido no Windows (sem ":" do ISO 8601).
    assert caminho.name == "570__20260902T143712Z.json"

    envelope = json.loads(caminho.read_text(encoding="utf-8"))
    assert envelope["fonte"] == "steam"
    assert envelope["identificador"] == "570"
    assert envelope["payload"]["570"]["data"]["name"] == "Dota 2"


def test_releitura_reconstroi_o_raw_record(tmp_path):
    storage = RawStorage(tmp_path, registrar_no_banco=False)
    storage.salvar_muitos([_registro(570), _registro(730)])

    relidos = sorted(storage.ler("steam"), key=lambda r: r.identificador)

    assert [r.identificador for r in relidos] == ["570", "730"]
    assert relidos[0].coletado_em == MOMENTO
    assert relidos[0].endpoint == "appdetails"


def test_regravar_a_mesma_coleta_nao_gera_arquivo_novo(tmp_path):
    """Idempotencia em disco: mesmo (fonte, endpoint, id, timestamp) = mesmo arquivo."""
    storage = RawStorage(tmp_path, registrar_no_banco=False)
    storage.salvar_muitos([_registro()])
    storage.salvar_muitos([_registro()])

    assert len(list(tmp_path.rglob("*.json"))) == 1
