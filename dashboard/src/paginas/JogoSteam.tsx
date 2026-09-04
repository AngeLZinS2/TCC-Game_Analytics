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
import type {
  DetalheJogoSteam,
  FichaJogoSteam,
  NoticiaSteam,
  PontoSerie,
} from "../api/tipos";
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

            {/* ==================== FICHA ==================== */}
            <FichaDoJogo ficha={dados.ficha} nome={jogo.nome} />

            {/* ==================== ULTIMAS ATUALIZACOES ==================== */}
            <UltimasAtualizacoes noticias={dados.noticias} />

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

// ---------------------------------------------------------------------------
// Ficha do jogo (Fase 16) — metadados que quase não mudam
// ---------------------------------------------------------------------------

/** Nome amigável dos órgãos de classificação. */
const ORGAOS: Record<string, string> = {
  esrb: "ESRB",
  pegi: "PEGI",
  usk: "USK",
  dejus: "DEJUS (BR)",
  cero: "CERO (JP)",
  kgrb: "GRAC (KR)",
  oflc: "OFLC",
  nzoflc: "OFLC (NZ)",
  csrr: "CSRR",
  mda: "IMDA (SG)",
};

function tempoDeJogo(minutos: number | null): string | null {
  if (!minutos) return null;
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h > 0 ? `${h}h${m ? ` ${m}min` : ""}` : `${m}min`;
}

function LinhaFicha({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-outline-variant/20 py-space-sm first:border-t-0">
      <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
        {rotulo}
      </div>
      <div className="mt-space-xxs font-body-md text-body-sm text-on-surface-variant">
        {children}
      </div>
    </div>
  );
}

function Chips({ itens }: { itens: string[] }) {
  return (
    <div className="flex flex-wrap gap-space-xxs">
      {itens.map((item) => (
        <span
          key={item}
          className="rounded bg-surface-container-highest px-space-xs py-space-xxs font-title-code text-title-code text-on-surface-variant"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function FichaDoJogo({ ficha, nome }: { ficha: FichaJogoSteam; nome: string }) {
  const nada =
    ficha.recursos.length === 0 &&
    ficha.idiomas.length === 0 &&
    !ficha.donos_estimados &&
    ficha.tags_comunidade.length === 0 &&
    !ficha.conquistas_total;

  if (nada) {
    return (
      <Painel icone="badge" titulo="Ficha do jogo">
        <p className="font-body-md text-body-sm text-outline">
          A ficha deste jogo ainda não foi coletada. Ela vem do <code>appdetails</code> e do
          SteamSpy — o coletor da Steam a preenche na próxima passada.
        </p>
      </Painel>
    );
  }

  const orgaos = Object.entries(ficha.classificacoes);

  return (
    <Painel
      icone="badge"
      titulo="Ficha do jogo"
      descricao="Metadados da loja Steam e estimativas do SteamSpy."
    >
      <div className="grid grid-cols-1 gap-x-space-lg md:grid-cols-2">
        <div>
          {ficha.recursos.length > 0 && (
            <LinhaFicha rotulo="Recursos">
              <Chips itens={ficha.recursos} />
            </LinhaFicha>
          )}
          {ficha.plataformas.length > 0 && (
            <LinhaFicha rotulo="Plataformas">
              {ficha.plataformas
                .map((p) => ({ windows: "Windows", mac: "macOS", linux: "Linux" })[p] ?? p)
                .join(" · ")}
              {ficha.suporte_controle && (
                <span className="ml-space-sm text-outline">
                  · controle {ficha.suporte_controle === "full" ? "total" : "parcial"}
                </span>
              )}
            </LinhaFicha>
          )}
          {ficha.idiomas.length > 0 && (
            <LinhaFicha rotulo={`Idiomas (${ficha.idiomas.length})`}>
              {ficha.idiomas.slice(0, 12).map((idioma) => (
                <span key={idioma} className="mr-space-sm inline-block">
                  {idioma}
                  {ficha.idiomas_com_audio.includes(idioma) && (
                    <Icone
                      nome="volume_up"
                      className="ml-[2px] align-middle text-[13px] text-primary"
                    />
                  )}
                </span>
              ))}
              {ficha.idiomas.length > 12 && ` +${ficha.idiomas.length - 12}`}
              <div className="mt-space-xxs text-outline">
                <Icone nome="volume_up" className="align-middle text-[12px]" /> ={" "}
                {ficha.idiomas_com_audio.length} com dublagem
              </div>
            </LinhaFicha>
          )}
        </div>

        <div>
          {(ficha.faixa_etaria !== null || orgaos.length > 0) && (
            <LinhaFicha rotulo="Classificação etária">
              {ficha.faixa_etaria ? (
                <strong className="text-on-surface">{ficha.faixa_etaria}+</strong>
              ) : null}
              {orgaos.length > 0 && (
                <span className="ml-space-sm">
                  {orgaos
                    .map(([org, nota]) => `${ORGAOS[org] ?? org.toUpperCase()} ${nota.toUpperCase()}`)
                    .join(" · ")}
                </span>
              )}
              {ficha.descritores_conteudo.length > 0 && (
                <div className="mt-space-xxs text-error/80">
                  {ficha.descritores_conteudo.join(", ")}
                </div>
              )}
            </LinhaFicha>
          )}
          {ficha.conquistas_total ? (
            <LinhaFicha rotulo="Conquistas">
              <strong className="text-on-surface">{fmtNumero(ficha.conquistas_total)}</strong>{" "}
              conquistas
              {ficha.conquistas_destaque.length > 0 && (
                <span className="ml-space-sm inline-flex gap-space-xxs align-middle">
                  {ficha.conquistas_destaque.slice(0, 6).map((c) => (
                    <img
                      key={c.nome}
                      src={c.icone}
                      alt={c.nome}
                      title={c.nome}
                      className="h-5 w-5 rounded"
                      onError={(e) => (e.currentTarget.style.display = "none")}
                    />
                  ))}
                </span>
              )}
            </LinhaFicha>
          ) : null}
          {(ficha.donos_estimados || ficha.tempo_jogo_medio_min) && (
            <LinhaFicha rotulo="Alcance (SteamSpy)">
              {ficha.donos_estimados && (
                <div>
                  Donos estimados:{" "}
                  <strong className="text-on-surface">{ficha.donos_estimados}</strong>{" "}
                  <span className="text-outline">(faixa, não número exato)</span>
                </div>
              )}
              {tempoDeJogo(ficha.tempo_jogo_medio_min) && (
                <div>
                  Tempo de jogo médio:{" "}
                  <strong className="text-on-surface">
                    {tempoDeJogo(ficha.tempo_jogo_medio_min)}
                  </strong>
                </div>
              )}
            </LinhaFicha>
          )}
          {(ficha.dlc_ids.length > 0 || ficha.analises_totais !== null || ficha.site_oficial) && (
            <LinhaFicha rotulo="Mais">
              {ficha.analises_totais !== null && (
                <div>{fmtNumero(ficha.analises_totais)} recomendações na loja</div>
              )}
              {ficha.dlc_ids.length > 0 && <div>{ficha.dlc_ids.length} DLC(s)</div>}
              {ficha.site_oficial && (
                <a
                  href={ficha.site_oficial}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline"
                >
                  Site oficial ↗
                </a>
              )}
            </LinhaFicha>
          )}
        </div>
      </div>

      {ficha.tags_comunidade.length > 0 && (
        <div className="mt-space-md border-t border-outline-variant/20 pt-space-sm">
          <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            Tags da comunidade
          </div>
          <div className="mt-space-xs flex flex-wrap gap-space-xxs">
            {ficha.tags_comunidade.slice(0, 15).map(([tag, votos]) => (
              <span
                key={tag}
                className="rounded-full bg-surface-container-highest px-space-sm py-space-xxs font-title-code text-title-code text-on-surface-variant"
                title={`${fmtNumero(votos)} votos`}
              >
                {tag}{" "}
                <span className="text-outline">{fmtCurto(votos)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {ficha.requisitos_minimos && (
        <details className="mt-space-md border-t border-outline-variant/20 pt-space-sm">
          <summary className="cursor-pointer font-label-caps text-label-caps uppercase tracking-widest text-outline">
            Requisitos mínimos
          </summary>
          <pre className="mt-space-xs whitespace-pre-wrap font-body-md text-body-sm text-on-surface-variant">
            {ficha.requisitos_minimos}
          </pre>
        </details>
      )}

      <p className="mt-space-md font-body-sm text-body-sm text-outline">
        Fonte: Steam Store API + SteamSpy · ficha de <strong>{nome}</strong>
        {ficha.coletado_ficha_em && ` · atualizada ${fmtRelativo(ficha.coletado_ficha_em)}`}
      </p>
    </Painel>
  );
}

// ---------------------------------------------------------------------------
// Últimas atualizações (ISteamNews)
// ---------------------------------------------------------------------------

function UltimasAtualizacoes({ noticias }: { noticias: NoticiaSteam[] }) {
  if (noticias.length === 0) {
    return (
      <Painel icone="campaign" titulo="Últimas atualizações">
        <p className="font-body-md text-body-sm text-outline">
          Nenhuma notícia coletada ainda. O feed oficial do jogo (patch notes e anúncios do
          estúdio) entra na próxima coleta da Steam.
        </p>
      </Painel>
    );
  }

  return (
    <Painel
      icone="campaign"
      titulo="Últimas atualizações"
      descricao="Patch notes e anúncios do feed oficial da Steam (ISteamNews)."
    >
      <ul className="space-y-space-sm">
        {noticias.map((n) => (
          <li
            key={n.gid}
            className="border-t border-outline-variant/20 pt-space-sm first:border-t-0 first:pt-0"
          >
            <div className="flex flex-wrap items-baseline gap-space-xs">
              {n.feed && <Selo cor="neutro">{n.feed}</Selo>}
              <span className="font-title-code text-title-code text-outline">
                {n.publicado_em ? fmtData(n.publicado_em) : "—"}
              </span>
            </div>
            {n.url ? (
              <a
                href={n.url}
                target="_blank"
                rel="noreferrer"
                className="mt-space-xxs block font-headline-sm text-headline-sm text-on-surface hover:text-primary"
              >
                {n.titulo} ↗
              </a>
            ) : (
              <div className="mt-space-xxs font-headline-sm text-headline-sm text-on-surface">
                {n.titulo}
              </div>
            )}
            {n.resumo && (
              <p className="mt-space-xxs line-clamp-3 font-body-md text-body-sm text-on-surface-variant">
                {n.resumo}
              </p>
            )}
          </li>
        ))}
      </ul>
    </Painel>
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
