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

from services.collectors.base import CollectionResult
from config import Settings, get_settings
from services.etl.raw_storage import RawStorage
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
    #: Falhas CONSECUTIVAS - zera a cada sucesso. Separado de `falhas` (que e
    #: o total da vida) porque o que caracteriza "quebrou" e a sequencia: uma
    #: fonte que falha 1 em cada 20 rodadas esta saudavel, uma que falhou as
    #: ultimas 3 seguidas nao esta.
    falhas_seguidas: int = 0
    #: `time.monotonic()` do ultimo sucesso. 0 = nunca teve. E o que sustenta
    #: o "sem sucesso ha tempo demais" do resumo diario.
    ultimo_sucesso: float = 0.0

    def reagendar(self, agora: float, sucesso: bool) -> None:
        espera = self.intervalo_segundos if sucesso else ESPERA_APOS_FALHA_SEGUNDOS
        self.proxima_em = agora + espera


def _apps_monitorados() -> list[int]:
    """Os app_ids com FICHA no banco - nao toda linha de `dim_jogo_steam`.

    **Nao e a semente.** O `SteamCollector` sem `app_ids` cai na lista fixa de
    `collectors/seeds/steam_apps.json`, que faz sentido para um primeiro
    `collect` numa base vazia. Para o agendador ela seria um bug silencioso:
    todo jogo trazido pela busca da tela - a coleta sob demanda de
    `/api/steam/coletar` - ficaria com o unico snapshot do dia em que entrou, e
    a serie dele nunca cresceria. A tela mostraria "so existe uma coleta ate
    agora" para sempre, sem que nada estivesse quebrado.

    Monitorar quem esta no banco faz a plataforma acompanhar o que foi trazido
    para ela, em vez de uma lista decidida antes de alguem usar o produto.

    **Por que o filtro de ficha (2026-09-16).** A varredura de ofertas (Fase
    35.1) cria uma linha por oferta ativa - o banco saiu de ~90 linhas para
    20.079. Sem o filtro, esta funcao devolvia as 20.079 e a tarefa `steam`
    pedia `appdetails` + avaliacoes de cada uma, a ~3s por app: 16,7 HORAS
    para uma passada de uma tarefa que roda a cada 60 minutos. Ela nunca
    fechava um ciclo e martelava a Steam sem intervalo - medido ao vivo na
    VPS, com o log em `posicao: 14, total: 20079`.

    O stub da varredura nao precisa disto: o preco dele ja vem da propria
    varredura, de hora em hora, e e so o que a tela de Ofertas mostra. Quem
    precisa de `appdetails` recorrente e quem tem ficha - os jogos com pagina
    de verdade, serie de jogadores e avaliacoes. Um stub vira monitorado no
    momento em que alguem abre a ficha dele e a coleta sob demanda roda.

    Devolve vazio quando o banco esta vazio, e ai a semente e a resposta certa.
    """
    from sqlalchemy import select

    from models.models import DimJogoSteam
    from models.session import session_scope

    with session_scope() as sessao:
        return list(
            sessao.scalars(
                select(DimJogoSteam.app_id).where(
                    DimJogoSteam.com_ficha()
                )
            )
        )


def _coletar_steam(settings: Settings, storage: RawStorage) -> CollectionResult:
    from services.collectors.steam_collector import (
        SteamCollector,
        apps_com_preco_alterado,
        top_mais_jogados,
    )

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

    # Fila de preco alterado (Fase 35): apps cujo `price_change_number` mudou
    # desde o ultimo sync do catalogo completo. Persistida no Postgres, nao em
    # memoria - sobrevive a restart. Some aos ja monitorados como o ranking
    # acima; `load_steam.py` desmarca cada um depois de reprocessar.
    ja_conhecidos = set(monitorados)
    com_preco_alterado = [
        app for app in apps_com_preco_alterado() if app not in ja_conhecidos
    ]
    monitorados = monitorados + com_preco_alterado

    logger.info(
        "apps monitorados",
        extra={
            "quantidade": len(monitorados) or "semente",
            "novos_do_ranking": len(descobertos),
            "preco_alterado": len(com_preco_alterado),
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


def _coletar_steam_precos_alterados(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Confirma preco/promocao SO dos apps sinalizados pelo `steam_catalogo`
    (Fase 35) - nunca a lista inteira de monitorados (isso e `_coletar_steam`
    acima, de hora em hora). Pode rodar com frequencia (10 em 10 min por
    padrao) sem virar scraping agressivo: o lote e so quem a propria Steam
    ja confirmou que mudou de preco (tipicamente umas dezenas de apps, nao
    os ~90 monitorados inteiros) - e quando nao ha ninguem sinalizado, nem
    chama a rede.
    """
    from services.collectors.steam_collector import SteamCollector, apps_com_preco_alterado

    alterados = apps_com_preco_alterado()
    if not alterados:
        return CollectionResult(fonte="steam", sucesso=True)

    coletor = SteamCollector(raw_storage=storage, app_ids=alterados, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_steam_catalogo(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Indice do catalogo completo + sync incremental de preco (Fase 35).

    Cada execucao processa so `steam_sync_pages_per_run` pagina(s) do
    `GetAppList` (checkpoint em `steam_sincronizacao`) e retorna - nunca o
    catalogo inteiro de uma vez. Ver `services/collectors/steam_catalogo.py`.
    """
    from services.collectors.steam_catalogo import SteamCatalogoCollector

    coletor = SteamCatalogoCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_steam_ofertas(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Varredura completa das ofertas ativas da Steam (Fase 35.1).

    Distinto de `_coletar_steam_precos_alterados`: aquela so confirma o que o
    `steam_catalogo` ja sinalizou como alterado (reage a mudanca futura);
    esta varre `/search/results/?specials=1` - o mesmo endpoint que a pagina
    `/specials` chama - e cobre TODA oferta ativa agora, incluindo as que ja
    estavam no ar antes de qualquer baseline nosso. Nao depende de
    `STEAM_API_KEY` (endpoint publico da loja), entao roda sem gate.
    """
    from services.collectors.steam_ofertas_collector import SteamOfertasCollector

    coletor = SteamOfertasCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_steam_online(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Usuarios simultaneos da plataforma Steam (numero da Valve, nao a soma)."""
    from services.collectors.steam_online import SteamOnlineCollector

    return SteamOnlineCollector(raw_storage=storage).run(carregar=True)


def _coletar_opendota(settings: Settings, storage: RawStorage) -> CollectionResult:
    from services.collectors.opendota_collector import OpenDotaCollector

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

    Uma chamada `action=parse` por wiki - sao 66, ~35s de intervalo (o limite
    PROPRIO de `action=parse` nos termos da Liquipedia, mais restrito que o
    geral - ver `liquipedia_parse_rate_limit_seconds`), entao uma varredura
    completa leva uns 35-40 minutos. Ainda cabe folgado no intervalo padrao de
    12h da tarefa.
    """
    from services.collectors import liquipedia_rate_limit
    from services.collectors.liquipedia_collector import LiquipediaCollector
    from services.etl.wikis import com_agenda

    liquipedia_rate_limit.checar()

    parciais: list[CollectionResult] = []
    wikis = com_agenda()
    for posicao, wiki in enumerate(wikis):
        coletor = LiquipediaCollector(
            raw_storage=storage, settings=settings, wiki=wiki.codigo
        )
        try:
            parciais.append(coletor.run(carregar=True))
        except Exception as exc:  # noqa: BLE001 - uma wiki nao derruba a varredura
            if liquipedia_rate_limit.eh_429(exc):
                # 429 e sinal do SERVIDOR, nao de uma wiki - continuar pra
                # proxima so martelaria a mesma parede 60+ vezes seguidas
                # (foi exatamente isso que aconteceu em 2026-09-15).
                liquipedia_rate_limit.acionar()
                logger.error(
                    "429 da Liquipedia - parando a varredura e pausando por "
                    f"{liquipedia_rate_limit.ESPERA_APOS_429_SEGUNDOS}s",
                    extra={"wiki": wiki.codigo},
                )
                parciais.append(CollectionResult(fonte="liquipedia", sucesso=False))
                break
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
        # uma varredura sem pausa nenhuma entre wikis - na epoca pensavamos
        # que o limite de `action=parse` era o geral (2s); e o proprio de
        # `action=parse` (30s), por isso o sleep agora e o mais longo.
        if posicao < len(wikis) - 1:
            time.sleep(settings.liquipedia_parse_rate_limit_seconds)

    return _somar(parciais, "liquipedia")


#: Onde o rodizio parou. Estado em memoria de proposito: perde-se no restart, e
#: perder significa recomecar a varredura, nao corromper nada.
_proxima_wiki_de_equipes = 0


def _coletar_equipes(settings: Settings, storage: RawStorage) -> CollectionResult:
    """As paginas de equipe, algumas wikis por rodada.

    Rodizio em vez de varredura completa: ver `agendador_equipes_por_rodada`.
    """
    global _proxima_wiki_de_equipes

    from services.collectors import liquipedia_rate_limit
    from services.collectors.liquipedia_wiki_collector import LiquipediaWikiCollector
    from services.etl.wikis import com_times

    liquipedia_rate_limit.checar()

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
            if liquipedia_rate_limit.eh_429(exc):
                liquipedia_rate_limit.acionar()
                logger.error(
                    "429 da Liquipedia - parando o rodizio de equipes e "
                    f"pausando por {liquipedia_rate_limit.ESPERA_APOS_429_SEGUNDOS}s",
                    extra={"wiki": wiki.codigo},
                )
                parciais.append(CollectionResult(fonte="liquipedia", sucesso=False))
                break
            logger.warning(
                "equipes de uma wiki falharam",
                extra={"wiki": wiki.codigo, "erro": f"{type(exc).__name__}: {exc}"},
            )
            parciais.append(CollectionResult(fonte="liquipedia", sucesso=False))
        finally:
            coletor.close()

        # `LiquipediaWikiCollector.collect()` ja aciona o breaker e para
        # sozinho (retorno normal, sem levantar) quando ve um 429 num lote -
        # o `except` acima nunca chega a rodar nesse caso. Sem esta checagem
        # o rodizio deste laco seguiria pra proxima wiki da lista mesmo com
        # o breaker ja ligado, so pra esbarrar em `checar()` de novo do lado
        # de dentro do proximo coletor.
        if liquipedia_rate_limit.esta_bloqueada():
            break

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
    torneios conhecidos, e cada um e uma chamada `action=parse` (~35s de
    intervalo - o limite proprio de `action=parse`, mais restrito que o
    geral). Uma wiki com muitos torneios conhecidos pode levar dezenas de
    minutos sozinha; ainda cabe no intervalo padrao de 24h da tarefa.
    """
    global _proxima_wiki_de_brackets

    from services.collectors import liquipedia_rate_limit
    from services.collectors.liquipedia_bracket_collector import (
        LiquipediaBracketCollector,
        torneios_conhecidos,
    )
    from services.etl.wikis import com_agenda

    liquipedia_rate_limit.checar()

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
            if liquipedia_rate_limit.eh_429(exc):
                liquipedia_rate_limit.acionar()
                logger.error(
                    "429 da Liquipedia - parando o rodizio de brackets e "
                    f"pausando por {liquipedia_rate_limit.ESPERA_APOS_429_SEGUNDOS}s",
                    extra={"wiki": wiki.codigo},
                )
                parciais.append(CollectionResult(fonte="liquipedia", sucesso=False))
                break
            logger.warning(
                "brackets de uma wiki falharam",
                extra={"wiki": wiki.codigo, "erro": f"{type(exc).__name__}: {exc}"},
            )
            parciais.append(CollectionResult(fonte="liquipedia", sucesso=False))
        finally:
            coletor.close()

        # `LiquipediaBracketCollector.collect()` ja aciona o breaker e para
        # sozinho (retorno normal, sem levantar) quando ve um 429 num
        # torneio - o `except` acima e so para outros erros que escapem do
        # coletor. Sem esta checagem o rodizio seguiria pra proxima wiki
        # mesmo com o breaker ja ligado.
        if liquipedia_rate_limit.esta_bloqueada():
            break

        # O coletor ja pausa ENTRE torneios da mesma wiki (dentro do proprio
        # `client`, que e reaproveitado ali, no intervalo PROPRIO de
        # `action=parse`). O que falta e a pausa ENTRE wikis deste laco -
        # mesmo motivo dos outros dois sleeps deste arquivo, mesmo intervalo
        # (e tambem `action=parse`).
        if posicao < len(lote) - 1:
            time.sleep(settings.liquipedia_parse_rate_limit_seconds)

    return _somar(parciais, "liquipedia")


def _coletar_ranking(settings: Settings, storage: RawStorage) -> CollectionResult:
    """O ranking mais recente da Valve (CS2). Uma chamada, sem backfill.

    O backfill dos meses anteriores e um `cli.py collect valve-standings
    --todos` manual, uma vez; daqui em diante o snapshot novo entra sozinho.
    """
    from services.collectors.valve_standings_collector import ValveStandingsCollector

    coletor = ValveStandingsCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_precos(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Preco dos jogos pagos nas outras lojas (IsThereAnyDeal)."""
    from services.collectors.itad_collector import ItadCollector

    coletor = ItadCollector(
        raw_storage=storage,
        settings=settings,
        revalidar_vazios_dias=settings.itad_revalidar_vazios_dias,
    )
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_resumo_reviews(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Resumo por IA (Groq) das avaliacoes de cada jogo pago."""
    from services.collectors.resumo_reviews import ResumoReviewsCollector

    coletor = ResumoReviewsCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_tempo_jogo(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Tempo estimado pra zerar cada jogo (HowLongToBeat)."""
    from services.collectors.hltb_collector import HltbCollector

    coletor = HltbCollector(
        raw_storage=storage,
        settings=settings,
        revalidar_vazios_dias=settings.hltb_revalidar_vazios_dias,
    )
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_xbox(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Catalogo do Game Pass + ficha/preco da Microsoft Store (mercado BR)."""
    from services.collectors.xbox_collector import XboxCollector

    coletor = XboxCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_agentes_valorant(
    settings: Settings, storage: RawStorage
) -> CollectionResult:
    """Elenco de agentes do VALORANT (valorant-api.com)."""
    from services.collectors.valorant_agentes import AgentesValorantCollector

    coletor = AgentesValorantCollector(raw_storage=storage)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_campeoes_lol(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Elenco de campeoes de LoL e o desempenho na rota principal (OP.GG)."""
    from services.collectors.lol_campeoes import CampeoesLolCollector

    coletor = CampeoesLolCollector(raw_storage=storage)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_herois_dota(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Lore e habilidades de cada heroi de Dota (datafeed da Valve)."""
    from services.collectors.dota_herois import HeroisDotaCollector

    coletor = HeroisDotaCollector(raw_storage=storage)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_esports_opgg(
    settings: Settings, storage: RawStorage
) -> CollectionResult:
    """Agenda e resultados do cenario profissional de LoL (OP.GG)."""
    from services.collectors.opgg_esports import OpggEsportsCollector

    coletor = OpggEsportsCollector(raw_storage=storage)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def _coletar_vlr(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Resultados e agenda de Valorant do vlr.gg."""
    from services.collectors.vlr import VlrCollector

    return VlrCollector(raw_storage=storage).run(carregar=True)


def _coletar_vlr_rankings(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Snapshot do rating de equipes de Valorant do vlr.gg (prior do modelo)."""
    from services.collectors.vlr_rankings import VlrRankingsCollector

    return VlrRankingsCollector(raw_storage=storage).run(carregar=True)


def _coletar_vlr_agenda(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Só as próximas partidas de Valorant do vlr.gg (tarefa de 5 min)."""
    from services.collectors.vlr import VlrCollector

    return VlrCollector(raw_storage=storage, apenas_agenda=True).run(carregar=True)


def _coletar_hltv(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Próximas partidas de Counter-Strike do hltv.org (tarefa de 5 min)."""
    from services.collectors.hltv import HltvCollector

    return HltvCollector(raw_storage=storage).run(carregar=True)


def _coletar_pandascore_cs(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Agenda + resultados de CS via PandaScore (troca o scraping do hltv)."""
    from services.collectors.pandascore import PandaScoreCollector

    return PandaScoreCollector(raw_storage=storage, jogo="csgo").run(carregar=True)


def _coletar_pandascore_lol(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Agenda + resultados de LoL via PandaScore (LCK/LPL/LEC/LCS...).

    Roda junto do `esports_opgg`: a PandaScore dá a estrutura de torneio e o
    histórico, o OP.GG segue povoando escudo de time. O `_preferir_fonte_dedicada`
    faz a PandaScore mandar no que aparece na tela e no modelo.
    """
    from services.collectors.pandascore import PandaScoreCollector

    return PandaScoreCollector(raw_storage=storage, jogo="lol").run(carregar=True)


def _coletar_pandascore_cod(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Agenda + resultados de Call of Duty via PandaScore (CDL, EWC, Challengers).

    CoD não tinha nenhuma fonte — a tela de Partidas ficava vazia. Fora de
    temporada da CDL há só o histórico; em temporada, a agenda também.
    """
    from services.collectors.pandascore import PandaScoreCollector

    return PandaScoreCollector(raw_storage=storage, jogo="codmw").run(carregar=True)


def _coletar_pandascore_ow(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Agenda + resultados de Overwatch via PandaScore (OWCS, World Cup)."""
    from services.collectors.pandascore import PandaScoreCollector

    return PandaScoreCollector(raw_storage=storage, jogo="ow").run(carregar=True)


def _coletar_pandascore_r6(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Agenda + resultados de Rainbow Six Siege via PandaScore (as ligas regionais)."""
    from services.collectors.pandascore import PandaScoreCollector

    return PandaScoreCollector(raw_storage=storage, jogo="r6siege").run(carregar=True)


def _coletar_pandascore_rl(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Agenda + resultados de Rocket League via PandaScore (RLCS, EWC)."""
    from services.collectors.pandascore import PandaScoreCollector

    return PandaScoreCollector(raw_storage=storage, jogo="rl").run(carregar=True)


def _coletar_ubi_r6(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Ranking oficial de R6 (SI Points Standings da Ubisoft)."""
    from services.collectors.ubi_r6 import UbiR6Collector

    return UbiR6Collector(raw_storage=storage).run(carregar=True)


def _coletar_owcs(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Classificacao do Stage corrente do OWCS (Liquipedia)."""
    from services.collectors.owcs_standings import OwcsStandingsCollector

    return OwcsStandingsCollector(raw_storage=storage).run(carregar=True)


def _coletar_rlcs(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Leaderboard oficial de pontos da RLCS (blast.tv), por regiao."""
    from services.collectors.rlcs_rankings import RlcsRankingsCollector

    return RlcsRankingsCollector(raw_storage=storage).run(carregar=True)


def _coletar_dltv(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Ranking mundial de Dota 2 do DLTV (não há ranking oficial da Valve)."""
    from services.collectors.dltv_ranking import DltvRankingCollector

    return DltvRankingCollector(raw_storage=storage).run(carregar=True)


def _coletar_pandascore_val(settings: Settings, storage: RawStorage) -> CollectionResult:
    """PandaScore de Valorant — só pelo escudo dos times.

    O vlr.gg continua a fonte de Valorant (tem o detalhe por mapa, o ranking).
    Estas linhas ficam atrás do `vlr:` na precedência (`etl.agenda_fontes`); o
    valor é o `image_url` de cada time, que o `carregar_agenda` faz backfill no
    `dim_equipe` que a raspagem do vlr.gg deixou sem logo.
    """
    from services.collectors.pandascore import PandaScoreCollector

    return PandaScoreCollector(raw_storage=storage, jogo="valorant").run(carregar=True)


def _coletar_vlr_detalhes(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Detalhe por mapa e por jogador das partidas de Valorant ja decididas."""
    from services.collectors.vlr_detalhes import VlrDetalhesCollector

    return VlrDetalhesCollector(raw_storage=storage).run(carregar=True)


def _coletar_lolesports(settings: Settings, storage: RawStorage) -> CollectionResult:
    """Scoreboard ao vivo (campeao/KDA/ouro) das partidas de LoL em andamento."""
    from services.collectors.lolesports import LolEsportsCollector

    return LolEsportsCollector(raw_storage=storage).run(carregar=True)


def _coletar_lolesports_cenario(
    settings: Settings, storage: RawStorage
) -> CollectionResult:
    """Classificacao por split (LCK/LPL/LEC...) e elencos, da API oficial de LoL."""
    from services.collectors.lolesports_cenario import LolCenarioCollector

    return LolCenarioCollector(raw_storage=storage).run(carregar=True)


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

    from models.models import AgendaPartida, DimJogo, DimPartida
    from models.session import session_scope
    from services.ml.confronto import ajustar_e_salvar

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
    ela nao teria o que fazer. A de resumo de avaliacoes por IA
    (`resumo_reviews`) idem com `GROQ_API_KEY`. A de tempo pra zerar (`hltb`)
    nao pede chave, mas e engenharia reversa de um endpoint nao-oficial -
    `hltb_enabled` deixa desligar sem mexer em codigo se um dia parar de
    responder direito.
    """
    tarefas = [
        Tarefa(
            nome="steam",
            intervalo_segundos=settings.agendador_steam_minutos * 60,
            executar=_coletar_steam,
        ),
        Tarefa(
            nome="steam_online",
            intervalo_segundos=settings.agendador_steam_online_minutos * 60,
            executar=_coletar_steam_online,
        ),
        # Sem gate de chave - `/search/results/` e endpoint publico da loja,
        # ao contrario das outras tarefas Steam abaixo.
        Tarefa(
            nome="steam_ofertas",
            intervalo_segundos=settings.agendador_steam_ofertas_minutos * 60,
            executar=_coletar_steam_ofertas,
        ),
    ]
    if settings.steam_api_key:
        tarefas.append(
            Tarefa(
                nome="steam_catalogo",
                intervalo_segundos=settings.agendador_steam_catalogo_minutos * 60,
                executar=_coletar_steam_catalogo,
            )
        )
        tarefas.append(
            Tarefa(
                nome="steam_precos_alterados",
                intervalo_segundos=settings.agendador_steam_precos_alterados_minutos * 60,
                executar=_coletar_steam_precos_alterados,
            )
        )
    tarefas += [
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
    if settings.groq_api_key:
        tarefas.append(
            Tarefa(
                nome="resumo_reviews",
                intervalo_segundos=settings.agendador_resumo_reviews_minutos * 60,
                executar=_coletar_resumo_reviews,
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
    if settings.xbox_enabled:
        tarefas.append(
            Tarefa(
                nome="xbox",
                intervalo_segundos=settings.agendador_xbox_minutos * 60,
                executar=_coletar_xbox,
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
            nome="vlr",
            intervalo_segundos=settings.agendador_vlr_minutos * 60,
            executar=_coletar_vlr,
        )
    )
    tarefas.append(
        Tarefa(
            nome="vlr_agenda",
            intervalo_segundos=settings.agendador_agenda_proxima_minutos * 60,
            executar=_coletar_vlr_agenda,
        )
    )
    # A PandaScore (API) troca o scraping do hltv.org quando há chave. Sem
    # chave, cai de volta no hltv — que passa por Cloudflare só com `curl_cffi`
    # e cobre todos os tiers. O LoL da PandaScore roda junto do `esports_opgg`
    # (fontes complementares — ver `_coletar_pandascore_lol`).
    if settings.pandascore_api_key:
        for nome, executar in (
            ("pandascore_cs", _coletar_pandascore_cs),
            ("pandascore_lol", _coletar_pandascore_lol),
            ("pandascore_cod", _coletar_pandascore_cod),
            ("pandascore_ow", _coletar_pandascore_ow),
            ("pandascore_r6", _coletar_pandascore_r6),
            ("pandascore_rl", _coletar_pandascore_rl),
            ("pandascore_val", _coletar_pandascore_val),
        ):
            tarefas.append(
                Tarefa(
                    nome=nome,
                    intervalo_segundos=settings.agendador_pandascore_minutos * 60,
                    executar=executar,
                )
            )
    else:
        tarefas.append(
            Tarefa(
                nome="hltv",
                intervalo_segundos=settings.agendador_agenda_proxima_minutos * 60,
                executar=_coletar_hltv,
            )
        )
    tarefas.append(
        Tarefa(
            nome="vlr_rankings",
            intervalo_segundos=settings.agendador_vlr_rankings_minutos * 60,
            executar=_coletar_vlr_rankings,
        )
    )
    tarefas.append(
        Tarefa(
            nome="ubi_r6",
            intervalo_segundos=settings.agendador_ubi_r6_minutos * 60,
            executar=_coletar_ubi_r6,
        )
    )
    tarefas.append(
        Tarefa(
            nome="owcs",
            intervalo_segundos=settings.agendador_owcs_minutos * 60,
            executar=_coletar_owcs,
        )
    )
    tarefas.append(
        Tarefa(
            nome="rlcs",
            intervalo_segundos=settings.agendador_rlcs_minutos * 60,
            executar=_coletar_rlcs,
        )
    )
    tarefas.append(
        Tarefa(
            nome="dltv",
            intervalo_segundos=settings.agendador_dltv_minutos * 60,
            executar=_coletar_dltv,
        )
    )
    tarefas.append(
        Tarefa(
            nome="vlr_detalhes",
            intervalo_segundos=settings.agendador_vlr_detalhes_minutos * 60,
            executar=_coletar_vlr_detalhes,
        )
    )
    tarefas.append(
        Tarefa(
            nome="lolesports",
            intervalo_segundos=settings.agendador_lolesports_minutos * 60,
            executar=_coletar_lolesports,
        )
    )
    tarefas.append(
        Tarefa(
            nome="lol_cenario",
            intervalo_segundos=settings.agendador_lolesports_cenario_minutos * 60,
            executar=_coletar_lolesports_cenario,
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


#: Fracao do intervalo a partir da qual a tarefa ja merece aviso.
#:
#: Uma tarefa que ocupa metade do proprio slot ainda funciona, mas nao tem
#: folga nenhuma pra crescer - e crescer e o normal aqui, porque quase toda
#: fila e proporcional ao tamanho do catalogo. O aviso e pra dar tempo de
#: reagir ANTES de virar erro.
_FRACAO_DE_AVISO = 0.5


def _conferir_duracao(tarefa: Tarefa, segundos: float) -> None:
    """Uma tarefa periodica tem que caber no proprio intervalo.

    Parece obvio, mas ninguem estava conferindo, e o custo disso foi real: em
    2026-09-16 a tarefa `steam` passou a pedir `appdetails` de 20.079 apps a
    ~3s cada - 16,7 HORAS de passada, numa tarefa agendada a cada 60 minutos.
    Ela nunca fechava um ciclo e martelava a Steam sem intervalo, e o log nao
    dizia absolutamente nada: cada app individual era um INFO de sucesso.

    O agendador ja tinha os dois numeros na mao (mede a duracao desde sempre,
    e o intervalo esta na propria `Tarefa`) - so nunca os comparava.

    E deliberadamente generico, e nao uma checagem do tamanho da fila: a
    proxima vez que isto acontecer pode ser por outro motivo (uma API que
    ficou lenta, um rate limit novo, uma fonte que dobrou de tamanho) e o
    sintoma vai ser o mesmo. Nao impede o problema - impede que ele passe
    calado, que foi o que deixou este durar.
    """
    intervalo = tarefa.intervalo_segundos
    if intervalo <= 0:
        return
    if segundos >= intervalo:
        logger.error(
            "tarefa nao cabe no proprio intervalo - ela nunca fecha um ciclo "
            "e a fonte externa fica sem pausa entre as chamadas",
            extra={
                "fonte": tarefa.nome,
                "segundos": round(segundos, 2),
                "intervalo_segundos": intervalo,
                "vezes_o_intervalo": round(segundos / intervalo, 2),
            },
        )
        _avisar(
            "\n".join(
                [
                    "[PlayDB] tarefa nao cabe no proprio intervalo",
                    "",
                    f"fonte: {tarefa.nome}",
                    f"levou {round(segundos / 60)} min para uma cadencia de "
                    f"{round(intervalo / 60)} min",
                    "",
                    "Ela nunca fecha um ciclo e a fonte externa fica sem pausa.",
                ]
            ),
            chave=f"estourou:{tarefa.nome}",
            # 12h: e um problema estrutural (fila cresceu, API ficou lenta),
            # nao um susto - repetir a cada rodada nao acrescenta nada.
            cooldown=12 * 3600.0,
        )
    elif segundos >= intervalo * _FRACAO_DE_AVISO:
        logger.warning(
            "tarefa ocupando boa parte do proprio intervalo - sem folga "
            "pra crescer",
            extra={
                "fonte": tarefa.nome,
                "segundos": round(segundos, 2),
                "intervalo_segundos": intervalo,
                "fracao_do_intervalo": round(segundos / intervalo, 2),
            },
        )


#: Quantas vezes o proprio intervalo uma tarefa pode rodar antes de o vigia
#: considera-la travada. Tres e folgado de proposito: uma rodada lenta ja e
#: avisada por `_conferir_duracao`; o vigia e pra travamento mesmo.
_FATOR_TRAVADA = 3.0

#: De quanto em quanto tempo o vigia acorda pra conferir.
_INTERVALO_DO_VIGIA = 60.0

#: Falhas seguidas antes de avisar por Telegram.
#:
#: Nao e 1 de proposito: fonte externa falha sozinha o tempo todo (a
#: Liquipedia da 429 a cada ciclo, por exemplo) e avisar na primeira faria o
#: chat virar ruido - e chat ruidoso vira chat silenciado, que e pior que
#: nao ter canal. Duas seguidas ja separa "a internet piscou" de "isto
#: quebrou".
_FALHAS_ANTES_DE_AVISAR = 2


def _avisar(texto: str, chave: str, cooldown: float = 3600.0) -> None:
    """Manda um aviso operacional, se o canal estiver configurado.

    Import tardio e `except` largo porque avisar sobre um problema jamais
    pode causar outro: sem Telegram configurado, ou com ele fora do ar, o
    agendador segue exatamente igual.
    """
    try:
        from services.notificacoes import telegram

        telegram.enviar(texto, chave=chave, cooldown_segundos=cooldown)
    except Exception as exc:  # noqa: BLE001 - aviso nunca derruba a coleta
        logger.warning(
            "falha ao despachar aviso",
            extra={"erro": f"{type(exc).__name__}: {exc}", "chave": chave},
        )


class _Vigia:
    """Avisa quando uma tarefa fica presa DENTRO da execucao.

    `_conferir_duracao` so mede tarefa que TERMINA - e por isso nao viu o
    pior caso real deste projeto: em 2026-09-16 o agendador local ficou 8
    HORAS parado em `hrtimer_nanosleep`, com CPU em 0% e sem uma linha de
    log, porque o ITAD devolveu 429 com `Retry-After` longo e o urllib3
    dormiu a espera inteira dentro da requisicao (ver `_RetryComTeto` em
    `http_client.py`, que corrige a causa). Como as ~35 tarefas rodam em
    serie numa thread so, steam_online, vlr e lolesports envelheceram um dia
    inteiro sem ninguem perceber.

    Esta classe nao mata a tarefa - matar thread em Python nao e seguro, e
    a causa raiz ja foi corrigida. Ela garante que a PROXIMA vez apareca no
    log em minutos, e nao seja descoberta por acaso olhando um painel.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tarefa: Tarefa | None = None
        self._inicio = 0.0
        self._avisada = False

    def entrando(self, tarefa: Tarefa) -> None:
        with self._lock:
            self._tarefa = tarefa
            self._inicio = time.monotonic()
            self._avisada = False

    def saindo(self) -> None:
        with self._lock:
            self._tarefa = None

    def conferir(self) -> None:
        """Um ciclo do vigia. Separado de `iniciar` pra ser testavel."""
        with self._lock:
            tarefa = self._tarefa
            if tarefa is None or self._avisada:
                return
            decorrido = time.monotonic() - self._inicio
            limite = tarefa.intervalo_segundos * _FATOR_TRAVADA
            if decorrido < limite:
                return
            self._avisada = True  # uma vez por execucao, nao a cada minuto

        logger.error(
            "tarefa possivelmente travada - segue em execucao e esta "
            "segurando a fila inteira do agendador",
            extra={
                "fonte": tarefa.nome,
                "segundos": round(decorrido),
                "intervalo_segundos": tarefa.intervalo_segundos,
            },
        )
        # O aviso mais importante do canal: e o unico sintoma de um problema
        # que, sem ele, so se descobre olhando um painel por acaso - foi
        # assim que 8 horas de travamento passaram batidas.
        _avisar(
            "\n".join(
                [
                    "[PlayDB] tarefa travada",
                    "",
                    f"fonte: {tarefa.nome}",
                    f"ha {round(decorrido / 60)} min em execucao "
                    f"(cadencia: {round(tarefa.intervalo_segundos / 60)} min)",
                    "",
                    "A fila do agendador esta parada atras dela.",
                ]
            ),
            chave=f"travada:{tarefa.nome}",
        )

    def iniciar(self, parada: "Parada") -> None:
        def laco() -> None:
            while not parada.parando:
                if parada.dormir(_INTERVALO_DO_VIGIA):
                    return
                self.conferir()

        threading.Thread(target=laco, name="vigia-agendador", daemon=True).start()


#: De quanto em quanto tempo mandar o resumo de estado.
_INTERVALO_DO_RESUMO = 24 * 3600.0


def montar_resumo(tarefas: list[Tarefa]) -> str:
    """Texto do resumo diario, a partir do que o agendador ja sabe.

    De proposito NAO consulta o banco nem importa nada de `controllers/`: o
    que o agendador conhece melhor que qualquer um e o proprio ciclo - o que
    rodou, o que falhou, o que esta ha tempo demais sem um sucesso. Frescor
    por fonte, que e a mesma pergunta vista do banco, ja e trabalho do painel
    admin; duplicar a consulta aqui seria duas verdades pra manter.

    O resumo existe menos pelo conteudo e mais pela CADENCIA: um canal que
    so fala quando ha problema e indistinguivel de um canal quebrado. Uma
    mensagem por dia prova que o caminho inteiro esta vivo.
    """
    agora = time.monotonic()

    quebradas = [t for t in tarefas if t.falhas_seguidas >= _FALHAS_ANTES_DE_AVISAR]
    # Sem sucesso ha mais de 3x a propria cadencia - o equivalente, visto de
    # dentro, ao "fonte parada" do painel.
    paradas = [
        t
        for t in tarefas
        if t.ultimo_sucesso > 0
        and (agora - t.ultimo_sucesso) > t.intervalo_segundos * _FATOR_TRAVADA
    ]
    nunca = [t for t in tarefas if t.ultimo_sucesso == 0 and t.execucoes > 0]

    linhas = [
        "[PlayDB] resumo de 24h",
        "",
        f"tarefas: {len(tarefas)}",
        f"execucoes: {sum(t.execucoes for t in tarefas)}",
        f"falhas: {sum(t.falhas for t in tarefas)}",
    ]

    if quebradas:
        linhas += ["", "falhando agora:"]
        linhas += [f"  {t.nome} ({t.falhas_seguidas}x seguidas)" for t in quebradas]
    if paradas:
        linhas += ["", "sem sucesso ha tempo demais:"]
        linhas += [
            f"  {t.nome} (ha {round((agora - t.ultimo_sucesso) / 3600)}h)"
            for t in paradas
        ]
    if nunca:
        linhas += ["", "nunca tiveram sucesso:"]
        linhas += [f"  {t.nome}" for t in nunca]
    if not (quebradas or paradas or nunca):
        linhas += ["", "tudo dentro do esperado."]

    return "\n".join(linhas)


def _contar_falha(tarefa: Tarefa, erro: str) -> None:
    """Soma a falha e avisa quando virar sequencia.

    Avisar na PRIMEIRA falha seria o caminho mais curto pra tornar o canal
    inutil: fonte externa pisca o tempo todo, e a Liquipedia deste projeto
    falha a cada ciclo por 429 ha 13 dias. O que merece aviso e a sequencia
    (`_FALHAS_ANTES_DE_AVISAR`), e mesmo ela com cooldown longo - uma fonte
    quebrada nao precisa avisar de hora em hora que continua quebrada.
    """
    tarefa.falhas += 1
    tarefa.falhas_seguidas += 1
    if tarefa.falhas_seguidas < _FALHAS_ANTES_DE_AVISAR:
        return

    _avisar(
        "\n".join(
            [
                "[PlayDB] coleta falhando",
                "",
                f"fonte: {tarefa.nome}",
                f"{tarefa.falhas_seguidas} falhas seguidas",
                f"ultimo erro: {erro[:200]}",
            ]
        ),
        chave=f"falha:{tarefa.nome}",
        # 6h: tempo de dar bom dia e olhar, sem repetir no meio da noite.
        cooldown=6 * 3600.0,
    )


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
        # A contagem fica so em `_contar_falha` (chamado abaixo) - somar aqui
        # tambem contava duas vezes a mesma falha.
        logger.exception(
            "coleta falhou",
            extra={"fonte": tarefa.nome, "erro": f"{type(exc).__name__}: {exc}"},
        )
        # Tambem confere aqui: uma tarefa que estoura o intervalo E TERMINA
        # EM ERRO e o pior caso dos dois, e era justamente o que ficava sem
        # numero nenhum no log.
        _conferir_duracao(tarefa, time.monotonic() - inicio)
        _contar_falha(tarefa, f"{type(exc).__name__}: {exc}")
        return False

    duracao = time.monotonic() - inicio
    _conferir_duracao(tarefa, duracao)

    tarefa.execucoes += 1
    if not resultado.sucesso:
        logger.warning(
            "coleta nao concluida",
            extra={"fonte": tarefa.nome, "erro": resultado.erro},
        )
        _contar_falha(tarefa, resultado.erro or "sem detalhe")
        return False

    tarefa.falhas_seguidas = 0
    tarefa.ultimo_sucesso = time.monotonic()

    logger.info(
        "coleta concluida",
        extra={
            "fonte": tarefa.nome,
            "coletados": resultado.registros_coletados,
            "carregados": resultado.registros_carregados,
            "segundos": round(duracao, 2),
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
        from services.etl.load_jogos import sincronizar

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

    vigia = _Vigia()
    vigia.iniciar(parada)

    logger.info(
        "agendador iniciado",
        extra={
            "tarefas": {t.nome: round(t.intervalo_segundos / 60) for t in tarefas},
            "rodar_ao_iniciar": settings.agendador_rodar_ao_iniciar,
        },
    )

    # Primeiro resumo so daqui a 24h: mandar um na subida faria cada deploy
    # virar mensagem, e deploy nao e evento operacional.
    proximo_resumo = time.monotonic() + _INTERVALO_DO_RESUMO

    while not parada.parando:
        if time.monotonic() >= proximo_resumo:
            proximo_resumo = time.monotonic() + _INTERVALO_DO_RESUMO
            # Sem chave: o resumo e raro por natureza, nao precisa cooldown.
            _avisar(montar_resumo(tarefas), chave=None)

        proxima = min(tarefas, key=lambda t: t.proxima_em)
        espera = proxima.proxima_em - time.monotonic()

        if espera > 0 and parada.dormir(espera):
            break
        if parada.parando:
            break

        vigia.entrando(proxima)
        try:
            sucesso = _executar(proxima, settings, storage)
        finally:
            vigia.saindo()
        proxima.reagendar(time.monotonic(), sucesso)

    logger.info(
        "agendador encerrado",
        extra={"execucoes": {t.nome: t.execucoes for t in tarefas},
               "falhas": {t.nome: t.falhas for t in tarefas}},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(rodar())
