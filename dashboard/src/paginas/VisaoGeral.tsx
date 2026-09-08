/**
 * Visao geral: o estado da coleta em numeros, com um recorte de cada dominio.
 *
 * Porte da tela "Visão Geral" do Stitch: cabecalho com pulso ao vivo e
 * seletor de periodo, quatro KPIs com chanfro HUD, dois paineis lado a lado
 * (ranking da Steam e a serie de partidas por dia) e a tabela de coletas por
 * fonte.
 */

import { useMemo, useState } from "react";

import {
  useMaisJogadosSteam,
  usePartidasPorDia,
  useSaude,
  useSerieTotalSteam,
  useVisaoGeral,
} from "../api/consultas";
import type { MaisJogadoSteam, PartidasPorDia, VisaoGeral } from "../api/tipos";
import { AcontecendoAgora } from "../componentes/AcontecendoAgora";
import { Botao, Consulta, Icone } from "../componentes/base";
import { AreaNeon } from "../componentes/graficos/AreaNeon";
import { BarraCheia, KpiHud, Painel, Segmentos } from "../componentes/hud";
import { corDoJogo } from "../tema";
import {
  fmtCurto,
  fmtDataCurta,
  fmtDataHora,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
} from "../utilitarios/formatos";

/** Janelas do seletor de periodo, em dias. `null` = tudo que foi coletado. */
const PERIODOS = [
  { valor: 1, rotulo: "24h" },
  { valor: 7, rotulo: "7 dias" },
  { valor: 30, rotulo: "30 dias" },
  { valor: null, rotulo: "Tudo" },
] as const;

/**
 * O que cada coletor busca e em que ritmo.
 *
 * Descreve o codigo dos coletores, nao um dado coletado - por isso e constante
 * e nao vem da API. A janela de 60 min do Steam e o `snapshot_bucket_minutes`
 * do `config.py`; a OpenDota nao tem janela porque o grao dela e a partida.
 *
 * A chave e `raw_data.fonte`. `liquipedia` cobre os tres coletores da wiki
 * (agenda, equipes, brackets), que gravam sob a mesma fonte; `valve` e o
 * Regional Standings de CS2, que vem do GitHub, nao de uma API REST. Toda fonte
 * que roda no `agendador.py` precisa ter uma linha aqui - sem ela a tabela
 * mostra "—" em tipo e frequencia.
 */
const FONTES: Record<
  string,
  {
    etiqueta: string;
    cor: string;
    api: string;
    descricao: string;
    frequencia: string;
  }
> = {
  steam: {
    etiqueta: "STEAM",
    cor: "#66C0F4",
    api: "Steam Web API",
    descricao: "Jogadores simultâneos, avaliações e preço da loja",
    frequencia: "janela de 60 min",
  },
  steam_online: {
    etiqueta: "STEAM",
    cor: "#8f98a0",
    api: "valvesoftware.com/about/stats",
    descricao:
      "Usuários simultâneos reais da plataforma Steam + nomes do Top 100 mais jogado",
    frequencia: "a cada 15 min",
  },
  opendota: {
    etiqueta: "DOTA 2",
    cor: "#16ef7a",
    api: "OpenDota API",
    descricao: "Partidas profissionais, heróis e séries minuto a minuto",
    frequencia: "por partida",
  },
  dota_herois: {
    etiqueta: "DOTA 2",
    cor: "#e0654f",
    api: "Datafeed dota2.com + OpenDota",
    descricao: "Lore, habilidades e guia de itens do meta de cada herói",
    frequencia: "semanal",
  },
  liquipedia: {
    etiqueta: "LIQUIPEDIA",
    cor: "#a78bfa",
    api: "Liquipedia (MediaWiki API)",
    descricao: "Agenda de confrontos, equipes e brackets de torneio — 66 wikis de esports",
    frequencia: "ticker 2×/dia; equipes e brackets diários",
  },
  valve: {
    etiqueta: "VALVE",
    cor: "#f59e0b",
    api: "GitHub (Regional Standings)",
    descricao: "Ranking mundial oficial de CS2 — pontuação por equipe",
    frequencia: "mensal (verificado toda semana)",
  },
  hltv: {
    etiqueta: "CS2",
    cor: "#3b82f6",
    api: "hltv.org/matches",
    descricao: "Partidas de Counter-Strike por vir — id estável, horário UTC e evento",
    frequencia: "a cada 5 min",
  },
  pandascore: {
    etiqueta: "PANDASCORE",
    cor: "#14b8a6",
    api: "PandaScore API",
    descricao: "Agenda e resultados de esports (CS, LoL, CoD, OW, R6, RL; Valorant só escudo)",
    frequencia: "a cada 30 min",
  },
  vlr: {
    etiqueta: "VALORANT",
    cor: "#ff4655",
    api: "vlr.gg",
    descricao: "Confrontos de Valorant: placar de série, evento e horário",
    frequencia: "resultados 1×/dia; agenda a cada 5 min",
  },
  vlr_rankings: {
    etiqueta: "VALORANT",
    cor: "#fb7185",
    api: "vlr.gg/rankings",
    descricao: "Ranking de equipes por região — prior do modelo de confronto",
    frequencia: "semanal",
  },
  vlr_detalhes: {
    etiqueta: "VALORANT",
    cor: "#fda4af",
    api: "vlr.gg (página da partida)",
    descricao: "Detalhe por mapa e por jogador das partidas já decididas",
    frequencia: "diário",
  },
  valorant_agentes: {
    etiqueta: "VALORANT",
    cor: "#ff8a80",
    api: "valorant-api.com",
    descricao: "Elenco do VALORANT: função e habilidades dos agentes",
    frequencia: "semanal",
  },
  opgg_esports: {
    etiqueta: "LOL",
    cor: "#5383e8",
    api: "OP.GG (servidor MCP)",
    descricao: "Confrontos profissionais de LoL: placar, liga, horário e escudo",
    frequencia: "a cada 6 h",
  },
  lol_campeoes: {
    etiqueta: "LOL",
    cor: "#c8aa6e",
    api: "OP.GG",
    descricao: "Campeões de LoL: desempenho, tier e taxa de ban por rota",
    frequencia: "semanal",
  },
  itad: {
    etiqueta: "PREÇO",
    cor: "#22c55e",
    api: "IsThereAnyDeal API",
    descricao: "Preço atual em ~33 lojas e menor preço histórico por jogo",
    frequencia: "a cada 12 h",
  },
  hltb: {
    etiqueta: "HLTB",
    cor: "#0ea5e9",
    api: "HowLongToBeat",
    descricao: "Tempo estimado para zerar cada jogo",
    frequencia: "diário",
  },
};

export function VisaoGeralPagina() {
  const [periodo, setPeriodo] = useState<number | null>(7);

  const geral = useVisaoGeral();
  const maisJogados = useMaisJogadosSteam(100);
  const porDia = usePartidasPorDia("dota2");
  const serieTotal = useSerieTotalSteam();
  const saude = useSaude();

  const online = saude.data?.status === "ok";

  /** A coleta mais recente de qualquer fonte: e o "quao fresco" do painel. */
  const ultimaColeta = useMemo(
    () =>
      geral.data?.coletas
        .map((coleta) => coleta.ultima_coleta)
        .filter((data): data is string => Boolean(data))
        .sort()
        .at(-1),
    [geral.data],
  );

  // O seletor de periodo recorta a serie de partidas - o unico conteudo
  // temporal da tela. Os KPIs sao contagens totais do banco e nao respondem a
  // ele; fingir que respondem seria pior que a assimetria.
  const serieRecortada = useMemo(() => {
    const dados = porDia.data ?? [];
    if (periodo === null) return dados;
    const corte = Date.now() - periodo * 86400_000;
    return dados.filter((ponto) => new Date(ponto.data).getTime() >= corte);
  }, [porDia.data, periodo]);

  const partidasNoPeriodo = serieRecortada.reduce(
    (soma, ponto) => soma + ponto.partidas,
    0,
  );

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-space-xs">
          <div className="flex flex-wrap items-center gap-space-sm">
            <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-primary drop-shadow-[0_0_12px_rgba(0,229,255,0.4)]">
              Visão Geral
            </h1>

            <div className="inline-flex items-center gap-space-xs rounded bg-surface-container-high px-space-sm py-space-xxs shadow-inner">
              <span className="relative flex h-2.5 w-2.5">
                {online && (
                  <span
                    className="absolute inline-flex h-full w-full animate-ping rounded-full bg-tertiary-container opacity-80"
                    aria-hidden
                  />
                )}
                <span
                  className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                    online
                      ? "bg-tertiary-container shadow-[0_0_8px_#16ef7a]"
                      : "bg-error"
                  }`}
                />
              </span>
              <span
                className={`font-badge-status text-badge-status uppercase tracking-widest ${
                  online ? "text-tertiary" : "text-error"
                }`}
              >
                {online ? "Ao vivo" : "Sem contato"}
              </span>
            </div>

            <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
              Telemetry // Deck 01
            </span>
          </div>

          <p className="flex items-center gap-space-xs font-body-sm text-body-sm text-on-surface-variant">
            <Icone nome="update" className="text-[15px] text-primary" />
            Última sincronização:{" "}
            <span className="font-title-code text-title-code text-on-surface">
              {fmtDataHora(ultimaColeta)}
            </span>
            <span className="text-outline">({fmtRelativo(ultimaColeta)})</span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-space-sm">
          <div className="flex items-center rounded bg-surface-container-low p-space-xxs shadow-sm">
            {PERIODOS.map((opcao) => (
              <button
                key={opcao.rotulo}
                type="button"
                aria-pressed={periodo === opcao.valor}
                onClick={() => setPeriodo(opcao.valor)}
                className={`rounded px-space-sm py-space-xs font-title-code text-title-code transition-colors ${
                  periodo === opcao.valor
                    ? "bg-surface-container-high text-primary shadow-sm"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {opcao.rotulo}
              </button>
            ))}
          </div>

          <Botao
            icone="refresh"
            aoClicar={() => {
              geral.refetch();
              maisJogados.refetch();
              porDia.refetch();
            }}
            desabilitado={geral.isFetching}
          >
            {geral.isFetching ? "Sincronizando…" : "Sincronizar"}
          </Botao>
        </div>
      </section>

      {/* ============ ACONTECENDO AGORA + DESTAQUE DO MODELO ============ */}
      <AcontecendoAgora />

      {/* ==================== QUATRO KPIS ==================== */}
      <Consulta estado={geral} altura={160}>
        {(dados: VisaoGeral) => {
          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta="Usuários simultâneos na Steam"
                canto="VALVE"
                valor={
                  dados.steam_usuarios_online !== null
                    ? fmtNumero(dados.steam_usuarios_online)
                    : "—"
                }
                valorNumerico={dados.steam_usuarios_online}
                formatarValor={fmtNumero}
                rotulo="Conectados à Steam agora"
                variacao={dados.steam_usuarios_online_variacao}
                notaVariacao="vs. coleta anterior"
                acento="primaria"
              >
                <div className="mt-space-sm flex items-baseline gap-space-xs font-title-code text-title-code text-on-surface-variant">
                  <span className="text-tertiary">
                    {dados.steam_usuarios_em_jogo !== null
                      ? fmtNumero(dados.steam_usuarios_em_jogo)
                      : "—"}
                  </span>
                  dentro de um jogo
                </div>
              </KpiHud>

              <KpiHud
                etiqueta="Snapshots da Steam"
                canto="SÉRIE TEMPORAL"
                valor={fmtNumero(dados.snapshots_steam)}
                valorNumerico={dados.snapshots_steam}
                formatarValor={fmtNumero}
                rotulo="Linhas de fato do catálogo"
                acento="secundaria"
                notaVariacao={`${fmtNumero(dados.jogos_steam)} jogos monitorados`}
              >
                <Segmentos
                  acesos={Math.min(6, Math.ceil(serieTotal.data?.length ?? 0))}
                />
              </KpiHud>

              <KpiHud
                etiqueta="Partidas coletadas"
                canto="STAR SCHEMA"
                valor={fmtNumero(dados.partidas)}
                valorNumerico={dados.partidas}
                formatarValor={fmtNumero}
                rotulo="Partidas profissionais"
                acento="terciaria"
                notaVariacao={`${fmtNumero(dados.linhas_fato_partida)} linhas de fato`}
              >
                <BarraCheia acesa={Boolean(dados.partidas)} acento="terciaria" />
              </KpiHud>

              <KpiHud
                etiqueta="Jogadores identificados"
                canto={`${fmtNumero(dados.personagens)} HERÓIS`}
                valor={fmtNumero(dados.jogadores)}
                valorNumerico={dados.jogadores}
                formatarValor={fmtNumero}
                rotulo="Na dimensão de jogador"
                acento="primaria"
                notaVariacao="fatos anônimos não contam"
              >
                <Segmentos
                  acesos={dados.jogadores ? 6 : 0}
                  acento="primaria"
                />
              </KpiHud>
            </section>
          );
        }}
      </Consulta>

      {/* ==================== DOIS PAINEIS ==================== */}
      <section className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        <Painel
          icone="leaderboard"
          titulo="Top 100 mais jogados na Steam"
          descricao="Jogadores dentro do jogo neste instante, direto da Valve — atualiza sozinho."
          meta={
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {maisJogados.isFetching ? (
                <span className="text-primary">atualizando…</span>
              ) : (
                <>ao vivo · <span className="text-primary">Valve</span></>
              )}
            </span>
          }
        >
          <Consulta estado={maisJogados}>
            {(lista: MaisJogadoSteam[]) => {
              const maximo = lista[0]?.jogadores_agora || 1;
              return (
                <div className="rolagem-discreta max-h-[28rem] overflow-y-auto pr-space-xs">
                  <div className="grid gap-space-xxs">
                    {lista.map((jogo) => (
                      <button
                        key={jogo.app_id}
                        type="button"
                        onClick={() =>
                          window.open(
                            `https://store.steampowered.com/app/${jogo.app_id}/`,
                            "_blank",
                            "noopener,noreferrer",
                          )
                        }
                        className="flex w-full items-center gap-space-sm rounded bg-surface-container px-space-sm py-space-xs text-left transition-colors hover:bg-surface-container-high"
                      >
                        <span className="w-7 shrink-0 font-label-caps text-label-caps tabular-nums text-outline">
                          #{String(jogo.posicao).padStart(2, "0")}
                        </span>

                        <span className="min-w-0 flex-1 truncate font-body-md text-body-sm font-bold text-on-surface">
                          {jogo.nome ?? `App ${jogo.app_id}`}
                        </span>

                        {jogo.variacao_semana !== null &&
                          jogo.variacao_semana !== 0 && (
                            <span
                              className={`flex shrink-0 items-center font-badge-status text-badge-status tabular-nums ${
                                jogo.variacao_semana > 0
                                  ? "text-tertiary"
                                  : "text-error"
                              }`}
                              title="Movimento vs. a semana passada"
                            >
                              <Icone
                                nome={
                                  jogo.variacao_semana > 0
                                    ? "arrow_drop_up"
                                    : "arrow_drop_down"
                                }
                                className="text-[14px]"
                              />
                              {Math.abs(jogo.variacao_semana)}
                            </span>
                          )}

                        <span className="w-20 shrink-0 text-right font-title-code text-title-code tabular-nums text-primary">
                          {fmtCurto(jogo.jogadores_agora)}
                        </span>

                        <span
                          className="hidden h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-surface-container-lowest sm:block"
                          aria-hidden
                        >
                          <span
                            className="block h-full rounded-full bg-gradient-to-r from-primary-container to-primary"
                            style={{
                              width: `${Math.max(
                                4,
                                (jogo.jogadores_agora / maximo) * 100,
                              ).toFixed(1)}%`,
                            }}
                          />
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            }}
          </Consulta>
        </Painel>

        <Painel
          icone="show_chart"
          titulo="Partidas de Dota 2 coletadas por dia"
          descricao="Data de disputa da partida, não a da coleta."
          meta={
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Período{" "}
              <span className="text-primary">
                {PERIODOS.find((p) => p.valor === periodo)?.rotulo}
              </span>
            </span>
          }
        >
          <Consulta estado={porDia}>
            {() => (
              <AreaNeon
                pontos={serieRecortada.map((ponto: PartidasPorDia) => ({
                  rotulo: fmtDataCurta(ponto.data),
                  valor: ponto.partidas,
                  detalhe: `${fmtNumero(ponto.partidas)} partidas`,
                }))}
                formatarValor={(valor) => fmtCurto(valor)}
                rodapeEsquerda={
                  <>
                    No período:{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {fmtNumero(partidasNoPeriodo)} partidas
                    </strong>
                  </>
                }
                rodapeDireita="Valve Dota 2 Network"
              />
            )}
          </Consulta>
        </Painel>
      </section>

      {/* ==================== COLETAS POR FONTE ==================== */}
      <Painel
        icone="database"
        titulo="Coletas por fonte de dados"
        descricao="Cada payload bruto fica gravado em disco e registrado em raw_data, o que permite reprocessar o ETL sem chamar as APIs de novo."
        meta={
          <span
            className={`inline-flex items-center gap-space-xs rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${
              online ? "bg-tertiary-container/10 text-tertiary" : "bg-error/10 text-error"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                online
                  ? "animate-pulse bg-tertiary-container shadow-[0_0_4px_#16ef7a]"
                  : "bg-error"
              }`}
              aria-hidden
            />
            {geral.data?.coletas.length ?? 0} pipelines
          </span>
        }
      >
        {/* Linha fina de gradiente, como no desenho. */}
        <div
          className="h-[2px] w-full rounded-full bg-gradient-to-r from-primary-container via-secondary to-transparent"
          aria-hidden
        />

        <Consulta estado={geral}>
          {(dados: VisaoGeral) => (
            <div className="rolagem-discreta overflow-x-auto rounded-lg">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                    <th className="px-space-md py-space-sm">Fonte</th>
                    <th className="px-space-md py-space-sm">Tipo de dados</th>
                    <th className="px-space-md py-space-sm text-center">Frequência</th>
                    <th className="px-space-md py-space-sm text-center">Última coleta</th>
                    <th className="px-space-md py-space-sm text-right">
                      Payloads brutos
                    </th>
                    <th className="px-space-md py-space-sm text-right">Status</th>
                  </tr>
                </thead>

                <tbody>
                  {dados.coletas.map((coleta, indice) => {
                    const meta = FONTES[coleta.fonte];
                    const ativa = coleta.payloads > 0;

                    return (
                      <tr
                        key={coleta.fonte}
                        className={`transition-colors hover:bg-surface-container ${
                          indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                        }`}
                      >
                        <td className="px-space-md py-space-sm">
                          <div className="flex items-center gap-space-xs font-title-code text-title-code text-on-surface">
                            <span
                              className="rounded bg-surface-container-highest px-space-xs py-space-xxs font-badge-status text-badge-status"
                              style={{ color: meta?.cor ?? corDoJogo(coleta.fonte) }}
                            >
                              {meta?.etiqueta ?? coleta.fonte.toUpperCase()}
                            </span>
                            {meta?.api ?? coleta.fonte}
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm font-body-md text-body-sm text-on-surface-variant">
                          {meta?.descricao ?? "—"}
                        </td>

                        <td className="px-space-md py-space-sm text-center font-title-code text-title-code text-outline">
                          {meta?.frequencia ?? "—"}
                        </td>

                        <td
                          className="px-space-md py-space-sm text-center font-body-md text-body-sm text-on-surface-variant"
                          title={fmtDataHora(coleta.ultima_coleta)}
                        >
                          {fmtRelativo(coleta.ultima_coleta)}
                        </td>

                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code text-primary">
                          {fmtNumero(coleta.payloads)}
                        </td>

                        <td className="px-space-md py-space-sm text-right">
                          <span
                            className={`inline-flex items-center gap-space-xs rounded px-space-xs py-space-xxs font-badge-status text-badge-status ${
                              ativa
                                ? "bg-tertiary-container/10 text-tertiary"
                                : "bg-surface-container-highest text-outline"
                            }`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                ativa
                                  ? "animate-pulse bg-tertiary-container shadow-[0_0_4px_#16ef7a]"
                                  : "bg-outline"
                              }`}
                              aria-hidden
                            />
                            {ativa ? "Online / OK" : "Sem coleta"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Consulta>

        <div className="flex flex-wrap items-center justify-between gap-space-sm border-t border-outline-variant/30 pt-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span>
            Cobertura:{" "}
            <span className="text-primary">
              {fmtPercentual(
                geral.data?.coletas.length
                  ? (geral.data.coletas.filter((c) => c.payloads > 0).length /
                      geral.data.coletas.length) *
                      100
                  : 0,
                0,
              )}
            </span>{" "}
            das fontes com payload
          </span>
          <span>
            Latência da API{" "}
            <span className="text-primary">
              {saude.data ? `${saude.data.latenciaMs}ms` : "—"}
            </span>
          </span>
        </div>
      </Painel>
    </>
  );
}
