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
  MenorPrecoHistorico,
  NoticiaSteam,
  OfertaLoja,
  PontoSerie,
} from "../api/tipos";
import { Botao, Consulta, Icone, Selo } from "../componentes/base";
import { CapaJogo } from "../componentes/CapaJogo";
import { AreaNeon } from "../componentes/graficos/AreaNeon";
import { BarraFina, KpiHud, Painel } from "../componentes/hud";
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
        const { jogo, ficha } = dados;
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
                    imagemUrl={ficha.imagem_header}
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
                valorNumerico={jogo.jogadores_simultaneos}
                formatarValor={fmtNumero}
                rotulo={`Coletado ${fmtRelativo(jogo.janela_coleta)}`}
                variacao={jogo.variacao_jogadores}
                notaVariacao="vs. coleta anterior"
                acento="primaria"
              >
                <div className="mt-space-md">
                  <BarraFina
                    largura={
                      jogo.pico_jogadores && jogo.jogadores_simultaneos
                        ? Math.min(100, (jogo.jogadores_simultaneos / jogo.pico_jogadores) * 100)
                        : 0
                    }
                    className="bg-gradient-to-r from-primary-container to-secondary"
                    altura="h-2"
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta="Avaliações positivas"
                canto="STEAM REVIEWS"
                valor={fmtPercentual(jogo.nota_avaliacoes, 0)}
                valorNumerico={paraNumero(jogo.nota_avaliacoes)}
                formatarValor={(v) => fmtPercentual(v, 0)}
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
                valorNumerico={jogo.pico_jogadores}
                formatarValor={fmtCurto}
                rotulo="Maior valor já coletado"
                acento="secundaria"
                notaVariacao={`${fmtNumero(dados.serie.length)} snapshots na série`}
              />

              <KpiHud
                etiqueta="Preço atual"
                canto={jogo.moeda ?? "—"}
                valor={fmtMoeda(jogo.preco_no_momento, jogo.moeda)}
                valorNumerico={paraNumero(jogo.preco_no_momento)}
                formatarValor={(v) => fmtMoeda(v, jogo.moeda)}
                rotulo={
                  jogo.desconto_percentual
                    ? `${jogo.desconto_percentual}% de desconto`
                    : "sem desconto"
                }
                acento="primaria"
              />
            </section>

            {/* ==================== ONDE COMPRAR ==================== */}
            <OndeComprar
              ofertas={dados.ofertas}
              menor={dados.menor_preco_historico}
              gratuito={jogo.gratuito}
            />

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

/** Nome curto e amigável dos órgãos de classificação. */
const ORGAOS: Record<string, string> = {
  esrb: "ESRB",
  pegi: "PEGI",
  usk: "USK",
  dejus: "DEJUS",
  cero: "CERO",
  oflc: "OFLC",
  kgrb: "GRAC",
};

/** Recursos que descrevem COMO se joga — vão em destaque, com ícone. */
const ICONE_MODO: Record<string, string> = {
  "Single-player": "person",
  "Multi-player": "groups",
  "Co-op": "handshake",
  "Online Co-op": "handshake",
  "LAN Co-op": "handshake",
  "Shared/Split Screen Co-op": "splitscreen",
  "Shared/Split Screen": "splitscreen",
  "PvP": "swords",
  "Online PvP": "swords",
  "Cross-Platform Multiplayer": "sync_alt",
  "MMO": "public",
};

/** Ícone dos outros recursos conhecidos. O que não estiver aqui vira chip liso. */
const ICONE_RECURSO: Record<string, string> = {
  "Steam Achievements": "trophy",
  "Steam Trading Cards": "style",
  "Steam Cloud": "cloud",
  "Steam Workshop": "extension",
  "Full controller support": "stadia_controller",
  "Partial Controller Support": "stadia_controller",
  "Valve Anti-Cheat enabled": "shield",
  "Remote Play on Phone": "smartphone",
  "Remote Play on Tablet": "tablet",
  "Remote Play on TV": "tv",
  "Remote Play Together": "cast",
  "Family Sharing": "family_restroom",
  "In-App Purchases": "shopping_cart",
  "Captions available": "closed_caption",
  "Steam Timeline": "timeline",
  "HDR available": "hdr_on",
};

function tempoDeJogo(minutos: number | null): string | null {
  if (!minutos) return null;
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h > 0 ? `${h}h${m ? ` ${m}min` : ""}` : `${m}min`;
}

/** "1,000,000 .. 2,000,000" -> "1 mi – 2 mi". */
function faixaDeDonos(bruto: string): string {
  const nums = bruto.match(/[\d,]+/g)?.map((n) => Number(n.replace(/,/g, ""))) ?? [];
  if (nums.length < 2) return bruto;
  return `${fmtCurto(nums[0])} – ${fmtCurto(nums[1])}`;
}

const FEEDS_OFICIAIS = [
  "Community Announcements",
  "Steam Community Announcements",
  "Product Update",
];

/** Um dos quatro tiles do resumo da ficha. */
function TileFicha({
  icone,
  rotulo,
  acento,
  children,
}: {
  icone: string;
  rotulo: string;
  acento: "primary" | "secondary" | "tertiary";
  children: React.ReactNode;
}) {
  const glow = {
    primary: "bg-primary-container/10",
    secondary: "bg-secondary-container/20",
    tertiary: "bg-tertiary-container/10",
  }[acento];
  const cor = {
    primary: "text-primary-container",
    secondary: "text-secondary",
    tertiary: "text-tertiary-container",
  }[acento];

  return (
    <div className="relative overflow-hidden rounded-xl bg-surface-container-lowest p-space-base">
      <div
        className={`pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full blur-2xl ${glow}`}
        aria-hidden
      />
      <div className="relative z-10 flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
        <Icone nome={icone} className={`text-[16px] ${cor}`} />
        {rotulo}
      </div>
      <div className="relative z-10 mt-space-sm font-body-md text-body-sm text-on-surface">
        {children}
      </div>
    </div>
  );
}

function FichaDoJogo({ ficha, nome }: { ficha: FichaJogoSteam; nome: string }) {
  const vazia =
    ficha.recursos.length === 0 &&
    ficha.idiomas.length === 0 &&
    !ficha.donos_estimados &&
    ficha.tags_comunidade.length === 0 &&
    !ficha.conquistas_total;

  if (vazia) {
    return (
      <Painel icone="badge" titulo="Ficha do jogo">
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          A ficha ainda não foi coletada — ela vem do <code>appdetails</code> e do SteamSpy,
          e o coletor da Steam a preenche na próxima passada.
        </p>
      </Painel>
    );
  }

  const modos = ficha.recursos.filter((r) => r in ICONE_MODO);
  const outros = ficha.recursos.filter((r) => !(r in ICONE_MODO));
  const orgaos = Object.entries(ficha.classificacoes);
  const notasNumericas = orgaos
    .map(([, n]) => parseInt(n, 10))
    .filter((n) => !Number.isNaN(n));
  const idadeSelo = ficha.faixa_etaria
    ? `${ficha.faixa_etaria}+`
    : notasNumericas.length > 0
      ? `${Math.max(...notasNumericas)}+`
      : orgaos.length > 0
        ? "Classificado"
        : "Livre";
  const plataformas = ficha.plataformas.map(
    (p) => ({ windows: "Windows", mac: "macOS", linux: "Linux" })[p] ?? p,
  );
  const maxVotos = Math.max(...ficha.tags_comunidade.map(([, v]) => v), 1);

  return (
    <Painel
      icone="badge"
      titulo="Ficha do jogo"
      descricao="O que a página da Steam informa, mais as estimativas do SteamSpy."
    >
      {/* ---------- resumo em quatro tiles ---------- */}
      <div className="grid grid-cols-2 gap-space-sm lg:grid-cols-4">
        <TileFicha icone="shield_person" rotulo="Classificação" acento="tertiary">
          <div className="font-headline-sm text-headline-sm text-on-surface">{idadeSelo}</div>
          {orgaos.length > 0 && (
            <div className="mt-space-xxs font-title-code text-title-code text-outline">
              {orgaos
                .slice(0, 3)
                .map(([o, n]) => `${ORGAOS[o] ?? o.toUpperCase()} ${n.toUpperCase()}`)
                .join(" · ")}
            </div>
          )}
        </TileFicha>

        <TileFicha icone="devices" rotulo="Plataformas" acento="primary">
          <div className="font-headline-sm text-headline-sm text-on-surface">
            {plataformas.length > 0 ? plataformas.join(" · ") : "—"}
          </div>
          {ficha.suporte_controle && (
            <div className="mt-space-xxs font-title-code text-title-code text-outline">
              <Icone nome="stadia_controller" className="align-middle text-[13px]" /> controle{" "}
              {ficha.suporte_controle === "full" ? "total" : "parcial"}
            </div>
          )}
        </TileFicha>

        <TileFicha icone="language" rotulo="Idiomas" acento="secondary">
          <div className="font-headline-sm text-headline-sm text-on-surface">
            {ficha.idiomas.length || "—"}
          </div>
          {ficha.idiomas_com_audio.length > 0 && (
            <div className="mt-space-xxs font-title-code text-title-code text-outline">
              {ficha.idiomas_com_audio.length} com dublagem
            </div>
          )}
        </TileFicha>

        <TileFicha icone="trophy" rotulo="Conquistas" acento="tertiary">
          <div className="font-headline-sm text-headline-sm text-on-surface">
            {ficha.conquistas_total ? fmtNumero(ficha.conquistas_total) : "nenhuma"}
          </div>
          {ficha.conquistas_destaque.length > 0 && (
            <div className="mt-space-xs flex gap-space-xxs">
              {ficha.conquistas_destaque.slice(0, 5).map((c) => (
                <img
                  key={c.nome}
                  src={c.icone}
                  alt={c.nome}
                  title={c.nome}
                  className="h-5 w-5 rounded"
                  onError={(e) => (e.currentTarget.style.display = "none")}
                />
              ))}
            </div>
          )}
        </TileFicha>
      </div>

      {/* ---------- descritores de conteúdo ---------- */}
      {ficha.descritores_conteudo.length > 0 && (
        <div className="flex flex-wrap items-center gap-space-xs rounded-lg border border-error/25 bg-error/5 px-space-base py-space-sm">
          <Icone nome="warning" className="text-[16px] text-error" />
          <span className="font-title-code text-title-code uppercase tracking-wide text-error/90">
            {ficha.descritores_conteudo.join(" · ")}
          </span>
        </div>
      )}

      {/* ---------- modos de jogo + recursos ---------- */}
      {(modos.length > 0 || outros.length > 0) && (
        <div className="rounded-xl bg-surface-container-lowest p-space-base">
          <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            Modos de jogo e recursos
          </div>
          {modos.length > 0 && (
            <div className="mt-space-sm flex flex-wrap gap-space-xs">
              {modos.map((modo) => (
                <span
                  key={modo}
                  className="inline-flex items-center gap-space-xxs rounded-lg bg-primary-container/10 px-space-sm py-space-xs font-title-code text-title-code text-primary-container"
                >
                  <Icone nome={ICONE_MODO[modo]} className="text-[15px]" />
                  {modo}
                </span>
              ))}
            </div>
          )}
          {outros.length > 0 && (
            <div className="mt-space-sm flex flex-wrap gap-space-xxs">
              {outros.map((r) => (
                <span
                  key={r}
                  className="inline-flex items-center gap-space-xxs rounded bg-surface-container-high px-space-sm py-space-xxs font-title-code text-title-code text-on-surface-variant"
                >
                  {ICONE_RECURSO[r] && (
                    <Icone nome={ICONE_RECURSO[r]} className="text-[13px] text-outline" />
                  )}
                  {r}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ---------- alcance (SteamSpy) ---------- */}
      {(ficha.donos_estimados ||
        ficha.tempo_jogo_medio_min ||
        ficha.analises_totais !== null) && (
        <div className="grid grid-cols-1 gap-space-sm rounded-xl bg-surface-container-lowest p-space-base sm:grid-cols-3">
          {ficha.donos_estimados && (
            <div>
              <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Donos estimados
              </div>
              <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-primary-container">
                {faixaDeDonos(ficha.donos_estimados)}
              </div>
              <div className="mt-space-xxs font-title-code text-title-code text-outline">
                faixa do SteamSpy · não é número exato
              </div>
            </div>
          )}
          {tempoDeJogo(ficha.tempo_jogo_medio_min) && (
            <div>
              <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Tempo de jogo médio
              </div>
              <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-secondary">
                {tempoDeJogo(ficha.tempo_jogo_medio_min)}
              </div>
              <div className="mt-space-xxs font-title-code text-title-code text-outline">
                por dono, no total
              </div>
            </div>
          )}
          {ficha.analises_totais !== null && (
            <div>
              <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Recomendações na loja
              </div>
              <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-tertiary-container">
                {fmtCurto(ficha.analises_totais)}
              </div>
              {(ficha.dlc_ids.length > 0 || ficha.site_oficial) && (
                <div className="mt-space-xxs font-title-code text-title-code text-outline">
                  {ficha.dlc_ids.length > 0 && `${ficha.dlc_ids.length} DLC`}
                  {ficha.dlc_ids.length > 0 && ficha.site_oficial && " · "}
                  {ficha.site_oficial && (
                    <a
                      href={ficha.site_oficial}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary hover:underline"
                    >
                      site oficial ↗
                    </a>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ---------- tags da comunidade ---------- */}
      {ficha.tags_comunidade.length > 0 && (
        <div className="rounded-xl bg-surface-container-lowest p-space-base">
          <div className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
            <Icone nome="sell" className="text-[15px] text-secondary" />
            O que a comunidade marca
          </div>
          <div className="mt-space-sm space-y-space-xs">
            {ficha.tags_comunidade.slice(0, 8).map(([tag, votos]) => (
              <div key={tag} className="flex items-center gap-space-sm">
                <span className="w-32 shrink-0 truncate font-title-code text-title-code text-on-surface-variant">
                  {tag}
                </span>
                <div className="flex-1">
                  <BarraFina
                    largura={Math.max(4, (votos / maxVotos) * 100)}
                    className="bg-gradient-to-r from-primary-container to-secondary"
                    altura="h-2"
                  />
                </div>
                <span className="w-12 shrink-0 text-right font-title-code text-title-code text-outline">
                  {fmtCurto(votos)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ---------- idiomas + requisitos, recolhidos ---------- */}
      <div className="flex flex-col gap-space-sm sm:flex-row">
        {ficha.idiomas.length > 0 && (
          <details className="flex-1 rounded-lg bg-surface-container-lowest px-space-base py-space-sm">
            <summary className="cursor-pointer font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Idiomas ({ficha.idiomas.length})
            </summary>
            <p className="mt-space-xs font-body-md text-body-sm text-on-surface-variant">
              {ficha.idiomas.map((idioma) => (
                <span key={idioma} className="mr-space-sm inline-block">
                  {idioma}
                  {ficha.idiomas_com_audio.includes(idioma) && (
                    <Icone
                      nome="volume_up"
                      className="ml-[2px] align-middle text-[12px] text-primary"
                    />
                  )}
                </span>
              ))}
            </p>
          </details>
        )}
        {ficha.requisitos_minimos && (
          <details className="flex-1 rounded-lg bg-surface-container-lowest px-space-base py-space-sm">
            <summary className="cursor-pointer font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Requisitos mínimos
            </summary>
            <pre className="mt-space-xs whitespace-pre-wrap font-body-md text-body-sm text-on-surface-variant">
              {ficha.requisitos_minimos}
            </pre>
          </details>
        )}
      </div>

      <p className="font-body-sm text-body-sm text-outline">
        <strong>{nome}</strong> · Steam Store API + SteamSpy
        {ficha.coletado_ficha_em && ` · atualizada ${fmtRelativo(ficha.coletado_ficha_em)}`}
      </p>
    </Painel>
  );
}

// ---------------------------------------------------------------------------
// Últimas atualizações (ISteamNews)
// ---------------------------------------------------------------------------

function CartaoNoticia({ noticia, destaque }: { noticia: NoticiaSteam; destaque: boolean }) {
  const oficial = !noticia.feed || FEEDS_OFICIAIS.includes(noticia.feed);

  return (
    <a
      href={noticia.url ?? undefined}
      target="_blank"
      rel="noreferrer"
      className={`group relative block overflow-hidden rounded-xl border-l-2 bg-surface-container-lowest p-space-base transition-colors hover:bg-surface-container ${
        oficial ? "border-primary-container" : "border-outline/40"
      }`}
    >
      <div className="flex flex-wrap items-center gap-space-xs">
        {noticia.feed && (
          <span
            className={`rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${
              oficial
                ? "bg-primary-container/15 text-primary-container"
                : "bg-surface-container-high text-outline"
            }`}
          >
            {oficial ? "Steam · oficial" : noticia.feed}
          </span>
        )}
        <span className="font-title-code text-title-code text-outline">
          {noticia.publicado_em ? fmtData(noticia.publicado_em) : "—"}
        </span>
        {destaque && (
          <span className="rounded bg-tertiary-container/15 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary-container">
            mais recente
          </span>
        )}
      </div>

      <h3
        className={`mt-space-xs font-headline-sm text-on-surface transition-colors group-hover:text-primary ${
          destaque ? "text-headline-md" : "text-headline-sm"
        }`}
      >
        {noticia.titulo}
      </h3>

      {noticia.resumo && (
        <p className="mt-space-xs line-clamp-2 font-body-md text-body-sm text-on-surface-variant">
          {noticia.resumo}
        </p>
      )}

      {noticia.url && (
        <span className="mt-space-sm inline-flex items-center gap-space-xxs font-title-code text-title-code text-primary opacity-0 transition-opacity group-hover:opacity-100">
          Abrir na Steam <Icone nome="open_in_new" className="text-[14px]" />
        </span>
      )}
    </a>
  );
}

function UltimasAtualizacoes({ noticias }: { noticias: NoticiaSteam[] }) {
  if (noticias.length === 0) {
    return (
      <Painel icone="campaign" titulo="Últimas atualizações">
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          Nenhuma notícia coletada ainda. O feed oficial do jogo — patch notes e anúncios do
          estúdio — entra na próxima coleta da Steam.
        </p>
      </Painel>
    );
  }

  return (
    <Painel
      icone="campaign"
      titulo="Últimas atualizações"
      descricao="Patch notes e anúncios do feed oficial da Steam."
      meta={
        <Selo cor="neutro">
          {noticias.length} {noticias.length === 1 ? "post" : "posts"}
        </Selo>
      }
    >
      <div className="grid grid-cols-1 gap-space-sm lg:grid-cols-2">
        {noticias.map((n, i) => (
          <CartaoNoticia key={n.gid} noticia={n} destaque={i === 0} />
        ))}
      </div>
    </Painel>
  );
}

// ---------------------------------------------------------------------------
// Onde comprar (Fase 17, IsThereAnyDeal)
// ---------------------------------------------------------------------------

function moedaBr(valor: number | string | null, moeda: string | null): string {
  const n = typeof valor === "string" ? Number(valor) : valor;
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  try {
    return n.toLocaleString("pt-BR", {
      style: "currency",
      currency: moeda || "BRL",
    });
  } catch {
    return `${moeda ?? ""} ${n.toFixed(2)}`;
  }
}

function OndeComprar({
  ofertas,
  menor,
  gratuito,
}: {
  ofertas: OfertaLoja[];
  menor: MenorPrecoHistorico | null;
  gratuito: boolean | null;
}) {
  if (gratuito) return null;
  if (ofertas.length === 0) {
    // Sem oferta ativa agora - mas se o ITAD ja viu o jogo em promocao algum
    // dia, essa informacao ainda vale a pena mostrar (ex.: jogo saiu de
    // linha, ou nenhuma loja tem estoque no momento).
    return (
      <Painel
        icone="sell"
        titulo="Onde comprar"
        descricao="Comparação de preço entre lojas (IsThereAnyDeal)."
      >
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          {menor
            ? "Nenhuma loja com oferta agora."
            : "Este jogo ainda não passou pelo coletor de preço (IsThereAnyDeal) — a próxima rodada periódica traz o comparativo."}
        </p>
        {menor && (
          <p className="mt-space-sm font-body-md text-body-sm text-on-surface-variant">
            Já custou{" "}
            <strong className="text-tertiary-container">
              {moedaBr(menor.preco, menor.moeda)}
            </strong>
            {menor.loja && ` na ${menor.loja}`}
            {menor.data && ` (${fmtData(menor.data)})`} — o menor preço já registrado.
          </p>
        )}
      </Painel>
    );
  }

  const maisBarata = ofertas[0];
  const precoSteam = ofertas.find((o) => o.loja.toLowerCase() === "steam")?.preco;
  const economia =
    precoSteam !== undefined && Number(maisBarata.preco) < Number(precoSteam)
      ? Number(precoSteam) - Number(maisBarata.preco)
      : 0;
  const naMinima =
    menor !== null &&
    Math.abs(Number(maisBarata.preco) - Number(menor.preco)) < 0.01;

  return (
    <Painel
      icone="sell"
      titulo="Onde comprar"
      descricao="Preço atual em outras lojas — IsThereAnyDeal, ~33 lojas."
      meta={
        menor !== null && (
          <span
            className="rounded-lg bg-surface-container-lowest px-space-sm py-space-xs font-title-code text-title-code text-outline"
            title={
              menor.data
                ? `menor preço registrado, em ${fmtData(menor.data)}`
                : "menor preço registrado"
            }
          >
            mínima histórica:{" "}
            <strong className="text-tertiary-container">
              {moedaBr(menor.preco, menor.moeda)}
            </strong>
            {menor.loja ? ` · ${menor.loja}` : ""}
          </span>
        )
      }
    >
      {/* faixa-resumo */}
      <div className="flex flex-wrap items-baseline gap-space-sm rounded-xl bg-surface-container-lowest p-space-base">
        <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
          Melhor preço
        </span>
        <span className="font-headline-kpi text-headline-kpi leading-none text-primary-container">
          {moedaBr(maisBarata.preco, maisBarata.moeda)}
        </span>
        <span className="font-title-code text-title-code text-on-surface-variant">
          na {maisBarata.loja}
        </span>
        {economia > 0 && (
          <span className="rounded bg-tertiary-container/15 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary-container">
            {moedaBr(economia, maisBarata.moeda)} abaixo da Steam
          </span>
        )}
        {naMinima && (
          <span className="rounded bg-tertiary-container/15 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary-container">
            no menor preço de sempre
          </span>
        )}
      </div>

      {/* lista de lojas */}
      <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
              <th className="px-space-md py-space-sm">Loja</th>
              <th className="px-space-md py-space-sm text-right">Preço</th>
              <th className="px-space-md py-space-sm text-right">De</th>
              <th className="px-space-md py-space-sm text-right">Desc.</th>
              <th className="px-space-md py-space-sm" />
            </tr>
          </thead>
          <tbody className="font-body-md text-body-sm">
            {ofertas.map((o, i) => (
              <tr
                key={o.loja + i}
                className={i % 2 ? "bg-[#131824]" : "bg-[#10141D]"}
                style={
                  o.melhor
                    ? { boxShadow: "inset 3px 0 0 #00e5ff" }
                    : undefined
                }
              >
                <td className="px-space-md py-space-sm">
                  <span className="font-headline-sm text-headline-sm text-on-surface">
                    {o.loja}
                  </span>
                  {o.melhor && (
                    <span className="ml-space-xs rounded bg-primary-container/15 px-space-xxs py-[1px] font-badge-status text-badge-status uppercase text-primary-container">
                      melhor
                    </span>
                  )}
                  {o.drm && (
                    <span className="ml-space-xs font-title-code text-title-code text-outline">
                      {o.drm}
                    </span>
                  )}
                </td>
                <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface">
                  {moedaBr(o.preco, o.moeda)}
                </td>
                <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-outline">
                  {o.desconto ? (
                    <s>{moedaBr(o.preco_normal, o.moeda)}</s>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-space-md py-space-sm text-right">
                  {o.desconto ? (
                    <span className="rounded bg-tertiary-container/15 px-space-xs py-space-xxs font-title-code text-title-code text-tertiary-container">
                      −{o.desconto}%
                    </span>
                  ) : (
                    <span className="text-outline">—</span>
                  )}
                </td>
                <td className="px-space-md py-space-sm text-right">
                  {o.url && (
                    <a
                      href={o.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-space-xxs font-title-code text-title-code text-primary hover:underline"
                    >
                      abrir <Icone nome="open_in_new" className="text-[13px]" />
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="font-body-sm text-body-sm text-outline">
        Preço em BRL para o Brasil. Chave de Steam de loja terceira ativa na sua conta
        normalmente — confira a coluna de DRM. Fonte: isthereanydeal.com
      </p>
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
