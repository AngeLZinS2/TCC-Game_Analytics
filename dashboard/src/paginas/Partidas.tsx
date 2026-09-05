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

import {
  useFiltrosPartidas,
  useConfrontos,
  useResumoConfrontos,
  usePartidas,
  usePartidasPorDia,
  useResumoPartidas,
  useSaude,
} from "../api/consultas";
import type { Partida, PartidasPorDia, ResumoPartidas } from "../api/tipos";
import { Botao, Consulta, Icone, Selo } from "../componentes/base";
import { AreaNeon } from "../componentes/graficos/AreaNeon";
import { HistogramaNeon } from "../componentes/graficos/HistogramaNeon";
import {
  BarraFina,
  BarraSegmentada,
  CAMPO,
  KpiHud,
  Paginacao,
  Painel,
  Sparkline,
} from "../componentes/hud";
import { EstatisticasConfrontos } from "../componentes/EstatisticasConfrontos";
import { ListaConfrontos } from "../componentes/ListaConfrontos";
import { SeletorDeJogo } from "../componentes/SeletorDeJogo";
import { useJogoAtual } from "../layout/JogoAtual";
import { corDoJogo, PALETA_POLOS } from "../tema";
import {
  fmtCurto,
  fmtDataCurta,
  fmtDataHora,
  fmtDuracao,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
} from "../utilitarios/formatos";

/** Janelas do seletor de periodo, em dias. `null` = tudo. */
const PERIODOS = [
  { valor: 7, rotulo: "7D" },
  { valor: 30, rotulo: "30D" },
  { valor: 90, rotulo: "90D" },
  { valor: null, rotulo: "Tudo" },
] as const;

/** O lado vencedor escrito, com a cor que o placar usa. */
export function LadoVencedor({ vencedor }: { vencedor: string | null }) {
  if (vencedor === "radiant") return <Selo cor="positivo">Radiant</Selo>;
  if (vencedor === "dire") return <Selo cor="negativo">Dire</Selo>;
  return <span className="text-outline">—</span>;
}

export function PartidasPagina() {
  const navegar = useNavigate();
  const { jogo } = useJogoAtual();

  const [liga, setLiga] = useState("");
  const [modo, setModo] = useState("");
  const [periodo, setPeriodo] = useState<number | null>(null);
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(1);
  const [paginaConfrontos, setPaginaConfrontos] = useState(1);
  const [porPagina, setPorPagina] = useState(25);

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
  const confrontos = useConfrontos(jogo, paginaConfrontos);
  const resumoConfrontos = useResumoConfrontos(jogo);
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
  useEffect(() => setPaginaConfrontos(1), [jogo]);
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
            <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-primary drop-shadow-[0_0_12px_rgba(0,229,255,0.4)]">
              Partidas
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
                    online ? "bg-tertiary-container shadow-[0_0_8px_#16ef7a]" : "bg-error"
                  }`}
                />
              </span>
              <span
                className={`font-badge-status text-badge-status uppercase tracking-widest ${
                  online ? "text-tertiary" : "text-error"
                }`}
              >
                {online ? "Feed ativo" : "Sem contato"}
              </span>
            </div>
            <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
              Match Analytics // Deck 02
            </span>
          </div>

          {/*
            A frase do star schema descreve o que a OpenDota entrega, e ela só
            cobre Dota 2. Deixá-la fixa afirmaria, para os outros treze
            esportes, um grão de dado que a tela não tem — a mesma classe de
            erro de dizer a fonte errada num painel de procedência.
          */}
          <p className="font-body-sm text-body-sm text-on-surface-variant">
            {temPartidaDetalhada
              ? "Star schema de partidas profissionais. Uma partida vira dez linhas de fato — uma por jogador — e as dimensões são compartilhadas entre os jogos."
              : "Calendário profissional: quem jogou, quando e o placar da série. Este jogo não tem partida com detalhe por jogador — a fonte publica o resultado do confronto, não o que aconteceu dentro dele."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-space-sm">
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

          <Botao
            icone="refresh"
            aoClicar={() => partidas.refetch()}
            desabilitado={partidas.isFetching}
          >
            {partidas.isFetching ? "Atualizando…" : "Atualizar telemetria"}
          </Botao>
        </div>
      </section>

      {/* ==================== BARRA DE FILTROS ==================== */}
      <section className="space-y-space-md rounded-xl bg-surface-container-low/90 p-space-base shadow-lg">
        <div className="flex flex-wrap items-center gap-space-sm">
          {/*
            O padrão do seletor exige `partidas > 0`, e vale para Heróis e
            Jogadores — eles leem o fato por jogador, que só a OpenDota
            entrega. Esta tela não: desde que ela mostra confrontos com placar
            do calendário, um jogo com agenda tem conteúdo aqui. Com o gate
            padrão, League of Legends aparecia como "nada coletado ainda"
            tendo 67 confrontos e 61 equipes no banco.
          */}
          <SeletorDeJogo disponivel={(j) => j.partidas > 0 || j.agenda > 0} />
          {/*
            Torneio, modo e busca filtram a tabela POR PARTIDA. Sem
            `dim_partida` ela não é renderizada, e um filtro que não filtra
            nada é pior que filtro nenhum: parece que o recorte foi aplicado.
          */}
          {temPartidaDetalhada && (
          <label className="flex items-center gap-space-xs">
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Torneio
            </span>
            <select
              value={liga}
              onChange={(evento) => setLiga(evento.target.value)}
              className={CAMPO}
            >
              <option value="">Todos os torneios</option>
              {filtros.data?.ligas.map((nome) => (
                <option key={nome} value={nome}>
                  {nome}
                </option>
              ))}
            </select>
          </label>
          )}

          {temPartidaDetalhada && (
          <label className="flex items-center gap-space-xs">
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Modo
            </span>
            <select
              value={modo}
              onChange={(evento) => setModo(evento.target.value)}
              className={CAMPO}
            >
              <option value="">Todos os modos</option>
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
              placeholder="Buscar por torneio ou ID da partida…"
              aria-label="Buscar partida"
              className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-space-sm font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
            />
          </div>
          )}
        </div>
      </section>

      {/*
        Os blocos entre este comentário e o de "confrontos decididos" leem
        `dim_partida` — duração, jogador, herói —, e ela só existe para Dota 2:
        a OpenDota é a única fonte com esse grão. Para os outros treze esportes
        eles rendiam a tela inteira zerada, então dão lugar à estatística do
        calendário, que é o que esses jogos têm.
      */}
      {!temPartidaDetalhada && (
        <Consulta estado={resumoConfrontos} altura={160}>
          {(dados) => <EstatisticasConfrontos dados={dados} />}
        </Consulta>
      )}

      {/* ==================== QUATRO KPIS ==================== */}
      {temPartidaDetalhada && (
      <Consulta estado={resumo} altura={160}>
        {(dados: ResumoPartidas) => {
          const winrateRadiant = (dados.winrate_radiant ?? 50) / 100;
          const serie = (porDia.data ?? []).map((ponto) => ponto.partidas);

          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta="Partidas analisadas"
                canto="STAR SCHEMA"
                valor={fmtNumero(dados.partidas)}
                valorNumerico={dados.partidas}
                formatarValor={fmtNumero}
                rotulo="Partidas profissionais"
                acento="primaria"
                notaVariacao={`${fmtDataCurta(dados.primeira_partida)} — ${fmtDataCurta(dados.ultima_partida)}`}
              >
                <Sparkline valores={serie} />
              </KpiHud>

              <KpiHud
                etiqueta="Duração mediana"
                canto="MEDIANA"
                valor={fmtDuracao(dados.duracao_mediana_segundos)}
                valorNumerico={dados.duracao_mediana_segundos}
                formatarValor={fmtDuracao}
                rotulo="Metade das partidas abaixo disso"
                acento="secundaria"
                notaVariacao={`média de ${fmtDuracao(dados.duracao_media_segundos)}`}
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
                etiqueta="Radiant vs Dire"
                canto="EQUILÍBRIO"
                valor={fmtPercentual(dados.winrate_radiant)}
                valorNumerico={dados.winrate_radiant}
                formatarValor={(v) => fmtPercentual(v)}
                rotulo="Vitórias do lado Radiant"
                acento="terciaria"
              >
                <div className="mt-space-md">
                  <BarraSegmentada
                    fracaoA={winrateRadiant}
                    legendaEsquerda={
                      <>
                        Radiant {fmtPercentual(dados.winrate_radiant, 1)} · Dire{" "}
                        {fmtPercentual(100 - (dados.winrate_radiant ?? 50), 1)}
                      </>
                    }
                    legendaDireita={
                      Math.abs((dados.winrate_radiant ?? 50) - 50) < 5
                        ? "EQUILIBRADO"
                        : "DESVIO"
                    }
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta="Jogadores monitorados"
                canto={`${fmtNumero(dados.personagens_usados)} HERÓIS`}
                valor={fmtNumero(dados.jogadores_distintos)}
                valorNumerico={dados.jogadores_distintos}
                formatarValor={fmtNumero}
                rotulo="Jogadores distintos no recorte"
                acento="primaria"
                notaVariacao="fatos anônimos não contam"
              />
            </section>
          );
        }}
      </Consulta>
      )}

      {/* ==================== DOIS PAINEIS ==================== */}
      {temPartidaDetalhada && (
      <section className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        <Painel
          icone="bar_chart"
          titulo="Distribuição de duração das partidas"
          descricao="Faixas de 10 minutos. A coluna destacada é a moda."
        >
          <Consulta estado={resumo}>
            {(dados: ResumoPartidas) => (
              <HistogramaNeon
                faixas={dados.distribuicao_duracao.map((faixa) => ({
                  rotulo: faixa.rotulo,
                  valor: faixa.partidas,
                }))}
                formatarValor={(valor) => `${fmtNumero(valor)} partidas`}
                rodapeEsquerda={
                  <>
                    Mediana:{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {fmtDuracao(dados.duracao_mediana_segundos)}
                    </strong>
                  </>
                }
                rodapeDireita={`${fmtNumero(dados.partidas)} partidas`}
              />
            )}
          </Consulta>
        </Painel>

        <Painel
          icone="show_chart"
          titulo="Volume de ingestão de partidas"
          descricao="Data de disputa da partida, não a da coleta."
        >
          <Consulta estado={porDia}>
            {(dados: PartidasPorDia[]) => (
              <AreaNeon
                pontos={dados.map((ponto) => ({
                  rotulo: fmtDataCurta(ponto.data),
                  valor: ponto.partidas,
                  detalhe: `${fmtNumero(ponto.partidas)} partidas`,
                }))}
                formatarValor={(valor) => fmtCurto(valor)}
                rodapeEsquerda={
                  <>
                    Pico diário:{" "}
                    <strong className="font-title-code text-title-code text-on-surface">
                      {fmtNumero(Math.max(...dados.map((p) => p.partidas), 0))} partidas
                    </strong>
                  </>
                }
                rodapeDireita={`${dados.length} dias com coleta`}
              />
            )}
          </Consulta>
        </Painel>
      </section>
      )}

      {/* ==================== CONFRONTOS DECIDIDOS ==================== */}
      <Painel
        icone="scoreboard"
        titulo="Confrontos com resultado"
        descricao="Placar da série, do calendário — Liquipedia e OP.GG. Grão diferente da tabela abaixo: um 3x1 é um confronto, não três partidas."
        meta={
          <Selo>{confrontos.data?.length ?? 0} em tela</Selo>
        }
      >
        <Consulta
          estado={confrontos}
          altura={200}
          vazio="Nenhum confronto decidido no calendário deste jogo."
        >
          {(lista) => (
            <>
              <ListaConfrontos confrontos={lista} />
              <div className="flex items-center justify-between gap-space-sm pt-space-sm">
                <Botao
                  icone="chevron_left"
                  aoClicar={() => setPaginaConfrontos((p) => Math.max(1, p - 1))}
                  desabilitado={paginaConfrontos === 1}
                >
                  Anteriores
                </Botao>
                <span className="font-badge-status text-badge-status uppercase tracking-wider text-outline">
                  página {paginaConfrontos}
                </span>
                <Botao
                  icone="chevron_right"
                  aoClicar={() => setPaginaConfrontos((p) => p + 1)}
                  // Sem total no endpoint: a página cheia é o único sinal de
                  // que pode haver mais. Melhor que inventar uma contagem.
                  desabilitado={lista.length < 20}
                >
                  Seguintes
                </Botao>
              </div>
            </>
          )}
        </Consulta>
      </Painel>

      {/* ==================== TABELA DENSA ==================== */}
      {/* Por PARTIDA: sem `dim_partida` ela nao tem o que listar, e o painel
          de confrontos acima ja e a lista deste jogo. */}
      {temPartidaDetalhada && (
      <Painel
        icone="history"
        titulo="Histórico operacional de partidas"
        descricao="Clique em uma linha para ver o placar completo."
        meta={<Selo cor="primario">{visiveis.length} em tela</Selo>}
      >
        <Consulta estado={partidas} vazio="Nenhuma partida bate com esse filtro.">
          {() =>
            visiveis.length === 0 ? (
              <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                Nenhuma partida desta página bate com o modo ou a busca.
              </p>
            ) : (
              <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                      <th className="px-space-md py-space-sm">Match ID</th>
                      <th className="px-space-md py-space-sm">Liga / Torneio</th>
                      <th className="px-space-md py-space-sm">Modo</th>
                      <th className="px-space-md py-space-sm">Duração</th>
                      <th className="px-space-md py-space-sm">Vencedor</th>
                      <th className="px-space-md py-space-sm">Patch</th>
                      <th className="px-space-md py-space-sm text-right">Disputada</th>
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
          aoMudarPagina={setPagina}
          aoMudarPorPagina={setPorPagina}
          resumo={
            <>
              Exibindo {visiveis.length} de {daPagina.length} nesta página
              {modo || busca ? " (recorte local)" : ""}
            </>
          }
        />

        <div className="flex flex-wrap items-center justify-between gap-space-sm border-t border-outline-variant/30 pt-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span>
            Pipeline:{" "}
            <span className={online ? "text-tertiary" : "text-error"}>
              {online ? "ativo" : "sem contato"}
            </span>
          </span>
          <span
            style={{ color: PALETA_POLOS.neutro }}
            className="font-title-code text-title-code"
          >
            OpenDota ingest · {fmtNumero(resumo.data?.partidas)} partidas
          </span>
        </div>
      </Painel>
      )}
    </>
  );
}
