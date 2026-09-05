"""Agendador de coleta: o que transforma o script num pipeline.

Ate aqui a plataforma coletava quando alguem digitava `cli.py collect`. O
resultado disso estava medido no banco: 3 janelas de coleta da Steam cobrindo 16
horas, com dois snapshots por jogo. Uma tabela de fato desenhada para serie
temporal, com uma serie que nao existia. E o modelo de confronto ajustado sobre
71 partidas, quando a agenda ja listava 83 que ainda seriam jogadas.

Nenhum dos dois problemas se resolve com codigo melhor - os dois se resolvem
coletando de novo, muitas vezes, sozinho.

**Por que um laco proprio e nao um cron do sistema.** O cron seria menos codigo,
mas viveria fora do projeto: nao apareceria no `docker-compose.yml`, nao seria
versionado junto e dependeria de configuracao manual em cada maquina. Aqui a
periodicidade e parte da aplicacao, e sobe com ela.

**Por que um servico separado e nao um `APScheduler` dentro da API.** Coleta e
trabalho de lote: demorada, com rede lenta, e que nao deve nada ao ciclo de vida
de um servidor HTTP. Dentro da API, uma coleta longa competiria com as
requisicoes do dashboard, e reiniciar a API para um deploy interromperia a
ingestao. Separado, cada um cai e sobe por conta.

**Repetir e seguro.** A coleta da Steam grava em `(app_id, janela_coleta)`, que
e unico, com a janela truncada por hora - rodar duas vezes na mesma hora e um
UPDATE, nao uma linha nova. A da OpenDota pula partidas ja no banco. Por isso o
agendador pode coletar assim que sobe, sem que um restart em laco suje o dado.

**O desligamento e limpo entre tarefas, nao dentro de uma.** O SIGTERM acorda a
espera na hora, mas uma coleta ja em curso vai ate o fim - nao ha como
interromper o coletor no meio sem enfiar o sinal na assinatura dele. Medido: com
os 10s padrao do Docker, parar durante uma coleta dava exit 137. Por isso o
`docker-compose.yml` da 180s de prazo. Se ainda assim o prazo estourar, o dano e
zero: os payloads ja estao em `data/raw/` e a carga e transacional.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from collectors.base import CollectionResult
from config import Settings, get_settings
from etl.raw_storage import RawStorage
from logging_config import configurar_logging

logger = logging.getLogger("agendador")

#: Quanto esperar antes de tentar de novo a fonte que falhou.
#:
#: Nao e o intervalo normal: uma fonte fora do ar as 3h nao deve ficar mais 6
#: horas em silencio, nem ser martelada a cada segundo. Cinco minutos e curto o
#: bastante para aproveitar uma queda passageira e longo o bastante para nao
#: virar tempestade de tentativas.
ESPERA_APOS_FALHA_SEGUNDOS = 300


@dataclass
class Tarefa:
    """Uma fonte e a periodicidade dela."""

    nome: str
    intervalo_segundos: float
    executar: Callable[[Settings, RawStorage], CollectionResult]

    #: Momento (monotonic) em que esta tarefa deve rodar de novo.
    proxima_em: float = 0.0
    execucoes: int = 0
    falhas: int = 0

    def reagendar(self, agora: float, sucesso: bool) -> None:
        espera = self.intervalo_segundos if sucesso else ESPERA_APOS_FALHA_SEGUNDOS
        self.proxima_em = agora + espera


def _apps_monitorados() -> list[int]:
    """Os app_ids que ja estao no banco.

    **Nao e a semente.** O `SteamCollector` sem `app_ids` cai na lista fixa de
    `collectors/seeds/steam_apps.json`, que faz sentido para um primeiro
    `collect` numa base vazia. Para o agendador ela seria um bug silencioso:
    todo jogo trazido pela busca da tela - a coleta sob demanda de
    `/api/steam/coletar` - ficaria com o unico snapshot do dia em que entrou, e
    a serie dele nunca cresceria. A tela mostraria "so existe uma coleta ate
    agora" para sempre, sem que nada estivesse quebrado.

    Monitorar quem esta no banco faz a plataforma acompanhar o que foi trazido
    para ela, em vez de uma lista decidida antes de alguem usar o produto.

    Devolve vazio quando o banco esta vazio, e ai a semente e a resposta certa.
    """
    from sqlalchemy import select

    from db.models import DimJogoSteam
    from db.session import session_scope

    with session_scope() as sessao:
        return list(sessao.scalars(select(DimJogoSteam.app_id)))


def _coletar_steam(settings: Settings, storage: RawStorage) -> CollectionResult:
    from collectors.steam_collector import SteamCollector, top_mais_jogados

    monitorados = _apps_monitorados()

    # O ranking oficial de mais jogados entra a cada rodada, SOMANDO aos que ja
    # sao monitorados. E o que faz o catalogo acompanhar o que esta em alta sem
    # ninguem cadastrar nada - e a uniao (em vez da substituicao) e o que
    # garante que um jogo trazido pela busca da tela continue com a serie
    # crescendo mesmo depois de cair do top.
    descobertos: list[int] = []
    if settings.steam_top_jogados:
        do_ranking = top_mais_jogados(settings.steam_top_jogados, settings)
        ja_conhecidos = set(monitorados)
        descobertos = [app for app in do_ranking if app not in ja_conhecidos]
        monitorados = monitorados + descobertos

    logger.info(
        "apps monitorados",
        extra={
            "quantidade": len(monitorados) or "semente",
            "novos_do_ranking": len(descobertos),
        },
    )

    # `app_ids=None` faz o coletor usar a semente - o que so vale numa base
    # vazia, no primeiro `up`.
    coletor = SteamCollector(
        raw_storage=storage, app_ids=monitorados or None, settings=settings
    )
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_opendota(settings: Settings, storage: RawStorage) -> CollectionResult:
    from collectors.opendota_collector import OpenDotaCollector

    coletor = OpenDotaCollector(
        raw_storage=storage,
        limite=settings.agendador_opendota_limite,
        settings=settings,
        # O ponto do agendador e trazer o que ainda nao temos. Recoletar as
        # mesmas 100 partidas a cada seis horas gastaria a API publica para
        # reescrever linhas identicas.
        pular_existentes=True,
    )
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _somar(parciais: list[CollectionResult], fonte: str) -> CollectionResult:
    """Junta os resultados de varias wikis num resultado so.

    `sucesso` e verdadeiro se ALGUMA wiki respondeu. Exigir todas faria uma wiki
    dormente derrubar o resultado das outras 70, e reagendar a varredura inteira
    para daqui a cinco minutos por causa dela.
    """
    return CollectionResult(
        fonte=fonte,
        sucesso=any(p.sucesso for p in parciais) if parciais else False,
        registros_coletados=sum(p.registros_coletados for p in parciais),
        registros_processados=sum(p.registros_processados for p in parciais),
        registros_carregados=sum(p.registros_carregados for p in parciais),
        falhas=sum(1 for p in parciais if not p.sucesso),
    )


def _coletar_liquipedia(settings: Settings, storage: RawStorage) -> CollectionResult:
    """A agenda de TODAS as wikis que tem `Liquipedia:Matches`.

    Uma chamada por wiki - sao 66, cerca de tres minutos no intervalo padrao.
    Barato o suficiente para varrer tudo a cada rodada.
    """
    from collectors.liquipedia_collector import LiquipediaCollector
    from etl.wikis import com_agenda

    parciais: list[CollectionResult] = []
    wikis = com_agenda()
    for posicao, wiki in enumerate(wikis):
        coletor = LiquipediaCollector(
            raw_storage=storage, settings=settings, wiki=wiki.codigo
        )
        try:
            parciais.append(coletor.run(carregar=True))
        except Exception as exc:  # noqa: BLE001 - uma wiki nao derruba a varredura
            logger.warning(
                "agenda de uma wiki falhou",
                extra={"wiki": wiki.codigo, "erro": f"{type(exc).__name__}: {exc}"},
            )
            parciais.append(CollectionResult(fonte="liquipedia", sucesso=False))
        finally:
            coletor.close()

        # Cada `LiquipediaCollector` cria o proprio `RateLimitedClient` do
        # zero - o intervalo minimo entre chamadas so vale DENTRO de uma
        # instancia, nunca ENTRE wikis deste laco. Sem este sleep, 66 wikis
        # saiam a ~1 chamada/segundo, e foi exatamente isso que aconteceu:
        # a Liquipedia bloqueou o IP com 429 por mais de uma hora depois de
        # uma varredura sem pausa nenhuma entre wikis.
        if posicao < len(wikis) - 1:
            time.sleep(settings.liquipedia_rate_limit_seconds)

    return _somar(parciais, "liquipedia")


#: Onde o rodizio parou. Estado em memoria de proposito: perde-se no restart, e
#: perder significa recomecar a varredura, nao corromper nada.
_proxima_wiki_de_equipes = 0


def _coletar_equipes(settings: Settings, storage: RawStorage) -> CollectionResult:
    """As paginas de equipe, algumas wikis por rodada.

    Rodizio em vez de varredura completa: ver `agendador_equipes_por_rodada`.
    """
    global _proxima_wiki_de_equipes

    from collectors.liquipedia_wiki_collector import LiquipediaWikiCollector
    from etl.wikis import com_times

    todas = com_times()
    if not todas:
        return CollectionResult(fonte="liquipedia", sucesso=True)

    quantas = min(settings.agendador_equipes_por_rodada, len(todas))
    lote = [
        todas[(_proxima_wiki_de_equipes + i) % len(todas)] for i in range(quantas)
    ]
    _proxima_wiki_de_equipes = (_proxima_wiki_de_equipes + quantas) % len(todas)

    logger.info(
        "rodizio de equipes",
        extra={"wikis": [w.codigo for w in lote], "de": len(todas)},
    )

    parciais: list[CollectionResult] = []
    for posicao, wiki in enumerate(lote):
        coletor = LiquipediaWikiCollector(
            raw_storage=storage, settings=settings, wiki=wiki.codigo
        )
        try:
            parciais.append(coletor.run(carregar=True))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "equipes de uma wiki falharam",
                extra={"wiki": wiki.codigo, "erro": f"{type(exc).__name__}: {exc}"},
            )
            parciais.append(CollectionResult(fonte="liquipedia", sucesso=False))
        finally:
            coletor.close()

        # Mesmo motivo do sleep em `_coletar_liquipedia`: o cliente e novo a
        # cada wiki, entao o intervalo minimo nao sobrevive entre iteracoes
        # deste laco sem um sleep explicito aqui.
        if posicao < len(lote) - 1:
            time.sleep(settings.liquipedia_rate_limit_seconds)

    return _somar(parciais, "liquipedia")


#: Onde o rodizio de brackets parou. Mesmo motivo do de equipes: em memoria,
#: perde-se no restart, e perder so significa recomecar a varredura.
_proxima_wiki_de_brackets = 0


def _coletar_brackets(settings: Settings, storage: RawStorage) -> CollectionResult:
    """O bracket de cada torneio ja conhecido, algumas wikis por rodada.

    "Ja conhecido" quer dizer: torneios que `_coletar_liquipedia` (o ticker) ja
    viu pelo menos uma vez e gravou em `agenda_partida.torneio`. O bracket da
    o historico INTEIRO daquele torneio - nao so a janela de dias que o ticker
    enxerga - e e a fonte que alimenta o Bradley-Terry para todo jogo que nao e
    Dota 2 (Fase 13). Um torneio de 24 confrontos decididos rendeu mais
    historico sozinho do que semanas de ticker.

    Rodizio pelo mesmo motivo do de equipes: uma wiki pode ter dezenas de
    torneios conhecidos, e cada um e uma chamada.
    """
    global _proxima_wiki_de_brackets

    from collectors.liquipedia_bracket_collector import (
        LiquipediaBracketCollector,
        torneios_conhecidos,
    )
    from etl.wikis import com_agenda

    todas = com_agenda()
    if not todas:
        return CollectionResult(fonte="liquipedia", sucesso=True)

    quantas = min(settings.agendador_brackets_por_rodada, len(todas))
    lote = [
        todas[(_proxima_wiki_de_brackets + i) % len(todas)] for i in range(quantas)
    ]
    _proxima_wiki_de_brackets = (_proxima_wiki_de_brackets + quantas) % len(todas)

    logger.info(
        "rodizio de brackets",
        extra={"wikis": [w.codigo for w in lote], "de": len(todas)},
    )

    parciais: list[CollectionResult] = []
    for posicao, wiki in enumerate(lote):
        torneios = torneios_conhecidos(wiki.codigo)
        if not torneios:
            continue

        coletor = LiquipediaBracketCollector(
            raw_storage=storage,
            settings=settings,
            wiki=wiki.codigo,
            torneios=torneios,
        )
        try:
            parciais.append(coletor.run(carregar=True))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "brackets de uma wiki falharam",
                extra={"wiki": wiki.codigo, "erro": f"{type(exc).__name__}: {exc}"},
            )
            parciais.append(CollectionResult(fonte="liquipedia", sucesso=False))
        finally:
            coletor.close()

        # O coletor ja pausa ENTRE torneios da mesma wiki (dentro do proprio
        # `client`, que e reaproveitado ali). O que falta e a pausa ENTRE
        # wikis deste laco - mesmo motivo dos outros dois sleeps deste arquivo.
        if posicao < len(lote) - 1:
            time.sleep(settings.liquipedia_rate_limit_seconds)

    return _somar(parciais, "liquipedia")


def _coletar_ranking(settings: Settings, storage: RawStorage) -> CollectionResult:
    """O ranking mais recente da Valve (CS2). Uma chamada, sem backfill.

    O backfill dos meses anteriores e um `cli.py collect valve-standings
    --todos` manual, uma vez; daqui em diante o snapshot novo entra sozinho.
    """
    from collectors.valve_standings_collector import ValveStandingsCollector

    coletor = ValveStandingsCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_precos(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Preco dos jogos pagos nas outras lojas (IsThereAnyDeal)."""
    from collectors.itad_collector import ItadCollector

    coletor = ItadCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_tempo_jogo(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Tempo estimado pra zerar cada jogo (HowLongToBeat)."""
    from collectors.hltb_collector import HltbCollector

    coletor = HltbCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_agentes_valorant(
    settings: Settings, storage: RawStorage
) -> CollectionResult:
    """Elenco de agentes do VALORANT (valorant-api.com)."""
    from collectors.valorant_agentes import AgentesValorantCollector

    coletor = AgentesValorantCollector(raw_storage=storage)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_campeoes_lol(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Elenco de campeoes de LoL e o desempenho na rota principal (OP.GG)."""
    from collectors.lol_campeoes import CampeoesLolCollector

    coletor = CampeoesLolCollector(raw_storage=storage)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_herois_dota(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Lore e habilidades de cada heroi de Dota (datafeed da Valve)."""
    from collectors.dota_herois import HeroisDotaCollector

    coletor = HeroisDotaCollector(raw_storage=storage)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_esports_opgg(
    settings: Settings, storage: RawStorage
) -> CollectionResult:
    """Agenda e resultados do cenario profissional de LoL (OP.GG)."""
    from collectors.opgg_esports import OpggEsportsCollector

    coletor = OpggEsportsCollector(raw_storage=storage)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


#: Minimo de confrontos decididos para valer a pena reajustar um jogo.
#:
#: O mesmo piso que `ml.confronto.ajustar_e_salvar` exige - abaixo dele ele
#: levanta `ValueError`, e agendar a falha so encheria o log.
MINIMO_CONFRONTOS_TREINO = 10


def _treinar_confronto(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Reajusta a previsao de confronto de TODO jogo com historico suficiente.

    **Por que isto e uma tarefa e nao um comando manual.** A coleta roda de 6 em
    6 horas e o modelo era ajustado a mao: dos treze jogos com modelo, nove
    tinham artefato de dois dias antes, treinados sobre um historico que ja
    tinha crescido. A tela mostrava probabilidade e metrica de validacao de uma
    amostra que nao existia mais.

    Um jogo que falha nao leva os outros: `ajustar_e_salvar` levanta quando o
    historico e curto demais, e isso e estado normal para um jogo recem-entrado
    no catalogo - nao motivo para o restante ficar sem reajuste.
    """
    from sqlalchemy import func, select

    from db.models import AgendaPartida, DimJogo, DimPartida
    from db.session import session_scope
    from ml.confronto import ajustar_e_salvar

    with session_scope() as sessao:
        # Um jogo entra se tem confronto decidido em QUALQUER uma das duas
        # fontes: `dim_partida` (OpenDota, so Dota) ou `agenda_partida` (ticker
        # da Liquipedia e OP.GG). Olhar so uma delas deixaria metade de fora.
        codigos = [
            codigo
            for codigo, agenda, partidas in sessao.execute(
                select(
                    DimJogo.codigo,
                    select(func.count())
                    .select_from(AgendaPartida)
                    .where(
                        AgendaPartida.id_jogo == DimJogo.id_jogo,
                        AgendaPartida.vitoria_a.is_not(None),
                    )
                    .scalar_subquery(),
                    select(func.count())
                    .select_from(DimPartida)
                    .where(DimPartida.id_jogo == DimJogo.id_jogo)
                    .scalar_subquery(),
                )
            )
            if max(agenda, partidas) >= MINIMO_CONFRONTOS_TREINO
        ]

    resultado = CollectionResult(fonte="confronto", sucesso=True)
    for codigo in codigos:
        try:
            ajustar_e_salvar(codigo)
            resultado.registros_carregados += 1
        except Exception as exc:  # noqa: BLE001 - um jogo nao derruba os outros
            resultado.falhas += 1
            logger.warning(
                "reajuste de confronto falhou",
                extra={"jogo": codigo, "erro": f"{type(exc).__name__}: {exc}"},
            )

    resultado.registros_coletados = len(codigos)
    resultado.registros_processados = len(codigos)
    # Falhar em todos e falha da tarefa; falhar em um jogo novo, nao.
    resultado.sucesso = bool(codigos) and resultado.registros_carregados > 0
    return resultado


def montar_tarefas(settings: Settings) -> list[Tarefa]:
    """As tarefas do agendador, na ordem em que rodam quando empatam.

    A tarefa de preco (`itad`) so entra quando ha `ITAD_API_KEY` - sem chave
    ela nao teria o que fazer. A de tempo pra zerar (`hltb`) nao pede chave,
    mas e engenharia reversa de um endpoint nao-oficial - `hltb_enabled`
    deixa desligar sem mexer em codigo se um dia parar de responder direito.
    """
    tarefas = [
        Tarefa(
            nome="steam",
            intervalo_segundos=settings.agendador_steam_minutos * 60,
            executar=_coletar_steam,
        ),
        Tarefa(
            nome="opendota",
            intervalo_segundos=settings.agendador_opendota_minutos * 60,
            executar=_coletar_opendota,
        ),
        Tarefa(
            nome="liquipedia",
            intervalo_segundos=settings.agendador_liquipedia_minutos * 60,
            executar=_coletar_liquipedia,
        ),
        Tarefa(
            nome="equipes",
            intervalo_segundos=settings.agendador_equipes_minutos * 60,
            executar=_coletar_equipes,
        ),
        Tarefa(
            nome="brackets",
            intervalo_segundos=settings.agendador_brackets_minutos * 60,
            executar=_coletar_brackets,
        ),
        Tarefa(
            nome="ranking",
            intervalo_segundos=settings.agendador_ranking_minutos * 60,
            executar=_coletar_ranking,
        ),
    ]
    if settings.itad_api_key:
        tarefas.append(
            Tarefa(
                nome="precos",
                intervalo_segundos=settings.agendador_precos_minutos * 60,
                executar=_coletar_precos,
            )
        )
    if settings.hltb_enabled:
        tarefas.append(
            Tarefa(
                nome="tempo_jogo",
                intervalo_segundos=settings.agendador_tempo_jogo_minutos * 60,
                executar=_coletar_tempo_jogo,
            )
        )
    if settings.opgg_enabled:
        tarefas.append(
            Tarefa(
                nome="esports_opgg",
                intervalo_segundos=settings.agendador_esports_opgg_minutos * 60,
                executar=_coletar_esports_opgg,
            )
        )
    tarefas.append(
        Tarefa(
            nome="treino_confronto",
            intervalo_segundos=settings.agendador_treino_confronto_minutos * 60,
            executar=_treinar_confronto,
        )
    )
    tarefas.append(
        Tarefa(
            nome="agentes_valorant",
            intervalo_segundos=settings.agendador_agentes_minutos * 60,
            executar=_coletar_agentes_valorant,
        )
    )
    if settings.opgg_enabled:
        tarefas.append(
            Tarefa(
                nome="campeoes_lol",
                intervalo_segundos=settings.agendador_agentes_minutos * 60,
                executar=_coletar_campeoes_lol,
            )
        )
    tarefas.append(
        Tarefa(
            nome="herois_dota",
            intervalo_segundos=settings.agendador_agentes_minutos * 60,
            executar=_coletar_herois_dota,
        )
    )
    return tarefas


@dataclass
class Parada:
    """Sinal de desligamento, compartilhado entre o laco e os handlers.

    `docker compose stop` manda SIGTERM e espera dez segundos antes do SIGKILL.
    Um `time.sleep(3600)` ignoraria o sinal e o container morreria no tapa; um
    `Event.wait(timeout)` acorda na hora. A diferenca aparece toda vez que
    alguem reinicia o servico.
    """

    evento: threading.Event = field(default_factory=threading.Event)

    def pedir_parada(self, *_args) -> None:
        if not self.evento.is_set():
            logger.info("desligamento pedido, encerrando apos a tarefa atual")
        self.evento.set()

    def dormir(self, segundos: float) -> bool:
        """Espera, mas acorda se o desligamento chegar. `True` = hora de sair."""
        return self.evento.wait(timeout=max(0.0, segundos))

    @property
    def parando(self) -> bool:
        return self.evento.is_set()


def _executar(tarefa: Tarefa, settings: Settings, storage: RawStorage) -> bool:
    """Roda uma tarefa. Devolve se foi bem-sucedida.

    Nenhuma excecao escapa: uma fonte fora do ar nao pode derrubar o agendador e
    levar as outras duas junto. Esse e o motivo de o `except` ser largo aqui e
    so aqui.
    """
    inicio = time.monotonic()
    try:
        resultado = tarefa.executar(settings, storage)
    except Exception as exc:  # noqa: BLE001 - isolamento entre fontes
        tarefa.falhas += 1
        logger.exception(
            "coleta falhou",
            extra={"fonte": tarefa.nome, "erro": f"{type(exc).__name__}: {exc}"},
        )
        return False

    tarefa.execucoes += 1
    if not resultado.sucesso:
        tarefa.falhas += 1
        logger.warning(
            "coleta nao concluida",
            extra={"fonte": tarefa.nome, "erro": resultado.erro},
        )
        return False

    logger.info(
        "coleta concluida",
        extra={
            "fonte": tarefa.nome,
            "coletados": resultado.registros_coletados,
            "carregados": resultado.registros_carregados,
            "segundos": round(time.monotonic() - inicio, 2),
        },
    )
    return True


def rodar(parada: Parada | None = None) -> int:
    """O laco. Roda ate receber SIGTERM/SIGINT."""
    settings = get_settings()
    configurar_logging(settings.log_level, settings.log_format)

    parada = parada or Parada()
    signal.signal(signal.SIGTERM, parada.pedir_parada)
    signal.signal(signal.SIGINT, parada.pedir_parada)

    # `dim_jogo` precisa ter as wikis antes de qualquer carga: o loader da
    # agenda resolve o `id_jogo` pelo codigo e falha se ele nao existir.
    try:
        from etl.load_jogos import sincronizar

        sincronizar()
    except Exception as exc:  # noqa: BLE001 - banco fora do ar nao trava o boot
        logger.warning(
            "nao foi possivel sincronizar dim_jogo",
            extra={"erro": f"{type(exc).__name__}: {exc}"},
        )

    tarefas = montar_tarefas(settings)
    storage = RawStorage(settings.raw_data_path, registrar_no_banco=True)

    agora = time.monotonic()
    for tarefa in tarefas:
        # Sem `rodar_ao_iniciar`, a primeira coleta so acontece um intervalo
        # depois - o que num intervalo de 12h significa meio dia de silencio
        # depois de um deploy.
        tarefa.proxima_em = agora if settings.agendador_rodar_ao_iniciar else (
            agora + tarefa.intervalo_segundos
        )

    logger.info(
        "agendador iniciado",
        extra={
            "tarefas": {t.nome: round(t.intervalo_segundos / 60) for t in tarefas},
            "rodar_ao_iniciar": settings.agendador_rodar_ao_iniciar,
        },
    )

    while not parada.parando:
        proxima = min(tarefas, key=lambda t: t.proxima_em)
        espera = proxima.proxima_em - time.monotonic()

        if espera > 0 and parada.dormir(espera):
            break
        if parada.parando:
            break

        sucesso = _executar(proxima, settings, storage)
        proxima.reagendar(time.monotonic(), sucesso)

    logger.info(
        "agendador encerrado",
        extra={"execucoes": {t.nome: t.execucoes for t in tarefas},
               "falhas": {t.nome: t.falhas for t in tarefas}},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(rodar())
