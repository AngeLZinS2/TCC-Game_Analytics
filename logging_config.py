"""Logging estruturado compartilhado por coletores, ETL e API.

Requisito nao funcional: todo coletor loga sucesso/falha, quantidade de
registros e tempo de execucao. O formato JSON facilita ingestao posterior;
o formato texto e mais legivel durante o desenvolvimento.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Atributos que o logging ja coloca em todo LogRecord; o que sobrar e "extra"
# e vira campo do JSON.
_RESERVADOS = set(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": record.getMessage(),
        }
        for chave, valor in record.__dict__.items():
            if chave not in _RESERVADOS:
                payload[chave] = valor
        if record.exc_info:
            payload["excecao"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)-28s %(message)s%(_extras)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        extras = {
            chave: valor
            for chave, valor in record.__dict__.items()
            if chave not in _RESERVADOS
        }
        record._extras = f"  {extras}" if extras else ""  # type: ignore[attr-defined]
        return super().format(record)


def configurar_logging(nivel: str = "INFO", formato: str = "json") -> None:
    """Idempotente: chamar varias vezes nao duplica handlers."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if formato == "json" else TextFormatter())

    root = logging.getLogger()
    for existente in list(root.handlers):
        root.removeHandler(existente)
    root.addHandler(handler)
    root.setLevel(nivel.upper())

    # Bibliotecas verbosas demais para o nivel INFO do projeto.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
