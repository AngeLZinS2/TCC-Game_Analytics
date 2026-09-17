/**
 * Detalhe de um jogo da Steam: atributos + a serie temporal coletada.
 *
 * Porte da tela "Detalhe do Jogo" do Stitch: cabecalho com capa e chips,
 * caixa do Metacritic, fileira de KPIs, o grafico principal de jogadores
 * simultaneos, dois graficos menores (preco e volume de avaliacoes) e a tabela
 * de telemetria.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  useColetarJogo,
  useDesfavoritarJogo,
  useFavoritarJogo,
  useFavoritosJogos,
  useJogoSteam,
} from "@models/api/consultas";
import type {
  DetalheJogoSteam,
  DlcEmPromocao,
  FichaJogoSteam,
  MenorPrecoHistorico,
  NoticiaSteam,
  OfertaLoja,
  PontoHistoricoPrecoSteam,
  PontoSerie,
  PromocaoAtivaSteam,
} from "@models/api/tipos";
import { Botao, Consulta, Icone, MensagemErro, Selo } from "@views/componentes/base";
import { BotaoFavoritar } from "@views/componentes/BotaoFavoritar";
import { ArteJogo, CapaJogo } from "@views/componentes/CapaJogo";
import { CarrosselMidia } from "@views/componentes/CarrosselMidia";
import { AreaNeon } from "@views/componentes/graficos/AreaNeon";
import { BarraFina, KpiHud, Painel } from "@views/componentes/hud";
import {
  classificacaoSteam,
  fmtCurto,
  fmtData,
  fmtDataHora,
  fmtDecimal,
  fmtMoeda,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
  paraNumero,
} from "@util/formatos";

/** Janelas do seletor do grafico principal, em dias. `null` = tudo (`rotulo`
 * tambem `null` nesse caso - o texto vem de `painel.periodos.tudo`). */
const PERIODOS = [
  { valor: 7, rotulo: "7D" },
  { valor: 30, rotulo: "30D" },
  { valor: null, rotulo: null },
] as const;

const CHIP_CLASSIFICACAO = {
  positiva: "bg-tertiary/10 text-tertiary",
  neutra: "bg-surface-container-highest text-on-surface-variant",
  negativa: "bg-error/10 text-error",
} as const;

export function JogoSteamPagina() {
  const { t } = useTranslation();
  const { appId } = useParams();
  const [periodo, setPeriodo] = useState<number | null>(null);

  const detalhe = useJogoSteam(Number(appId));
  const favoritosJogos = useFavoritosJogos();
  const favoritar = useFavoritarJogo();
  const desfavoritar = useDesfavoritarJogo();
  const coletar = useColetarJogo();

  /*
   * Coleta sob demanda de quem chegou aqui sem ficha.
   *
   * A varredura de ofertas (Fase 35.1) povoa `dim_jogo_steam` com ~18 mil
   * apps que so tem nome, imagem e tags. Abrir um deles - clicando num
   * cartao de Ofertas - caia numa ficha vazia e sem saida: a linha existia,
   * entao nada no site se oferecia para busca-la. Agora a propria visita
   * dispara a coleta, que e exatamente o que o Catalogo ja fazia ao clicar
   * num resultado "da loja".
   *
   * `pedidos` guarda os app_ids ja pedidos NESTA montagem: sem isso, o
   * `invalidateQueries` do sucesso traria `ficha_coletada` de novo por um
   * instante e o efeito dispararia a coleta em laco.
   */
  const pedidos = useRef(new Set<number>());
  const fichaFaltando = detalhe.data?.ficha_coletada === false;

  useEffect(() => {
    const id = Number(appId);
    if (!fichaFaltando || !Number.isFinite(id) || pedidos.current.has(id)) return;
    pedidos.current.add(id);
    coletar.mutate(id);
  }, [fichaFaltando, appId, coletar]);
  const favoritado = favoritosJogos.data?.some(
    (f) => f.fonte === "steam" && f.jogo_id === appId,
  );

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

        // Sem ficha: a coleta ja foi disparada no efeito acima. Renderizar a
        // ficha vazia aqui mostraria travessao em todo campo e um grafico sem
        // ponto - pior que dizer que o dado esta a caminho.
        if (!dados.ficha_coletada) {
          return (
            <section className="flex flex-col items-center gap-space-base rounded-xl bg-surface-container-low p-space-3xl text-center shadow-2xl">
              <ArteJogo
                appId={jogo.app_id}
                nome={jogo.nome}
                imagemUrl={jogo.imagem_header}
                className="h-28 w-full max-w-md"
              />
              <h1 className="font-headline-md text-headline-md font-bold text-on-surface">
                {jogo.nome}
              </h1>

              {coletar.isError ? (
                <>
                  <MensagemErro erro={coletar.error} />
                  <Botao
                    icone="refresh"
                    aoClicar={() => coletar.mutate(Number(appId))}
                    desabilitado={coletar.isPending}
                  >
                    {t("jogoSteam.semFicha.tentarDeNovo")}
                  </Botao>
                </>
              ) : (
                <>
                  <span className="flex items-center gap-space-xs font-body-md text-body-md text-on-surface-variant">
                    <Icone nome="progress_activity" className="animate-spin text-[18px] text-primary" />
                    {t("jogoSteam.semFicha.coletando")}
                  </span>
                  <p className="max-w-md font-body-sm text-body-sm text-outline">
                    {t("jogoSteam.semFicha.explicacao")}
                  </p>
                </>
              )}
            </section>
          );
        }

        const pontos = serieRecortada.map((ponto: PontoSerie) => ({
          rotulo: fmtDataHora(ponto.janela_coleta),
          valor: ponto.jogadores_simultaneos ?? 0,
          detalhe: t("jogoSteam.grafico.jogadores", { contagem: fmtNumero(ponto.jogadores_simultaneos) }),
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
                to="/catalogo/steam"
                className="relative z-10 inline-flex items-center gap-space-xxs font-title-code text-title-code text-outline transition-colors hover:text-primary"
              >
                <Icone nome="arrow_back" className="text-[16px]" />
                {t("jogoSteam.voltar")}
              </Link>

              {/*
                Duas colunas: identidade a esquerda, galeria a direita. Antes a
                galeria ficava ABAIXO do titulo, o que deixava metade da largura
                vazia e empurrava os KPIs pra fora da primeira tela - o cabecalho
                sozinho passava de 550px de altura.
              */}
              <div className="relative z-10 mt-space-sm grid grid-cols-1 items-center gap-space-lg lg:grid-cols-[minmax(0,1fr)_minmax(0,34rem)]">
                <div className="flex min-w-0 items-start gap-space-base">
                  <CapaJogo
                    appId={jogo.app_id}
                    nome={jogo.nome}
                    imagemUrl={ficha.imagem_header}
                    className="h-20 w-20 rounded-lg"
                  />

                  <div className="min-w-0">
                    <div className="flex items-center gap-space-sm">
                      <h1 className="font-display-hero text-display-hero uppercase leading-none tracking-tight text-on-surface">
                        {jogo.nome}
                      </h1>
                      <BotaoFavoritar
                        favoritado={Boolean(favoritado)}
                        ocupado={favoritar.isPending || desfavoritar.isPending}
                        rotulo={t("jogoSteam.favoritarJogo")}
                        aoAlternar={() =>
                          favoritado
                            ? desfavoritar.mutate({ fonte: "steam", jogo_id: String(jogo.app_id) })
                            : favoritar.mutate({ fonte: "steam", jogo_id: String(jogo.app_id) })
                        }
                      />
                    </div>

                    <p className="mt-space-xs font-title-code text-title-code uppercase text-outline">
                      {t("jogoSteam.dev")} <span className="text-on-surface-variant">{jogo.desenvolvedora ?? "—"}</span>{" "}
                      · {t("jogoSteam.pub")}{" "}
                      <span className="text-on-surface-variant">{jogo.publicadora ?? "—"}</span>
                      {jogo.data_lancamento && (
                        <>
                          {" "}· {t("jogoSteam.lancamento")}{" "}
                          <span className="text-on-surface-variant">
                            {fmtData(jogo.data_lancamento)}
                          </span>
                        </>
                      )}
                      {" "}· {t("jogoSteam.appid")}{" "}
                      <span className="text-on-surface-variant">{jogo.app_id}</span>
                    </p>

                    <div className="mt-space-sm flex flex-wrap items-center gap-space-xs">
                      {jogo.gratuito && <Selo cor="positivo">{t("jogoSteam.gratuito")}</Selo>}
                      {jogo.generos.map((genero) => (
                        <span
                          key={genero}
                          className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-secondary"
                        >
                          {genero}
                        </span>
                      ))}

                      {/* O Metacritic vira pilula na mesma linha dos generos:
                          como bloco proprio ele forcava uma coluna so pra si e
                          brigava com a galeria pelo mesmo espaco. */}
                      {jogo.nota_metacritic !== null && (
                        <span
                          className="inline-flex items-center gap-space-xxs rounded border border-tertiary/30 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-outline"
                          title={t("jogoSteam.metacriticTitle")}
                        >
                          Metacritic
                          <strong className="font-title-code text-title-code text-tertiary">
                            {jogo.nota_metacritic}
                          </strong>
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* A galeria da loja: trailer primeiro, capturas depois. */}
                {ficha.midias.length > 0 && <CarrosselMidia midias={ficha.midias} />}
              </div>
            </section>

            {/* ==================== KPIS ==================== */}
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta={t("jogoSteam.kpis.jogadoresSimultaneos")}
                canto={t("jogoSteam.kpis.agora")}
                valor={fmtNumero(jogo.jogadores_simultaneos)}
                valorNumerico={jogo.jogadores_simultaneos}
                formatarValor={fmtNumero}
                rotulo={t("jogoSteam.kpis.coletado", { tempo: fmtRelativo(jogo.janela_coleta) })}
                variacao={jogo.variacao_jogadores}
                notaVariacao={t("jogoSteam.kpis.vsColetaAnterior")}
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
                etiqueta={t("jogoSteam.kpis.avaliacoesPositivas")}
                canto={t("jogoSteam.kpis.steamReviews")}
                valor={fmtPercentual(jogo.nota_avaliacoes, 0)}
                valorNumerico={paraNumero(jogo.nota_avaliacoes)}
                formatarValor={(v) => fmtPercentual(v, 0)}
                rotulo={t("jogoSteam.kpis.avaliacoesNoTotal", { contagem: fmtCurto(jogo.numero_avaliacoes) })}
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
                      {t("jogoSteam.kpis.semClassificacao")}
                    </span>
                  )}
                </div>
              </KpiHud>

              <KpiHud
                etiqueta={t("jogoSteam.kpis.picoHistorico")}
                canto={t("jogoSteam.kpis.peakCcu")}
                valor={fmtCurto(jogo.pico_jogadores)}
                valorNumerico={jogo.pico_jogadores}
                formatarValor={fmtCurto}
                rotulo={t("jogoSteam.kpis.maiorValorColetado")}
                acento="secundaria"
                notaVariacao={t("jogoSteam.kpis.snapshotsNaSerie", { contagem: fmtNumero(dados.serie.length) })}
              />

              <KpiHud
                etiqueta={t("jogoSteam.kpis.precoAtual")}
                canto={jogo.moeda ?? "—"}
                valor={fmtMoeda(jogo.preco_no_momento, jogo.moeda)}
                valorNumerico={paraNumero(jogo.preco_no_momento)}
                formatarValor={(v) => fmtMoeda(v, jogo.moeda)}
                rotulo={
                  jogo.desconto_percentual
                    ? t("jogoSteam.kpis.descontoPercentual", { percentual: jogo.desconto_percentual })
                    : t("jogoSteam.kpis.semDesconto")
                }
                acento="primaria"
              />
            </section>

            {/* ==================== PRECO NA STEAM (Fase 35) ==================== */}
            <PrecoNaSteam
              appId={jogo.app_id}
              moeda={jogo.moeda}
              promocao={dados.promocao_ativa}
              historico={dados.historico_preco_steam}
            />

            {/* ==================== ONDE COMPRAR ==================== */}
            <OndeComprar
              ofertas={dados.ofertas}
              menor={dados.menor_preco_historico}
              gratuito={jogo.gratuito}
            />

            {/* ==================== DLCs EM PROMOCAO ==================== */}
            <DlcsEmPromocao dlcs={dados.dlc_em_promocao} />

            {/* ==================== TEMPO PRA ZERAR ==================== */}
            <TempoParaZerar ficha={dados.ficha} nomeSteam={jogo.nome} />

            {/* ==================== REQUISITOS E IDIOMAS ==================== */}
            <RequisitosEIdiomas ficha={dados.ficha} />

            {/* ==================== FICHA ==================== */}
            <FichaDoJogo ficha={dados.ficha} nome={jogo.nome} />

            {/* ==================== ULTIMAS ATUALIZACOES ==================== */}
            <UltimasAtualizacoes noticias={dados.noticias} />

            {/* ==================== GRAFICO PRINCIPAL ==================== */}
            <Painel
              icone="show_chart"
              titulo={t("jogoSteam.grafico.titulo")}
              descricao={t("jogoSteam.grafico.descricao")}
              meta={
                <div className="flex items-center rounded bg-surface-container-low p-space-xxs shadow-sm">
                  {PERIODOS.map((opcao) => (
                    <button
                      key={opcao.rotulo ?? "tudo"}
                      type="button"
                      aria-pressed={periodo === opcao.valor}
                      onClick={() => setPeriodo(opcao.valor)}
                      className={`rounded px-space-sm py-space-xs font-title-code text-title-code transition-colors ${
                        periodo === opcao.valor
                          ? "bg-surface-container-high text-primary shadow-sm"
                          : "text-on-surface-variant hover:text-on-surface"
                      }`}
                    >
                      {opcao.rotulo ?? t("painel.periodos.tudo")}
                    </button>
                  ))}
                </div>
              }
            >
              {dados.serie.length < 2 && (
                <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                  {dados.serie.length === 0
                    ? t("jogoSteam.grafico.nenhumSnapshot")
                    : t("jogoSteam.grafico.umaColeta")}
                </p>
              )}

              <AreaNeon
                pontos={pontos}
                formatarValor={(valor) => fmtCurto(valor)}
                rodapeEsquerda={
                  <>
                    {t("jogoSteam.grafico.picoDaSerie")}{" "}
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
                  titulo={t("jogoSteam.precoHistorico.titulo")}
                  descricao={
                    dados.historico_preco_steam.length > 0
                      ? t("jogoSteam.precoHistorico.descricaoDedup")
                      : t("jogoSteam.precoHistorico.descricao")
                  }
                >
                  {/* Preferimos o historico deduplicado (Fase 35) - so uma
                      linha quando o preco muda de verdade. Sem ele ainda
                      (app nao reprocessado), cai no snapshot horario de
                      sempre, para a secao nao ficar vazia. */}
                  <AreaNeon
                    pontos={
                      dados.historico_preco_steam.length > 0
                        ? dados.historico_preco_steam.map((ponto) => ({
                            rotulo: fmtDataHora(ponto.registrado_em),
                            valor: paraNumero(ponto.preco_final) ?? 0,
                            detalhe: fmtMoeda(ponto.preco_final, jogo.moeda),
                          }))
                        : dados.serie.map((ponto) => ({
                            rotulo: fmtDataHora(ponto.janela_coleta),
                            valor: paraNumero(ponto.preco_no_momento) ?? 0,
                            detalhe: fmtMoeda(ponto.preco_no_momento, jogo.moeda),
                          }))
                    }
                    formatarValor={(valor) => fmtMoeda(valor, jogo.moeda)}
                  />
                </Painel>

                <Painel
                  icone="reviews"
                  titulo={t("jogoSteam.volumeAvaliacoes.titulo")}
                  descricao={t("jogoSteam.volumeAvaliacoes.descricao")}
                >
                  <AreaNeon
                    pontos={dados.serie.map((ponto) => ({
                      rotulo: fmtDataHora(ponto.janela_coleta),
                      valor: ponto.numero_avaliacoes ?? 0,
                      detalhe: t("jogoSteam.volumeAvaliacoes.avaliacoes", { contagem: fmtNumero(ponto.numero_avaliacoes) }),
                    }))}
                    formatarValor={(valor) => fmtCurto(valor)}
                  />
                </Painel>
              </section>
            )}

            {/* ==================== TABELA ==================== */}
            <Painel
              icone="table_rows"
              titulo={t("jogoSteam.tabela.titulo")}
              descricao={t("jogoSteam.tabela.descricao")}
              meta={
                <Botao icone="file_download" aoClicar={() => exportarCsv(dados)}>
                  {t("jogoSteam.tabela.exportarCsv")}
                </Botao>
              }
            >
              {dados.serie.length === 0 ? (
                <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                  {t("jogoSteam.tabela.nadaColetado")}
                </p>
              ) : (
                <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                        <th className="px-space-md py-space-sm">{t("jogoSteam.tabela.colunas.janela")}</th>
                        <th className="px-space-md py-space-sm text-right">
                          {t("jogoSteam.tabela.colunas.jogadoresCcu")}
                        </th>
                        <th className="px-space-md py-space-sm text-right">{t("jogoSteam.tabela.colunas.nota")}</th>
                        <th className="px-space-md py-space-sm text-right">{t("jogoSteam.tabela.colunas.avaliacoes")}</th>
                        <th className="px-space-md py-space-sm text-right">{t("jogoSteam.tabela.colunas.preco")}</th>
                        <th className="px-space-md py-space-sm text-right">{t("jogoSteam.tabela.colunas.desconto")}</th>
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
  const { t } = useTranslation();
  const vazia =
    ficha.recursos.length === 0 &&
    ficha.idiomas.length === 0 &&
    !ficha.donos_estimados &&
    ficha.tags_comunidade.length === 0 &&
    !ficha.conquistas_total;

  if (vazia) {
    return (
      <Painel icone="badge" titulo={t("jogoSteam.ficha.titulo")}>
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          {t("jogoSteam.ficha.naoColetada")}
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
        ? t("jogoSteam.ficha.classificado")
        : t("jogoSteam.ficha.livre");
  const plataformas = ficha.plataformas.map(
    (p) => ({ windows: "Windows", mac: "macOS", linux: "Linux" })[p] ?? p,
  );
  const maxVotos = Math.max(...ficha.tags_comunidade.map(([, v]) => v), 1);

  return (
    <Painel
      icone="badge"
      titulo={t("jogoSteam.ficha.titulo")}
      descricao={t("jogoSteam.ficha.descricao")}
    >
      {/* ---------- resumo em quatro tiles ---------- */}
      <div className="grid grid-cols-2 gap-space-sm lg:grid-cols-4">
        <TileFicha icone="shield_person" rotulo={t("jogoSteam.ficha.classificacao")} acento="tertiary">
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

        <TileFicha icone="devices" rotulo={t("jogoSteam.ficha.plataformas")} acento="primary">
          <div className="font-headline-sm text-headline-sm text-on-surface">
            {plataformas.length > 0 ? plataformas.join(" · ") : "—"}
          </div>
          {ficha.suporte_controle && (
            <div className="mt-space-xxs font-title-code text-title-code text-outline">
              <Icone nome="stadia_controller" className="align-middle text-[13px]" />{" "}
              {t("jogoSteam.ficha.controle", {
                tipo:
                  ficha.suporte_controle === "full"
                    ? t("jogoSteam.ficha.controleTotal")
                    : t("jogoSteam.ficha.controleParcial"),
              })}
            </div>
          )}
        </TileFicha>

        <TileFicha icone="language" rotulo={t("jogoSteam.ficha.idiomas")} acento="secondary">
          <div className="font-headline-sm text-headline-sm text-on-surface">
            {ficha.idiomas.length || "—"}
          </div>
          {ficha.idiomas_com_audio.length > 0 && (
            <div className="mt-space-xxs font-title-code text-title-code text-outline">
              {t("jogoSteam.ficha.comDublagem", { contagem: ficha.idiomas_com_audio.length })}
            </div>
          )}
        </TileFicha>

        <TileFicha icone="trophy" rotulo={t("jogoSteam.ficha.conquistas")} acento="tertiary">
          <div className="font-headline-sm text-headline-sm text-on-surface">
            {ficha.conquistas_total ? fmtNumero(ficha.conquistas_total) : t("jogoSteam.ficha.nenhuma")}
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
            {t("jogoSteam.ficha.modosDeJogoRecursos")}
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
                {t("jogoSteam.ficha.donosEstimados")}
              </div>
              <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-primary-container">
                {faixaDeDonos(ficha.donos_estimados)}
              </div>
              <div className="mt-space-xxs font-title-code text-title-code text-outline">
                {t("jogoSteam.ficha.faixaSteamSpy")}
              </div>
            </div>
          )}
          {tempoDeJogo(ficha.tempo_jogo_medio_min) && (
            <div>
              <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                {t("jogoSteam.ficha.tempoDeJogoMedio")}
              </div>
              <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-secondary">
                {tempoDeJogo(ficha.tempo_jogo_medio_min)}
              </div>
              <div className="mt-space-xxs font-title-code text-title-code text-outline">
                {t("jogoSteam.ficha.porDono")}
              </div>
            </div>
          )}
          {ficha.analises_totais !== null && (
            <div>
              <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                {t("jogoSteam.ficha.recomendacoesNaLoja")}
              </div>
              <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-tertiary-container">
                {fmtCurto(ficha.analises_totais)}
              </div>
              {(ficha.dlc_ids.length > 0 || ficha.site_oficial) && (
                <div className="mt-space-xxs font-title-code text-title-code text-outline">
                  {ficha.dlc_ids.length > 0 && t("jogoSteam.ficha.dlc", { contagem: ficha.dlc_ids.length })}
                  {ficha.dlc_ids.length > 0 && ficha.site_oficial && " · "}
                  {ficha.site_oficial && (
                    <a
                      href={ficha.site_oficial}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary hover:underline"
                    >
                      {t("jogoSteam.ficha.siteOficial")}
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
            {t("jogoSteam.ficha.oQueComunidadeMarca")}
          </div>
          <div className="mt-space-sm space-y-space-xs">
            {ficha.tags_comunidade.slice(0, 8).map(([tag, votos]) => (
              <div key={tag} className="flex items-center gap-space-sm">
                {/* O rotulo encolhe no celular: com `w-32` fixo (128px) a
                    barra sobrava com 55px a 390px - estreita demais pra
                    comunicar proporcao, que e a unica funcao dela. */}
                <span className="w-24 shrink-0 truncate font-title-code text-title-code text-on-surface-variant sm:w-32">
                  {tag}
                </span>
                <div className="flex-1">
                  <BarraFina
                    largura={Math.max(4, (votos / maxVotos) * 100)}
                    className="bg-gradient-to-r from-primary-container to-secondary"
                    altura="h-2"
                  />
                </div>
                {/* `w-20` e medido, nao chutado: nesta fonte (IBM Plex Mono
                    13px) o pior caso de `fmtCurto` e "999,9 mil" = 72px. Com o
                    `w-12` (48px) anterior, as OITO linhas cortavam o numero -
                    "91,2 mil" precisa de 64px. E corte sem reticencias, entao
                    a pessoa lia um numero errado sem perceber que faltava
                    digito. */}
                <span className="w-20 shrink-0 text-right font-title-code text-title-code text-outline">
                  {fmtCurto(votos)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Idiomas e requisitos saíram daqui: viraram painel próprio, logo
          abaixo do "Quanto tempo leva" (ver `RequisitosEIdiomas`). Recolhidos
          num `<details>`, eram a informação que mais dava trabalho de achar. */}

      <p className="font-body-sm text-body-sm text-outline">
        <strong>{nome}</strong> · Steam Store API + SteamSpy
        {ficha.coletado_ficha_em &&
          t("jogoSteam.ficha.atualizada", { tempo: fmtRelativo(ficha.coletado_ficha_em) })}
      </p>
    </Painel>
  );
}

// ---------------------------------------------------------------------------
// Últimas atualizações (ISteamNews)
// ---------------------------------------------------------------------------

function CartaoNoticia({ noticia, destaque }: { noticia: NoticiaSteam; destaque: boolean }) {
  const { t } = useTranslation();
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
            {oficial ? t("jogoSteam.noticias.oficial") : noticia.feed}
          </span>
        )}
        <span className="font-title-code text-title-code text-outline">
          {noticia.publicado_em ? fmtData(noticia.publicado_em) : "—"}
        </span>
        {destaque && (
          <span className="rounded bg-tertiary-container/15 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary-container">
            {t("jogoSteam.noticias.maisRecente")}
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
          {t("jogoSteam.noticias.abrirNaSteam")} <Icone nome="open_in_new" className="text-[14px]" />
        </span>
      )}
    </a>
  );
}

function UltimasAtualizacoes({ noticias }: { noticias: NoticiaSteam[] }) {
  const { t } = useTranslation();
  if (noticias.length === 0) {
    return (
      <Painel icone="campaign" titulo={t("jogoSteam.noticias.titulo")}>
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          {t("jogoSteam.noticias.vazio")}
        </p>
      </Painel>
    );
  }

  return (
    <Painel
      icone="campaign"
      titulo={t("jogoSteam.noticias.titulo")}
      descricao={t("jogoSteam.noticias.descricao")}
      meta={
        <Selo cor="neutro">
          {noticias.length} {noticias.length === 1 ? t("jogoSteam.noticias.post") : t("jogoSteam.noticias.posts")}
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
// Preco na Steam (Fase 35) - primeiro-partido, distinto do "Onde comprar"
// (ITAD, cross-loja) logo abaixo. O link para a loja e sempre gerado a
// partir do app_id, nunca de um dado vindo do front.
// ---------------------------------------------------------------------------

function PrecoNaSteam({
  appId,
  moeda,
  promocao,
  historico,
}: {
  appId: number;
  moeda: string | null;
  promocao: PromocaoAtivaSteam | null;
  historico: PontoHistoricoPrecoSteam[];
}) {
  const { t } = useTranslation();
  const menor =
    historico.length > 0
      ? historico.reduce((min, p) =>
          Number(p.preco_final) < Number(min.preco_final) ? p : min
        )
      : null;

  return (
    <div className="flex flex-wrap items-center gap-space-base rounded-xl bg-surface-container-lowest px-space-base py-space-sm">
      {promocao && (
        <span className="flex items-center gap-space-xs font-body-sm text-body-sm text-on-surface-variant">
          <Icone nome="local_offer" className="text-[16px] text-tertiary" />
          {t("jogoSteam.precoSteam.promocaoDesde", { data: fmtData(promocao.iniciada_em) })}
        </span>
      )}
      {menor && (
        <span className="font-body-sm text-body-sm text-on-surface-variant">
          {t("jogoSteam.precoSteam.menorHistorico")}{" "}
          <strong className="text-tertiary-container">{fmtMoeda(menor.preco_final, moeda)}</strong>
        </span>
      )}
      <a
        href={`https://store.steampowered.com/app/${appId}`}
        target="_blank"
        rel="noopener noreferrer"
        className="ml-auto inline-flex items-center gap-space-xs font-title-code text-title-code text-primary hover:underline"
      >
        {t("jogoSteam.precoSteam.verNaSteam")}
        <Icone nome="open_in_new" className="text-[14px]" />
      </a>
    </div>
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

/** DLCs deste jogo em promocao agora.
 *
 * A lista de Ofertas mostra so jogo - "Pack de Temporada 2026" no meio dos
 * jogos nao ajuda ninguem a achar o que comprar. Mas a promocao da DLC vale,
 * e aqui ela tem o contexto que faltava la: o jogo dono ao lado.
 *
 * So preco de promocao, como o resto do painel de preco desta tela: a DLC
 * nao tem pagina propria no site, entao nao ha pra onde levar quem clicar -
 * o nome, a arte e quanto custa agora e o que da pra oferecer sem prometer
 * navegacao que nao existe.
 */
function DlcsEmPromocao({ dlcs }: { dlcs: DlcEmPromocao[] }) {
  const { t } = useTranslation();
  if (dlcs.length === 0) return null;

  return (
    <Painel
      icone="extension"
      titulo={t("jogoSteam.dlcs.titulo")}
      descricao={t("jogoSteam.dlcs.descricao")}
    >
      <ul className="flex flex-col gap-space-xs">
        {dlcs.map((dlc) => (
          <li
            key={dlc.app_id}
            className="flex items-center gap-space-sm rounded-lg bg-surface-container-lowest px-space-sm py-space-xs"
          >
            {dlc.imagem_header && (
              <img
                src={dlc.imagem_header}
                alt=""
                loading="lazy"
                className="hidden h-[34px] w-[72px] shrink-0 rounded object-cover sm:block"
              />
            )}
            <span className="min-w-0 flex-1 truncate font-body-md text-body-sm text-on-surface">
              {dlc.nome}
            </span>
            <span className="shrink-0 rounded bg-tertiary-container/20 px-space-xs font-title-code text-title-code text-tertiary-container">
              -{dlc.desconto_percentual}%
            </span>
            <span className="shrink-0 font-title-code text-title-code tabular-nums text-on-surface">
              {moedaBr(dlc.preco_final, dlc.moeda)}
            </span>
          </li>
        ))}
      </ul>
    </Painel>
  );
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
  const { t } = useTranslation();
  if (gratuito) return null;
  if (ofertas.length === 0) {
    // Sem oferta ativa agora - mas se o ITAD ja viu o jogo em promocao algum
    // dia, essa informacao ainda vale a pena mostrar (ex.: jogo saiu de
    // linha, ou nenhuma loja tem estoque no momento).
    return (
      <Painel
        icone="sell"
        titulo={t("jogoSteam.ondeComprar.titulo")}
        descricao={t("jogoSteam.ondeComprar.descricao")}
      >
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          {menor ? t("jogoSteam.ondeComprar.nenhumaOferta") : t("jogoSteam.ondeComprar.naoColetado")}
        </p>
        {menor && (
          <p className="mt-space-sm font-body-md text-body-sm text-on-surface-variant">
            {t("jogoSteam.ondeComprar.jaCustou")}{" "}
            <strong className="text-tertiary-container">
              {moedaBr(menor.preco, menor.moeda)}
            </strong>
            {menor.loja && t("jogoSteam.ondeComprar.naLoja", { loja: menor.loja })}
            {menor.data && t("jogoSteam.ondeComprar.naData", { data: fmtData(menor.data) })}
            {t("jogoSteam.ondeComprar.menorPrecoRegistrado")}
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
      titulo={t("jogoSteam.ondeComprar.titulo")}
      descricao={t("jogoSteam.ondeComprar.descricaoComOfertas")}
      meta={
        menor !== null && (
          <span
            className="rounded-lg bg-surface-container-lowest px-space-sm py-space-xs font-title-code text-title-code text-outline"
            title={
              menor.data
                ? t("jogoSteam.ondeComprar.menorPrecoEm", { data: fmtData(menor.data) })
                : t("jogoSteam.ondeComprar.menorPrecoRegistradoTitle")
            }
          >
            {t("jogoSteam.ondeComprar.minimaHistorica")}{" "}
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
          {t("jogoSteam.ondeComprar.melhorPreco")}
        </span>
        <span className="font-headline-kpi text-headline-kpi leading-none text-primary-container">
          {moedaBr(maisBarata.preco, maisBarata.moeda)}
        </span>
        <span className="font-title-code text-title-code text-on-surface-variant">
          {t("jogoSteam.ondeComprar.na", { loja: maisBarata.loja })}
        </span>
        {economia > 0 && (
          <span className="rounded bg-tertiary-container/15 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary-container">
            {t("jogoSteam.ondeComprar.abaixoDaSteam", { valor: moedaBr(economia, maisBarata.moeda) })}
          </span>
        )}
        {naMinima && (
          <span className="rounded bg-tertiary-container/15 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary-container">
            {t("jogoSteam.ondeComprar.noMenorPrecoDeSempre")}
          </span>
        )}
      </div>

      {/* lista de lojas */}
      <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
              <th className="px-space-md py-space-sm">{t("jogoSteam.ondeComprar.colunas.loja")}</th>
              <th className="px-space-md py-space-sm text-right">{t("jogoSteam.ondeComprar.colunas.preco")}</th>
              <th className="px-space-md py-space-sm text-right">{t("jogoSteam.ondeComprar.colunas.de")}</th>
              <th className="px-space-md py-space-sm text-right">{t("jogoSteam.ondeComprar.colunas.desc")}</th>
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
                    ? { boxShadow: "inset 3px 0 0 #5a8cff" }
                    : undefined
                }
              >
                <td className="px-space-md py-space-sm">
                  <span className="font-headline-sm text-headline-sm text-on-surface">
                    {o.loja}
                  </span>
                  {o.melhor && (
                    <span className="ml-space-xs rounded bg-primary-container/15 px-space-xxs py-[1px] font-badge-status text-badge-status uppercase text-primary-container">
                      {t("jogoSteam.ondeComprar.melhor")}
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
                      {t("jogoSteam.ondeComprar.abrir")} <Icone nome="open_in_new" className="text-[13px]" />
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="font-body-sm text-body-sm text-outline">
        {t("jogoSteam.ondeComprar.rodape")}
      </p>
    </Painel>
  );
}

// ---------------------------------------------------------------------------
// Quanto tempo leva pra zerar (Fase 18, HowLongToBeat)
// ---------------------------------------------------------------------------

/**
 * Diferente do "Tempo de jogo médio" da ficha (SteamSpy: quanto os donos
 * jogaram de fato, em média, incluindo quem só passou por perto), isto é
 * quanto uma pessoa leva pra ZERAR — estimativa da comunidade do
 * HowLongToBeat, curada por quem terminou o jogo.
 */
function TempoParaZerar({ ficha, nomeSteam }: { ficha: FichaJogoSteam; nomeSteam: string }) {
  const { t } = useTranslation();
  const temTempo =
    ficha.hltb_horas_historia !== null ||
    ficha.hltb_horas_extras !== null ||
    ficha.hltb_horas_completista !== null;

  if (!temTempo) {
    return (
      <Painel
        icone="hourglass_top"
        titulo={t("jogoSteam.tempoParaZerar.titulo")}
        descricao={t("jogoSteam.tempoParaZerar.descricao")}
      >
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          {ficha.coletado_tempo_em
            ? t("jogoSteam.tempoParaZerar.semTempoRegistrado")
            : t("jogoSteam.tempoParaZerar.naoColetado")}
        </p>
      </Painel>
    );
  }

  const nomeDivergente =
    ficha.hltb_nome && ficha.hltb_nome.trim().toLowerCase() !== nomeSteam.trim().toLowerCase()
      ? ficha.hltb_nome
      : null;

  return (
    <Painel
      icone="hourglass_top"
      titulo={t("jogoSteam.tempoParaZerar.titulo")}
      descricao={t("jogoSteam.tempoParaZerar.descricao")}
      meta={
        ficha.hltb_id && (
          <a
            href={`https://howlongtobeat.com/game/${ficha.hltb_id}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-space-xxs rounded-lg bg-surface-container-lowest px-space-sm py-space-xs font-title-code text-title-code text-primary hover:underline"
          >
            {t("jogoSteam.tempoParaZerar.verNoHltb")} <Icone nome="open_in_new" className="text-[13px]" />
          </a>
        )
      }
    >
      <div className="grid grid-cols-1 gap-space-sm rounded-xl bg-surface-container-lowest p-space-base sm:grid-cols-3">
        <div>
          <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("jogoSteam.tempoParaZerar.historiaPrincipal")}
          </div>
          <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-primary-container">
            {ficha.hltb_horas_historia !== null ? `${fmtDecimal(ficha.hltb_horas_historia)}h` : "—"}
          </div>
        </div>
        <div>
          <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("jogoSteam.tempoParaZerar.historiaExtras")}
          </div>
          <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-secondary">
            {ficha.hltb_horas_extras !== null ? `${fmtDecimal(ficha.hltb_horas_extras)}h` : "—"}
          </div>
        </div>
        <div>
          <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("jogoSteam.tempoParaZerar.completista")}
          </div>
          <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-tertiary-container">
            {ficha.hltb_horas_completista !== null
              ? `${fmtDecimal(ficha.hltb_horas_completista)}h`
              : "—"}
          </div>
        </div>
      </div>

      {nomeDivergente && (
        <p className="font-body-sm text-body-sm text-outline">
          {t("jogoSteam.tempoParaZerar.casadoComo")}{" "}
          <strong className="text-on-surface-variant">{nomeDivergente}</strong>{" "}
          {t("jogoSteam.tempoParaZerar.noHltb")}
        </p>
      )}
    </Painel>
  );
}

// ---------------------------------------------------------------------------
// Requisitos e idiomas
// ---------------------------------------------------------------------------

/**
 * Requisitos de sistema e idiomas, abertos por padrão.
 *
 * Antes viviam recolhidos num `<details>` no fim da ficha - a informação que
 * mais dá trabalho achar ("roda na minha máquina?" e "tem português?") era
 * justamente a que exigia dois cliques e uma rolagem até o rodapé.
 *
 * Mínimo e recomendado ficam em abas em vez de um bloco só: são a mesma lista
 * de campos com valores diferentes, e lado a lado viram uma parede de texto
 * onde ninguém acha a diferença. A aba de recomendado só existe quando o jogo
 * publica - a Steam entrega só o mínimo em vários (9 dos nossos 25).
 */
function RequisitosEIdiomas({ ficha }: { ficha: FichaJogoSteam }) {
  const { t } = useTranslation();
  const temRecomendado = Boolean(ficha.requisitos_recomendados);
  const [aba, setAba] = useState<"minimos" | "recomendados">("minimos");

  if (!ficha.requisitos_minimos && ficha.idiomas.length === 0) return null;

  const requisitos =
    aba === "recomendados" ? ficha.requisitos_recomendados : ficha.requisitos_minimos;

  return (
    <Painel
      icone="memory"
      titulo={t("jogoSteam.requisitos.titulo")}
      descricao={t("jogoSteam.requisitos.descricao")}
      meta={
        ficha.idiomas.length > 0 && (
          <Selo>{t("jogoSteam.requisitos.idiomasContagem", { contagem: ficha.idiomas.length })}</Selo>
        )
      }
    >
      <div className="grid grid-cols-1 gap-space-base lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* ---------- requisitos, com aba ---------- */}
        {ficha.requisitos_minimos && (
          <div className="flex flex-col gap-space-sm">
            <div className="flex gap-space-xxs">
              {(
                [
                  ["minimos", t("jogoSteam.requisitos.minimos")],
                  ["recomendados", t("jogoSteam.requisitos.recomendados")],
                ] as const
              )
                .filter(([chave]) => chave === "minimos" || temRecomendado)
                .map(([chave, rotulo]) => (
                  <button
                    key={chave}
                    type="button"
                    onClick={() => setAba(chave)}
                    aria-pressed={aba === chave}
                    className={`rounded px-space-md py-space-xs font-label-caps text-label-caps uppercase tracking-widest transition-colors ${
                      aba === chave
                        ? "bg-surface-container-high text-primary shadow-[inset_0_-2px_0_0_#5a8cff]"
                        : "text-outline hover:bg-surface-container hover:text-on-surface"
                    }`}
                  >
                    {rotulo}
                  </button>
                ))}

              {!temRecomendado && (
                <span
                  className="self-center pl-space-sm font-body-sm text-body-sm text-outline"
                  title={t("jogoSteam.requisitos.semRecomendadosTitle")}
                >
                  {t("jogoSteam.requisitos.semRecomendadosPublicados")}
                </span>
              )}
            </div>

            {/* Um cartão por campo, em grade - não uma linha larga por campo.
                Em linha, "12 GB RAM" ficava sozinho num vão de 700px e o olho
                tinha que atravessar a tela do rótulo até o valor; em cartão,
                rótulo e valor ficam a dois centímetros um do outro e a leitura
                vira vertical. A Steam manda um `<li>` por campo, então cada
                linha do texto já é um cartão. */}
            <dl className="grid grid-cols-1 gap-space-sm sm:grid-cols-2">
              {(requisitos ?? "")
                .split("\n")
                .map((linha) => {
                  const corte = linha.indexOf(":");
                  const temRotulo = corte > 0 && corte < 24;
                  return {
                    rotulo: temRotulo ? linha.slice(0, corte) : null,
                    valor: temRotulo ? linha.slice(corte + 1).trim() : linha.trim(),
                  };
                })
                // Campo sem valor ("Additional Notes:" vazio) viraria um cartão
                // em branco - a Steam manda vários assim.
                .filter((campo) => campo.valor)
                .map((campo, i) => (
                  <div
                    key={`${i}-${campo.rotulo ?? campo.valor}`}
                    className="flex flex-col gap-space-xxs rounded-lg bg-surface-container-lowest p-space-sm"
                  >
                    {campo.rotulo && (
                      <dt className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                        {campo.rotulo}
                      </dt>
                    )}
                    <dd className="m-0 font-body-md text-body-sm text-on-surface">
                      {campo.valor}
                    </dd>
                  </div>
                ))}
            </dl>
          </div>
        )}

        {/* ---------- idiomas ---------- */}
        {ficha.idiomas.length > 0 && (
          <div className="flex flex-col gap-space-sm">
            <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {t("jogoSteam.requisitos.idiomas")}
              <span className="ml-space-xs text-on-surface-variant">
                <Icone nome="volume_up" className="align-middle text-[12px] text-primary" />{" "}
                {t("jogoSteam.requisitos.comDublagem")}
              </span>
            </div>

            <div className="rolagem-discreta max-h-72 overflow-auto rounded-lg bg-surface-container-lowest p-space-base">
              <div className="flex flex-wrap gap-space-xxs">
                {ficha.idiomas.map((idioma) => {
                  const dublado = ficha.idiomas_com_audio.includes(idioma);
                  return (
                    <span
                      key={idioma}
                      className={`inline-flex items-center gap-space-xxs rounded px-space-xs py-space-xxs font-body-sm text-body-sm ${
                        dublado
                          ? "bg-primary-container/15 text-on-surface"
                          : "bg-surface-container text-on-surface-variant"
                      }`}
                    >
                      {idioma}
                      {dublado && (
                        <Icone nome="volume_up" className="text-[12px] text-primary" />
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
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
