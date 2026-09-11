/**
 * Painel admin: estatísticas do site + saúde da VPS.
 *
 * Porte do mesmo vocabulário visual da Visão Geral (`KpiHud` com contagem
 * animada, `Segmentos`, `AreaNeon`, tabela com hairline em gradiente e linhas
 * alternadas, pulso "ao vivo") — o painel usa o design system do projeto em
 * vez de reinventar um estilo próprio, e ganha de graça as mesmas animações
 * de entrada.
 *
 * Sem sistema de contas (ver `AdminLogin.tsx`) — o gate é só uma senha
 * (`ADMIN_SENHA`) e um token HMAC sem estado no servidor. Não é um
 * substituto para um login de verdade; é a tela que o usuário pediu para vir
 * primeiro, com o sistema de login como um passo separado antes de qualquer
 * deploy na VPS.
 *
 * "Contas criadas" fica de fora de propósito: não existe sistema de contas
 * no site, então não haveria dado real para mostrar.
 */

import { useEffect, useState } from "react";

import {
  useBancoAdmin,
  useSistemaAdmin,
  useVisaoGeralAdmin,
} from "@models/api/consultas";
import { ErroApi } from "@models/api/cliente";
import { limparTokenAdmin, tokenAdmin } from "@models/admin/sessao";
import type { SaudeBanco, VisaoGeralAdmin } from "@models/api/tipos";
import { Botao, Consulta, Icone, Selo } from "@views/componentes/base";
import { KpiHud, Painel, Segmentos } from "@views/componentes/hud";
import { AreaNeon, type PontoArea } from "@views/componentes/graficos/AreaNeon";
import { useEntrarNaTela } from "@models/hooks/animacao";
import { fmtNumero } from "@util/formatos";
import { AdminLogin } from "./AdminLogin";
import { MedidorRadial } from "./MedidorRadial";

/** Quantos dos 6 segmentos acender: a fração do dia dentro do mês/ano, com piso de 1 se já houve algo hoje. */
function razaoSegmentos(hoje: number, periodo: number): number {
  if (hoje <= 0) return 0;
  return Math.min(6, Math.max(1, Math.round((hoje / Math.max(periodo, 1)) * 6)));
}

export function AdminPagina() {
  const [autenticado, setAutenticado] = useState(() => Boolean(tokenAdmin()));

  const visaoGeral = useVisaoGeralAdmin();
  const sistema = useSistemaAdmin();
  const banco = useBancoAdmin();

  // Token expirado/invalidado: qualquer 401 numa das três consultas manda de
  // volta pro login, em vez de deixar a tela presa num erro genérico.
  useEffect(() => {
    const expirou = [visaoGeral.error, sistema.error, banco.error].some(
      (erro) => erro instanceof ErroApi && erro.status === 401,
    );
    if (expirou) {
      limparTokenAdmin();
      setAutenticado(false);
    }
  }, [visaoGeral.error, sistema.error, banco.error]);

  if (!autenticado) {
    return <AdminLogin aoAutenticar={() => setAutenticado(true)} />;
  }

  function sair() {
    limparTokenAdmin();
    setAutenticado(false);
  }

  const online = (visaoGeral.data?.online_agora ?? 0) > 0;

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-space-sm">
          <h1 className="flex items-center gap-space-xs font-headline-lg text-headline-lg uppercase tracking-wide text-on-surface">
            <Icone nome="admin_panel_settings" className="text-[24px] text-primary" />
            Painel Admin
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
              {visaoGeral.data ? `${fmtNumero(visaoGeral.data.online_agora)} no site agora` : "—"}
            </span>
          </div>
        </div>

        <Botao icone="logout" aoClicar={sair}>
          Sair
        </Botao>
      </section>

      {/* ==================== KPIS DO DIA ==================== */}
      <Consulta estado={visaoGeral} altura={160}>
        {(geral: VisaoGeralAdmin) => (
          <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
            <KpiHud
              etiqueta="Tempo real"
              canto="AGORA"
              valor={fmtNumero(geral.online_agora)}
              valorNumerico={geral.online_agora}
              formatarValor={fmtNumero}
              rotulo="visitantes no site"
              acento="terciaria"
              notaVariacao="janela de 90s"
            >
              <Segmentos acesos={Math.min(6, geral.online_agora)} acento="terciaria" />
            </KpiHud>

            <KpiHud
              etiqueta="Hoje"
              canto="ACESSOS"
              valor={fmtNumero(geral.acessos_hoje)}
              valorNumerico={geral.acessos_hoje}
              formatarValor={fmtNumero}
              rotulo="page views"
              acento="primaria"
              notaVariacao={`${fmtNumero(geral.acessos_mes)} no mês`}
            >
              <Segmentos acesos={razaoSegmentos(geral.acessos_hoje, geral.acessos_mes)} />
            </KpiHud>

            <KpiHud
              etiqueta="Hoje"
              canto="VISITANTES"
              valor={fmtNumero(geral.visitantes_unicos_hoje)}
              valorNumerico={geral.visitantes_unicos_hoje}
              formatarValor={fmtNumero}
              rotulo="visitantes únicos"
              acento="secundaria"
              notaVariacao={`${fmtNumero(geral.visitantes_unicos_mes)} no mês`}
            >
              <Segmentos
                acesos={razaoSegmentos(geral.visitantes_unicos_hoje, geral.visitantes_unicos_mes)}
                acento="secundaria"
              />
            </KpiHud>

            <KpiHud
              etiqueta="Hoje"
              canto="BUSCAS"
              valor={fmtNumero(geral.buscas_hoje)}
              valorNumerico={geral.buscas_hoje}
              formatarValor={fmtNumero}
              rotulo="buscas realizadas"
              acento="primaria"
              notaVariacao={`${fmtNumero(geral.buscas_mes)} no mês`}
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
            detalhe: `${fmtNumero(p.acessos)} acessos · ${fmtNumero(p.visitantes_unicos)} visitantes`,
          }));
          const totalPeriodo = geral.serie_acessos.reduce((soma, p) => soma + p.acessos, 0);

          return (
            <Painel
              icone="show_chart"
              titulo="Acessos nos últimos 30 dias"
              descricao="Uma linha por visitante anônimo (id gerado no navegador), não por conta — o site não tem login."
            >
              <AreaNeon
                pontos={pontos}
                formatarValor={(v) => fmtNumero(v)}
                rodapeEsquerda={
                  <>
                    No período:{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {fmtNumero(totalPeriodo)} acessos
                    </strong>
                  </>
                }
                rodapeDireita="Telemetria própria"
              />
            </Painel>
          );
        }}
      </Consulta>

      <div className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        {/* ==================== HOJE / MES / ANO ==================== */}
        <Consulta estado={visaoGeral} altura={220}>
          {(geral: VisaoGeralAdmin) => (
            <Painel icone="calendar_month" titulo="Acessos, visitantes e buscas por período">
              <div
                className="h-[2px] w-full rounded-full bg-gradient-to-r from-primary-container via-secondary to-transparent"
                aria-hidden
              />
              <div className="rolagem-discreta overflow-x-auto rounded-lg">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                      <th className="px-space-md py-space-sm">Período</th>
                      <th className="px-space-md py-space-sm text-right">Acessos</th>
                      <th className="px-space-md py-space-sm text-right">Visitantes</th>
                      <th className="px-space-md py-space-sm text-right">Buscas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { rotulo: "Hoje", icone: "bolt", acessos: geral.acessos_hoje, visitantes: geral.visitantes_unicos_hoje, buscas: geral.buscas_hoje },
                      { rotulo: "Este mês", icone: "calendar_view_month", acessos: geral.acessos_mes, visitantes: geral.visitantes_unicos_mes, buscas: geral.buscas_mes },
                      { rotulo: "Este ano", icone: "event_available", acessos: geral.acessos_ano, visitantes: geral.visitantes_unicos_ano, buscas: geral.buscas_ano },
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
        <Consulta estado={visaoGeral} altura={220} vazio="Nenhuma busca registrada ainda.">
          {(geral: VisaoGeralAdmin) => <TermosMaisBuscados termos={geral.termos_mais_buscados} />}
        </Consulta>
      </div>

      {/* ==================== SAUDE DA VPS ==================== */}
      <Painel
        icone="dns"
        titulo="Saúde do servidor"
        descricao="Atualiza sozinho a cada 10s."
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
              {sistema.data.fonte === "netdata" ? "Netdata" : "Local (psutil)"}
            </span>
          )
        }
      >
        {sistema.isError ? (
          <Selo cor="negativo">Não foi possível ler a saúde do servidor.</Selo>
        ) : sistema.data ? (
          <>
            <div className="grid grid-cols-1 gap-space-base sm:grid-cols-3">
              <MedidorRadial rotulo="CPU" icone="memory" percentual={sistema.data.cpu?.percentual ?? null} detalhe={sistema.data.cpu?.detalhe ?? "sem dado"} />
              <MedidorRadial rotulo="Memória" icone="developer_board" percentual={sistema.data.memoria?.percentual ?? null} detalhe={sistema.data.memoria?.detalhe ?? "sem dado"} />
              <MedidorRadial rotulo="Disco" icone="storage" percentual={sistema.data.disco?.percentual ?? null} detalhe={sistema.data.disco?.detalhe ?? "sem dado"} />
            </div>

            {sistema.data.carga_1min !== null && (
              <div className="flex flex-wrap items-center justify-center gap-space-xs pt-space-xs">
                {[
                  { rotulo: "1 min", valor: sistema.data.carga_1min },
                  { rotulo: "5 min", valor: sistema.data.carga_5min },
                  { rotulo: "15 min", valor: sistema.data.carga_15min },
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

      {/* ==================== BANCO DE DADOS ==================== */}
      <Consulta estado={banco} altura={260}>
        {(dados: SaudeBanco) => <BancoDeDados dados={dados} />}
      </Consulta>
    </>
  );
}

/**
 * Chips de rank: a ordem já vem do backend (mais buscado primeiro), então o
 * número do rank é dado real, não decoração — só a entrada escalonada
 * (opacidade + leve deslize) é estética.
 */
function TermosMaisBuscados({ termos }: { termos: string[] }) {
  const entrou = useEntrarNaTela(termos.join(","));

  return (
    <Painel
      icone="search"
      titulo="Termos mais buscados"
      descricao="Steam e Xbox, últimos 30 dias."
    >
      {termos.length === 0 ? (
        <p className="font-body-sm text-body-sm text-outline">Nenhuma busca registrada ainda.</p>
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

/** Tabela de tamanho das tabelas do banco, com barra proporcional à maior. */
function BancoDeDados({ dados }: { dados: SaudeBanco }) {
  const entrou = useEntrarNaTela(dados.tabelas.map((t) => t.linhas).join(","));
  const maximo = dados.tabelas[0]?.linhas || 1;

  return (
    <Painel
      icone="database"
      titulo="Banco de dados"
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
