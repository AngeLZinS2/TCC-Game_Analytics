"""Painel admin - login por conta (Firebase) + estatisticas do site.

Reusa a mesma conta do resto do site (`usuario.exigir_usuario` - Google,
GitHub ou e-mail/senha via Firebase Auth): nao ha login separado. Acesso ao
painel e uma questao de autorizacao, nao autenticacao - o uid da conta
logada precisa estar em `ADMIN_FIREBASE_UIDS` (`.env`), uma lista de contas
liberadas, nunca uma senha propria.

Sem `ADMIN_FIREBASE_UIDS` configurada, o painel inteiro responde 503 - mesmo
padrao do assistente sem `OPENROUTER_API_KEY`: a ausencia da configuracao e
o proprio "desligado", sem precisar de outro flag. Uma conta logada mas fora
da lista recebe 403, nao 401 - a diferenca importa pro frontend distinguir
"precisa logar" de "logado, mas sem acesso".
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from controllers.routers.usuario import UsuarioAtual, exigir_usuario
from models.models import (
    AgendaPartida,
    DimAppSteamNome,
    DimJogador,
    DimJogo,
    DimJogoSteam,
    DimJogoXbox,
    DimPartida,
    DimUsuario,
    FatoAcessoSite,
    FatoAvaliacaoSteam,
    FatoBusca,
    FatoLolJogadorPartida,
    FatoMinutoPartida,
    EventoSteam,
    FatoSnapshotJogoSteam,
    FatoSnapshotJogoXbox,
    HistoricoPrecoSteam,
    PromocaoSteam,
    RankingExterno,
    RawData,
    SincronizacaoSteam,
)
from models.session import get_db
from services.ml import telemetria_site
from views.schemas import (
    ContaResumo,
    EventoAtividade,
    ListaAtividade,
    ListaContasAdmin,
    MetricaSistema,
    PontoAcessoDia,
    SaudeBanco,
    SaudeCatalogoSteam,
    SaudeServicos,
    SaudeSistema,
    ServicoColeta,
    SincronizacaoSteamStatus,
    StatusAdmin,
    TermoBuscado,
    TabelaBanco,
    VisaoGeralAdmin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Autenticacao
# ---------------------------------------------------------------------------


def _uids_admin(settings: Settings) -> set[str]:
    return {
        uid.strip() for uid in (settings.admin_firebase_uids or "").split(",") if uid.strip()
    }


def exigir_admin(usuario: UsuarioAtual = Depends(exigir_usuario)) -> UsuarioAtual:
    """Dependencia do FastAPI - toda rota admin usa isto.

    Empilha em cima de `exigir_usuario`: primeiro precisa de uma conta
    logada (401 sem isso, como qualquer outra rota protegida), depois checa
    se o uid dela esta na lista de administradores.
    """
    uids_admin = _uids_admin(get_settings())
    if not uids_admin:
        raise HTTPException(
            status_code=503, detail="painel admin nao configurado (ADMIN_FIREBASE_UIDS)"
        )
    if usuario.firebase_uid not in uids_admin:
        raise HTTPException(status_code=403, detail="conta sem acesso ao painel admin")
    return usuario


@router.get("/eu-sou-admin", response_model=StatusAdmin)
def eu_sou_admin(usuario: UsuarioAtual = Depends(exigir_usuario)) -> StatusAdmin:
    """So exige login (nao `exigir_admin`) - e o proprio jeito da conta
    descobrir se tem acesso, pra decidir se mostra o link do painel na
    barra lateral. Uma conta sem acesso nunca ve `/admin` mencionado em
    lugar nenhum, alem de continuar barrada no backend se tentar entrar
    pela URL direto.
    """
    return StatusAdmin(admin=usuario.firebase_uid in _uids_admin(get_settings()))


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

    # Ontem ATE A MESMA HORA - nao o dia inteiro.
    #
    # Comparar "hoje" (dia em curso) com "ontem fechado" e comparar coisas
    # diferentes: as 9h da manha o painel mostraria -85% todo santo dia, e
    # quem lesse aprenderia a ignorar a variacao. Recortando ontem no mesmo
    # ponto do dia, "+12%" passa a significar "hoje esta melhor que ontem
    # nesta altura", que e a unica leitura util de um dia incompleto.
    decorrido = agora - inicio_dia
    inicio_ontem = inicio_dia - timedelta(days=1)
    fim_ontem = inicio_ontem + decorrido

    linha_ontem = sessao.execute(
        select(
            func.count(),
            func.count(func.distinct(FatoAcessoSite.visitante_id)),
        ).where(
            FatoAcessoSite.criado_em >= inicio_ontem,
            FatoAcessoSite.criado_em < fim_ontem,
        )
    ).first()
    acessos_ontem = (linha_ontem[0] or 0) if linha_ontem else 0
    unicos_ontem = (linha_ontem[1] or 0) if linha_ontem else 0
    buscas_ontem = (
        sessao.execute(
            select(func.count())
            .select_from(FatoBusca)
            .where(
                FatoBusca.criado_em >= inicio_ontem,
                FatoBusca.criado_em < fim_ontem,
            )
        ).scalar()
        or 0
    )

    # Ultimos 30 dias pro grafico - `date_trunc` agrupa por dia no proprio SQL.
    dia_col = func.date_trunc("day", FatoAcessoSite.criado_em).label("dia")
    inicio_serie = inicio_dia - timedelta(days=29)

    # Buscas por dia, na mesma janela - o grafico sobrepoe as tres series, e
    # antes a de buscas era a unica sem dado diario. Consulta a parte porque
    # sao tabelas diferentes; casadas por data no Python, que e barato pra 30
    # pontos e evita um FULL OUTER JOIN so pra isso.
    dia_busca = func.date_trunc("day", FatoBusca.criado_em).label("dia")
    buscas_por_dia = {
        linha[0].date(): linha[1]
        for linha in sessao.execute(
            select(dia_busca, func.count())
            .where(FatoBusca.criado_em >= inicio_serie)
            .group_by(dia_busca)
        )
    }

    serie_acessos = [
        PontoAcessoDia(
            dia=linha[0].date(),
            acessos=linha[1],
            visitantes_unicos=linha[2],
            buscas=buscas_por_dia.get(linha[0].date(), 0),
        )
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

    # Quantos dias de historico existem AO TODO (nao so na janela de 30): o
    # seletor de periodo da tela nao pode oferecer "90 dias" quando ha 3.
    historico_dias = (
        sessao.execute(
            select(func.count(func.distinct(func.date(FatoAcessoSite.criado_em))))
        ).scalar()
        or 0
    )

    # A contagem sempre esteve aqui (e ela que ordena) - so era descartada,
    # e a tela mostrava um ranking sem numero.
    inicio_termos = agora - timedelta(days=30)
    termos = [
        TermoBuscado(termo=linha[0], buscas=linha[1])
        for linha in sessao.execute(
            select(FatoBusca.termo, func.count().label("buscas"))
            .where(FatoBusca.criado_em >= inicio_termos)
            .group_by(FatoBusca.termo)
            .order_by(func.count().desc(), FatoBusca.termo)
            .limit(10)
        )
    ]

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
        acessos_ontem=acessos_ontem,
        visitantes_unicos_ontem=unicos_ontem,
        buscas_ontem=buscas_ontem,
        historico_dias=int(historico_dias),
        serie_acessos=serie_acessos,
        termos_mais_buscados=termos,
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
    # `system.uptime` do Netdata ja vem em segundos - e o uptime do HOST,
    # que e o numero que interessa no painel (o container reinicia a cada
    # deploy; a VPS, nao).
    uptime = (
        dados.get("system.uptime", {}).get("dimensions", {}).get("uptime") or {}
    ).get("value")

    return SaudeSistema(
        fonte="netdata",
        cpu=cpu,
        memoria=memoria,
        disco=disco,
        carga_1min=(carga.get("load1") or {}).get("value"),
        carga_5min=(carga.get("load5") or {}).get("value"),
        carga_15min=(carga.get("load15") or {}).get("value"),
        uptime_segundos=float(uptime) if uptime is not None else None,
    )


def _sistema_via_psutil() -> SaudeSistema:
    """O que se ve rodando local, sem VPS/Netdata pra consultar - reflete a
    maquina onde o container esta, nao necessariamente um host inteiro."""
    import psutil

    cpu_pct = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disco = psutil.disk_usage("/")
    # Rodando local isto e o uptime do CONTAINER, nao de um host - por isso
    # `fonte="local"` acompanha o numero na tela: 5 minutos aqui significa
    # "subi o container agora", nao "a maquina reiniciou".
    uptime = max(0.0, time.time() - psutil.boot_time())

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
        uptime_segundos=uptime,
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
    ("dim_app_steam_nome", DimAppSteamNome),
    ("fato_avaliacao_steam", FatoAvaliacaoSteam),
    ("fato_snapshot_jogo_steam", FatoSnapshotJogoSteam),
    ("steam_sincronizacao", SincronizacaoSteam),
    ("steam_historico_preco", HistoricoPrecoSteam),
    ("steam_promocoes", PromocaoSteam),
    ("steam_eventos", EventoSteam),
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


# ---------------------------------------------------------------------------
# Catalogo Steam (Fase 35) - progresso do crawl completo + sync incremental.
#
# Diferente de `/banco`, que so conta linhas: aqui mostra o CHECKPOINT em si
# (`steam_sincronizacao`) - concluido ou nao, ultimo appid, quando rodou pela
# ultima vez. `dim_jogo_steam` (catalogo MONITORADO, exibido em `/banco`) nao
# muda com o crawl - so `dim_app_steam_nome` (o indice completo) muda, e e
# isso que este endpoint deixa claro.
# ---------------------------------------------------------------------------


@router.get(
    "/steam-catalogo",
    response_model=SaudeCatalogoSteam,
    dependencies=[Depends(exigir_admin)],
)
def steam_catalogo(sessao: Session = Depends(get_db)) -> SaudeCatalogoSteam:
    fases = [
        SincronizacaoSteamStatus(
            fase=linha.tipo_sincronizacao,
            status=linha.status,
            last_appid=linha.last_appid,
            registros_processados=linha.registros_processados,
            registros_criados=linha.registros_criados,
            registros_atualizados=linha.registros_atualizados,
            registros_falhos=linha.registros_falhos,
            iniciada_em=linha.iniciada_em,
            concluida_em=linha.concluida_em,
            atualizado_em=linha.atualizado_em,
        )
        for linha in sessao.execute(
            select(SincronizacaoSteam).order_by(SincronizacaoSteam.tipo_sincronizacao)
        ).scalars()
    ]
    apps_indexados = sessao.execute(
        select(func.count()).select_from(DimAppSteamNome)
    ).scalar_one()

    return SaudeCatalogoSteam(fases=fases, apps_indexados=apps_indexados)


# ---------------------------------------------------------------------------
# Contas - quantas existem, so nome + data de criacao (LGPD: sem e-mail, sem
# uid do Firebase - nada que identifique a pessoa fora do proprio site)
# ---------------------------------------------------------------------------


@router.get("/contas", response_model=ListaContasAdmin, dependencies=[Depends(exigir_admin)])
def contas(
    sessao: Session = Depends(get_db), limite: int = Query(default=500, ge=1, le=2000)
) -> ListaContasAdmin:
    total = sessao.execute(select(func.count()).select_from(DimUsuario)).scalar_one()

    linhas = sessao.execute(
        select(DimUsuario.nome_exibicao, DimUsuario.criado_em)
        .order_by(DimUsuario.criado_em.desc())
        .limit(limite)
    ).all()

    return ListaContasAdmin(
        total=total,
        contas=[
            ContaResumo(nome_exibicao=nome, criado_em=criado_em) for nome, criado_em in linhas
        ],
    )


# ---------------------------------------------------------------------------
# Servicos - frescor por fonte de coleta
#
# **Por que frescor e nao latencia.** O painel de referencia pedia "API PlayDB
# 42ms, Banco 8ms, Steam Sync 1m ago". Deste trio, so o "1m ago" existe neste
# projeto: nao ha medicao de tempo de resposta de API em lugar nenhum - nem
# tabela, nem coluna, nem coletor que registre isso. Inventar milissegundos
# seria o tipo de numero decorativo que o painel inteiro existe pra evitar.
#
# O que o banco sabe de verdade e QUANDO cada fonte entregou dado pela ultima
# vez: `raw_data` grava `fonte` + `coletado_em` a cada payload, com indice
# proprio (`ix_raw_data_fonte_coletado_em`). Cruzando isso com a cadencia
# configurada da tarefa que alimenta a fonte, da pra afirmar algo util e
# verdadeiro: "esta fonte deveria ter coletado ha 10 minutos e nao coletou".
#
# A unica latencia do painel e a do banco, medida NA HORA (`SELECT 1`) - nao
# lida de um historico que nao existe.
# ---------------------------------------------------------------------------

#: `fonte` de `raw_data` -> `nome` da Tarefa do agendador que a alimenta.
#:
#: Precisa ser explicito porque os dois vocabularios nasceram separados: a
#: tarefa `precos` grava a fonte `itad`, `tempo_jogo` grava `hltb`, as sete
#: `pandascore_*` gravam a mesma fonte `pandascore`. Quando uma fonte tem
#: mais de uma tarefa, vale a MAIS FREQUENTE - e ela que define o quao velho
#: o dado pode ficar antes de ser um problema.
#:
#: Fonte fora deste mapa nao vira alarme: vira `sem_cadencia` ("existe, mas
#: nao ha tarefa agendada esperando dela"). E o caso real do `hltv`,
#: aposentado quando o PandaScore assumiu.
_TAREFA_POR_FONTE: dict[str, tuple[str, ...]] = {
    "steam": ("steam", "steam_precos_alterados"),
    "steam_online": ("steam_online",),
    "steam_ofertas": ("steam_ofertas",),
    "steam_catalogo": ("steam_catalogo",),
    "itad": ("precos",),
    "hltb": ("tempo_jogo",),
    "resumo_reviews": ("resumo_reviews",),
    "xbox": ("xbox",),
    "opendota": ("opendota",),
    "liquipedia": ("liquipedia", "equipes", "brackets"),
    "vlr": ("vlr_agenda", "vlr"),
    "vlr_detalhes": ("vlr_detalhes",),
    "vlr_rankings": ("vlr_rankings",),
    "lolesports": ("lolesports", "lol_cenario"),
    "pandascore": ("pandascore_cs", "pandascore_lol", "pandascore_val"),
    "opgg_esports": ("esports_opgg",),
    "valve": ("ranking",),
    "ubi_r6": ("ubi_r6",),
    "rlcs": ("rlcs",),
    "dltv": ("dltv",),
    "owcs": ("owcs",),
    "dota_herois": ("herois_dota",),
    "lol_campeoes": ("campeoes_lol",),
    "valorant_agentes": ("agentes_valorant",),
}

#: Folga antes de chamar uma fonte de atrasada. Uma tarefa que roda a cada
#: 60 min quase nunca fecha exatamente em 60 - ela espera a anterior, leva o
#: proprio tempo de execucao, e reagenda depois. Sem folga, metade do painel
#: viveria amarelo sem nada estar errado.
_FOLGA_ATRASO = 1.5
#: A partir daqui nao e mais "rodada lenta", e "parou".
_FATOR_PARADO = 4.0


def _cadencia_por_fonte() -> dict[str, int]:
    """`{fonte: minutos}` da tarefa mais frequente que alimenta cada fonte.

    Le do proprio `montar_tarefas()` em vez de repetir os numeros aqui: o
    agendador e a autoridade sobre a cadencia, e um intervalo mudado no
    `.env` tem que mudar o painel junto.
    """
    from agendador import montar_tarefas

    intervalos = {
        tarefa.nome: tarefa.intervalo_segundos
        for tarefa in montar_tarefas(get_settings())
    }
    cadencias: dict[str, int] = {}
    for fonte, nomes in _TAREFA_POR_FONTE.items():
        candidatos = [intervalos[nome] for nome in nomes if nome in intervalos]
        if candidatos:
            cadencias[fonte] = max(1, round(min(candidatos) / 60))
    return cadencias


def _status_do_frescor(minutos: float | None, cadencia: int | None) -> str:
    if cadencia is None:
        return "sem_cadencia"
    if minutos is None:
        return "parado"
    if minutos <= cadencia * _FOLGA_ATRASO:
        return "ok"
    if minutos <= cadencia * _FATOR_PARADO:
        return "atrasado"
    return "parado"


@router.get(
    "/servicos", response_model=SaudeServicos, dependencies=[Depends(exigir_admin)]
)
def servicos(sessao: Session = Depends(get_db)) -> SaudeServicos:
    """Frescor por fonte de coleta + latencia do banco medida agora."""
    agora = datetime.now(timezone.utc)
    cadencias = _cadencia_por_fonte()

    linhas = sessao.execute(
        select(
            RawData.fonte,
            func.count().label("payloads"),
            func.max(RawData.coletado_em).label("ultima"),
        )
        .group_by(RawData.fonte)
        .order_by(RawData.fonte)
    ).all()

    servicos_lista: list[ServicoColeta] = []
    for linha in linhas:
        minutos = (
            (agora - linha.ultima).total_seconds() / 60 if linha.ultima else None
        )
        cadencia = cadencias.get(linha.fonte)
        servicos_lista.append(
            ServicoColeta(
                fonte=linha.fonte,
                ultima_coleta=linha.ultima,
                minutos_desde=round(minutos, 1) if minutos is not None else None,
                intervalo_minutos=cadencia,
                status=_status_do_frescor(minutos, cadencia),
                payloads=linha.payloads,
            )
        )

    # Ordem util pra quem opera: o que exige acao primeiro. Dentro do mesmo
    # status, o mais atrasado na frente.
    ordem = {"parado": 0, "atrasado": 1, "ok": 2, "sem_cadencia": 3}
    servicos_lista.sort(
        key=lambda s: (ordem.get(s.status, 9), -(s.minutos_desde or 0))
    )

    # A UNICA latencia real do painel - medida nesta requisicao, nao lida de
    # um historico que nao existe.
    inicio = time.perf_counter()
    try:
        sessao.execute(select(1)).scalar()
        latencia = round((time.perf_counter() - inicio) * 1000, 1)
    except Exception:  # noqa: BLE001 - se o banco nao responde, nao ha numero
        latencia = None

    # Contagens, nao um palpite sobre o agendador estar de pe (ver a nota em
    # `SaudeServicos`). Quem interpreta e a tela.
    return SaudeServicos(
        servicos=servicos_lista,
        banco_latencia_ms=latencia,
        fontes_paradas=sum(1 for s in servicos_lista if s.status == "parado"),
        fontes_atrasadas=sum(1 for s in servicos_lista if s.status == "atrasado"),
        fontes_total=len(servicos_lista),
    )


# ---------------------------------------------------------------------------
# Atividade - eventos reais, derivados
#
# Nao existe tabela de log neste projeto, e a alternativa a inventar eventos
# nao e uma tela vazia: e olhar pro que o banco JA registra com carimbo de
# tempo proprio. Tres origens, todas verificaveis:
#
#   * `raw_data`            - a ultima coleta de cada fonte;
#   * `dim_usuario`         - contas criadas;
#   * `steam_sincronizacao` - o estado de cada fase do crawl.
#
# Cada evento aqui aconteceu de fato. O que o painel NAO tem e historico de
# eventos passados (so o ultimo de cada tipo) - e isso a tela diz, em vez de
# fingir um fluxo continuo.
# ---------------------------------------------------------------------------


@router.get(
    "/atividade", response_model=ListaAtividade, dependencies=[Depends(exigir_admin)]
)
def atividade(
    sessao: Session = Depends(get_db), limite: int = Query(default=12, ge=1, le=50)
) -> ListaAtividade:
    eventos: list[EventoAtividade] = []

    # Coletas: a mais recente de cada fonte.
    for linha in sessao.execute(
        select(RawData.fonte, func.max(RawData.coletado_em).label("ultima"))
        .group_by(RawData.fonte)
        .order_by(func.max(RawData.coletado_em).desc())
        .limit(limite)
    ):
        if linha.ultima is None:
            continue
        eventos.append(
            EventoAtividade(
                tipo="coleta",
                titulo=f"{linha.fonte} coletado",
                quando=linha.ultima,
            )
        )

    # Contas criadas - so a data, nunca nome/e-mail (mesmo cuidado de LGPD
    # que `/contas` ja tem: o painel conta pessoas, nao as identifica).
    for (criado_em,) in sessao.execute(
        select(DimUsuario.criado_em).order_by(DimUsuario.criado_em.desc()).limit(5)
    ):
        if criado_em is None:
            continue
        eventos.append(
            EventoAtividade(tipo="conta", titulo="nova conta criada", quando=criado_em)
        )

    # Sincronizacao da Steam: uma linha por fase, com o nivel vindo do dado
    # (falhas > 0 vira atencao de verdade, nao enfeite).
    for sync in sessao.execute(select(SincronizacaoSteam)).scalars():
        quando = sync.concluida_em or sync.atualizado_em
        if quando is None:
            continue
        eventos.append(
            EventoAtividade(
                tipo="sincronizacao",
                titulo=f"sync Steam ({sync.tipo_sincronizacao}): {sync.status}",
                detalhe=(
                    f"{sync.registros_processados} processados, "
                    f"{sync.registros_falhos} falhas"
                ),
                quando=quando,
                nivel="atencao" if sync.registros_falhos else "ok",
            )
        )

    eventos.sort(key=lambda e: e.quando, reverse=True)
    return ListaAtividade(eventos=eventos[:limite])
