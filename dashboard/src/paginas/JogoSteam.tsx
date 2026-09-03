/**
 * Detalhe de um jogo da Steam: atributos + a serie temporal coletada.
 *
 * Porte da tela "Detalhe do Jogo" do Stitch: cabecalho com capa e chips,
 * caixa do Metacritic, fileira de KPIs, o grafico principal de jogadores
 * simultaneos, dois graficos menores (preco e volume de avaliacoes) e a tabela
 * de telemetria.
 */

import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useJogoSteam } from "../api/consultas";
import type { DetalheJogoSteam, PontoSerie } from "../api/tipos";
import { Botao, Consulta, Icone, Selo } from "../componentes/base";
import { CapaJogo } from "../componentes/CapaJogo";
import { AreaNeon } from "../componentes/graficos/AreaNeon";
import { KpiHud, Painel } from "../componentes/hud";
import {
  classificacaoSteam,
  fmtCurto,
  fmtData,
  fmtDataHora,
  fmtMoeda,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
  paraNumero,
} from "../utilitarios/formatos";

/** Janelas do seletor do grafico principal, em dias. `null` = tudo. */
const PERIODOS = [
  { valor: 7, rotulo: "7D" },
  { valor: 30, rotulo: "30D" },
  { valor: null, rotulo: "Tudo" },
] as const;

const CHIP_CLASSIFICACAO = {
  positiva: "bg-tertiary/10 text-tertiary",
  neutra: "bg-surface-container-highest text-on-surface-variant",
  negativa: "bg-error/10 text-error",
} as const;

export function JogoSteamPagina() {
  const { appId } = useParams();
  const [periodo, setPeriodo] = useState<number | null>(null);

  const detalhe = useJogoSteam(Number(appId));

  const serieRecortada = useMemo(() => {
    const serie = detalhe.data?.serie ?? [];
    if (periodo === null) return serie;
    const corte = Date.now() - periodo * 86400_000;
    return serie.filter((ponto) => new Date(ponto.janela_coleta).getTime() >= corte);
  }, [detalhe.data, periodo]);

  return (
    <Consulta estado={detalhe} altura={320}>
      {(dados: DetalheJogoSteam) => {
        const { jogo } = dados;
        const classificacao = classificacaoSteam(jogo.classificacao_steam);

        const pontos = serieRecortada.map((ponto: PontoSerie) => ({
          rotulo: fmtDataHora(ponto.janela_coleta),
          valor: ponto.jogadores_simultaneos ?? 0,
          detalhe: `${fmtNumero(ponto.jogadores_simultaneos)} jogadores`,
        }));

        return (
          <>
            {/* ==================== CABECALHO ==================== */}
            <section className="relative overflow-hidden rounded-xl bg-surface-container-low p-space-lg shadow-2xl">
              <div
                className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary-container/10 blur-3xl"
                aria-hidden
              />

              <Link
                to="/steam"
                className="relative z-10 inline-flex items-center gap-space-xxs font-title-code text-title-code text-outline transition-colors hover:text-primary"
              >
                <Icone nome="arrow_back" className="text-[16px]" />
                Voltar para o catálogo
              </Link>

              <div className="relative z-10 mt-space-sm flex flex-col justify-between gap-space-base lg:flex-row lg:items-start">
                <div className="flex min-w-0 items-start gap-space-base">
                  <CapaJogo
                    appId={jogo.app_id}
                    nome={jogo.nome}
                    className="h-20 w-20 rounded-lg"
                  />

                  <div className="min-w-0">
                    <h1 className="font-display-hero text-display-hero uppercase leading-none tracking-tight text-on-surface">
                      {jogo.nome}
                    </h1>

                    <p className="mt-space-xs font-title-code text-title-code uppercase text-outline">
                      DEV: <span className="text-on-surface-variant">{jogo.desenvolvedora ?? "—"}</span>{" "}
                      · PUB:{" "}
                      <span className="text-on-surface-variant">{jogo.publicadora ?? "—"}</span>
                      {jogo.data_lancamento && (
                        <>
                          {" "}· LANÇAMENTO:{" "}
                          <span className="text-on-surface-variant">
                            {fmtData(jogo.data_lancamento)}
                          </span>
                        </>
                      )}
                      {" "}· APPID:{" "}
                      <span className="text-on-surface-variant">{jogo.app_id}</span>
                    </p>

                    <div className="mt-space-sm flex flex-wrap gap-space-xs">
                      {jogo.gratuito && <Selo cor="positivo">Gratuito</Selo>}
                      {jogo.generos.map((genero) => (
                        <span
                          key={genero}
                          className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-secondary"
                        >
                          {genero}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {jogo.nota_metacritic !== null && (
                  <div
                    className="shrink-0 rounded-lg border border-tertiary/30 bg-surface-container px-space-lg py-space-sm text-center"
                    title="Nota da crítica no Metacritic"
                  >
                    <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                      Metacritic
                    </div>
                    <div className="font-headline-kpi text-headline-kpi leading-none text-tertiary">
                      {jogo.nota_metacritic}
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* ==================== KPIS ==================== */}
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta="Jogadores simultâneos"
                canto="AGORA"
                valor={fmtNumero(jogo.jogadores_simultaneos)}
                rotulo={`Coletado ${fmtRelativo(jogo.janela_coleta)}`}
                variacao={jogo.variacao_jogadores}
                notaVariacao="vs. coleta anterior"
                acento="primaria"
              >
                <div className="mt-space-md h-2 w-full overflow-hidden rounded-full bg-surface-container-lowest">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-primary-container to-secondary"
                    style={{
                      width: `${
                        jogo.pico_jogadores && jogo.jogadores_simultaneos
                          ? Math.min(
                              100,
                              (jogo.jogadores_simultaneos / jogo.pico_jogadores) * 100,
                            )
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta="Avaliações positivas"
                canto="STEAM REVIEWS"
                valor={fmtPercentual(jogo.nota_avaliacoes, 0)}
                rotulo={`${fmtCurto(jogo.numero_avaliacoes)} avaliações no total`}
                acento="terciaria"
              >
                <div className="mt-space-md">
                  {classificacao ? (
                    <span
                      className={`inline-flex rounded px-space-sm py-space-xxs font-badge-status text-badge-status uppercase ${
                        CHIP_CLASSIFICACAO[classificacao.polaridade]
                      }`}
                    >
                      {classificacao.texto}
                    </span>
                  ) : (
                    <span className="font-label-caps text-label-caps text-outline">
                      sem classificação
                    </span>
                  )}
                </div>
              </KpiHud>

              <KpiHud
                etiqueta="Pico histórico"
                canto="PEAK CCU"
                valor={fmtCurto(jogo.pico_jogadores)}
                rotulo="Maior valor já coletado"
                acento="secundaria"
                notaVariacao={`${fmtNumero(dados.serie.length)} snapshots na série`}
              />

              <KpiHud
                etiqueta="Preço atual"
                canto={jogo.moeda ?? "—"}
                valor={fmtMoeda(jogo.preco_no_momento, jogo.moeda)}
                rotulo={
                  jogo.desconto_percentual
                    ? `${jogo.desconto_percentual}% de desconto`
                    : "sem desconto"
                }
                acento="primaria"
              />
            </section>

            {/* ==================== GRAFICO PRINCIPAL ==================== */}
            <Painel
              icone="show_chart"
              titulo="Jogadores simultâneos ao longo do tempo"
              descricao="Um ponto por janela de coleta (padrão: 1 hora)."
              meta={
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
              }
            >
              {dados.serie.length < 2 && (
                <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                  {dados.serie.length === 0
                    ? "Nenhum snapshot coletado ainda para este jogo."
                    : "Só existe uma coleta até agora — a série ganha forma quando o coletor rodar de novo."}
                </p>
              )}

              <AreaNeon
                pontos={pontos}
                formatarValor={(valor) => fmtCurto(valor)}
                rodapeEsquerda={
                  <>
                    Pico da série:{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {fmtNumero(Math.max(...pontos.map((p) => p.valor), 0))}
                    </strong>
                  </>
                }
                rodapeDireita="Steam Web API"
              />
            </Painel>

            {/* ==================== DOIS GRAFICOS MENORES ==================== */}
            {dados.serie.length > 0 && (
              <section className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
                <Painel
                  icone="payments"
                  titulo="Histórico de preço"
                  descricao="O mesmo eixo de tempo da série de jogadores."
                >
                  <AreaNeon
                    pontos={dados.serie.map((ponto) => ({
                      rotulo: fmtDataHora(ponto.janela_coleta),
                      valor: paraNumero(ponto.preco_no_momento) ?? 0,
                      detalhe: fmtMoeda(ponto.preco_no_momento, jogo.moeda),
                    }))}
                    formatarValor={(valor) => fmtMoeda(valor, jogo.moeda)}
                  />
                </Painel>

                <Painel
                  icone="reviews"
                  titulo="Volume de avaliações"
                  descricao="Contagem acumulada de reviews a cada coleta."
                >
                  <AreaNeon
                    pontos={dados.serie.map((ponto) => ({
                      rotulo: fmtDataHora(ponto.janela_coleta),
                      valor: ponto.numero_avaliacoes ?? 0,
                      detalhe: `${fmtNumero(ponto.numero_avaliacoes)} avaliações`,
                    }))}
                    formatarValor={(valor) => fmtCurto(valor)}
                  />
                </Painel>
              </section>
            )}

            {/* ==================== TABELA ==================== */}
            <Painel
              icone="table_rows"
              titulo="Histórico de telemetria"
              descricao="Uma linha por (app_id, janela de coleta) — a chave de idempotência do fato."
              meta={
                <Botao icone="file_download" aoClicar={() => exportarCsv(dados)}>
                  Exportar CSV
                </Botao>
              }
            >
              {dados.serie.length === 0 ? (
                <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                  Nada coletado ainda.
                </p>
              ) : (
                <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                        <th className="px-space-md py-space-sm">Janela de coleta</th>
                        <th className="px-space-md py-space-sm text-right">
                          Jogadores (CCU)
                        </th>
                        <th className="px-space-md py-space-sm text-right">Nota</th>
                        <th className="px-space-md py-space-sm text-right">Avaliações</th>
                        <th className="px-space-md py-space-sm text-right">Preço</th>
                        <th className="px-space-md py-space-sm text-right">Desconto</th>
                      </tr>
                    </thead>

                    <tbody className="font-body-md text-body-sm">
                      {[...dados.serie].reverse().map((ponto, indice) => (
                        <tr
                          key={ponto.janela_coleta}
                          className={`transition-colors hover:bg-surface-container-high/60 ${
                            indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                          }`}
                        >
                          <td className="px-space-md py-space-sm font-title-code text-title-code text-on-surface-variant">
                            {fmtDataHora(ponto.janela_coleta)}
                          </td>
                          <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-tertiary">
                            {fmtNumero(ponto.jogadores_simultaneos)}
                          </td>
                          <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface">
                            {fmtPercentual(ponto.nota_avaliacoes, 0)}
                          </td>
                          <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                            {fmtNumero(ponto.numero_avaliacoes)}
                          </td>
                          <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-primary">
                            {fmtMoeda(ponto.preco_no_momento, jogo.moeda)}
                          </td>
                          <td className="px-space-md py-space-sm text-right">
                            {ponto.desconto_percentual ? (
                              <span className="rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status text-tertiary">
                                -{ponto.desconto_percentual}%
                              </span>
                            ) : (
                              <span className="text-outline">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Painel>
          </>
        );
      }}
    </Consulta>
  );
}

/** Exporta a serie inteira do jogo como CSV. */
function exportarCsv(dados: DetalheJogoSteam): void {
  const cabecalho = [
    "janela_coleta",
    "jogadores_simultaneos",
    "nota_avaliacoes",
    "numero_avaliacoes",
    "preco_no_momento",
    "desconto_percentual",
  ];

  const linhas = [
    cabecalho.join(";"),
    ...dados.serie.map((ponto) =>
      [
        ponto.janela_coleta,
        ponto.jogadores_simultaneos ?? "",
        ponto.nota_avaliacoes ?? "",
        ponto.numero_avaliacoes ?? "",
        ponto.preco_no_momento ?? "",
        ponto.desconto_percentual ?? "",
      ].join(";"),
    ),
  ];

  // BOM + ponto e virgula: e o que o Excel em pt-BR abre sem pedir importacao.
  const blob = new Blob(["﻿" + linhas.join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `telemetria-${dados.jogo.app_id}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
