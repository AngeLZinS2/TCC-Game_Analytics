"""Armazenamento dos payloads brutos.

Regra de design do projeto: o JSON recebido de qualquer API e gravado ANTES
de ser normalizado. Assim, quando o ETL muda, da para reprocessar tudo sem
rechamar a API (util quando o limite e restritivo, como na Riot).

Layout em disco:

    data/raw/<fonte>/<endpoint>/<AAAA-MM-DD>/<identificador>__<timestamp>.json

O conteudo do arquivo tem envelope proprio (fonte, endpoint, identificador,
coletado_em, payload) para ser auto-descritivo na releitura.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert

from collectors.base import RawRecord
from db.models import RawData
from db.session import session_scope

logger = logging.getLogger(__name__)

_INVALIDOS = re.compile(r"[^A-Za-z0-9._-]+")
FORMATO_TIMESTAMP = "%Y%m%dT%H%M%SZ"


def _sanitizar(valor: str) -> str:
    """Torna o valor seguro como nome de arquivo/pasta (inclusive no Windows)."""
    limpo = _INVALIDOS.sub("-", valor).strip("-.")
    return limpo[:120] or "sem-id"


class RawStorage:
    """Grava payloads em disco e registra o manifesto na tabela `raw_data`.

    Args:
        base_dir: raiz dos arquivos brutos.
        registrar_no_banco: quando False, escreve so em disco (util em testes
            e para coletar sem o Postgres no ar).
    """

    def __init__(self, base_dir: Path, registrar_no_banco: bool = True) -> None:
        self.base_dir = Path(base_dir)
        self.registrar_no_banco = registrar_no_banco

    # -- escrita ------------------------------------------------------------

    def caminho_para(self, registro: RawRecord) -> Path:
        dia = registro.coletado_em.astimezone(timezone.utc).strftime("%Y-%m-%d")
        carimbo = registro.coletado_em.astimezone(timezone.utc).strftime(FORMATO_TIMESTAMP)
        nome = f"{_sanitizar(registro.identificador)}__{carimbo}.json"
        return (
            self.base_dir
            / _sanitizar(registro.fonte)
            / _sanitizar(registro.endpoint)
            / dia
            / nome
        )

    def salvar(self, registro: RawRecord) -> Path:
        caminho = self.caminho_para(registro)
        caminho.parent.mkdir(parents=True, exist_ok=True)

        envelope = {
            "fonte": registro.fonte,
            "endpoint": registro.endpoint,
            "identificador": registro.identificador,
            "coletado_em": registro.coletado_em.astimezone(timezone.utc).isoformat(),
            "payload": registro.payload,
        }
        conteudo = json.dumps(envelope, ensure_ascii=False, indent=2)
        caminho.write_text(conteudo, encoding="utf-8")
        return caminho

    def salvar_muitos(self, registros: Sequence[RawRecord]) -> int:
        if not registros:
            return 0

        manifestos: list[dict[str, object]] = []
        for registro in registros:
            caminho = self.salvar(registro)
            bruto = caminho.read_bytes()
            manifestos.append(
                {
                    "fonte": registro.fonte,
                    "endpoint": registro.endpoint,
                    "identificador": registro.identificador,
                    "caminho_arquivo": str(caminho.relative_to(self.base_dir)),
                    "hash_payload": hashlib.sha256(bruto).hexdigest(),
                    "tamanho_bytes": len(bruto),
                    "coletado_em": registro.coletado_em,
                }
            )

        if self.registrar_no_banco:
            self._registrar(manifestos)

        logger.info(
            "payloads brutos gravados",
            extra={"quantidade": len(manifestos), "diretorio": str(self.base_dir)},
        )
        return len(manifestos)

    @staticmethod
    def _registrar(manifestos: list[dict[str, object]]) -> None:
        stmt = pg_insert(RawData).values(manifestos)
        # Reexecutar a mesma coleta nao duplica o manifesto.
        stmt = stmt.on_conflict_do_nothing(constraint="uq_raw_data_coleta")
        with session_scope() as sessao:
            sessao.execute(stmt)

    # -- releitura (reprocessamento) ----------------------------------------

    def ler(self, fonte: str, endpoint: str | None = None) -> Iterator[RawRecord]:
        """Percorre os payloads ja gravados, do mais antigo para o mais recente."""
        raiz = self.base_dir / _sanitizar(fonte)
        if endpoint:
            raiz = raiz / _sanitizar(endpoint)
        if not raiz.exists():
            return

        for caminho in sorted(raiz.rglob("*.json")):
            envelope = json.loads(caminho.read_text(encoding="utf-8"))
            yield RawRecord(
                fonte=envelope["fonte"],
                endpoint=envelope["endpoint"],
                identificador=envelope["identificador"],
                payload=envelope["payload"],
                coletado_em=datetime.fromisoformat(envelope["coletado_em"]),
            )

    def ler_ultima_coleta(self, fonte: str) -> list[RawRecord]:
        """So os registros do carimbo de tempo mais recente de cada endpoint."""
        por_endpoint: dict[str, list[RawRecord]] = {}
        for registro in self.ler(fonte):
            por_endpoint.setdefault(registro.endpoint, []).append(registro)

        selecionados: list[RawRecord] = []
        for registros in por_endpoint.values():
            mais_recente = max(r.coletado_em for r in registros)
            # Uma "coleta" pode levar minutos; agrupamos pelo mesmo dia/hora.
            limite = mais_recente.replace(minute=0, second=0, microsecond=0)
            selecionados.extend(r for r in registros if r.coletado_em >= limite)
        return selecionados


class NullRawStorage:
    """Descarta os payloads. Usado em testes que so exercitam o parse."""

    def salvar_muitos(self, registros: Sequence[RawRecord]) -> int:
        return len(registros)
