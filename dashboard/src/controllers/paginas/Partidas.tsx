/**
 * Partidas coletadas.
 *
 * Porte da tela "Partidas" do Stitch: cabecalho de comando, a barra de filtros
 * com o seletor de jogo e os dropdowns, quatro KPIs (um deles com a barra
 * segmentada de winrate), histograma de duracao, serie de ingestao e a tabela
 * densa com paginacao.
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  useAgendaPartidas,
  useFiltrosPartidas,
  useConfrontos,
  useResumoConfrontos,
  usePartidas,
  usePartidasPorDia,
  useResumoPartidas,
  useSaude,
} from "@models/api/consultas";
import type {
  Partida,
  PartidaAgendada,
  PartidasPorDia,
  ResumoPartidas,
} from "@models/api/tipos";
import { Botao, Consulta, Icone, Selo } from "@views/componentes/base";
import { AreaNeon } from "@views/componentes/graficos/AreaNeon";
import { HistogramaNeon } from "@views/componentes/graficos/HistogramaNeon";
import {
  BarraFina,
  BarraSegmentada,
  CAMPO,
  KpiHud,
  LABEL_CAMPO,
  Paginacao,
  Painel,
  Sparkline,
} from "@views/componentes/hud";
import { EstatisticasConfrontos } from "@views/componentes/EstatisticasConfrontos";
import { useEhMobile } from "@models/hooks/media";
import { paraCartaoPartida } from "@views/componentes/CartaoConfronto";
import {
  SeletorModoConfrontos,
  VisaoConfrontos,
  useModoConfrontos,
} from "@views/componentes/VisaoConfrontos";
import { useJogoAtual } from "@views/layout/JogoAtual";
import { corDoJogo, PALETA_POLOS } from "@views/tema";
import {
  fmtCurto,
  fmtDataCurta,
  fmtDataHora,
  fmtDuracao,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
} from "@util/formatos";

/** Janelas do seletor de periodo, em dias. `null` = tudo (rotulo `null`
 * tambem - o texto vem de `painel.periodos.tudo`). */
const PERIODOS = [
  { valor: 7, rotulo: "7D" },
  { valor: 30, rotulo: "30D" },
  { valor: 90, rotulo: "90D" },
  { valor: null, rotulo: null },
] as const;

/** O lado vencedor escrito, com a cor que o placar usa. */
export function LadoVencedor({ vencedor }: { vencedor: string | null }) {
  if (vencedor === "radiant") return <Selo cor="positivo">Radiant</Selo>;
  if (vencedor === "dire") return <Selo cor="negativo">Dire</Selo>;
  return <span className="text-outline">—</span>;
}

/** Escudo pequeno de time — logo quando há, senão a sigla. */
function EscudoMini({
  logo,
  tag,
  nome,
}: {
  logo: string | null;
  tag: string | null;
  nome: string;
}) {
  if (logo) {
    return (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm bg-neutral-200 p-[1px]">
        <img src={logo} alt="" className="max-h-full max-w-full object-contain" />
      </span>
    );
  }
  return (
    <span
      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm bg-surface-container-highest text-[8px] font-bold uppercase leading-none text-outline"
      aria-hidden
    >
      {(tag || nome).slice(0, 2)}
    </span>
  );
}

/** Radiant × Dire de uma partida, com escudo e o vencedor em negrito. */
function TimesDaPartida({ partida: p }: { partida: Partida }) {
  const nomeA = p.equipe_a_nome ?? "Radiant";
  const nomeB = p.equipe_b_nome ?? "Dire";
  const classe = (venceu: boolean) =>
    `truncate ${venceu ? "font-bold text-on-surface" : "text-on-surface-variant"}`;
  return (
    <div className="flex items-center gap-space-xs font-title-code text-title-code">
      <EscudoMini logo={p.equipe_a_logo} tag={p.equipe_a_tag} nome={nomeA} />
      <span className={`max-w-[9rem] ${classe(p.vitoria_a === true)}`} title={nomeA}>
        {nomeA}
      </span>
      <span className="shrink-0 text-[10px] uppercase text-outline">vs</span>
      <EscudoMini logo={p.equipe_b_logo} tag={p.equipe_b_tag} nome={nomeB} />
      <span className={`max-w-[9rem] ${classe(p.vitoria_a === false)}`} title={nomeB}>
        {nomeB}
      </span>
    </div>
  );
}

/**
 * `secao` reparte a tela entre duas sub-abas de E-Sports:
 *
 * - `partidas`  — o grao de PARTIDA (`dim_partida`): KPIs, histogramas e a
 *   tabela densa. So Dota 2 tem esse detalhe.
 * - `resultados` — o grao de CONFRONTO (placar da serie, do calendario):
 *   existe para quase todos os jogos.
 *
 * Uma so tela porque as duas leem o mesmo jogo e a mesma barra de contexto;
 * o `secao` decide quais paineis aparecem.
 */
export function PartidasPagina({
  secao = "partidas",
}: {
  secao?: "partidas" | "resultados";
} = {}) {
  const { t } = useTranslation();
  const navegar = useNavigate();
  const { jogo } = useJogoAtual();
  const emResultados = secao === "resultados";

  const [liga, setLiga] = useState("");
  const [modo, setModo] = useState("");
  const [periodo, setPeriodo] = useState<number | null>(null);
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(1);
  const [paginaConfrontos, setPaginaConfrontos] = useState(1);
  const [modoConfrontos, setModoConfrontos] = useModoConfrontos();
  // A agenda (próximas) guarda a própria preferência de modo, separada dos
  // resultados — dá pra querer cartão numa aba e lista na outra.
  const [modoAgenda, setModoAgenda] = useModoConfrontos("playdb:agenda-modo");
  // O histórico operacional (só Dota) também: a "Lista" aqui é a tabela densa.
  const [modoHistorico, setModoHistorico] = useModoConfrontos(
    "playdb:dota-partidas-modo",
  );
  // 5 por página no celular, 25/20 no desktop (só o valor inicial depende da tela).
  const ehMobile = useEhMobile();
  const [porPagina, setPorPagina] = useState(() => (ehMobile ? 5 : 25));
  const [porPaginaConfrontos, setPorPaginaConfrontos] = useState(() =>
    ehMobile ? 5 : 20,
  );

  const desde = useMemo(() => {
    if (periodo === null) return undefined;
    return new Date(Date.now() - periodo * 86400_000).toISOString().slice(0, 10);
  }, [periodo]);

  const filtros = useFiltrosPartidas(jogo);
  const resumo = useResumoPartidas(jogo);
  const porDia = usePartidasPorDia(jogo);
  const saude = useSaude();
  // O calendario decidido existe para os 14 jogos; `dim_partida`, so para
  // Dota 2. Por isso este hook nao depende dos filtros da tabela abaixo -
  // eles falam de partida com detalhe, que os outros jogos nao tem.
  // `+ 1`: uma linha extra pra saber se há próxima página (o endpoint não
  // devolve total).
  const confrontos = useConfrontos(
    jogo,
    paginaConfrontos,
    porPaginaConfrontos + 1,
  );
  const resumoConfrontos = useResumoConfrontos(jogo);
  const agenda = useAgendaPartidas(jogo);
  // Zero aqui nao e "sem dado": e "a fonte deste jogo nao publica partida,
  // so a serie". `dim_partida` so tem linha para Dota 2.
  const temPartidaDetalhada = (resumo.data?.partidas ?? 0) > 0;

  // Uma linha a mais do que cabe na pagina: e assim que da para saber se existe
  // proxima pagina sem o backend devolver o total.
  const partidas = usePartidas({
    jogo,
    liga: liga || undefined,
    desde,
    limite: porPagina + 1,
    deslocamento: (pagina - 1) * porPagina,
  });

  // Qualquer troca de filtro volta para a primeira pagina - continuar na pagina
  // 7 de um recorte novo mostraria uma tela vazia sem explicacao.
  useEffect(() => setPaginaConfrontos(1), [jogo, porPaginaConfrontos]);
  useEffect(() => setPagina(1), [jogo, liga, modo, periodo, busca, porPagina]);

  const online = saude.data?.status === "ok";

  /**
   * `modo` e `busca` filtram no cliente porque o endpoint nao os aceita.
   * O recorte vale para a pagina em tela, e o rodape diz isso - esconder a
   * diferenca faria a contagem parecer global.
   */
  const daPagina = (partidas.data ?? []).slice(0, porPagina);
  const visiveis = daPagina.filter((partida) => {
    if (modo && partida.modo !== modo) return false;
    if (busca) {
      const alvo = `${partida.liga_nome ?? ""} ${partida.id_externo}`.toLowerCase();
      if (!alvo.includes(busca.toLowerCase())) return false;
    }
    return true;
  });

  const temProxima = (partidas.data?.length ?? 0) > porPagina;
  const totalPaginas = temProxima ? pagina + 1 : pagina;

  return (
    <>
      {/* ==================== CABECALHO DE COMANDO ==================== */}
      <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-space-xs">
          <div className="flex flex-wrap items-center gap-space-sm">
            <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-on-surface">
              {emResultados ? t("partidas.cabecalho.resultados") : t("partidas.cabecalho.partidas")}
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
                {online ? t("partidas.cabecalho.feedAtivo") : t("partidas.cabecalho.semContato")}
              </span>
            </div>
            <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
              {emResultados ? t("partidas.cabecalho.deckResultados") : t("partidas.cabecalho.deckPartidas")}
            </span>
          </div>

          {/*
            A frase do star schema descreve o que a OpenDota entrega, e ela só
            cobre Dota 2. Deixá-la fixa afirmaria, para os outros treze
            esportes, um grão de dado que a tela não tem — a mesma classe de
            erro de dizer a fonte errada num painel de procedência.
          */}
          <p className="font-body-sm text-body-sm text-on-surface-variant">
            {emResultados
              ? t("partidas.cabecalho.descricaoResultados")
              : temPartidaDetalhada
                ? t("partidas.cabecalho.descricaoComDetalhe")
                : t("partidas.cabecalho.descricaoSemDetalhe")}
          </p>
        </div>

        {!emResultados && temPartidaDetalhada && (
        <div className="flex flex-wrap items-center gap-space-sm">
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

          <Botao
            icone="refresh"
            aoClicar={() => partidas.refetch()}
            desabilitado={partidas.isFetching}
          >
            {partidas.isFetching ? t("partidas.cabecalho.atualizando") : t("partidas.cabecalho.atualizarTelemetria")}
          </Botao>
        </div>
        )}
      </section>

      {/* ==================== BARRA DE FILTROS ==================== */}
      {/* Torneio, modo e busca filtram a tabela POR PARTIDA. Sem `dim_partida`
          ela nao e renderizada, e um filtro que nao filtra nada e pior que
          filtro nenhum. Na aba Resultados nada disso se aplica. */}
      {!emResultados && temPartidaDetalhada && (
      <section className="space-y-space-md rounded-xl bg-surface-container-low/90 p-space-base shadow-lg">
        <div className="flex flex-wrap items-center gap-space-sm">
          {temPartidaDetalhada && (
          <label className={LABEL_CAMPO}>
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {t("partidas.filtros.torneio")}
            </span>
            <select
              value={liga}
              onChange={(evento) => setLiga(evento.target.value)}
              className={CAMPO}
            >
              <option value="">{t("partidas.filtros.todosOsTorneios")}</option>
              {filtros.data?.ligas.map((nome) => (
                <option key={nome} value={nome}>
                  {nome}
                </option>
              ))}
            </select>
          </label>
          )}

          {temPartidaDetalhada && (
          <label className={LABEL_CAMPO}>
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {t("partidas.filtros.modo")}
            </span>
            <select
              value={modo}
              onChange={(evento) => setModo(evento.target.value)}
              className={CAMPO}
            >
              <option value="">{t("partidas.filtros.todosOsModos")}</option>
              {filtros.data?.modos.map((nome) => (
                <option key={nome} value={nome}>
                  {nome}
                </option>
              ))}
            </select>
          </label>
          )}

          {temPartidaDetalhada && (
          <div className="relative min-w-[16rem] flex-1">
            <Icone
              nome="manage_search"
              className="absolute left-space-sm top-1/2 -translate-y-1/2 text-[20px] text-primary-container"
            />
            <input
              type="search"
              value={busca}
              onChange={(evento) => setBusca(evento.target.value)}
              placeholder={t("partidas.filtros.buscarPlaceholder")}
              aria-label={t("partidas.filtros.buscarAriaLabel")}
              className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-space-sm font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
            />
          </div>
          )}
        </div>
      </section>
      )}

      {/*
        Os blocos entre este comentário e o de "confrontos decididos" leem
        `dim_partida` — duração, jogador, herói —, e ela só existe para Dota 2:
        a OpenDota é a única fonte com esse grão. Para os outros treze esportes
        eles rendiam a tela inteira zerada, então dão lugar à estatística do
        calendário, que é o que esses jogos têm.
      */}
      {emResultados && (
        <Consulta estado={resumoConfrontos} altura={160}>
          {(dados) => <EstatisticasConfrontos dados={dados} />}
        </Consulta>
      )}

      {/* ==================== PRÓXIMAS PARTIDAS ==================== */}
      {!emResultados && (
        <Painel
          icone="event_upcoming"
          titulo={t("partidas.proximasPartidas.titulo")}
          descricao={t("partidas.proximasPartidas.descricao")}
          meta={
            <div className="flex flex-wrap items-center gap-space-sm">
              <SeletorModoConfrontos modo={modoAgenda} aoMudar={setModoAgenda} />
              {agenda.isFetching ? (
                <span className="font-label-caps text-label-caps uppercase tracking-widest text-primary">
                  {t("partidas.proximasPartidas.atualizando")}
                </span>
              ) : (
                <Selo cor="primario">{t("partidas.proximasPartidas.marcadas", { contagem: agenda.data?.length ?? 0 })}</Selo>
              )}
            </div>
          }
        >
          <Consulta
            estado={agenda}
            altura={160}
            vazio={t("partidas.proximasPartidas.vazio")}
          >
            {(lista: PartidaAgendada[]) => (
              <VisaoConfrontos confrontos={lista} modo={modoAgenda} />
            )}
          </Consulta>
        </Painel>
      )}

      {/* Aba Partidas num jogo sem `dim_partida`: o histórico com detalhe não
          existe, mas as próximas partidas acima e a aba Resultados sim. */}
      {!emResultados && !temPartidaDetalhada && (
        <p className="rounded-xl bg-surface-container-low/90 px-space-lg py-space-base font-body-md text-body-md text-on-surface-variant shadow-lg">
          {t("partidas.semDetalhePorJogadorPrefixo")}
          <strong className="text-on-surface">{t("partidas.cabecalho.resultados")}</strong>
          {t("partidas.semDetalhePorJogadorSufixo")}
        </p>
      )}

      {/* ==================== QUATRO KPIS ==================== */}
      {!emResultados && temPartidaDetalhada && (
      <Consulta estado={resumo} altura={160}>
        {(dados: ResumoPartidas) => {
          const winrateRadiant = (dados.winrate_radiant ?? 50) / 100;
          const serie = (porDia.data ?? []).map((ponto) => ponto.partidas);

          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta={t("partidas.kpis.partidasAnalisadas")}
                canto={t("partidas.kpis.starSchema")}
                valor={fmtNumero(dados.partidas)}
                valorNumerico={dados.partidas}
                formatarValor={fmtNumero}
                rotulo={t("partidas.kpis.partidasProfissionais")}
                acento="primaria"
                notaVariacao={`${fmtDataCurta(dados.primeira_partida)} — ${fmtDataCurta(dados.ultima_partida)}`}
              >
                <Sparkline valores={serie} />
              </KpiHud>

              <KpiHud
                etiqueta={t("partidas.kpis.duracaoMediana")}
                canto={t("partidas.kpis.mediana")}
                valor={fmtDuracao(dados.duracao_mediana_segundos)}
                valorNumerico={dados.duracao_mediana_segundos}
                formatarValor={fmtDuracao}
                rotulo={t("partidas.kpis.metadeAbaixo")}
                acento="secundaria"
                notaVariacao={t("partidas.kpis.mediaDe", { tempo: fmtDuracao(dados.duracao_media_segundos) })}
              >
                <div className="mt-space-md">
                  <BarraFina
                    largura={
                      dados.duracao_media_segundos && dados.duracao_mediana_segundos
                        ? Math.min(
                            100,
                            (dados.duracao_mediana_segundos /
                              dados.duracao_media_segundos) *
                              100,
                          )
                        : 0
                    }
                    className="bg-gradient-to-r from-secondary-container to-secondary"
                    altura="h-2"
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta={t("partidas.kpis.radiantVsDire")}
                canto={t("partidas.kpis.equilibrio")}
                valor={fmtPercentual(dados.winrate_radiant)}
                valorNumerico={dados.winrate_radiant}
                formatarValor={(v) => fmtPercentual(v)}
                rotulo={t("partidas.kpis.vitoriasRadiant")}
                acento="terciaria"
              >
                <div className="mt-space-md">
                  <BarraSegmentada
                    fracaoA={winrateRadiant}
                    legendaEsquerda={t("partidas.kpis.radiantDirePct", {
                      radiant: fmtPercentual(dados.winrate_radiant, 1),
                      dire: fmtPercentual(100 - (dados.winrate_radiant ?? 50), 1),
                    })}
                    legendaDireita={
                      Math.abs((dados.winrate_radiant ?? 50) - 50) < 5
                        ? t("partidas.kpis.equilibrado")
                        : t("partidas.kpis.desvio")
                    }
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta={t("partidas.kpis.jogadoresMonitorados")}
                canto={t("partidas.kpis.herois", { contagem: fmtNumero(dados.personagens_usados) })}
                valor={fmtNumero(dados.jogadores_distintos)}
                valorNumerico={dados.jogadores_distintos}
                formatarValor={fmtNumero}
                rotulo={t("partidas.kpis.jogadoresDistintos")}
                acento="primaria"
                notaVariacao={t("partidas.kpis.fatosAnonimos")}
              />
            </section>
          );
        }}
      </Consulta>
      )}

      {/* ==================== DOIS PAINEIS ==================== */}
      {!emResultados && temPartidaDetalhada && (
      <section className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        <Painel
          icone="bar_chart"
          titulo={t("partidas.distribuicao.titulo")}
          descricao={t("partidas.distribuicao.descricao")}
        >
          <Consulta estado={resumo}>
            {(dados: ResumoPartidas) => (
              <HistogramaNeon
                faixas={dados.distribuicao_duracao.map((faixa) => ({
                  rotulo: faixa.rotulo,
                  valor: faixa.partidas,
                }))}
                formatarValor={(valor) => t("partidas.distribuicao.partidas", { contagem: fmtNumero(valor) })}
                rodapeEsquerda={
                  <>
                    {t("partidas.distribuicao.mediana")}{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {fmtDuracao(dados.duracao_mediana_segundos)}
                    </strong>
                  </>
                }
                rodapeDireita={t("partidas.distribuicao.partidas", { contagem: fmtNumero(dados.partidas) })}
              />
            )}
          </Consulta>
        </Painel>

        <Painel
          icone="show_chart"
          titulo={t("partidas.ingestao.titulo")}
          descricao={t("partidas.ingestao.descricao")}
        >
          <Consulta estado={porDia}>
            {(dados: PartidasPorDia[]) => (
              <AreaNeon
                pontos={dados.map((ponto) => ({
                  rotulo: fmtDataCurta(ponto.data),
                  valor: ponto.partidas,
                  detalhe: t("partidas.distribuicao.partidas", { contagem: fmtNumero(ponto.partidas) }),
                }))}
                formatarValor={(valor) => fmtCurto(valor)}
                rodapeEsquerda={
                  <>
                    {t("partidas.ingestao.picoDiario")}{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {t("partidas.ingestao.picoPartidas", {
                        contagem: fmtNumero(Math.max(...dados.map((p) => p.partidas), 0)),
                      })}
                    </strong>
                  </>
                }
                rodapeDireita={t("partidas.ingestao.diasComColeta", { contagem: dados.length })}
              />
            )}
          </Consulta>
        </Painel>
      </section>
      )}

      {/* ==================== CONFRONTOS DECIDIDOS ==================== */}
      {emResultados && (
      <Painel
        icone="scoreboard"
        titulo={t("partidas.confrontosDecididos.titulo")}
        descricao={t("partidas.confrontosDecididos.descricao")}
        meta={
          <div className="flex flex-wrap items-center gap-space-sm">
            <SeletorModoConfrontos modo={modoConfrontos} aoMudar={setModoConfrontos} />
            <Selo>
              {t("partidas.confrontosDecididos.emTela", {
                contagem: Math.min(confrontos.data?.length ?? 0, porPaginaConfrontos),
              })}
            </Selo>
          </div>
        }
      >
        <Consulta
          estado={confrontos}
          altura={200}
          vazio={t("partidas.confrontosDecididos.vazio")}
        >
          {(lista) => {
            const naPagina = lista.slice(0, porPaginaConfrontos);
            const temProxima = lista.length > porPaginaConfrontos;
            return (
              <>
                <VisaoConfrontos confrontos={naPagina} modo={modoConfrontos} />
                <Paginacao
                  pagina={paginaConfrontos}
                  // Sem total no endpoint: a página cheia + 1 é o único sinal
                  // de que pode haver mais.
                  totalPaginas={temProxima ? paginaConfrontos + 1 : paginaConfrontos}
                  porPagina={porPaginaConfrontos}
                  opcoesPorPagina={[5, 15, 25, 50]}
                  aoMudarPagina={setPaginaConfrontos}
                  aoMudarPorPagina={setPorPaginaConfrontos}
                  resumo={t("partidas.confrontosDecididos.confrontosNestaPagina", { contagem: naPagina.length })}
                />
              </>
            );
          }}
        </Consulta>
      </Painel>
      )}

      {/* ==================== TABELA DENSA ==================== */}
      {/* Por PARTIDA: sem `dim_partida` ela nao tem o que listar. */}
      {!emResultados && temPartidaDetalhada && (
      <Painel
        icone="history"
        titulo={t("partidas.historico.titulo")}
        descricao={
          modoHistorico === "lista"
            ? t("partidas.historico.descricaoLista")
            : t("partidas.historico.descricaoCartao")
        }
        meta={
          <div className="flex flex-wrap items-center gap-space-sm">
            <SeletorModoConfrontos modo={modoHistorico} aoMudar={setModoHistorico} />
            <Selo cor="primario">{t("partidas.historico.emTela", { contagem: visiveis.length })}</Selo>
          </div>
        }
      >
        <Consulta estado={partidas} vazio={t("partidas.historico.vazio")}>
          {() =>
            visiveis.length === 0 ? (
              <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                {t("partidas.historico.nenhumaNaPagina")}
              </p>
            ) : modoHistorico !== "lista" ? (
              <VisaoConfrontos
                confrontos={visiveis}
                modo={modoHistorico}
                coercao={paraCartaoPartida}
                aoClicarItem={(c) =>
                  c.id_rota && navegar(`/partidas/${c.id_rota}`)
                }
              />
            ) : (
              <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                      <th className="px-space-md py-space-sm">{t("partidas.historico.colunas.matchId")}</th>
                      <th className="px-space-md py-space-sm">{t("partidas.historico.colunas.times")}</th>
                      <th className="px-space-md py-space-sm">{t("partidas.historico.colunas.liga")}</th>
                      <th className="px-space-md py-space-sm">{t("partidas.historico.colunas.modo")}</th>
                      <th className="px-space-md py-space-sm">{t("partidas.historico.colunas.duracao")}</th>
                      <th className="px-space-md py-space-sm">{t("partidas.historico.colunas.vencedor")}</th>
                      <th className="px-space-md py-space-sm">{t("partidas.historico.colunas.patch")}</th>
                      <th className="px-space-md py-space-sm text-right">{t("partidas.historico.colunas.disputada")}</th>
                    </tr>
                  </thead>

                  <tbody className="font-body-md text-body-sm">
                    {visiveis.map((partida: Partida, indice) => (
                      <tr
                        key={partida.id_partida}
                        onClick={() => navegar(`/partidas/${partida.id_partida}`)}
                        className={`cursor-pointer transition-colors hover:bg-surface-container-high/60 ${
                          indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                        }`}
                      >
                        <td className="px-space-md py-space-sm">
                          <div className="flex items-center gap-space-xs">
                            <span
                              className="h-2 w-2 shrink-0 rounded-full"
                              style={{ background: corDoJogo(jogo) }}
                              aria-hidden
                            />
                            <span className="font-title-code text-title-code text-on-surface">
                              #{partida.id_externo}
                            </span>
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm">
                          <TimesDaPartida partida={partida} />
                        </td>

                        <td className="px-space-md py-space-sm text-on-surface-variant">
                          {partida.liga_nome ?? "—"}
                        </td>

                        <td className="px-space-md py-space-sm">
                          <span className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-secondary">
                            {partida.modo ?? "—"}
                          </span>
                        </td>

                        <td className="px-space-md py-space-sm font-title-code text-title-code text-on-surface">
                          {fmtDuracao(partida.duracao_segundos)}
                        </td>

                        <td className="px-space-md py-space-sm">
                          <LadoVencedor vencedor={partida.vencedor} />
                        </td>

                        <td className="px-space-md py-space-sm font-title-code text-title-code text-outline">
                          {partida.patch ?? "—"}
                        </td>

                        <td
                          className="px-space-md py-space-sm text-right font-title-code text-title-code text-on-surface-variant"
                          title={fmtDataHora(partida.data_inicio)}
                        >
                          {fmtRelativo(partida.data_inicio)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Consulta>

        <Paginacao
          pagina={pagina}
          totalPaginas={totalPaginas}
          porPagina={porPagina}
          opcoesPorPagina={[5, 15, 25, 50]}
          aoMudarPagina={setPagina}
          aoMudarPorPagina={setPorPagina}
          resumo={
            <>
              {t("partidas.historico.exibindo", { visiveis: visiveis.length, total: daPagina.length })}
              {modo || busca ? t("partidas.historico.recorteLocal") : ""}
            </>
          }
        />

        <div className="flex flex-wrap items-center justify-between gap-space-sm border-t border-outline-variant/30 pt-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span>
            {t("partidas.historico.pipeline")}{" "}
            <span className={online ? "text-tertiary" : "text-error"}>
              {online ? t("partidas.historico.ativo") : t("partidas.historico.semContato")}
            </span>
          </span>
          <span
            style={{ color: PALETA_POLOS.neutro }}
            className="font-title-code text-title-code"
          >
            {t("partidas.historico.ingest", { contagem: fmtNumero(resumo.data?.partidas) })}
          </span>
        </div>
      </Painel>
      )}
    </>
  );
}
