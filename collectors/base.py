"""Interface comum dos coletores.

Todo coletor implementa tres passos independentes:

    collect()   -> fala com a API externa e devolve RawRecord's
    save_raw()  -> persiste os payloads crus (disco + manifesto em raw_data)
    parse()     -> transforma RawRecord's em modelos validados (sem tocar na rede)

A separacao e o que permite reprocessar: `parse()` roda igual sobre registros
recem-coletados ou relidos do disco, e adicionar/remover uma fonte nao afeta
as demais.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, Sequence, TypeVar

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RawRecord:
    """Um payload bruto, como veio da API."""

    fonte: str
    endpoint: str
    identificador: str
    payload: Any
    coletado_em: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(slots=True)
class CollectionResult:
    """Resumo de uma execucao, usado tanto no log quanto no retorno da CLI."""

    fonte: str
    sucesso: bool
    registros_coletados: int = 0
    registros_processados: int = 0
    registros_carregados: int = 0
    falhas: int = 0
    duracao_segundos: float = 0.0
    erro: str | None = None


TParsed = TypeVar("TParsed")


class BaseCollector(ABC, Generic[TParsed]):
    """Classe base de todos os coletores.

    Subclasses definem `fonte` e implementam collect/parse; `save_raw` e `run`
    ja vem prontos.
    """

    fonte: str = "desconhecida"

    def __init__(self, raw_storage: "RawStorageProtocol") -> None:
        self.raw_storage = raw_storage
        self.logger = logging.getLogger(f"collectors.{self.fonte}")

    @abstractmethod
    def collect(self) -> list[RawRecord]:
        """Chama a API externa. Unico ponto do coletor que usa rede."""

    @abstractmethod
    def parse(self, registros: Sequence[RawRecord]) -> TParsed:
        """Converte payloads brutos em modelos validados. Funcao pura."""

    def save_raw(self, registros: Sequence[RawRecord]) -> int:
        """Grava os payloads antes de qualquer normalizacao."""
        return self.raw_storage.salvar_muitos(registros)

    def load(self, dados: TParsed) -> int:
        """Persiste os dados normalizados. Sobrescrever quando houver banco."""
        raise NotImplementedError

    def run(self, carregar: bool = True) -> CollectionResult:
        """Orquestra collect -> save_raw -> parse -> load, com log estruturado."""
        inicio = time.monotonic()
        resultado = CollectionResult(fonte=self.fonte, sucesso=False)
        self.logger.info("coleta iniciada", extra={"fonte": self.fonte})

        try:
            registros = self.collect()
            resultado.registros_coletados = len(registros)

            self.save_raw(registros)

            dados = self.parse(registros)
            resultado.registros_processados = _tamanho(dados)

            if carregar:
                resultado.registros_carregados = self.load(dados)

            resultado.sucesso = True
        except Exception as exc:  # noqa: BLE001 - a falha vira log + resultado
            resultado.erro = f"{type(exc).__name__}: {exc}"
            self.logger.exception("coleta falhou", extra={"fonte": self.fonte})
            raise
        finally:
            resultado.falhas = getattr(self, "falhas", 0)
            resultado.duracao_segundos = round(time.monotonic() - inicio, 3)
            self.logger.info(
                "coleta finalizada",
                extra={
                    "fonte": self.fonte,
                    "sucesso": resultado.sucesso,
                    "registros_coletados": resultado.registros_coletados,
                    "registros_processados": resultado.registros_processados,
                    "registros_carregados": resultado.registros_carregados,
                    "falhas": resultado.falhas,
                    "duracao_segundos": resultado.duracao_segundos,
                },
            )

        return resultado


def _tamanho(dados: Any) -> int:
    """Conta itens de um resultado de parse sem exigir um tipo especifico."""
    if dados is None:
        return 0
    if hasattr(dados, "total"):
        return int(dados.total)
    if isinstance(dados, Sequence):
        return len(dados)
    return 1


class RawStorageProtocol:
    """Contrato minimo esperado de um armazenamento bruto (ver etl.raw_storage)."""

    def salvar_muitos(self, registros: Sequence[RawRecord]) -> int:  # pragma: no cover
        raise NotImplementedError
