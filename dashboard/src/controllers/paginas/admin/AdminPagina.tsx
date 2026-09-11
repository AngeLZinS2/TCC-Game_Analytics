/**
 * Painel admin: estatísticas do site + saúde da VPS.
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
import type { MetricaSistema } from "@models/api/tipos";
import { Icone, MensagemErro, Selo, TabelaRolavel } from "@views/componentes/base";
import { BarraFina, KpiHud, Painel } from "@views/componentes/hud";
import { AreaNeon, type PontoArea } from "@views/componentes/graficos/AreaNeon";
import { fmtNumero } from "@util/formatos";
import { AdminLogin } from "./AdminLogin";

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

  const geral = visaoGeral.data;
  const pontosAcesso: PontoArea[] =
    geral?.serie_acessos.map((p) => ({
      rotulo: p.dia.slice(5).replace("-", "/"),
      valor: p.acessos,
      detalhe: `${fmtNumero(p.acessos)} acessos · ${fmtNumero(p.visitantes_unicos)} visitantes`,
    })) ?? [];

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-space-sm">
        <h1 className="flex items-center gap-space-xs font-headline-sm text-headline-sm uppercase tracking-wide text-primary">
          <Icone nome="admin_panel_settings" className="text-[24px]" />
          Painel Admin
        </h1>
        <button
          type="button"
          onClick={sair}
          className="flex items-center gap-space-xxs rounded bg-surface-container px-space-sm py-space-xs font-title-code text-title-code text-on-surface-variant transition-colors hover:text-error"
        >
          <Icone nome="logout" className="text-[16px]" />
          Sair
        </button>
      </header>

      {/* ==================== KPIs DO DIA ==================== */}
      {visaoGeral.isError ? (
        <MensagemErro erro={visaoGeral.error} />
      ) : (
        <div className="grid grid-cols-2 gap-space-base lg:grid-cols-4">
          <KpiHud
            etiqueta="Agora"
            acento="terciaria"
            valor={geral ? fmtNumero(geral.online_agora) : "—"}
            rotulo="online no site"
          />
          <KpiHud
            etiqueta="Hoje"
            acento="primaria"
            valor={geral ? fmtNumero(geral.acessos_hoje) : "—"}
            rotulo="acessos"
          />
          <KpiHud
            etiqueta="Hoje"
            acento="secundaria"
            valor={geral ? fmtNumero(geral.visitantes_unicos_hoje) : "—"}
            rotulo="visitantes únicos"
          />
          <KpiHud
            etiqueta="Hoje"
            acento="primaria"
            valor={geral ? fmtNumero(geral.buscas_hoje) : "—"}
            rotulo="buscas"
          />
        </div>
      )}

      {/* ==================== HOJE / MÊS / ANO ==================== */}
      {geral && (
        <Painel icone="calendar_month" titulo="Acessos, visitantes e buscas por período">
          <TabelaRolavel minLargura="32rem">
            <table className="w-full text-left font-body-sm text-body-sm">
              <thead>
                <tr className="border-b border-outline-variant/30 font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  <th className="px-space-sm py-space-xs">Período</th>
                  <th className="px-space-sm py-space-xs text-right">Acessos</th>
                  <th className="px-space-sm py-space-xs text-right">Visitantes únicos</th>
                  <th className="px-space-sm py-space-xs text-right">Buscas</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { rotulo: "Hoje", acessos: geral.acessos_hoje, visitantes: geral.visitantes_unicos_hoje, buscas: geral.buscas_hoje },
                  { rotulo: "Este mês", acessos: geral.acessos_mes, visitantes: geral.visitantes_unicos_mes, buscas: geral.buscas_mes },
                  { rotulo: "Este ano", acessos: geral.acessos_ano, visitantes: geral.visitantes_unicos_ano, buscas: geral.buscas_ano },
                ].map((linha) => (
                  <tr key={linha.rotulo} className="border-b border-outline-variant/10 last:border-0">
                    <td className="px-space-sm py-space-xs text-on-surface">{linha.rotulo}</td>
                    <td className="px-space-sm py-space-xs text-right tabular-nums text-on-surface-variant">
                      {fmtNumero(linha.acessos)}
                    </td>
                    <td className="px-space-sm py-space-xs text-right tabular-nums text-on-surface-variant">
                      {fmtNumero(linha.visitantes)}
                    </td>
                    <td className="px-space-sm py-space-xs text-right tabular-nums text-on-surface-variant">
                      {fmtNumero(linha.buscas)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TabelaRolavel>
        </Painel>
      )}

      {/* ==================== SERIE DE 30 DIAS ==================== */}
      <Painel icone="show_chart" titulo="Acessos nos últimos 30 dias">
        <AreaNeon pontos={pontosAcesso} formatarValor={(v) => fmtNumero(v)} />
      </Painel>

      {/* ==================== TERMOS MAIS BUSCADOS ==================== */}
      {geral && (
        <Painel
          icone="search"
          titulo="Termos mais buscados"
          descricao="Steam e Xbox, últimos 30 dias."
        >
          {geral.termos_mais_buscados.length === 0 ? (
            <p className="font-body-sm text-body-sm text-outline">Nenhuma busca registrada ainda.</p>
          ) : (
            <div className="flex flex-wrap gap-space-xs">
              {geral.termos_mais_buscados.map((termo) => (
                <Selo key={termo} cor="primario">
                  {termo}
                </Selo>
              ))}
            </div>
          )}
        </Painel>
      )}

      {/* ==================== SAUDE DA VPS ==================== */}
      <Painel
        icone="dns"
        titulo="Saúde do servidor"
        meta={
          sistema.data && (
            <Selo cor={sistema.data.fonte === "netdata" ? "positivo" : "neutro"}>
              {sistema.data.fonte === "netdata" ? "Netdata" : "Local (psutil)"}
            </Selo>
          )
        }
        descricao="Atualiza a cada 10s."
      >
        {sistema.isError ? (
          <MensagemErro erro={sistema.error} />
        ) : sistema.data ? (
          <div className="grid grid-cols-1 gap-space-base sm:grid-cols-3">
            <MetricaBarra rotulo="CPU" icone="memory" metrica={sistema.data.cpu} />
            <MetricaBarra rotulo="Memória" icone="developer_board" metrica={sistema.data.memoria} />
            <MetricaBarra rotulo="Disco" icone="storage" metrica={sistema.data.disco} />
          </div>
        ) : (
          <p className="font-body-sm text-body-sm text-outline">Carregando…</p>
        )}

        {sistema.data && (sistema.data.carga_1min !== null) && (
          <p className="mt-space-sm font-body-sm text-body-sm text-outline">
            Carga média: {sistema.data.carga_1min?.toFixed(2)} (1min) ·{" "}
            {sistema.data.carga_5min?.toFixed(2)} (5min) · {sistema.data.carga_15min?.toFixed(2)} (15min)
          </p>
        )}
      </Painel>

      {/* ==================== BANCO DE DADOS ==================== */}
      <Painel
        icone="database"
        titulo="Banco de dados"
        meta={banco.data && <Selo cor="neutro">{banco.data.tamanho_texto}</Selo>}
      >
        {banco.isError ? (
          <MensagemErro erro={banco.error} />
        ) : banco.data ? (
          <TabelaRolavel minLargura="24rem">
            <table className="w-full text-left font-body-sm text-body-sm">
              <thead>
                <tr className="border-b border-outline-variant/30 font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  <th className="px-space-sm py-space-xs">Tabela</th>
                  <th className="px-space-sm py-space-xs text-right">Linhas</th>
                </tr>
              </thead>
              <tbody>
                {banco.data.tabelas.map((tabela) => (
                  <tr key={tabela.tabela} className="border-b border-outline-variant/10 last:border-0">
                    <td className="px-space-sm py-space-xs text-on-surface">{tabela.tabela}</td>
                    <td className="px-space-sm py-space-xs text-right tabular-nums text-on-surface-variant">
                      {fmtNumero(tabela.linhas)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TabelaRolavel>
        ) : (
          <p className="font-body-sm text-body-sm text-outline">Carregando…</p>
        )}
      </Painel>
    </>
  );
}

function MetricaBarra({
  rotulo,
  icone,
  metrica,
}: {
  rotulo: string;
  icone: string;
  metrica: MetricaSistema | null;
}) {
  const cor = !metrica
    ? undefined
    : metrica.percentual >= 90
      ? "#ff8a93"
      : metrica.percentual >= 70
        ? "#f3b13b"
        : "#40d19e";

  return (
    <div className="flex flex-col gap-space-xs rounded-lg bg-surface-container-lowest p-space-base">
      <div className="flex items-center justify-between font-label-caps text-label-caps uppercase tracking-widest text-outline">
        <span className="flex items-center gap-space-xxs">
          <Icone nome={icone} className="text-[15px] text-primary" />
          {rotulo}
        </span>
        <span className="font-title-code text-title-code text-on-surface">
          {metrica ? `${metrica.percentual.toFixed(0)}%` : "—"}
        </span>
      </div>
      <BarraFina largura={metrica?.percentual ?? 0} cor={cor} />
      <span className="font-body-sm text-body-sm text-on-surface-variant">
        {metrica?.detalhe ?? "sem dado"}
      </span>
    </div>
  );
}
