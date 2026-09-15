/**
 * Painel admin: estatísticas do site + saúde da VPS.
 *
 * Porte do mesmo vocabulário visual da Visão Geral (`KpiHud` com contagem
 * animada, `Segmentos`, `AreaNeon`, tabela com hairline em gradiente e linhas
 * alternadas, pulso "ao vivo") — o painel usa o design system do projeto em
 * vez de reinventar um estilo próprio, e ganha de graça as mesmas animações
 * de entrada.
 *
 * Login é a mesma conta do resto do site (Firebase Auth) — `RotaProtegida`
 * (em `App.tsx`) já cuida de pedir login. Acesso ao painel em si é uma
 * autorização do backend (uid na lista `ADMIN_FIREBASE_UIDS`): uma conta
 * logada mas fora da lista recebe 403 em toda consulta daqui, tratado
 * abaixo como "sem acesso", não como "precisa logar".
 *
 * "Contas" mostra só nome e data de criação (`/api/admin/contas`) — nunca
 * e-mail nem o uid do Firebase, pra não virar um relatório de dado pessoal
 * (LGPD). Quem quiser mais detalhe de uma conta específica não tem como,
 * de propósito.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import {
  useBancoAdmin,
  useContasAdmin,
  useSistemaAdmin,
  useVisaoGeralAdmin,
} from "@models/api/consultas";
import { ErroApi } from "@models/api/cliente";
import { sairDaConta } from "@models/conta/acoes";
import type { ListaContasAdmin, SaudeBanco, VisaoGeralAdmin } from "@models/api/tipos";
import { Botao, Consulta, Icone, Selo } from "@views/componentes/base";
import { KpiHud, Painel, Segmentos } from "@views/componentes/hud";
import { AreaNeon, type PontoArea } from "@views/componentes/graficos/AreaNeon";
import { useEntrarNaTela } from "@models/hooks/animacao";
import { fmtData, fmtNumero } from "@util/formatos";
import { MedidorRadial } from "./MedidorRadial";

/** Quantos dos 6 segmentos acender: a fração do dia dentro do mês/ano, com piso de 1 se já houve algo hoje. */
function razaoSegmentos(hoje: number, periodo: number): number {
  if (hoje <= 0) return 0;
  return Math.min(6, Math.max(1, Math.round((hoje / Math.max(periodo, 1)) * 6)));
}

export function AdminPagina() {
  const { t } = useTranslation();
  const [saindo, setSaindo] = useState(false);

  const visaoGeral = useVisaoGeralAdmin();
  const sistema = useSistemaAdmin();
  const banco = useBancoAdmin();
  const contas = useContasAdmin();

  const semAcesso = [visaoGeral.error, sistema.error, banco.error, contas.error].some(
    (erro) => erro instanceof ErroApi && erro.status === 403,
  );

  async function sair() {
    setSaindo(true);
    try {
      await sairDaConta();
    } finally {
      setSaindo(false);
    }
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

  const online = (visaoGeral.data?.online_agora ?? 0) > 0;

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-space-sm">
          <h1 className="flex items-center gap-space-xs font-headline-lg text-headline-lg uppercase tracking-wide text-on-surface">
            <Icone nome="admin_panel_settings" className="text-[24px] text-primary" />
            {t("admin.titulo")}
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
                    : "bg-outline"
                }`}
              />
            </span>
            <span
              className={`font-badge-status text-badge-status uppercase tracking-widest ${
                online ? "text-tertiary" : "text-outline"
              }`}
            >
              {visaoGeral.data ? t("admin.noSiteAgora", { n: fmtNumero(visaoGeral.data.online_agora) }) : "—"}
            </span>
          </div>
        </div>

        <Botao icone="logout" aoClicar={sair} desabilitado={saindo}>
          {t("admin.sair")}
        </Botao>
      </section>

      {/* ==================== SAUDE DA VPS ==================== */}
      <Painel
        icone="dns"
        titulo={t("admin.saude.titulo")}
        descricao={t("admin.saude.descricao")}
        meta={
          sistema.data && (
            <span
              className={`inline-flex items-center gap-space-xs rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${
                sistema.data.fonte === "netdata"
                  ? "bg-tertiary-container/10 text-tertiary"
                  : "bg-surface-container-highest text-outline"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  sistema.isFetching
                    ? "animate-pulse bg-tertiary-container shadow-[0_0_4px_#40d19e]"
                    : sistema.data.fonte === "netdata"
                      ? "bg-tertiary-container"
                      : "bg-outline"
                }`}
                aria-hidden
              />
              {sistema.data.fonte === "netdata" ? t("admin.saude.netdata") : t("admin.saude.local")}
            </span>
          )
        }
      >
        {sistema.isError ? (
          <Selo cor="negativo">{t("admin.saude.erro")}</Selo>
        ) : sistema.data ? (
          <>
            <div className="grid grid-cols-1 gap-space-base sm:grid-cols-3">
              <MedidorRadial rotulo={t("admin.saude.cpu")} icone="memory" percentual={sistema.data.cpu?.percentual ?? null} detalhe={sistema.data.cpu?.detalhe ?? t("admin.saude.semDado")} />
              <MedidorRadial rotulo={t("admin.saude.memoria")} icone="developer_board" percentual={sistema.data.memoria?.percentual ?? null} detalhe={sistema.data.memoria?.detalhe ?? t("admin.saude.semDado")} />
              <MedidorRadial rotulo={t("admin.saude.disco")} icone="storage" percentual={sistema.data.disco?.percentual ?? null} detalhe={sistema.data.disco?.detalhe ?? t("admin.saude.semDado")} />
            </div>

            {sistema.data.carga_1min !== null && (
              <div className="flex flex-wrap items-center justify-center gap-space-xs pt-space-xs">
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
              </div>
            )}
          </>
        ) : (
          <div className="grid grid-cols-1 gap-space-base sm:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-48 animate-pulse rounded-lg bg-surface-container-high/60" />
            ))}
          </div>
        )}
      </Painel>

      {/* ==================== KPIS DO DIA ==================== */}
      <Consulta estado={visaoGeral} altura={160}>
        {(geral: VisaoGeralAdmin) => (
          <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
            <KpiHud
              etiqueta={t("admin.kpis.tempoReal")}
              canto={t("admin.kpis.agora")}
              valor={fmtNumero(geral.online_agora)}
              valorNumerico={geral.online_agora}
              formatarValor={fmtNumero}
              rotulo={t("admin.kpis.visitantesNoSite")}
              acento="terciaria"
              notaVariacao={t("admin.kpis.janela90s")}
            >
              <Segmentos acesos={Math.min(6, geral.online_agora)} acento="terciaria" />
            </KpiHud>

            <KpiHud
              etiqueta={t("admin.kpis.hoje")}
              canto={t("admin.kpis.acessosCanto")}
              valor={fmtNumero(geral.acessos_hoje)}
              valorNumerico={geral.acessos_hoje}
              formatarValor={fmtNumero}
              rotulo={t("admin.kpis.pageViews")}
              acento="primaria"
              notaVariacao={t("admin.kpis.noMes", { n: fmtNumero(geral.acessos_mes) })}
            >
              <Segmentos acesos={razaoSegmentos(geral.acessos_hoje, geral.acessos_mes)} />
            </KpiHud>

            <KpiHud
              etiqueta={t("admin.kpis.hoje")}
              canto={t("admin.kpis.visitantesCanto")}
              valor={fmtNumero(geral.visitantes_unicos_hoje)}
              valorNumerico={geral.visitantes_unicos_hoje}
              formatarValor={fmtNumero}
              rotulo={t("admin.kpis.visitantesUnicos")}
              acento="secundaria"
              notaVariacao={t("admin.kpis.noMes", { n: fmtNumero(geral.visitantes_unicos_mes) })}
            >
              <Segmentos
                acesos={razaoSegmentos(geral.visitantes_unicos_hoje, geral.visitantes_unicos_mes)}
                acento="secundaria"
              />
            </KpiHud>

            <KpiHud
              etiqueta={t("admin.kpis.hoje")}
              canto={t("admin.kpis.buscasCanto")}
              valor={fmtNumero(geral.buscas_hoje)}
              valorNumerico={geral.buscas_hoje}
              formatarValor={fmtNumero}
              rotulo={t("admin.kpis.buscasRealizadas")}
              acento="primaria"
              notaVariacao={t("admin.kpis.noMes", { n: fmtNumero(geral.buscas_mes) })}
            >
              <Segmentos acesos={razaoSegmentos(geral.buscas_hoje, geral.buscas_mes)} />
            </KpiHud>
          </section>
        )}
      </Consulta>

      {/* ==================== SERIE DE 30 DIAS ==================== */}
      <Consulta estado={visaoGeral} altura={220}>
        {(geral: VisaoGeralAdmin) => {
          const pontos: PontoArea[] = geral.serie_acessos.map((p) => ({
            rotulo: p.dia.slice(5).replace("-", "/"),
            valor: p.acessos,
            detalhe: t("admin.serie.detalheTooltip", {
              acessos: fmtNumero(p.acessos),
              visitantes: fmtNumero(p.visitantes_unicos),
            }),
          }));
          const totalPeriodo = geral.serie_acessos.reduce((soma, p) => soma + p.acessos, 0);

          return (
            <Painel
              icone="show_chart"
              titulo={t("admin.serie.titulo")}
              descricao={t("admin.serie.descricao")}
            >
              <AreaNeon
                pontos={pontos}
                formatarValor={(v) => fmtNumero(v)}
                rodapeEsquerda={
                  <>
                    {t("admin.serie.noPeriodo")}{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {t("admin.serie.acessos", { n: fmtNumero(totalPeriodo) })}
                    </strong>
                  </>
                }
                rodapeDireita={t("admin.serie.telemetriaPropria")}
              />
            </Painel>
          );
        }}
      </Consulta>

      <div className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        {/* ==================== HOJE / MES / ANO ==================== */}
        <Consulta estado={visaoGeral} altura={220}>
          {(geral: VisaoGeralAdmin) => (
            <Painel icone="calendar_month" titulo={t("admin.tabela.titulo")}>
              <div
                className="h-[2px] w-full rounded-full bg-gradient-to-r from-primary-container via-secondary to-transparent"
                aria-hidden
              />
              <div className="rolagem-discreta overflow-x-auto rounded-lg">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                      <th className="px-space-md py-space-sm">{t("admin.tabela.periodo")}</th>
                      <th className="px-space-md py-space-sm text-right">{t("admin.tabela.acessos")}</th>
                      <th className="px-space-md py-space-sm text-right">{t("admin.tabela.visitantes")}</th>
                      <th className="px-space-md py-space-sm text-right">{t("admin.tabela.buscas")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { rotulo: t("admin.tabela.hoje"), icone: "bolt", acessos: geral.acessos_hoje, visitantes: geral.visitantes_unicos_hoje, buscas: geral.buscas_hoje },
                      { rotulo: t("admin.tabela.esteMes"), icone: "calendar_view_month", acessos: geral.acessos_mes, visitantes: geral.visitantes_unicos_mes, buscas: geral.buscas_mes },
                      { rotulo: t("admin.tabela.esteAno"), icone: "event_available", acessos: geral.acessos_ano, visitantes: geral.visitantes_unicos_ano, buscas: geral.buscas_ano },
                    ].map((linha, indice) => (
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
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Painel>
          )}
        </Consulta>

        {/* ==================== TERMOS MAIS BUSCADOS ==================== */}
        <Consulta estado={visaoGeral} altura={220} vazio={t("admin.termos.vazio")}>
          {(geral: VisaoGeralAdmin) => <TermosMaisBuscados termos={geral.termos_mais_buscados} t={t} />}
        </Consulta>
      </div>

      {/* ==================== CONTAS ==================== */}
      <Consulta estado={contas} altura={260}>
        {(dados: ListaContasAdmin) => <Contas dados={dados} t={t} />}
      </Consulta>

      {/* ==================== BANCO DE DADOS ==================== */}
      <Consulta estado={banco} altura={260}>
        {(dados: SaudeBanco) => <BancoDeDados dados={dados} t={t} />}
      </Consulta>
    </>
  );
}

/**
 * Chips de rank: a ordem já vem do backend (mais buscado primeiro), então o
 * número do rank é dado real, não decoração — só a entrada escalonada
 * (opacidade + leve deslize) é estética.
 */
function TermosMaisBuscados({ termos, t }: { termos: string[]; t: TFunction }) {
  const entrou = useEntrarNaTela(termos.join(","));

  return (
    <Painel
      icone="search"
      titulo={t("admin.termos.titulo")}
      descricao={t("admin.termos.descricao")}
    >
      {termos.length === 0 ? (
        <p className="font-body-sm text-body-sm text-outline">{t("admin.termos.vazio")}</p>
      ) : (
        <div className="flex flex-col gap-space-xs">
          {termos.map((termo, indice) => (
            <div
              key={termo}
              className="flex items-center gap-space-sm rounded bg-surface-container-lowest px-space-sm py-space-xs"
              style={{
                opacity: entrou ? 1 : 0,
                transform: entrou ? "translateX(0)" : "translateX(-6px)",
                transition: `opacity 350ms ease-out ${indice * 60}ms, transform 350ms ease-out ${indice * 60}ms`,
              }}
            >
              <span className="w-6 shrink-0 font-label-caps text-label-caps tabular-nums text-outline">
                #{String(indice + 1).padStart(2, "0")}
              </span>
              <Icone nome="search" className="shrink-0 text-[14px] text-primary" />
              <span className="min-w-0 flex-1 truncate font-body-md text-body-sm font-bold text-on-surface">
                {termo}
              </span>
            </div>
          ))}
        </div>
      )}
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

/** Tabela de tamanho das tabelas do banco, com barra proporcional à maior. */
function BancoDeDados({ dados, t }: { dados: SaudeBanco; t: TFunction }) {
  const entrou = useEntrarNaTela(dados.tabelas.map((tab) => tab.linhas).join(","));
  const maximo = dados.tabelas[0]?.linhas || 1;

  return (
    <Painel
      icone="database"
      titulo={t("admin.banco.titulo")}
      meta={<Selo cor="neutro">{dados.tamanho_texto}</Selo>}
    >
      <div
        className="h-[2px] w-full rounded-full bg-gradient-to-r from-primary-container via-secondary to-transparent"
        aria-hidden
      />
      <div className="rolagem-discreta max-h-[24rem] overflow-y-auto pr-space-xs">
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
                    width: entrou ? `${Math.max(4, (tabela.linhas / maximo) * 100).toFixed(1)}%` : "0%",
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
