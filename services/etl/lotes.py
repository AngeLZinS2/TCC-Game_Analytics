"""Quebra de INSERT em lotes.

O Postgres aceita no maximo 65535 parametros por statement. Um upsert de N
linhas com C colunas manda N*C parametros, entao a partir de um certo volume o
INSERT em uma tacada so falha com

    number of parameters must be between 0 and 65535

Isso nao aparece durante o desenvolvimento, quando ha centenas de linhas, e
aparece de uma vez quando a coleta cresce - foi o que aconteceu ao paginar as
avaliacoes da Steam, que passaram de 1.200 para mais de 10.000 linhas.
"""

from __future__ import annotations

from typing import Any, Iterator, Sequence

#: Margem sobre o limite do Postgres: sobra espaco para os parametros que o
#: `ON CONFLICT DO UPDATE` acrescenta ao statement.
LIMITE_PARAMETROS = 60_000


def tamanho_do_lote(colunas: int) -> int:
    """Quantas linhas cabem num statement, dado o numero de colunas."""
    if colunas <= 0:
        raise ValueError("colunas deve ser positivo")
    return max(1, LIMITE_PARAMETROS // colunas)


def em_lotes(linhas: Sequence[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    """Fatia as linhas em lotes que cabem num unico INSERT.

    O tamanho sai do numero de colunas da primeira linha - todas as linhas de
    um upsert tem a mesma forma, porque saem do mesmo `model_dump()`.
    """
    if not linhas:
        return

    passo = tamanho_do_lote(len(linhas[0]))
    for inicio in range(0, len(linhas), passo):
        yield list(linhas[inicio : inicio + passo])
