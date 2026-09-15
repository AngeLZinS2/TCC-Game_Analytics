/**
 * Visao geral: o estado da coleta em numeros, com um recorte de cada dominio.
 *
 * Porte da tela "Visão Geral" do Stitch: cabecalho com pulso ao vivo e
 * seletor de periodo, quatro KPIs com chanfro HUD, dois paineis lado a lado
 * (ranking da Steam e a serie de partidas por dia) e a tabela de coletas por
 * fonte.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import pt from "@i18n/locales/pt";
import {
  useMaisJogadosSteam,
  usePartidasPorDia,
  useSaude,
  useSerieTotalSteam,
  useVisaoGeral,
} from "@models/api/consultas";
import type { MaisJogadoSteam, PartidasPorDia, VisaoGeral } from "@models/api/tipos";
import { AcontecendoAgora, DestaqueDoDia } from "@views/componentes/AcontecendoAgora";
import { Botao, Consulta, Icone } from "@views/componentes/base";
import { AreaNeon } from "@views/componentes/graficos/AreaNeon";
import { BarraCheia, KpiHud, Painel, Segmentos } from "@views/componentes/hud";
import { corDoJogo } from "@views/tema";
import {
  fmtCurto,
  fmtDataCurta,
  fmtDataHora,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
} from "@util/formatos";

/** Janelas do seletor de periodo, em dias. `null` = tudo que foi coletado.
 * `chave` e a chave de traducao em `painel.periodos.<chave>`. */
const PERIODOS = [
  { valor: 1, chave: "dia" },
  { valor: 7, chave: "semana" },
  { valor: 30, chave: "mes" },
  { valor: null, chave: "tudo" },
] as const;

/**
 * O que cada coletor busca e em que ritmo.
 *
 * Descreve o codigo dos coletores, nao um dado coletado - por isso e constante
 * e nao vem da API. So a cor e a API/URL de origem ficam aqui (nao mudam por
 * idioma); etiqueta/descricao/frequencia vem de `painel.fontes.<chave>` nos
 * arquivos de traducao (Fase 35).
 *
 * A chave e `raw_data.fonte`. `liquipedia` cobre os tres coletores da wiki
 * (agenda, equipes, brackets), que gravam sob a mesma fonte; `valve` e o
 * Regional Standings de CS2, que vem do GitHub, nao de uma API REST. Toda fonte
 * que roda no `agendador.py` precisa ter uma linha aqui - sem ela a tabela
 * mostra "—" em tipo e frequencia.
 */
const FONTES_META: Record<string, { cor: string; api: string }> = {
  steam: { cor: "#66C0F4", api: "Steam Web API" },
  steam_online: { cor: "#8f98a0", api: "valvesoftware.com/about/stats" },
  opendota: { cor: "#40d19e", api: "OpenDota API" },
  dota_herois: { cor: "#e0654f", api: "Datafeed dota2.com + OpenDota" },
  liquipedia: { cor: "#a78bfa", api: "Liquipedia (MediaWiki API)" },
  valve: { cor: "#f59e0b", api: "GitHub (Regional Standings)" },
  hltv: { cor: "#3b82f6", api: "hltv.org/matches" },
  pandascore: { cor: "#14b8a6", api: "PandaScore API" },
  vlr: { cor: "#ff4655", api: "vlr.gg" },
  vlr_rankings: { cor: "#fb7185", api: "vlr.gg/rankings" },
  vlr_detalhes: { cor: "#fda4af", api: "vlr.gg (página da partida)" },
  valorant_agentes: { cor: "#ff8a80", api: "valorant-api.com" },
  opgg_esports: { cor: "#5383e8", api: "OP.GG (servidor MCP)" },
  lol_campeoes: { cor: "#c8aa6e", api: "OP.GG" },
  itad: { cor: "#22c55e", api: "IsThereAnyDeal API" },
  hltb: { cor: "#0ea5e9", api: "HowLongToBeat" },
};

export function VisaoGeralPagina() {
  const { t } = useTranslation();
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
            <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-on-surface">
              {t("painel.titulo")}
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
                      ? "bg-tertiary-container shadow-[0_0_8px_#40d19e]"
                      : "bg-error"
                  }`}
                />
              </span>
              <span
                className={`font-badge-status text-badge-status uppercase tracking-widest ${
                  online ? "text-tertiary" : "text-error"
                }`}
              >
                {online ? t("painel.aoVivo") : t("painel.semContato")}
              </span>
            </div>

            <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
              {t("painel.telemetryDeck")}
            </span>
          </div>

          <p className="flex items-center gap-space-xs font-body-sm text-body-sm text-on-surface-variant">
            <Icone nome="update" className="text-[15px] text-primary" />
            {t("painel.ultimaSincronizacao")}{" "}
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
                key={opcao.chave}
                type="button"
                aria-pressed={periodo === opcao.valor}
                onClick={() => setPeriodo(opcao.valor)}
                className={`rounded px-space-sm py-space-xs font-title-code text-title-code transition-colors ${
                  periodo === opcao.valor
                    ? "bg-surface-container-high text-primary shadow-sm"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {t(`painel.periodos.${opcao.chave}`)}
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
            {geral.isFetching ? t("painel.sincronizando") : t("painel.sincronizar")}
          </Botao>
        </div>
      </section>

      {/* ==================== QUATRO KPIS ==================== */}
      <Consulta estado={geral} altura={160}>
        {(dados: VisaoGeral) => {
          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta={t("painel.kpis.usuariosSimultaneos")}
                canto="VALVE"
                valor={
                  dados.steam_usuarios_online !== null
                    ? fmtNumero(dados.steam_usuarios_online)
                    : "—"
                }
                valorNumerico={dados.steam_usuarios_online}
                formatarValor={fmtNumero}
                rotulo={t("painel.kpis.conectados")}
                variacao={dados.steam_usuarios_online_variacao}
                notaVariacao={t("painel.kpis.vsColetaAnterior")}
                acento="primaria"
              >
                <div className="mt-space-sm flex items-baseline gap-space-xs font-title-code text-title-code text-on-surface-variant">
                  <span className="text-tertiary">
                    {dados.steam_usuarios_em_jogo !== null
                      ? fmtNumero(dados.steam_usuarios_em_jogo)
                      : "—"}
                  </span>
                  {t("painel.kpis.dentroDeUmJogo")}
                </div>
              </KpiHud>

              <KpiHud
                etiqueta={t("painel.kpis.snapshots")}
                canto={t("painel.kpis.serieTemporal")}
                valor={fmtNumero(dados.snapshots_steam)}
                valorNumerico={dados.snapshots_steam}
                formatarValor={fmtNumero}
                rotulo={t("painel.kpis.linhasFatoCatalogo")}
                acento="secundaria"
                notaVariacao={t("painel.kpis.jogosMonitorados", { contagem: fmtNumero(dados.jogos_steam) })}
              >
                <Segmentos
                  acesos={Math.min(6, Math.ceil(serieTotal.data?.length ?? 0))}
                />
              </KpiHud>

              <KpiHud
                etiqueta={t("painel.kpis.partidasColetadas")}
                canto={t("painel.kpis.starSchema")}
                valor={fmtNumero(dados.partidas)}
                valorNumerico={dados.partidas}
                formatarValor={fmtNumero}
                rotulo={t("painel.kpis.partidasProfissionais")}
                acento="terciaria"
                notaVariacao={t("painel.kpis.linhasDeFato", { contagem: fmtNumero(dados.linhas_fato_partida) })}
              >
                <BarraCheia acesa={Boolean(dados.partidas)} acento="terciaria" />
              </KpiHud>

              <KpiHud
                etiqueta={t("painel.kpis.jogadoresIdentificados")}
                canto={t("painel.kpis.herois", { contagem: fmtNumero(dados.personagens) })}
                valor={fmtNumero(dados.jogadores)}
                valorNumerico={dados.jogadores}
                formatarValor={fmtNumero}
                rotulo={t("painel.kpis.naDimensaoJogador")}
                acento="primaria"
                notaVariacao={t("painel.kpis.fatosAnonimos")}
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
          titulo={t("painel.top100.titulo")}
          descricao={t("painel.top100.descricao")}
          meta={
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {maisJogados.isFetching ? (
                <span className="text-primary">{t("painel.top100.atualizando")}</span>
              ) : (
                <>{t("painel.top100.aoVivo")} · <span className="text-primary">Valve</span></>
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
                              title={t("painel.top100.movimento")}
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
          titulo={t("painel.partidasPorDia.titulo")}
          descricao={t("painel.partidasPorDia.descricao")}
          meta={
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {t("painel.partidasPorDia.periodo")}{" "}
              <span className="text-primary">
                {t(`painel.periodos.${PERIODOS.find((p) => p.valor === periodo)?.chave ?? "semana"}`)}
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
                  detalhe: t("painel.partidasPorDia.partidas", { contagem: fmtNumero(ponto.partidas) }),
                }))}
                formatarValor={(valor) => fmtCurto(valor)}
                rodapeEsquerda={
                  <>
                    {t("painel.partidasPorDia.noPeriodo")}{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {t("painel.partidasPorDia.partidas", { contagem: fmtNumero(partidasNoPeriodo) })}
                    </strong>
                  </>
                }
                rodapeDireita={t("painel.partidasPorDia.valveNetwork")}
              />
            )}
          </Consulta>
        </Painel>
      </section>

      {/* ======= DESTAQUE DO DIA + ACONTECENDO AGORA ======= */}
      <DestaqueDoDia />
      <AcontecendoAgora />

      {/* ==================== COLETAS POR FONTE ==================== */}
      <Painel
        icone="database"
        titulo={t("painel.coletas.titulo")}
        descricao={t("painel.coletas.descricao")}
        meta={
          <span
            className={`inline-flex items-center gap-space-xs rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${
              online ? "bg-tertiary-container/10 text-tertiary" : "bg-error/10 text-error"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                online
                  ? "animate-pulse bg-tertiary-container shadow-[0_0_4px_#40d19e]"
                  : "bg-error"
              }`}
              aria-hidden
            />
            {t("painel.coletas.pipelines", { contagem: geral.data?.coletas.length ?? 0 })}
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
                    <th className="px-space-md py-space-sm">{t("painel.coletas.fonte")}</th>
                    <th className="px-space-md py-space-sm">{t("painel.coletas.tipoDados")}</th>
                    <th className="px-space-md py-space-sm text-center">{t("painel.coletas.frequencia")}</th>
                    <th className="px-space-md py-space-sm text-center">{t("painel.coletas.ultimaColeta")}</th>
                    <th className="px-space-md py-space-sm text-right">
                      {t("painel.coletas.payloadsBrutos")}
                    </th>
                    <th className="px-space-md py-space-sm text-right">{t("painel.coletas.status")}</th>
                  </tr>
                </thead>

                <tbody>
                  {dados.coletas.map((coleta, indice) => {
                    const meta = FONTES_META[coleta.fonte];
                    const temTraducao = Object.prototype.hasOwnProperty.call(
                      (pt.painel.fontes as Record<string, unknown>),
                      coleta.fonte,
                    );
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
                              {temTraducao
                                ? t(`painel.fontes.${coleta.fonte}.etiqueta`)
                                : coleta.fonte.toUpperCase()}
                            </span>
                            {meta?.api ?? coleta.fonte}
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm font-body-md text-body-sm text-on-surface-variant">
                          {temTraducao ? t(`painel.fontes.${coleta.fonte}.descricao`) : "—"}
                        </td>

                        <td className="px-space-md py-space-sm text-center font-title-code text-title-code text-outline">
                          {temTraducao ? t(`painel.fontes.${coleta.fonte}.frequencia`) : "—"}
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
                                  ? "animate-pulse bg-tertiary-container shadow-[0_0_4px_#40d19e]"
                                  : "bg-outline"
                              }`}
                              aria-hidden
                            />
                            {ativa ? t("painel.coletas.onlineOk") : t("painel.coletas.semColeta")}
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
            {t("painel.coletas.cobertura")}{" "}
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
            {t("painel.coletas.dasFontesComPayload")}
          </span>
          <span>
            {t("painel.coletas.latenciaApi")}{" "}
            <span className="text-primary">
              {saude.data ? `${saude.data.latenciaMs}ms` : "—"}
            </span>
          </span>
        </div>
      </Painel>
    </>
  );
}
