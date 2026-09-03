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
    from collectors.steam_collector import SteamCollector

    monitorados = _apps_monitorados()
    logger.info(
        "apps monitorados",
        extra={"quantidade": len(monitorados) or "semente"},
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


def _coletar_liquipedia(settings: Settings, storage: RawStorage) -> CollectionResult:
    from collectors.liquipedia_collector import LiquipediaCollector

    coletor = LiquipediaCollector(raw_storage=storage, settings=settings)
    try:
        return coletor.run(carregar=True)
    finally:
        coletor.close()


def montar_tarefas(settings: Settings) -> list[Tarefa]:
    """As tarefas do agendador, na ordem em que rodam quando empatam."""
    return [
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
    ]


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
