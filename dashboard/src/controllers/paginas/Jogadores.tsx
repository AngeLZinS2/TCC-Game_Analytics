/**
 * Jogadores identificados nas partidas coletadas.
 *
 * Porte da tela "Jogadores" do Stitch: cabecalho de telemetria, barra de
 * controles, quatro KPIs, o spotlight dos tres melhores e a tabela ranqueavel
 * com abas de ordenacao e paginacao.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { useJogadores, useSaude } from "@models/api/consultas";
import { usePaginacaoLocal } from "@models/hooks/paginacao";
import type { ResumoJogador } from "@models/api/tipos";
import { Botao, Consulta, Icone, Selo } from "@views/componentes/base";
import {
  BarraFina,
  CAMPO,
  KpiHud,
  LABEL_CAMPO,
  Paginacao,
  Painel,
  Pilula,
  Segmentos,
  Sparkline,
} from "@views/componentes/hud";
import { useJogoAtual } from "@views/layout/JogoAtual";
import { corDoJogo } from "@views/tema";
import { fmtDecimal, fmtNumero, fmtPercentual } from "@util/formatos";

/** As abas de ordenacao rapida da toolbar da tabela. */
const ORDENACOES = [
  { valor: "partidas", chave: "volume", icone: "insights" },
  { valor: "kda", chave: "kda", icone: "swords" },
  { valor: "winrate", chave: "winrate", icone: "trending_up" },
  { valor: "gpm", chave: "gpm", icone: "payments" },
] as const;

type Ordenacao = (typeof ORDENACOES)[number]["valor"];

/** Cor da medalha por posicao no podio - ouro, prata e bronze do desenho. */
const MEDALHAS = ["#ffd700", "#e0e0e0", "#cd7f32"];

/** Nome do jogador, ou o id quando a fonte anonimizou o participante. */
function nomeDe(jogador: ResumoJogador): string {
  return jogador.nome ?? `#${jogador.id_jogador}`;
}

/**
 * Retrato do jogador — só o LoL traz foto (elenco da API oficial). Sem URL, ou
 * quando ela falha, cai na inicial, igual à `CapaXbox`.
 */
function RetratoJogador({
  nome,
  imagem,
  className = "h-8 w-8 font-title-code text-title-code",
}: {
  nome: string;
  imagem?: string | null;
  className?: string;
}) {
  const [falhou, setFalhou] = useState(false);
  if (falhou || !imagem) {
    return (
      <span
        className={`flex shrink-0 items-center justify-center rounded-full bg-surface-container-high text-on-surface-variant ${className}`}
        aria-hidden
      >
        {nome.charAt(0).toUpperCase()}
      </span>
    );
  }
  return (
    <img
      src={imagem}
      alt=""
      loading="lazy"
      onError={() => setFalhou(true)}
      className={`shrink-0 rounded-full bg-surface-container object-cover ${className}`}
    />
  );
}

function valorDe(jogador: ResumoJogador, ordem: Ordenacao): number {
  switch (ordem) {
    case "kda":
      return jogador.kda_medio ?? 0;
    case "winrate":
      return jogador.winrate;
    case "gpm":
      return Number(jogador.economia_por_minuto_media ?? 0);
    default:
      return jogador.partidas;
  }
}

/**
 * Cartao do podio.
 *
 * O desenho traz foto, nome real e time de cada jogador. Nada disso e
 * coletado: a OpenDota devolve o apelido e mais nada. Entao o lugar da foto e
 * ocupado pela inicial, e as tres celulas de estatistica trazem o que existe -
 * heroi assinatura, KDA e winrate.
 */
function CartaoMvp({
  jogador,
  posicao,
  jogo,
  t,
}: {
  jogador: ResumoJogador;
  posicao: number;
  jogo: string;
  t: TFunction;
}) {
  return (
    <div className="relative flex flex-col gap-space-md overflow-hidden rounded bg-surface-container-low p-space-base shadow-xl">
      <div
        className="pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full blur-2xl"
        style={{ background: `${MEDALHAS[posicao]}22` }}
        aria-hidden
      />

      <div className="flex items-start justify-between gap-space-sm">
        <div className="flex min-w-0 items-center gap-space-sm">
          <div className="relative shrink-0">
            <RetratoJogador
              nome={nomeDe(jogador)}
              imagem={jogador.imagem}
              className="h-14 w-14 font-headline-md text-headline-md shadow-md"
            />
            <span
              className="absolute -left-1 -top-1 rounded bg-surface-container-highest px-1.5 py-0.5 font-badge-status text-badge-status shadow"
              style={{ color: MEDALHAS[posicao] }}
            >
              #{posicao + 1}
            </span>
          </div>

          <div className="flex min-w-0 flex-col">
            <span className="truncate font-headline-md text-headline-md leading-tight text-on-surface">
              {nomeDe(jogador)}
            </span>
            <span className="font-body-sm text-body-sm text-outline">
              {t("jogadores.podio.partidasVitorias", {
                partidas: fmtNumero(jogador.partidas),
                vitorias: fmtNumero(jogador.vitorias),
              })}
            </span>
          </div>
        </div>

        <span
          className="shrink-0 rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase"
          style={{ background: `${corDoJogo(jogo)}22`, color: corDoJogo(jogo) }}
        >
          {jogo}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-space-xs rounded bg-surface-container-lowest/80 p-space-sm">
        <div className="flex min-w-0 flex-col">
          <span className="font-label-caps text-label-caps uppercase text-outline">
            {jogo === "leagueoflegends" ? t("jogadores.podio.campeaoAssinatura") : t("jogadores.podio.heroiAssinatura")}
          </span>
          <span className="truncate font-title-code text-title-code text-on-surface">
            {jogador.personagem_assinatura ?? "—"}
            {jogador.partidas_assinatura
              ? ` (${Math.round((jogador.partidas_assinatura / jogador.partidas) * 100)}%)`
              : ""}
          </span>
        </div>

        <div className="flex flex-col">
          <span className="font-label-caps text-label-caps uppercase text-outline">
            {t("jogadores.podio.kdaMedio")}
          </span>
          <span className="font-title-code text-title-code text-tertiary">
            {fmtDecimal(jogador.kda_medio, 2)}
          </span>
        </div>

        <div className="flex flex-col">
          <span className="font-label-caps text-label-caps uppercase text-outline">
            {t("jogadores.podio.winrate")}
          </span>
          <span className="font-title-code text-title-code text-primary">
            {fmtPercentual(jogador.winrate)}
          </span>
        </div>
      </div>
    </div>
  );
}

export function JogadoresPagina() {
  const { t } = useTranslation();
  const { jogo } = useJogoAtual();
  // LoL traz elenco (foto/rota/time) e o "GPM" na verdade é ouro por jogo — o
  // feed não dá duração de jogo confiável.
  const ehLol = jogo === "leagueoflegends";

  // LoL começa em 0 (mostra o elenco inteiro — partida com stat é rara, o feed
  // oficial só guarda ~2 semanas). Dota/resto começa em 3.
  const [minPartidas, setMinPartidas] = useState(
    jogo === "leagueoflegends" ? 0 : 3,
  );
  const [ordenacao, setOrdenacao] = useState<Ordenacao>("partidas");
  const [busca, setBusca] = useState("");

  // LoL: elenco inteiro (500+); a paginação é no cliente.
  const jogadores = useJogadores(jogo, minPartidas, ehLol ? 600 : 200);
  const saude = useSaude();

  const online = saude.data?.status === "ok";

  const ordenados = useMemo(() => {
    const lista = (jogadores.data ?? []).filter((jogador) =>
      busca ? nomeDe(jogador).toLowerCase().includes(busca.toLowerCase()) : true,
    );
    return [...lista].sort((a, b) => valorDe(b, ordenacao) - valorDe(a, ordenacao));
  }, [jogadores.data, ordenacao, busca]);

  // 5 por página no celular, 25 no desktop (o leitor troca).
  const pag = usePaginacaoLocal(ordenados, {
    porPaginaInicial: { mobile: 5, desktop: 25 },
    chaveReset: `${jogo}|${minPartidas}|${ordenacao}|${busca}`,
  });

  // O podio segue a ordenacao escolhida: "os tres melhores" depende de por qual
  // metrica se esta olhando, e travar em volume contradiria a aba ativa.
  const podio = ordenados.slice(0, 3);

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-space-xs">
          <div className="flex flex-wrap items-center gap-space-sm">
            <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-on-surface">
              {t("jogadores.cabecalho.titulo")}
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
                    online ? "bg-tertiary-container shadow-[0_0_8px_#40d19e]" : "bg-error"
                  }`}
                />
              </span>
              <span
                className={`font-badge-status text-badge-status uppercase tracking-widest ${
                  online ? "text-tertiary" : "text-error"
                }`}
              >
                {online ? t("jogadores.cabecalho.aoVivo") : t("jogadores.cabecalho.semContato")}
              </span>
            </div>
            <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
              {t("jogadores.cabecalho.deck")}
            </span>
          </div>

          <p className="font-body-sm text-body-sm text-on-surface-variant">
            {ehLol
              ? t("jogadores.cabecalho.descricaoLol")
              : t("jogadores.cabecalho.descricaoOutros")}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-space-sm">
          <label className={LABEL_CAMPO}>
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {ehLol ? t("jogadores.cabecalho.minJogos") : t("jogadores.cabecalho.minPartidas")}
            </span>
            <select
              value={minPartidas}
              onChange={(evento) => setMinPartidas(Number(evento.target.value))}
              className={CAMPO}
            >
              {(ehLol ? [0, 1, 3, 5, 10] : [1, 3, 5, 10]).map((valor) => (
                <option key={valor} value={valor}>
                  {valor === 0 ? t("jogadores.cabecalho.todos") : valor}
                </option>
              ))}
            </select>
          </label>

          <Botao
            icone="refresh"
            aoClicar={() => jogadores.refetch()}
            desabilitado={jogadores.isFetching}
          >
            {jogadores.isFetching ? t("jogadores.cabecalho.atualizando") : t("jogadores.cabecalho.atualizar")}
          </Botao>
        </div>
      </section>

      {/* ==================== CONTROLES ==================== */}
      <section className="flex flex-wrap items-center gap-space-md rounded-xl bg-surface-container-low/90 p-space-base shadow-lg">
        <div className="relative min-w-[16rem] flex-1">
          <Icone
            nome="manage_search"
            className="absolute left-space-sm top-1/2 -translate-y-1/2 text-[20px] text-primary-container"
          />
          <input
            type="search"
            value={busca}
            onChange={(evento) => setBusca(evento.target.value)}
            placeholder={t("jogadores.controles.buscarPlaceholder")}
            aria-label={t("jogadores.controles.buscarAria")}
            className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-space-sm font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
          />
        </div>
      </section>

      {/* ==================== QUATRO KPIS ==================== */}
      <Consulta estado={jogadores} altura={160} vazio={t("jogadores.vazioMinimo")}>
        {(lista: ResumoJogador[]) => {
          const comKda = lista.filter((j) => j.kda_medio !== null);
          const kdaMedio = comKda.length
            ? comKda.reduce((t, j) => t + (j.kda_medio ?? 0), 0) / comKda.length
            : null;
          const melhorWinrate = [...lista].sort((a, b) => b.winrate - a.winrate)[0];
          const participacoes = lista.reduce((t, j) => t + j.partidas, 0);

          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta={t("jogadores.kpis.jogadoresNoRecorte")}
                canto={minPartidas === 0 ? t("jogadores.kpis.elencoTodo") : t("jogadores.kpis.min", { n: minPartidas })}
                valor={fmtNumero(lista.length)}
                valorNumerico={lista.length}
                formatarValor={fmtNumero}
                rotulo={t("jogadores.kpis.identificadosNaDimensao")}
                acento="primaria"
                notaVariacao={t("jogadores.kpis.participacoes", { n: fmtNumero(participacoes) })}
              >
                <Segmentos acesos={lista.length ? 6 : 0} acento="primaria" />
              </KpiHud>

              <KpiHud
                etiqueta={t("jogadores.kpis.kdaMedioDoGrupo")}
                canto={t("jogadores.kpis.media")}
                valor={kdaMedio === null ? "—" : fmtDecimal(kdaMedio, 2)}
                valorNumerico={kdaMedio}
                formatarValor={(v) => fmtDecimal(v, 2)}
                rotulo={t("jogadores.kpis.kdaFormula")}
                acento="secundaria"
                notaVariacao={t("jogadores.kpis.comKdaCalculavel", { n: comKda.length })}
              >
                <Sparkline
                  valores={[...lista]
                    .sort((a, b) => (b.kda_medio ?? 0) - (a.kda_medio ?? 0))
                    .slice(0, 20)
                    .map((j) => j.kda_medio ?? 0)}
                  className="text-secondary"
                />
              </KpiHud>

              <KpiHud
                etiqueta={t("jogadores.kpis.maiorWinrate")}
                canto={t("jogadores.kpis.topo")}
                valor={melhorWinrate ? fmtPercentual(melhorWinrate.winrate) : "—"}
                valorNumerico={melhorWinrate?.winrate ?? null}
                formatarValor={(v) => fmtPercentual(v)}
                rotulo={melhorWinrate ? nomeDe(melhorWinrate) : t("jogadores.kpis.semDados")}
                acento="terciaria"
              >
                <div className="mt-space-md">
                  <BarraFina
                    largura={melhorWinrate?.winrate ?? 0}
                    className="bg-gradient-to-r from-tertiary-container to-tertiary"
                    altura="h-2"
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta={ehLol ? t("jogadores.kpis.campeoesAssinatura") : t("jogadores.kpis.heroisAssinatura")}
                canto={t("jogadores.kpis.diversidade")}
                valor={fmtNumero(
                  new Set(
                    lista.map((j) => j.personagem_assinatura).filter(Boolean),
                  ).size,
                )}
                valorNumerico={
                  new Set(
                    lista.map((j) => j.personagem_assinatura).filter(Boolean),
                  ).size
                }
                formatarValor={fmtNumero}
                rotulo={ehLol ? t("jogadores.kpis.campeoesDistintos") : t("jogadores.kpis.heroisDistintos")}
                acento="primaria"
                notaVariacao={t("jogadores.kpis.entrePresentesNoRecorte")}
              />
            </section>
          );
        }}
      </Consulta>

      {/* ==================== PODIO ==================== */}
      {podio.length > 0 && (
        <Painel
          icone="military_tech"
          titulo={t("jogadores.podio.destaquesPor", {
            ordenacao: t(`jogadores.ordenacoes.${ORDENACOES.find((o) => o.valor === ordenacao)?.chave}`),
          })}
          descricao={t("jogadores.podio.descricao")}
          meta={<Selo cor="primario">{t("jogadores.podio.top3")}</Selo>}
        >
          <div className="grid grid-cols-1 gap-space-base lg:grid-cols-3">
            {podio.map((jogador, indice) => (
              <CartaoMvp
                key={jogador.id_jogador}
                jogador={jogador}
                posicao={indice}
                jogo={jogo}
                t={t}
              />
            ))}
          </div>
        </Painel>
      )}

      {/* ==================== TABELA ==================== */}
      <Painel
        icone="table_rows"
        titulo={t("jogadores.tabela.titulo")}
        descricao={t("jogadores.tabela.descricao")}
        meta={
          <div className="flex flex-wrap items-center gap-space-xs">
            {ORDENACOES.map((opcao) => (
              <Pilula
                key={opcao.valor}
                ativa={ordenacao === opcao.valor}
                icone={opcao.icone}
                aoClicar={() => setOrdenacao(opcao.valor)}
              >
                {t(`jogadores.ordenacoes.${opcao.chave}`)}
              </Pilula>
            ))}
          </div>
        }
      >
        <Consulta estado={jogadores} vazio={t("jogadores.vazioMinimo")}>
          {() =>
            pag.fatia.length === 0 ? (
              <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                {t("jogadores.tabela.vazioBusca")}
              </p>
            ) : (
              <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                      <th className="px-space-md py-space-sm">{t("jogadores.tabela.colNumero")}</th>
                      <th className="px-space-md py-space-sm">{t("jogadores.tabela.colJogador")}</th>
                      <th className="px-space-md py-space-sm">
                        {ehLol ? t("jogadores.tabela.colCampeaoAssinatura") : t("jogadores.tabela.colHeroiAssinatura")}
                      </th>
                      <th className="px-space-md py-space-sm text-right">{t("jogadores.tabela.colPartidas")}</th>
                      <th className="px-space-md py-space-sm text-right">{t("jogadores.tabela.colVitorias")}</th>
                      <th className="px-space-md py-space-sm">{t("jogadores.tabela.colWinrate")}</th>
                      <th className="px-space-md py-space-sm text-right">{t("jogadores.tabela.colKda")}</th>
                      <th className="px-space-md py-space-sm text-right">
                        {ehLol ? t("jogadores.tabela.colOuroPorJogo") : t("jogadores.tabela.colGpm")}
                      </th>
                    </tr>
                  </thead>

                  <tbody className="font-body-md text-body-sm">
                    {pag.fatia.map((jogador, indice) => {
                      const posicao = (pag.pagina - 1) * pag.porPagina + indice;
                      return (
                        <tr
                          key={jogador.id_jogador}
                          className={`transition-colors hover:bg-surface-container-high/60 ${
                            indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                          }`}
                        >
                          <td className="px-space-md py-space-sm">
                            <span
                              className="font-label-caps text-label-caps"
                              style={{ color: MEDALHAS[posicao] ?? undefined }}
                            >
                              #{String(posicao + 1).padStart(2, "0")}
                            </span>
                          </td>

                          <td className="px-space-md py-space-sm">
                            <div className="flex items-center gap-space-sm">
                              <RetratoJogador
                                nome={nomeDe(jogador)}
                                imagem={jogador.imagem}
                              />
                              <div className="flex min-w-0 flex-col">
                                <span className="flex items-center gap-space-xs">
                                  <span className="truncate font-headline-sm text-headline-sm text-on-surface">
                                    {nomeDe(jogador)}
                                  </span>
                                  {jogador.papel && (
                                    <span className="shrink-0 rounded bg-surface-container px-space-xxs py-[1px] font-badge-status text-badge-status uppercase text-secondary">
                                      {jogador.papel}
                                    </span>
                                  )}
                                </span>
                                {jogador.equipe_nome && (
                                  <span className="truncate font-label-caps text-label-caps text-outline">
                                    {jogador.equipe_nome}
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>

                          <td className="px-space-md py-space-sm">
                            {jogador.personagem_assinatura ? (
                              <span className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-secondary">
                                {jogador.personagem_assinatura}
                                {jogador.partidas_assinatura
                                  ? ` ×${jogador.partidas_assinatura}`
                                  : ""}
                              </span>
                            ) : (
                              <span className="text-outline">—</span>
                            )}
                          </td>

                          <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface">
                            {fmtNumero(jogador.partidas)}
                          </td>

                          <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                            {fmtNumero(jogador.vitorias)}
                          </td>

                          <td className="px-space-md py-space-sm">
                            <div className="flex items-center gap-space-sm">
                              <div className="w-20">
                                <BarraFina
                                  largura={jogador.winrate}
                                  className="bg-gradient-to-r from-primary-container to-tertiary"
                                />
                              </div>
                              <span className="font-title-code text-title-code tabular-nums text-tertiary">
                                {fmtPercentual(jogador.winrate)}
                              </span>
                            </div>
                          </td>

                          <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-primary">
                            {fmtDecimal(jogador.kda_medio, 2)}
                          </td>

                          <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                            {fmtNumero(jogador.economia_por_minuto_media)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          }
        </Consulta>

        <Paginacao
          pagina={pag.pagina}
          totalPaginas={pag.totalPaginas}
          porPagina={pag.porPagina}
          opcoesPorPagina={[5, 15, 25, 50]}
          aoMudarPagina={pag.setPagina}
          aoMudarPorPagina={pag.setPorPagina}
          resumo={t("jogadores.tabela.paginacaoResumo", { n: fmtNumero(ordenados.length) })}
        />
      </Painel>
    </>
  );
}
