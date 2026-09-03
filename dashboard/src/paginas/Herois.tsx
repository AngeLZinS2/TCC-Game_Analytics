/**
 * Herois: winrate contra a linha de 50% e as medias por partida.
 *
 * Porte da tela "Heróis" do Stitch: barra de filtros, a distribuicao de
 * winrate em torno de um eixo central e a matriz de telemetria.
 *
 * A forma divergente e a leitura da tela: winrate nao e magnitude, e
 * polaridade - a pergunta e de que lado dos 50% o heroi caiu. Por isso o eixo
 * fica no meio e as barras crescem para os dois lados, em vez de um ranking
 * comum que so responderia "quem tem mais".
 */

import { useMemo, useState } from "react";

import { useJogosDisponiveis, usePersonagens, useSaude } from "../api/consultas";
import type { ResumoPersonagem } from "../api/tipos";
import { Botao, Consulta, Icone, Selo } from "../componentes/base";
import { RetratoHeroi } from "../componentes/RetratoHeroi";
import {
  CAMPO,
  ChipContagem,
  KpiHud,
  Painel,
  Pilula,
  Segmentos,
} from "../componentes/hud";
import { useJogoAtual } from "../layout/JogoAtual";
import { corDoJogo, PALETA_POLOS } from "../tema";
import { fmtDecimal, fmtNumero, fmtPercentual } from "../utilitarios/formatos";

const NO_GRAFICO = 10;

const ORDENACOES = [
  { valor: "winrate", rotulo: "Winrate", icone: "trending_up" },
  { valor: "partidas", rotulo: "Volume", icone: "insights" },
  { valor: "kda", rotulo: "KDA", icone: "swords" },
] as const;

type Ordenacao = (typeof ORDENACOES)[number]["valor"];

/**
 * Metade do topo e metade do fundo do ranking de winrate.
 *
 * Mostrar so os mais vitoriosos encheria um lado so do eixo e desperdicaria a
 * forma - o que interessa e ver os dois extremos em torno dos 50%.
 */
function extremos(itens: ResumoPersonagem[], quantidade: number): ResumoPersonagem[] {
  if (itens.length <= quantidade) return itens;
  const metade = Math.floor(quantidade / 2);
  return [...itens.slice(0, quantidade - metade), ...itens.slice(-metade)];
}

/** Uma linha do grafico divergente: nome + retrato de um lado, barra do outro. */
function LinhaDivergente({
  heroi,
  limite,
}: {
  heroi: ResumoPersonagem;
  /** Maior desvio absoluto do conjunto, para a escala ser a mesma dos dois lados. */
  limite: number;
}) {
  const desvio = heroi.winrate - 50;
  const positivo = desvio >= 0;
  const largura = `${Math.max(2, (Math.abs(desvio) / limite) * 100)}%`;

  const identidade = (
    <>
      <span className="mr-2 truncate font-body-sm text-body-sm text-on-surface transition-colors group-hover:text-primary">
        {heroi.nome}
      </span>
      <RetratoHeroi nome={heroi.nome} nomeInterno={heroi.nome_interno} />
    </>
  );

  const barra = (
    <div
      className="relative flex h-4 items-center transition-all duration-300"
      style={{
        width: largura,
        background: positivo ? PALETA_POLOS.positivo : PALETA_POLOS.negativo,
        boxShadow: `0 0 10px ${positivo ? "rgba(22,239,122,0.4)" : "rgba(255,138,147,0.4)"}`,
      }}
    >
      <span
        className={`absolute font-title-code text-[12px] ${positivo ? "-right-12" : "-left-12"}`}
        style={{ color: positivo ? PALETA_POLOS.positivo : PALETA_POLOS.negativo }}
      >
        {fmtPercentual(heroi.winrate)}
      </span>
    </div>
  );

  return (
    <div
      className="group flex h-8 w-full items-center"
      title={`${heroi.nome}: ${fmtPercentual(heroi.winrate)} em ${heroi.partidas} partidas`}
    >
      {positivo ? (
        <>
          <div className="flex w-1/2 items-center justify-end pr-space-md">{identidade}</div>
          <div className="flex w-1/2 items-center pl-1">{barra}</div>
        </>
      ) : (
        <>
          {/* Espelhado: a barra cresce para a esquerda a partir do eixo. */}
          <div className="flex w-1/2 items-center justify-end pr-1">{barra}</div>
          <div className="flex w-1/2 items-center pl-space-md">
            <RetratoHeroi nome={heroi.nome} nomeInterno={heroi.nome_interno} />
            <span className="ml-2 truncate font-body-sm text-body-sm text-on-surface transition-colors group-hover:text-primary">
              {heroi.nome}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

export function HeroisPagina() {
  const { jogo, definirJogo } = useJogoAtual();
  const [minPartidas, setMinPartidas] = useState(5);
  const [ordenacao, setOrdenacao] = useState<Ordenacao>("winrate");
  const [busca, setBusca] = useState("");

  const personagens = usePersonagens({
    jogo,
    min_partidas: minPartidas,
    ordenar_por: "winrate",
    limite: 200,
  });
  const jogosDisponiveis = useJogosDisponiveis();
  const saude = useSaude();

  const online = saude.data?.status === "ok";

  const filtrados = useMemo(
    () =>
      (personagens.data ?? []).filter((heroi) =>
        busca ? heroi.nome.toLowerCase().includes(busca.toLowerCase()) : true,
      ),
    [personagens.data, busca],
  );

  const tabela = useMemo(() => {
    const chave = (h: ResumoPersonagem) =>
      ordenacao === "partidas"
        ? h.partidas
        : ordenacao === "kda"
          ? (h.kda_medio ?? 0)
          : h.winrate;
    return [...filtrados].sort((a, b) => chave(b) - chave(a));
  }, [filtrados, ordenacao]);

  // A lista ja chega ordenada por winrate, entao o corte para o grafico e nas
  // duas pontas dela - nao da ordenacao escolhida para a tabela.
  const noGrafico = extremos(filtrados, NO_GRAFICO);
  const limite = Math.max(...noGrafico.map((h) => Math.abs(h.winrate - 50)), 1);

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-space-xs">
          <div className="flex flex-wrap items-center gap-space-sm">
            <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-primary drop-shadow-[0_0_12px_rgba(0,229,255,0.4)]">
              Heróis
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
                {online ? "Meta ativa" : "Sem contato"}
              </span>
            </div>
            <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
              Meta Analytics // Deck 03
            </span>
          </div>

          <p className="font-body-sm text-body-sm text-on-surface-variant">
            Agregação do fato de partidas por personagem. O corte de partidas mínimas
            existe porque um herói com duas partidas e duas vitórias tem 100% de winrate e
            nenhum significado estatístico — sem ele, a cauda curta lidera o ranking.
          </p>
        </div>

        <Botao
          icone="refresh"
          aoClicar={() => personagens.refetch()}
          desabilitado={personagens.isFetching}
        >
          {personagens.isFetching ? "Atualizando…" : "Atualizar meta"}
        </Botao>
      </section>

      {/* ==================== FILTROS ==================== */}
      <section className="flex flex-wrap items-center gap-space-md rounded-xl bg-surface-container-low/90 p-space-base shadow-lg">
        <div className="flex flex-wrap items-center gap-space-xs">
          {jogosDisponiveis.data?.map((disponivel) => (
            <ChipContagem
              key={disponivel.codigo}
              ativo={disponivel.codigo === jogo}
              contagem={disponivel.partidas}
              cor={corDoJogo(disponivel.codigo)}
              aoClicar={() => disponivel.partidas > 0 && definirJogo(disponivel.codigo)}
            >
              {disponivel.nome}
            </ChipContagem>
          ))}
        </div>

        <label className="flex items-center gap-space-xs">
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            Mín. partidas
          </span>
          <select
            value={minPartidas}
            onChange={(evento) => setMinPartidas(Number(evento.target.value))}
            className={CAMPO}
          >
            {[1, 3, 5, 10, 15, 20].map((valor) => (
              <option key={valor} value={valor}>
                {valor}
              </option>
            ))}
          </select>
        </label>

        <div className="relative min-w-[14rem] flex-1">
          <Icone
            nome="manage_search"
            className="absolute left-space-sm top-1/2 -translate-y-1/2 text-[20px] text-primary-container"
          />
          <input
            type="search"
            value={busca}
            onChange={(evento) => setBusca(evento.target.value)}
            placeholder="Buscar herói…"
            aria-label="Buscar herói"
            className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-space-sm font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
          />
        </div>
      </section>

      {/* ==================== KPIS ==================== */}
      <Consulta
        estado={personagens}
        altura={160}
        vazio="Nenhum herói atinge esse mínimo de partidas."
      >
        {(lista: ResumoPersonagem[]) => {
          const acima = lista.filter((h) => h.winrate > 50).length;
          const escolhas = lista.reduce((t, h) => t + h.partidas, 0);

          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta="Heróis no recorte"
                canto={`MÍN. ${minPartidas}`}
                valor={fmtNumero(lista.length)}
                rotulo="Na dimensão de personagem"
                acento="primaria"
                notaVariacao={`${fmtNumero(escolhas)} escolhas somadas`}
              >
                <Segmentos acesos={lista.length ? 6 : 0} acento="primaria" />
              </KpiHud>

              <KpiHud
                etiqueta="Acima dos 50%"
                canto="POLARIDADE"
                valor={fmtNumero(acima)}
                rotulo="Heróis com mais vitórias que derrotas"
                acento="terciaria"
                notaVariacao={`${fmtNumero(lista.length - acima)} abaixo ou na linha`}
              >
                <div className="mt-space-md flex h-2 w-full overflow-hidden rounded-full bg-surface-container-highest">
                  <div
                    className="h-full"
                    style={{
                      width: `${lista.length ? (acima / lista.length) * 100 : 0}%`,
                      background: PALETA_POLOS.positivo,
                    }}
                  />
                  <div
                    className="h-full flex-1"
                    style={{ background: PALETA_POLOS.negativo }}
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta="Maior winrate"
                canto="TOPO"
                valor={lista.length ? fmtPercentual(lista[0].winrate) : "—"}
                rotulo={lista.length ? lista[0].nome : "sem dados"}
                acento="secundaria"
                notaVariacao={
                  lista.length ? `${fmtNumero(lista[0].partidas)} partidas` : undefined
                }
              />

              <KpiHud
                etiqueta="Menor winrate"
                canto="CAUDA"
                valor={lista.length ? fmtPercentual(lista.at(-1)!.winrate) : "—"}
                rotulo={lista.length ? lista.at(-1)!.nome : "sem dados"}
                acento="primaria"
                notaVariacao={
                  lista.length
                    ? `${fmtNumero(lista.at(-1)!.partidas)} partidas`
                    : undefined
                }
              />
            </section>
          );
        }}
      </Consulta>

      {/* ==================== DISTRIBUICAO DIVERGENTE ==================== */}
      <Painel
        icone="compare_arrows"
        titulo={`Distribuição de winrate // top ${NO_GRAFICO} heróis`}
        descricao="Distância até os 50%: à direita, mais vitórias que derrotas; à esquerda, o contrário."
        meta={
          <span className="font-badge-status text-badge-status tracking-widest text-outline">
            LOC: {jogo.toUpperCase()}-META // H-01
          </span>
        }
      >
        <Consulta estado={personagens} vazio="Nenhum herói atinge esse mínimo de partidas.">
          {() =>
            noGrafico.length === 0 ? (
              <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                Nenhum herói bate com a busca.
              </p>
            ) : (
              <div className="relative w-full pt-space-lg">
                {/* Eixo central em 50%, com o rotulo por cima da linha. */}
                <div
                  className="absolute bottom-0 left-1/2 top-0 z-0 w-[1px] bg-outline-variant/50"
                  aria-hidden
                />
                <div className="absolute left-1/2 top-0 z-10 -translate-x-1/2 bg-surface-container-low px-1 font-label-caps text-label-caps text-outline">
                  50%
                </div>

                <div className="relative z-10 flex w-full flex-col justify-between gap-space-xs px-4">
                  {noGrafico.map((heroi) => (
                    <LinhaDivergente
                      key={heroi.id_personagem}
                      heroi={heroi}
                      limite={limite}
                    />
                  ))}
                </div>
              </div>
            )
          }
        </Consulta>

        <div className="flex flex-wrap items-center justify-between gap-space-sm border-t border-outline-variant/30 pt-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span className="flex items-center gap-space-base">
            <span className="inline-flex items-center gap-space-xs">
              <i
                className="h-2 w-2 rounded-full"
                style={{ background: PALETA_POLOS.positivo }}
                aria-hidden
              />
              Acima de 50%
            </span>
            <span className="inline-flex items-center gap-space-xs">
              <i
                className="h-2 w-2 rounded-full"
                style={{ background: PALETA_POLOS.negativo }}
                aria-hidden
              />
              Abaixo de 50%
            </span>
          </span>
          <span>
            Escala simétrica · ±
            <span className="text-primary">{fmtDecimal(limite, 1)} pontos</span>
          </span>
        </div>
      </Painel>

      {/* ==================== MATRIZ DE TELEMETRIA ==================== */}
      <Painel
        icone="table_rows"
        titulo="Matriz de telemetria"
        descricao="Médias por partida jogada, no recorte de filtros acima."
        meta={
          <div className="flex flex-wrap items-center gap-space-xs">
            {ORDENACOES.map((opcao) => (
              <Pilula
                key={opcao.valor}
                ativa={ordenacao === opcao.valor}
                icone={opcao.icone}
                aoClicar={() => setOrdenacao(opcao.valor)}
              >
                {opcao.rotulo}
              </Pilula>
            ))}
          </div>
        }
      >
        <Consulta estado={personagens} vazio="Nenhum herói atinge esse mínimo de partidas.">
          {() => (
            <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                    <th className="px-space-md py-space-sm">Herói</th>
                    <th className="px-space-md py-space-sm text-right">Partidas</th>
                    <th className="px-space-md py-space-sm text-right">Vitórias</th>
                    <th className="px-space-md py-space-sm">Winrate</th>
                    <th className="px-space-md py-space-sm text-right">KDA</th>
                    <th className="px-space-md py-space-sm text-right">K</th>
                    <th className="px-space-md py-space-sm text-right">D</th>
                    <th className="px-space-md py-space-sm text-right">A</th>
                    <th className="px-space-md py-space-sm text-right">GPM</th>
                    <th className="px-space-md py-space-sm text-right">XPM</th>
                  </tr>
                </thead>

                <tbody className="font-body-md text-body-sm">
                  {tabela.map((heroi, indice) => {
                    const positivo = heroi.winrate > 50;
                    const cor = positivo ? PALETA_POLOS.positivo : PALETA_POLOS.negativo;

                    return (
                      <tr
                        key={heroi.id_personagem}
                        className={`transition-colors hover:bg-surface-container-high/60 ${
                          indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                        }`}
                        style={{ boxShadow: `inset 3px 0 0 ${cor}` }}
                      >
                        <td className="px-space-md py-space-sm">
                          <div className="flex items-center gap-space-sm">
                            <RetratoHeroi
                              nome={heroi.nome}
                              nomeInterno={heroi.nome_interno}
                              className="h-8 w-8"
                            />
                            <span className="font-headline-sm text-headline-sm text-on-surface">
                              {heroi.nome}
                            </span>
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface">
                          {fmtNumero(heroi.partidas)}
                        </td>
                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                          {fmtNumero(heroi.vitorias)}
                        </td>

                        <td className="px-space-md py-space-sm">
                          <div className="flex items-center gap-space-sm">
                            <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-container-highest">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${heroi.winrate}%`,
                                  background: cor,
                                }}
                              />
                            </div>
                            <span
                              className="font-title-code text-title-code tabular-nums"
                              style={{ color: cor }}
                            >
                              {fmtPercentual(heroi.winrate)}
                            </span>
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-primary">
                          {fmtDecimal(heroi.kda_medio, 2)}
                        </td>
                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                          {fmtDecimal(heroi.kills_media, 1)}
                        </td>
                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                          {fmtDecimal(heroi.deaths_media, 1)}
                        </td>
                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                          {fmtDecimal(heroi.assists_media, 1)}
                        </td>
                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                          {fmtNumero(heroi.economia_por_minuto_media)}
                        </td>
                        <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                          {fmtNumero(heroi.experiencia_por_minuto_media)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Consulta>

        <div className="flex flex-wrap items-center justify-between gap-space-sm border-t border-outline-variant/30 pt-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span>
            {fmtNumero(tabela.length)} heróis · corte de {minPartidas} partidas
          </span>
          <Selo cor="primario">{jogo}</Selo>
        </div>
      </Painel>
    </>
  );
}
