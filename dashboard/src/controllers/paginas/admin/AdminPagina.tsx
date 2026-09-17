/**
 * Painel admin — centro de controle do PlayDB.
 *
 * Usa o design system do projeto (`Painel`, `KpiHud`, `AreaNeon`, `Selo`,
 * tokens de cor do Tailwind), com densidade maior que as telas públicas:
 * aqui o alvo é quem opera, e espaço vazio custa uma rolagem a mais para
 * achar o que quebrou.
 *
 * **Regra que decidiu o layout: só dado real.** Vários blocos do desenho de
 * referência não existem neste backend, e nenhum deles foi preenchido com
 * número plausível:
 *
 * * latência por API — não é medida em lugar nenhum. O painel de serviços
 *   mostra FRESCOR (`raw_data.coletado_em` contra a cadência da tarefa), que
 *   responde "algo parou de coletar?" — a pergunta que a latência nem
 *   responderia. A única latência exibida é a do banco, medida na hora;
 * * erros por API e crescimento por tabela — não há histórico nenhum
 *   gravado, então as colunas não existem em vez de existirem zeradas;
 * * "executar sincronização" — não há ação manual de sync no sistema, e o
 *   briefing pedia o botão só se ela já existisse;
 * * variação percentual — só aparece quando a janela equivalente de ontem
 *   teve movimento (ver `variacao`).
 *
 * Autorização é do backend (`ADMIN_FIREBASE_UIDS`): toda consulta daqui
 * responde 403 para conta fora da lista, e a tela trata isso como "sem
 * acesso". Esconder o link no menu é conveniência, nunca a proteção.
 *
 * "Contas" mostra só nome e data de criação — nunca e-mail nem uid do
 * Firebase, para o painel não virar relatório de dado pessoal (LGPD).
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import {
  useAtividadeAdmin,
  useBancoAdmin,
  useCatalogoSteamAdmin,
  useContasAdmin,
  useServicosAdmin,
  useSistemaAdmin,
  useVisaoGeralAdmin,
} from "@models/api/consultas";
import { ErroApi } from "@models/api/cliente";
import { sairDaConta } from "@models/conta/acoes";
import type {
  ListaContasAdmin,
  PontoAcessoDia,
  SaudeBanco,
  SaudeCatalogoSteam,
  SincronizacaoSteamStatus,
  TermoBuscado,
  VisaoGeralAdmin,
} from "@models/api/tipos";
import { Botao, Consulta, Icone, Selo } from "@views/componentes/base";
import { Painel, Pilula } from "@views/componentes/hud";
import { AreaNeon, type PontoArea } from "@views/componentes/graficos/AreaNeon";
import { useEntrarNaTela } from "@models/hooks/animacao";
import { fmtData, fmtNumero, fmtRelativo } from "@util/formatos";
import { CartaoRecurso, CartaoUptime } from "./CartaoRecurso";
import { PainelServicos } from "./PainelServicos";
import { PainelAlertas, montarAlertas } from "./PainelAlertas";
import { PainelAtividade } from "./PainelAtividade";

/**
 * Variação percentual contra a janela equivalente de ontem.
 *
 * `null` quando ontem não teve movimento: "+100%" sobre zero não informa
 * nada, e um painel que mostra isso ensina quem lê a ignorar o número. A
 * janela de ontem já vem recortada na mesma hora do dia pelo backend.
 */
function variacao(hoje: number, ontem: number): number | null {
  if (ontem <= 0) return null;
  return ((hoje - ontem) / ontem) * 100;
}

/** Períodos do gráfico. Só entra o que o histórico do banco sustenta. */
const PERIODOS = [7, 30, 90] as const;
type Periodo = (typeof PERIODOS)[number];

export function AdminPagina() {
  const { t } = useTranslation();
  const [saindo, setSaindo] = useState(false);
  const [periodo, setPeriodo] = useState<Periodo>(30);

  const visaoGeral = useVisaoGeralAdmin();
  const sistema = useSistemaAdmin();
  const servicos = useServicosAdmin();
  const atividade = useAtividadeAdmin();
  const banco = useBancoAdmin();
  const contas = useContasAdmin();
  const catalogoSteam = useCatalogoSteamAdmin();

  const consultas = [visaoGeral, sistema, servicos, atividade, banco, contas, catalogoSteam];
  const semAcesso = consultas.some(
    (consulta) => consulta.error instanceof ErroApi && consulta.error.status === 403,
  );

  const alertas = useMemo(
    () => montarAlertas(sistema.data, servicos.data, catalogoSteam.data, t),
    [sistema.data, servicos.data, catalogoSteam.data, t],
  );

  // "Atualizado há X": o dado mais VELHO entre as consultas, não o mais
  // novo — dizer "agora" porque uma das sete acabou de responder esconderia
  // as outras seis paradas.
  const atualizadoEm = Math.min(
    ...consultas.map((consulta) => consulta.dataUpdatedAt || Date.now()),
  );
  const atualizando = consultas.some((consulta) => consulta.isFetching);

  async function sair() {
    setSaindo(true);
    try {
      await sairDaConta();
    } finally {
      setSaindo(false);
    }
  }

  function atualizarTudo() {
    for (const consulta of consultas) void consulta.refetch();
  }

  if (semAcesso) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-space-base text-center">
        <Icone nome="lock" className="text-[40px] text-outline" />
        <h1 className="font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
          {t("admin.semAcesso.titulo")}
        </h1>
        <p className="max-w-sm font-body-sm text-body-sm text-outline">
          {t("admin.semAcesso.corpo")}
        </p>
        <Botao icone="logout" aoClicar={sair} desabilitado={saindo}>
          {t("admin.semAcesso.trocarConta")}
        </Botao>
      </div>
    );
  }

  // O status do topo é a conclusão do painel, não um enfeite: ele só diz
  // "operacional" quando não há alerta nenhum aberto.
  const critico = alertas.some((alerta) => alerta.nivel === "critico");
  const statusGeral = critico ? "critico" : alertas.length > 0 ? "atencao" : "ok";
  const CORES_STATUS = {
    ok: { texto: "text-tertiary", ponto: "bg-tertiary-container shadow-[0_0_8px_#40d19e]" },
    atencao: { texto: "text-secondary", ponto: "bg-secondary-fixed-dim" },
    critico: { texto: "text-error", ponto: "bg-error" },
  } as const;

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <section className="flex flex-col gap-space-sm pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-space-sm">
          <h1 className="flex items-center gap-space-xs font-headline-lg text-headline-lg uppercase tracking-wide text-on-surface">
            <Icone nome="admin_panel_settings" className="text-[24px] text-primary" />
            {t("admin.titulo")}
          </h1>

          <span className="inline-flex items-center gap-space-xs rounded bg-surface-container-high px-space-sm py-space-xxs shadow-inner">
            <span className="relative flex h-2.5 w-2.5">
              {statusGeral === "ok" && (
                <span
                  className="absolute inline-flex h-full w-full animate-ping rounded-full bg-tertiary-container opacity-80"
                  aria-hidden
                />
              )}
              <span
                className={`relative inline-flex h-2.5 w-2.5 rounded-full ${CORES_STATUS[statusGeral].ponto}`}
              />
            </span>
            <span
              className={`font-badge-status text-badge-status uppercase tracking-widest ${CORES_STATUS[statusGeral].texto}`}
            >
              {t(`admin.status.${statusGeral}`)}
            </span>
          </span>

          {visaoGeral.data && (
            <span className="inline-flex items-center gap-space-xs rounded bg-surface-container-high px-space-sm py-space-xxs font-badge-status text-badge-status uppercase tracking-widest text-on-surface-variant">
              <Icone nome="visibility" className="text-[13px] text-primary" />
              {t("admin.noSiteAgora", { n: fmtNumero(visaoGeral.data.online_agora) })}
            </span>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-space-sm">
          <span className="font-body-md text-[11px] text-outline">
            {atualizando
              ? t("admin.cabecalho.atualizando")
              : t("admin.cabecalho.atualizadoEm", {
                  quando: fmtRelativo(new Date(atualizadoEm).toISOString()),
                })}
          </span>
          <Botao icone="refresh" aoClicar={atualizarTudo} desabilitado={atualizando}>
            {t("admin.cabecalho.atualizar")}
          </Botao>
          <Botao icone="logout" aoClicar={sair} desabilitado={saindo}>
            {t("admin.sair")}
          </Botao>
        </div>
      </section>

      <p className="font-body-md text-body-sm text-outline">{t("admin.subtitulo")}</p>

      {/* ==================== SAUDE DO SERVIDOR ==================== */}
      <section className="grid grid-cols-1 gap-space-base sm:grid-cols-2 xl:grid-cols-4">
        {sistema.isError ? (
          <div className="sm:col-span-2 xl:col-span-4">
            <Selo cor="negativo">{t("admin.saude.erro")}</Selo>
          </div>
        ) : sistema.data ? (
          <>
            <CartaoRecurso
              rotulo={t("admin.saude.cpu")}
              icone="memory"
              percentual={sistema.data.cpu?.percentual ?? null}
              detalhe={sistema.data.cpu?.detalhe ?? null}
              atualizando={sistema.isFetching}
            />
            <CartaoRecurso
              rotulo={t("admin.saude.memoria")}
              icone="developer_board"
              percentual={sistema.data.memoria?.percentual ?? null}
              detalhe={sistema.data.memoria?.detalhe ?? null}
              atualizando={sistema.isFetching}
            />
            <CartaoRecurso
              rotulo={t("admin.saude.disco")}
              icone="storage"
              percentual={sistema.data.disco?.percentual ?? null}
              detalhe={sistema.data.disco?.detalhe ?? null}
              atualizando={sistema.isFetching}
            />
            <CartaoUptime
              segundos={sistema.data.uptime_segundos}
              fonte={sistema.data.fonte}
            />
          </>
        ) : (
          [1, 2, 3, 4].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-surface-container-high/60" />
          ))
        )}
      </section>

      {/* Carga do sistema só existe via Netdata (psutil não tem equivalente
          multiplataforma simples) — sem ela, a linha inteira some. */}
      {sistema.data?.carga_1min != null && (
        <div className="flex flex-wrap items-center gap-space-xs">
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("admin.saude.carga")}
          </span>
          {[
            { rotulo: t("admin.saude.min1"), valor: sistema.data.carga_1min },
            { rotulo: t("admin.saude.min5"), valor: sistema.data.carga_5min },
            { rotulo: t("admin.saude.min15"), valor: sistema.data.carga_15min },
          ].map((carga) => (
            <Selo key={carga.rotulo} cor="neutro">
              <Icone nome="speed" className="text-[13px]" />
              {carga.valor?.toFixed(2)} · {carga.rotulo}
            </Selo>
          ))}
          <Selo cor="neutro">
            {t(sistema.data.fonte === "netdata" ? "admin.saude.netdata" : "admin.saude.local")}
          </Selo>
        </div>
      )}

      {/* ==================== ALERTAS ==================== */}
      <PainelAlertas alertas={alertas} />

      {/* ==================== SERVICOS + ATIVIDADE ==================== */}
      <div className="grid grid-cols-1 gap-space-base xl:grid-cols-3">
        <div className="xl:col-span-2">
          <Consulta estado={servicos} altura={320}>
            {(dados) => <PainelServicos dados={dados} />}
          </Consulta>
        </div>
        <Consulta estado={atividade} altura={320}>
          {(dados) => <PainelAtividade dados={dados} />}
        </Consulta>
      </div>

      {/* ==================== KPIS ==================== */}
      <Consulta estado={visaoGeral} altura={160}>
        {(geral: VisaoGeralAdmin) => (
          <section className="grid grid-cols-1 gap-space-base sm:grid-cols-2 xl:grid-cols-4">
            <KpiAdmin
              rotulo={t("admin.kpis.visitantesNoSite")}
              canto={t("admin.kpis.agora")}
              valor={geral.online_agora}
              nota={t("admin.kpis.janela90s")}
              icone="visibility"
              acento="tertiary"
            />
            <KpiAdmin
              rotulo={t("admin.kpis.pageViews")}
              canto={t("admin.kpis.hoje")}
              valor={geral.acessos_hoje}
              delta={variacao(geral.acessos_hoje, geral.acessos_ontem)}
              nota={t("admin.kpis.vsOntem")}
              icone="ads_click"
              acento="primary"
            />
            <KpiAdmin
              rotulo={t("admin.kpis.visitantesUnicos")}
              canto={t("admin.kpis.hoje")}
              valor={geral.visitantes_unicos_hoje}
              delta={variacao(geral.visitantes_unicos_hoje, geral.visitantes_unicos_ontem)}
              nota={t("admin.kpis.vsOntem")}
              icone="group"
              acento="secondary"
            />
            <KpiAdmin
              rotulo={t("admin.kpis.buscasRealizadas")}
              canto={t("admin.kpis.hoje")}
              valor={geral.buscas_hoje}
              delta={variacao(geral.buscas_hoje, geral.buscas_ontem)}
              nota={t("admin.kpis.vsOntem")}
              icone="search"
              acento="primary"
            />
          </section>
        )}
      </Consulta>

      {/* ==================== SERIE DE ACESSOS ==================== */}
      <Consulta estado={visaoGeral} altura={260}>
        {(geral: VisaoGeralAdmin) => (
          <SerieAcessos
            geral={geral}
            periodo={periodo}
            aoTrocarPeriodo={setPeriodo}
            t={t}
          />
        )}
      </Consulta>

      <div className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        {/* ==================== POR PERIODO ==================== */}
        <Consulta estado={visaoGeral} altura={220}>
          {(geral: VisaoGeralAdmin) => <TabelaPorPeriodo geral={geral} t={t} />}
        </Consulta>

        {/* ==================== TERMOS MAIS BUSCADOS ==================== */}
        <Consulta estado={visaoGeral} altura={220}>
          {(geral: VisaoGeralAdmin) => (
            <TermosMaisBuscados termos={geral.termos_mais_buscados} t={t} />
          )}
        </Consulta>
      </div>

      {/* ==================== BANCO + STEAM ==================== */}
      <div className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        <Consulta estado={banco} altura={260}>
          {(dados: SaudeBanco) => <BancoDeDados dados={dados} t={t} />}
        </Consulta>
        <Consulta estado={catalogoSteam} altura={260}>
          {(dados: SaudeCatalogoSteam) => <CatalogoSteam dados={dados} t={t} />}
        </Consulta>
      </div>

      {/* ==================== CONTAS ==================== */}
      <Consulta estado={contas} altura={260}>
        {(dados: ListaContasAdmin) => <Contas dados={dados} t={t} />}
      </Consulta>
    </>
  );
}

/** KPI do painel: número grande, variação real (quando existe) e nota de contexto. */
function KpiAdmin({
  rotulo,
  canto,
  valor,
  delta,
  nota,
  icone,
  acento,
}: {
  rotulo: string;
  canto: string;
  valor: number;
  /** `null` = sem base de comparação. O bloco de variação simplesmente não
   * aparece, em vez de mostrar "+0%" ou "—" como se fosse medida. */
  delta?: number | null;
  nota: string;
  icone: string;
  acento: "primary" | "secondary" | "tertiary";
}) {
  const CORES = {
    primary: "text-primary",
    secondary: "text-secondary",
    tertiary: "text-tertiary",
  } as const;

  return (
    <article className="flex flex-col gap-space-xs rounded-xl bg-surface-container-low/90 p-space-base shadow-2xl">
      <header className="flex items-center justify-between gap-space-sm">
        <span className="flex min-w-0 items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant">
          <Icone nome={icone} className={`text-[15px] ${CORES[acento]}`} />
          <span className="truncate">{rotulo}</span>
        </span>
        <span className="shrink-0 font-badge-status text-badge-status uppercase tracking-widest text-outline">
          {canto}
        </span>
      </header>

      <div className="flex flex-wrap items-baseline gap-space-sm">
        <span className="font-headline-lg text-headline-lg tabular-nums text-on-surface">
          {fmtNumero(valor)}
        </span>
        {delta !== null && delta !== undefined && (
          <span
            className={`inline-flex items-center gap-space-xxs font-title-code text-title-code tabular-nums ${
              delta >= 0 ? "text-tertiary" : "text-error"
            }`}
          >
            <Icone
              nome={delta >= 0 ? "trending_up" : "trending_down"}
              className="text-[14px]"
            />
            {delta >= 0 ? "+" : ""}
            {delta.toFixed(1)}%
          </span>
        )}
      </div>

      <p className="font-body-md text-[11px] leading-tight text-outline">{nota}</p>
    </article>
  );
}

/**
 * Série de acessos, visitantes e buscas.
 *
 * O seletor de período só oferece o que o banco sustenta (`historico_dias`):
 * com 3 dias coletados, "90 dias" desenharia a mesma linha de "7 dias" e
 * daria a impressão de um histórico que não existe — o mesmo cuidado que o
 * seletor do Catálogo já tem.
 */
function SerieAcessos({
  geral,
  periodo,
  aoTrocarPeriodo,
  t,
}: {
  geral: VisaoGeralAdmin;
  periodo: number;
  aoTrocarPeriodo: (periodo: Periodo) => void;
  t: TFunction;
}) {
  // Os periodos que o historico sustenta. O menor sempre entra: com 3 dias
  // coletados, "7 dias" ainda e uma janela legitima (so nao cheia), mas
  // "90 dias" desenharia o mesmo grafico com outro rotulo.
  const disponiveis = PERIODOS.filter(
    (opcao) => geral.historico_dias >= opcao || opcao === PERIODOS[0],
  );
  // O periodo pedido pode nao existir: o padrao e 30 dias, e a tela abre
  // antes de saber quanto historico ha. Sem este ajuste, a pilula ativa
  // ficava DESABILITADA - selecionada e inclicavel ao mesmo tempo.
  const efetivo = disponiveis.includes(periodo as Periodo)
    ? periodo
    : disponiveis[disponiveis.length - 1];

  const serie = geral.serie_acessos.slice(-efetivo);
  const pontos: PontoArea[] = serie.map((ponto: PontoAcessoDia) => ({
    rotulo: ponto.dia.slice(5).replace("-", "/"),
    valor: ponto.acessos,
    detalhe: t("admin.serie.detalheTooltip", {
      acessos: fmtNumero(ponto.acessos),
      visitantes: fmtNumero(ponto.visitantes_unicos),
      buscas: fmtNumero(ponto.buscas),
    }),
  }));
  const total = serie.reduce((soma, ponto) => soma + ponto.acessos, 0);

  return (
    <Painel
      icone="show_chart"
      titulo={t("admin.serie.titulo")}
      descricao={t("admin.serie.descricao", { dias: geral.historico_dias })}
      meta={
        <div className="flex flex-wrap items-center gap-space-xxs">
          {PERIODOS.map((opcao) => {
            // Um período maior que o histórico não é escolha: mostraria o
            // mesmo desenho com outro rótulo.
            const temDado = disponiveis.includes(opcao);
            return (
              <Pilula
                key={opcao}
                ativa={efetivo === opcao}
                aoClicar={temDado ? () => aoTrocarPeriodo(opcao) : undefined}
                desabilitada={!temDado}
                titulo={
                  temDado
                    ? undefined
                    : t("admin.serie.semHistorico", { dias: geral.historico_dias })
                }
              >
                {t("admin.serie.dias", { n: opcao })}
              </Pilula>
            );
          })}
        </div>
      }
    >
      {pontos.length === 0 ? (
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          {t("admin.serie.vazio")}
        </p>
      ) : (
        <AreaNeon
          pontos={pontos}
          formatarValor={(valor) => fmtNumero(valor)}
          rodapeEsquerda={
            <>
              {t("admin.serie.noPeriodo")}{" "}
              <strong className="font-title-code text-title-code text-on-surface">
                {t("admin.serie.acessos", { n: fmtNumero(total) })}
              </strong>
            </>
          }
          rodapeDireita={t("admin.serie.telemetriaPropria")}
        />
      )}
    </Painel>
  );
}

/** Acessos, visitantes e buscas por recorte de tempo. */
function TabelaPorPeriodo({ geral, t }: { geral: VisaoGeralAdmin; t: TFunction }) {
  const linhas = [
    {
      rotulo: t("admin.tabela.hoje"),
      icone: "bolt",
      acessos: geral.acessos_hoje,
      visitantes: geral.visitantes_unicos_hoje,
      buscas: geral.buscas_hoje,
      delta: variacao(geral.acessos_hoje, geral.acessos_ontem),
    },
    {
      rotulo: t("admin.tabela.ontem"),
      icone: "history",
      acessos: geral.acessos_ontem,
      visitantes: geral.visitantes_unicos_ontem,
      buscas: geral.buscas_ontem,
      delta: null,
    },
    {
      rotulo: t("admin.tabela.esteMes"),
      icone: "calendar_view_month",
      acessos: geral.acessos_mes,
      visitantes: geral.visitantes_unicos_mes,
      buscas: geral.buscas_mes,
      delta: null,
    },
    {
      rotulo: t("admin.tabela.esteAno"),
      icone: "event_available",
      acessos: geral.acessos_ano,
      visitantes: geral.visitantes_unicos_ano,
      buscas: geral.buscas_ano,
      delta: null,
    },
  ];

  return (
    <Painel
      icone="calendar_month"
      titulo={t("admin.tabela.titulo")}
      descricao={t("admin.tabela.descricao")}
    >
      <div
        className="h-[2px] w-full rounded-full bg-gradient-to-r from-primary-container via-secondary to-transparent"
        aria-hidden
      />
      <div className="rolagem-discreta overflow-x-auto rounded-lg">
        <table className="w-full min-w-[420px] border-collapse text-left">
          <thead>
            <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
              <th className="px-space-md py-space-sm">{t("admin.tabela.periodo")}</th>
              <th className="px-space-md py-space-sm text-right">{t("admin.tabela.acessos")}</th>
              <th className="px-space-md py-space-sm text-right">{t("admin.tabela.visitantes")}</th>
              <th className="px-space-md py-space-sm text-right">{t("admin.tabela.buscas")}</th>
              <th className="px-space-md py-space-sm text-right">{t("admin.tabela.variacao")}</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((linha, indice) => (
              <tr
                key={linha.rotulo}
                className={`transition-colors hover:bg-surface-container ${
                  indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                }`}
              >
                <td className="px-space-md py-space-sm">
                  <span className="flex items-center gap-space-xs font-title-code text-title-code text-on-surface">
                    <Icone nome={linha.icone} className="text-[15px] text-primary" />
                    {linha.rotulo}
                  </span>
                </td>
                <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-primary">
                  {fmtNumero(linha.acessos)}
                </td>
                <td className="px-space-md py-space-sm text-right font-body-md text-body-sm tabular-nums text-on-surface-variant">
                  {fmtNumero(linha.visitantes)}
                </td>
                <td className="px-space-md py-space-sm text-right font-body-md text-body-sm tabular-nums text-on-surface-variant">
                  {fmtNumero(linha.buscas)}
                </td>
                <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums">
                  {linha.delta === null ? (
                    <span className="text-outline">—</span>
                  ) : (
                    <span className={linha.delta >= 0 ? "text-tertiary" : "text-error"}>
                      {linha.delta >= 0 ? "+" : ""}
                      {linha.delta.toFixed(1)}%
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="font-body-md text-[11px] leading-tight text-outline">
        {t("admin.tabela.notaVariacao")}
      </p>
    </Painel>
  );
}

/**
 * Ranking de busca. A ordem e a contagem vêm do backend — o número do rank é
 * dado real, só a entrada escalonada é estética.
 */
function TermosMaisBuscados({ termos, t }: { termos: TermoBuscado[]; t: TFunction }) {
  const entrou = useEntrarNaTela(termos.map((termo) => termo.termo).join(","));
  const maximo = termos[0]?.buscas || 1;

  return (
    <Painel
      icone="search"
      titulo={t("admin.termos.titulo")}
      descricao={t("admin.termos.descricao")}
    >
      {termos.length === 0 ? (
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          {t("admin.termos.vazio")}
        </p>
      ) : (
        <div className="flex flex-col gap-space-xs">
          {termos.map((termo, indice) => (
            <div
              key={termo.termo}
              className="flex items-center gap-space-sm rounded bg-surface-container-lowest px-space-sm py-space-xs"
              style={{
                opacity: entrou ? 1 : 0,
                transform: entrou ? "translateX(0)" : "translateX(-6px)",
                transition: `opacity 350ms ease-out ${indice * 60}ms, transform 350ms ease-out ${indice * 60}ms`,
              }}
            >
              <span className="w-6 shrink-0 font-label-caps text-label-caps tabular-nums text-outline">
                {String(indice + 1).padStart(2, "0")}
              </span>
              <span className="min-w-0 flex-1 truncate font-body-md text-body-sm font-bold text-on-surface">
                {termo.termo}
              </span>
              <span
                className="hidden h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-surface-container sm:block"
                aria-hidden
              >
                <span
                  className="block h-full rounded-full bg-gradient-to-r from-primary-container to-primary"
                  style={{
                    width: entrou ? `${Math.max(6, (termo.buscas / maximo) * 100).toFixed(1)}%` : "0%",
                    transition: "width 700ms cubic-bezier(0.16, 1, 0.3, 1)",
                  }}
                />
              </span>
              <span className="w-10 shrink-0 text-right font-title-code text-title-code tabular-nums text-primary">
                {fmtNumero(termo.buscas)}
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="font-body-md text-[11px] leading-tight text-outline">
        {t("admin.termos.nota")}
      </p>
    </Painel>
  );
}

/** Nome + data de criação de cada conta — nunca e-mail nem uid, de propósito (LGPD). */
function Contas({ dados, t }: { dados: ListaContasAdmin; t: TFunction }) {
  return (
    <Painel
      icone="group"
      titulo={t("admin.contas.titulo")}
      descricao={t("admin.contas.descricao")}
      meta={<Selo cor="neutro">{t("admin.contas.total", { n: fmtNumero(dados.total) })}</Selo>}
    >
      <div
        className="h-[2px] w-full rounded-full bg-gradient-to-r from-primary-container via-secondary to-transparent"
        aria-hidden
      />
      {dados.contas.length === 0 ? (
        <p className="font-body-sm text-body-sm text-outline">{t("admin.contas.vazio")}</p>
      ) : (
        <div className="rolagem-discreta max-h-[24rem] overflow-y-auto pr-space-xs">
          <div className="grid gap-space-xxs">
            {dados.contas.map((conta, indice) => (
              <div
                key={`${conta.criado_em}-${indice}`}
                className="flex items-center gap-space-sm rounded bg-surface-container px-space-sm py-space-xs transition-colors hover:bg-surface-container-high"
              >
                <Icone nome="account_circle" className="shrink-0 text-[16px] text-outline" />
                <span className="min-w-0 flex-1 truncate font-body-md text-body-sm font-bold text-on-surface">
                  {conta.nome_exibicao ?? t("admin.contas.semNome")}
                </span>
                <span className="shrink-0 font-title-code text-title-code tabular-nums text-on-surface-variant">
                  {fmtData(conta.criado_em)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Painel>
  );
}

/**
 * Tabelas do banco, com barra proporcional à maior.
 *
 * Sem coluna de crescimento: não existe histórico de contagem gravado, então
 * a variação por tabela não é calculável — e uma coluna de traços seria pior
 * que a ausência dela.
 */
function BancoDeDados({ dados, t }: { dados: SaudeBanco; t: TFunction }) {
  const entrou = useEntrarNaTela(dados.tabelas.map((tabela) => tabela.linhas).join(","));
  const maximo = dados.tabelas[0]?.linhas || 1;
  const totalLinhas = dados.tabelas.reduce((soma, tabela) => soma + tabela.linhas, 0);

  return (
    <Painel
      icone="database"
      titulo={t("admin.banco.titulo")}
      descricao={t("admin.banco.descricao")}
      meta={<Selo cor="neutro">{dados.tamanho_texto}</Selo>}
    >
      <div className="grid grid-cols-2 gap-space-sm">
        <div className="rounded-lg bg-surface-container-lowest px-space-base py-space-sm">
          <span className="block font-headline-sm text-headline-sm tabular-nums text-on-surface">
            {fmtNumero(dados.tabelas.length)}
          </span>
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("admin.banco.tabelas")}
          </span>
        </div>
        <div className="rounded-lg bg-surface-container-lowest px-space-base py-space-sm">
          <span className="block font-headline-sm text-headline-sm tabular-nums text-primary">
            {fmtNumero(totalLinhas)}
          </span>
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("admin.banco.registros")}
          </span>
        </div>
      </div>

      <div className="rolagem-discreta max-h-[20rem] overflow-y-auto pr-space-xs">
        <div className="grid gap-space-xxs">
          {dados.tabelas.map((tabela) => (
            <div
              key={tabela.tabela}
              className="flex items-center gap-space-sm rounded bg-surface-container px-space-sm py-space-xs transition-colors hover:bg-surface-container-high"
            >
              <span className="min-w-0 flex-1 truncate font-title-code text-title-code text-on-surface">
                {tabela.tabela}
              </span>
              <span className="w-20 shrink-0 text-right font-title-code text-title-code tabular-nums text-primary">
                {fmtNumero(tabela.linhas)}
              </span>
              <span
                className="hidden h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-surface-container-lowest sm:block"
                aria-hidden
              >
                <span
                  className="block h-full rounded-full bg-gradient-to-r from-primary-container to-primary"
                  style={{
                    width: entrou
                      ? `${Math.max(4, (tabela.linhas / maximo) * 100).toFixed(1)}%`
                      : "0%",
                    transition: "width 700ms cubic-bezier(0.16, 1, 0.3, 1)",
                  }}
                />
              </span>
            </div>
          ))}
        </div>
      </div>
    </Painel>
  );
}

/** Cor do `Selo` por status de uma fase do sync (`steam_sincronizacao`). */
const COR_STATUS_SYNC: Record<string, "positivo" | "neutro" | "negativo"> = {
  concluido: "positivo",
  em_andamento: "neutro",
  falhou: "negativo",
};

/**
 * Progresso do catálogo Steam completo (Fase 35) — checkpoint de verdade
 * (`steam_sincronizacao`), não a contagem crua de `BancoDeDados` acima.
 * `dim_jogo_steam` (o catálogo MONITORADO) não muda com este crawl — só
 * `apps_indexados` (`dim_app_steam_nome`, o índice completo) muda.
 *
 * Sem botão de "executar sincronização": não existe ação manual de sync
 * neste backend, e criar uma seria uma decisão de operação, não de layout.
 */
function CatalogoSteam({ dados, t }: { dados: SaudeCatalogoSteam; t: TFunction }) {
  return (
    <Painel
      icone="travel_explore"
      titulo={t("admin.catalogoSteam.titulo")}
      descricao={t("admin.catalogoSteam.descricao")}
      meta={
        <Selo cor="primario">
          {t("admin.catalogoSteam.appsIndexados", { contagem: fmtNumero(dados.apps_indexados) })}
        </Selo>
      }
    >
      {dados.fases.length === 0 ? (
        <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
          {t("admin.catalogoSteam.semDado")}
        </p>
      ) : (
        <div className="grid gap-space-sm">
          {dados.fases.map((fase: SincronizacaoSteamStatus) => (
            <div key={fase.fase} className="rounded-lg bg-surface-container px-space-base py-space-sm">
              <div className="flex flex-wrap items-center gap-space-sm">
                <span className="min-w-0 flex-1 font-title-code text-title-code text-on-surface">
                  {t(`admin.catalogoSteam.fases.${fase.fase}`, fase.fase)}
                </span>
                <Selo cor={COR_STATUS_SYNC[fase.status] ?? "neutro"}>
                  {t(`admin.catalogoSteam.status.${fase.status}`, fase.status)}
                </Selo>
                <span className="font-body-sm text-body-sm text-outline">
                  {fmtRelativo(fase.atualizado_em)}
                </span>
              </div>

              <div className="mt-space-xs grid grid-cols-2 gap-space-xs sm:grid-cols-4">
                {[
                  { rotulo: t("admin.catalogoSteam.processadosCurto"), valor: fase.registros_processados, cor: "text-primary" },
                  { rotulo: t("admin.catalogoSteam.criados"), valor: fase.registros_criados, cor: "text-tertiary" },
                  { rotulo: t("admin.catalogoSteam.atualizados"), valor: fase.registros_atualizados, cor: "text-on-surface" },
                  { rotulo: t("admin.catalogoSteam.falhas"), valor: fase.registros_falhos, cor: fase.registros_falhos > 0 ? "text-error" : "text-outline" },
                ].map((metrica) => (
                  <div key={metrica.rotulo}>
                    <span className={`block font-title-code text-title-code tabular-nums ${metrica.cor}`}>
                      {fmtNumero(metrica.valor)}
                    </span>
                    <span className="font-label-caps text-[10px] uppercase tracking-widest text-outline">
                      {metrica.rotulo}
                    </span>
                  </div>
                ))}
              </div>

              {fase.last_appid != null && (
                <p className="mt-space-xs font-body-md text-[11px] text-outline">
                  {t("admin.catalogoSteam.ultimoAppid", { appid: fmtNumero(fase.last_appid) })}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </Painel>
  );
}
