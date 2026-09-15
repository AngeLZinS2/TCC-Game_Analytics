"""Parsing puro do indice de catalogo completo (`IStoreService/GetAppList`).

Sem I/O: so converte o payload cru de cada pagina em linhas validadas. O
proximo cursor (`last_appid`) e o "acabou o catalogo?" (`concluido`) saem
direto do formato da resposta da Steam - nenhum estado extra precisa ser
carregado aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from services.collectors.base import RawRecord

FONTE = "steam_catalogo"


def _inteiro(valor: Any) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _epoch(valor: Any) -> datetime | None:
    numero = _inteiro(valor)
    if not numero:
        return None
    try:
        return datetime.fromtimestamp(numero, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


@dataclass(slots=True)
class LinhaCatalogoSteam:
    app_id: int
    nome: str
    tipo: str | None
    ultima_modificacao: datetime | None
    numero_mudanca_preco: int | None


@dataclass(slots=True)
class ResultadoCatalogoSteam:
    """Uma execucao da tarefa `steam_catalogo`.

    `fase` e "catalogo_inicial" ou "catalogo_incremental" quando alguma
    pagina foi de fato buscada, ou "sem_execucao" num tick que so verificou
    o relogio e nao bateu na Steam (sync incremental ainda nao venceu o
    intervalo configurado).
    """

    fase: str
    linhas: list[LinhaCatalogoSteam] = field(default_factory=list)
    #: Proximo cursor de paginacao - `None` quando nenhuma pagina trouxe apps.
    last_appid: int | None = None
    #: `True` quando a ULTIMA pagina processada disse `have_more_results=false`.
    concluido: bool = False
    paginas_processadas: int = 0

    @property
    def total(self) -> int:
        return len(self.linhas)


def transformar(
    registros: Sequence[RawRecord], fase: str | None
) -> ResultadoCatalogoSteam:
    if not fase or not registros:
        return ResultadoCatalogoSteam(fase=fase or "sem_execucao")

    linhas: list[LinhaCatalogoSteam] = []
    last_appid: int | None = None
    concluido = False

    for registro in registros:
        resposta = registro.payload or {}
        apps = resposta.get("apps") or []
        for item in apps:
            app_id = _inteiro(item.get("appid"))
            nome = (item.get("name") or "").strip()
            if app_id is None or not nome:
                continue
            linhas.append(
                LinhaCatalogoSteam(
                    app_id=app_id,
                    nome=nome,
                    tipo=item.get("type") or None,
                    ultima_modificacao=_epoch(item.get("last_modified")),
                    numero_mudanca_preco=_inteiro(item.get("price_change_number")),
                )
            )
        if apps:
            last_appid = _inteiro(apps[-1].get("appid")) or last_appid
        # A ultima pagina processada e quem decide - se ela nao tem mais
        # resultados, o crawl/incremental terminou.
        concluido = not bool(resposta.get("have_more_results"))

    return ResultadoCatalogoSteam(
        fase=fase,
        linhas=linhas,
        last_appid=last_appid,
        concluido=concluido,
        paginas_processadas=len(registros),
    )
