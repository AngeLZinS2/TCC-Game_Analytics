"""Painel admin - login por senha + estatisticas do site.

Sem sistema de contas (isso vem depois, antes do painel ir pra VPS de
verdade): uma senha so, guardada em `ADMIN_SENHA` no `.env`, nunca no
codigo. O login devolve um token assinado (HMAC com a propria senha) com
validade curta (`admin_token_horas`) - toda outra rota daqui exige esse
token no header `Authorization: Bearer <token>` via `exigir_admin`.

Sem `ADMIN_SENHA` configurada, o painel inteiro responde 503 - mesmo padrao
do assistente sem `OPENROUTER_API_KEY`: a ausencia da chave e o proprio
"desligado", sem precisar de outro flag.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from models.models import (
    AgendaPartida,
    DimJogador,
    DimJogo,
    DimJogoSteam,
    DimJogoXbox,
    DimPartida,
    FatoAcessoSite,
    FatoAvaliacaoSteam,
    FatoBusca,
    FatoLolJogadorPartida,
    FatoMinutoPartida,
    FatoSnapshotJogoSteam,
    FatoSnapshotJogoXbox,
    RankingExterno,
    RawData,
)
from models.session import get_db
from services.ml import telemetria_site
from views.schemas import (
    EntradaLoginAdmin,
    MetricaSistema,
    PontoAcessoDia,
    SaudeBanco,
    SaudeSistema,
    TabelaBanco,
    TokenAdmin,
    VisaoGeralAdmin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Autenticacao
# ---------------------------------------------------------------------------


def _assinar(corpo: str, segredo: str) -> str:
    return hmac.new(segredo.encode(), corpo.encode(), hashlib.sha256).hexdigest()


def _gerar_token(settings: Settings) -> tuple[str, datetime]:
    expira_em = datetime.now(timezone.utc) + timedelta(hours=settings.admin_token_horas)
    corpo = str(int(expira_em.timestamp()))
    return f"{corpo}.{_assinar(corpo, settings.admin_senha)}", expira_em


def _token_valido(token: str, settings: Settings) -> bool:
    try:
        corpo, assinatura = token.split(".", 1)
    except ValueError:
        return False
    if not hmac.compare_digest(assinatura, _assinar(corpo, settings.admin_senha)):
        return False
    try:
        return int(corpo) > time.time()
    except ValueError:
        return False


def exigir_admin(authorization: str | None = Header(default=None)) -> None:
    """Dependencia do FastAPI - toda rota admin (exceto `/login`) usa isto."""
    settings = get_settings()
    if not settings.admin_senha:
        raise HTTPException(
            status_code=503, detail="painel admin nao configurado (ADMIN_SENHA)"
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="token ausente")
    if not _token_valido(authorization.removeprefix("Bearer ").strip(), settings):
        raise HTTPException(status_code=401, detail="token invalido ou expirado")


@router.post("/login", response_model=TokenAdmin)
def login(entrada: EntradaLoginAdmin) -> TokenAdmin:
    settings = get_settings()
    if not settings.admin_senha:
        raise HTTPException(
            status_code=503, detail="painel admin nao configurado (ADMIN_SENHA)"
        )
    if not hmac.compare_digest(entrada.senha, settings.admin_senha):
        raise HTTPException(status_code=401, detail="senha incorreta")
    token, expira_em = _gerar_token(settings)
    return TokenAdmin(token=token, expira_em=expira_em)


# ---------------------------------------------------------------------------
# Visao geral - acessos, buscas, online agora
# ---------------------------------------------------------------------------


@router.get(
    "/visao-geral",
    response_model=VisaoGeralAdmin,
    dependencies=[Depends(exigir_admin)],
)
def visao_geral(sessao: Session = Depends(get_db)) -> VisaoGeralAdmin:
    agora = datetime.now(timezone.utc)
    inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_mes = inicio_dia.replace(day=1)
    inicio_ano = inicio_mes.replace(month=1)

    def _acessos(desde: datetime) -> tuple[int, int]:
        linha = sessao.execute(
            select(
                func.count(),
                func.count(func.distinct(FatoAcessoSite.visitante_id)),
            ).where(FatoAcessoSite.criado_em >= desde)
        ).first()
        return (linha[0] or 0, linha[1] or 0) if linha else (0, 0)

    def _buscas(desde: datetime) -> int:
        return (
            sessao.execute(
                select(func.count())
                .select_from(FatoBusca)
                .where(FatoBusca.criado_em >= desde)
            ).scalar()
            or 0
        )

    acessos_hoje, unicos_hoje = _acessos(inicio_dia)
    acessos_mes, unicos_mes = _acessos(inicio_mes)
    acessos_ano, unicos_ano = _acessos(inicio_ano)

    # Ultimos 30 dias pro grafico - `date_trunc` agrupa por dia no proprio SQL.
    dia_col = func.date_trunc("day", FatoAcessoSite.criado_em).label("dia")
    inicio_serie = inicio_dia - timedelta(days=29)
    serie_acessos = [
        PontoAcessoDia(dia=linha[0].date(), acessos=linha[1], visitantes_unicos=linha[2])
        for linha in sessao.execute(
            select(
                dia_col,
                func.count(),
                func.count(func.distinct(FatoAcessoSite.visitante_id)),
            )
            .where(FatoAcessoSite.criado_em >= inicio_serie)
            .group_by(dia_col)
            .order_by(dia_col)
        )
    ]

    inicio_termos = agora - timedelta(days=30)
    termos = sessao.execute(
        select(FatoBusca.termo)
        .where(FatoBusca.criado_em >= inicio_termos)
        .group_by(FatoBusca.termo)
        .order_by(func.count().desc())
        .limit(10)
    ).scalars().all()

    return VisaoGeralAdmin(
        online_agora=telemetria_site.online_agora(),
        acessos_hoje=acessos_hoje,
        acessos_mes=acessos_mes,
        acessos_ano=acessos_ano,
        visitantes_unicos_hoje=unicos_hoje,
        visitantes_unicos_mes=unicos_mes,
        visitantes_unicos_ano=unicos_ano,
        buscas_hoje=_buscas(inicio_dia),
        buscas_mes=_buscas(inicio_mes),
        buscas_ano=_buscas(inicio_ano),
        serie_acessos=serie_acessos,
        termos_mais_buscados=list(termos),
    )


# ---------------------------------------------------------------------------
# Sistema - CPU/RAM/disco (Netdata na VPS, psutil local)
# ---------------------------------------------------------------------------


def _fmt_bytes(valor: float) -> str:
    tamanho = float(valor)
    for unidade in ("B", "KiB", "MiB", "GiB"):
        if tamanho < 1024 or unidade == "GiB":
            return f"{tamanho:.1f} {unidade}"
        tamanho /= 1024
    return f"{tamanho:.1f} TiB"  # pragma: no cover - inalcancavel na pratica


def _sistema_via_netdata(settings: Settings) -> SaudeSistema | None:
    """`None` quando o Netdata nao respondeu - `sistema()` cai pro fallback."""
    try:
        resposta = requests.get(
            f"{settings.netdata_url.rstrip('/')}/api/v1/allmetrics",
            params={"format": "json"},
            timeout=settings.netdata_timeout_segundos,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except Exception as exc:  # noqa: BLE001 - cai pro fallback local
        logger.info(
            "Netdata indisponivel, usando fallback local",
            extra={"erro": f"{type(exc).__name__}: {exc}"},
        )
        return None

    cpu = None
    ociosa = (dados.get("system.cpu", {}).get("dimensions", {}).get("idle") or {}).get(
        "value"
    )
    if ociosa is not None:
        uso = max(0.0, 100.0 - ociosa)
        cpu = MetricaSistema(percentual=round(uso, 1), detalhe=f"{uso:.1f}% em uso")

    memoria = None
    ram_dims = dados.get("system.ram", {}).get("dimensions", {})
    if ram_dims:
        usado = (ram_dims.get("used") or {}).get("value") or 0.0
        livre = (ram_dims.get("free") or {}).get("value") or 0.0
        cache = (ram_dims.get("cached") or {}).get("value") or 0.0
        buffers = (ram_dims.get("buffers") or {}).get("value") or 0.0
        total = usado + livre + cache + buffers
        if total > 0:
            perc = usado / total * 100
            memoria = MetricaSistema(
                percentual=round(perc, 1),
                detalhe=f"{usado / 1024:.1f} GiB de {total / 1024:.1f} GiB",
            )

    disco = None
    disco_dims = dados.get("disk_space./", {}).get("dimensions", {})
    if disco_dims:
        usado = (disco_dims.get("used") or {}).get("value") or 0.0
        disponivel = (disco_dims.get("avail") or {}).get("value") or 0.0
        total = usado + disponivel
        if total > 0:
            perc = usado / total * 100
            disco = MetricaSistema(
                percentual=round(perc, 1),
                detalhe=f"{usado:.1f} GiB de {total:.1f} GiB",
            )

    carga = dados.get("system.load", {}).get("dimensions", {})
    return SaudeSistema(
        fonte="netdata",
        cpu=cpu,
        memoria=memoria,
        disco=disco,
        carga_1min=(carga.get("load1") or {}).get("value"),
        carga_5min=(carga.get("load5") or {}).get("value"),
        carga_15min=(carga.get("load15") or {}).get("value"),
    )


def _sistema_via_psutil() -> SaudeSistema:
    """O que se ve rodando local, sem VPS/Netdata pra consultar - reflete a
    maquina onde o container esta, nao necessariamente um host inteiro."""
    import psutil

    cpu_pct = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disco = psutil.disk_usage("/")

    return SaudeSistema(
        fonte="local",
        cpu=MetricaSistema(percentual=round(cpu_pct, 1), detalhe=f"{cpu_pct:.1f}% em uso"),
        memoria=MetricaSistema(
            percentual=round(mem.percent, 1),
            detalhe=f"{_fmt_bytes(mem.used)} de {_fmt_bytes(mem.total)}",
        ),
        disco=MetricaSistema(
            percentual=round(disco.percent, 1),
            detalhe=f"{_fmt_bytes(disco.used)} de {_fmt_bytes(disco.total)}",
        ),
    )


@router.get(
    "/sistema", response_model=SaudeSistema, dependencies=[Depends(exigir_admin)]
)
def sistema() -> SaudeSistema:
    settings = get_settings()
    return _sistema_via_netdata(settings) or _sistema_via_psutil()


# ---------------------------------------------------------------------------
# Banco - tamanho + linhas por tabela
# ---------------------------------------------------------------------------

#: So os modelos ja importados - contagem por ORM (`select(func.count())
#: .select_from(Modelo)`), nunca SQL com nome de tabela montado por string.
_TABELAS_PRINCIPAIS: list[tuple[str, type]] = [
    ("raw_data", RawData),
    ("dim_jogo_steam", DimJogoSteam),
    ("fato_avaliacao_steam", FatoAvaliacaoSteam),
    ("fato_snapshot_jogo_steam", FatoSnapshotJogoSteam),
    ("dim_jogo_xbox", DimJogoXbox),
    ("fato_snapshot_jogo_xbox", FatoSnapshotJogoXbox),
    ("dim_jogo", DimJogo),
    ("dim_jogador", DimJogador),
    ("dim_partida", DimPartida),
    ("fato_minuto_partida", FatoMinutoPartida),
    ("agenda_partida", AgendaPartida),
    ("fato_lol_jogador_partida", FatoLolJogadorPartida),
    ("ranking_externo", RankingExterno),
    ("fato_acesso_site", FatoAcessoSite),
    ("fato_busca", FatoBusca),
]


@router.get("/banco", response_model=SaudeBanco, dependencies=[Depends(exigir_admin)])
def banco(sessao: Session = Depends(get_db)) -> SaudeBanco:
    tamanho = sessao.execute(
        select(func.pg_size_pretty(func.pg_database_size(func.current_database())))
    ).scalar_one()

    tabelas = [
        TabelaBanco(
            tabela=nome,
            linhas=sessao.execute(select(func.count()).select_from(modelo)).scalar_one(),
        )
        for nome, modelo in _TABELAS_PRINCIPAIS
    ]
    tabelas.sort(key=lambda t: t.linhas, reverse=True)

    return SaudeBanco(tamanho_texto=tamanho, tabelas=tabelas)
