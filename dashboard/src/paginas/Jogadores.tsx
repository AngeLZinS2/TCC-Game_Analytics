/**
 * Jogadores identificados nas partidas coletadas.
 *
 * Porte da tela "Jogadores" do Stitch: cabecalho de telemetria, barra de
 * controles, quatro KPIs, o spotlight dos tres melhores e a tabela ranqueavel
 * com abas de ordenacao e paginacao.
 */

import { useEffect, useMemo, useState } from "react";

import { useJogadores, useJogosDisponiveis, useSaude } from "../api/consultas";
import type { ResumoJogador } from "../api/tipos";
import { Botao, Consulta, Icone, Selo } from "../componentes/base";
import {
  CAMPO,
  ChipContagem,
  KpiHud,
  Paginacao,
  Painel,
  Pilula,
  Segmentos,
  Sparkline,
} from "../componentes/hud";
import { useJogoAtual } from "../layout/JogoAtual";
import { corDoJogo } from "../tema";
import { fmtDecimal, fmtNumero, fmtPercentual } from "../utilitarios/formatos";

/** As abas de ordenacao rapida da toolbar da tabela. */
const ORDENACOES = [
  { valor: "partidas", rotulo: "Volume", icone: "insights" },
  { valor: "kda", rotulo: "KDA", icone: "swords" },
  { valor: "winrate", rotulo: "Winrate", icone: "trending_up" },
  { valor: "gpm", rotulo: "GPM", icone: "payments" },
] as const;

type Ordenacao = (typeof ORDENACOES)[number]["valor"];

/** Cor da medalha por posicao no podio - ouro, prata e bronze do desenho. */
const MEDALHAS = ["#ffd700", "#e0e0e0", "#cd7f32"];

/** Nome do jogador, ou o id quando a fonte anonimizou o participante. */
function nomeDe(jogador: ResumoJogador): string {
  return jogador.nome ?? `#${jogador.id_jogador}`;
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
}: {
  jogador: ResumoJogador;
  posicao: number;
  jogo: string;
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
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-surface-container-high font-headline-md text-headline-md text-on-surface-variant shadow-md">
              {nomeDe(jogador).charAt(0).toUpperCase()}
            </div>
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
              {fmtNumero(jogador.partidas)} partidas · {fmtNumero(jogador.vitorias)}{" "}
              vitórias
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
            Herói assinatura
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
            KDA médio
          </span>
          <span className="font-title-code text-title-code text-tertiary">
            {fmtDecimal(jogador.kda_medio, 2)}
          </span>
        </div>

        <div className="flex flex-col">
          <span className="font-label-caps text-label-caps uppercase text-outline">
            Winrate
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
  const { jogo, definirJogo } = useJogoAtual();

  const [minPartidas, setMinPartidas] = useState(3);
  const [ordenacao, setOrdenacao] = useState<Ordenacao>("partidas");
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(25);

  const jogadores = useJogadores(jogo, minPartidas, 200);
  const jogosDisponiveis = useJogosDisponiveis();
  const saude = useSaude();

  const online = saude.data?.status === "ok";

  useEffect(() => setPagina(1), [jogo, minPartidas, ordenacao, busca, porPagina]);

  const ordenados = useMemo(() => {
    const lista = (jogadores.data ?? []).filter((jogador) =>
      busca ? nomeDe(jogador).toLowerCase().includes(busca.toLowerCase()) : true,
    );
    return [...lista].sort((a, b) => valorDe(b, ordenacao) - valorDe(a, ordenacao));
  }, [jogadores.data, ordenacao, busca]);

  const totalPaginas = Math.max(1, Math.ceil(ordenados.length / porPagina));
  const daPagina = ordenados.slice((pagina - 1) * porPagina, pagina * porPagina);

  // O podio segue a ordenacao escolhida: "os tres melhores" depende de por qual
  // metrica se esta olhando, e travar em volume contradiria a aba ativa.
  const podio = ordenados.slice(0, 3);

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-space-xs">
          <div className="flex flex-wrap items-center gap-space-sm">
            <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-primary drop-shadow-[0_0_12px_rgba(0,229,255,0.4)]">
              Jogadores
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
                {online ? "Ao vivo" : "Sem contato"}
              </span>
            </div>
            <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
              Player Analytics // Deck 04
            </span>
          </div>

          <p className="font-body-sm text-body-sm text-on-surface-variant">
            Cada linha agrega o fato por jogador. Partidas em que a API anonimiza o
            participante geram fato sem jogador — o KDA continua analisável, mas elas não
            aparecem aqui.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-space-sm">
          <label className="flex items-center gap-space-xs">
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Mín. partidas
            </span>
            <select
              value={minPartidas}
              onChange={(evento) => setMinPartidas(Number(evento.target.value))}
              className={CAMPO}
            >
              {[1, 3, 5, 10].map((valor) => (
                <option key={valor} value={valor}>
                  {valor}
                </option>
              ))}
            </select>
          </label>

          <Botao
            icone="refresh"
            aoClicar={() => jogadores.refetch()}
            desabilitado={jogadores.isFetching}
          >
            {jogadores.isFetching ? "Atualizando…" : "Atualizar"}
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
            placeholder="Buscar jogador pelo apelido…"
            aria-label="Buscar jogador"
            className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-space-sm font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
          />
        </div>

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
      </section>

      {/* ==================== QUATRO KPIS ==================== */}
      <Consulta estado={jogadores} altura={160} vazio="Nenhum jogador atinge esse mínimo.">
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
                etiqueta="Jogadores no recorte"
                canto={`MÍN. ${minPartidas}`}
                valor={fmtNumero(lista.length)}
                rotulo="Identificados na dimensão"
                acento="primaria"
                notaVariacao={`${fmtNumero(participacoes)} participações`}
              >
                <Segmentos acesos={lista.length ? 6 : 0} acento="primaria" />
              </KpiHud>

              <KpiHud
                etiqueta="KDA médio do grupo"
                canto="MÉDIA"
                valor={kdaMedio === null ? "—" : fmtDecimal(kdaMedio, 2)}
                rotulo="(kills + assists) / deaths"
                acento="secundaria"
                notaVariacao={`${comKda.length} com KDA calculável`}
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
                etiqueta="Maior winrate"
                canto="TOPO"
                valor={melhorWinrate ? fmtPercentual(melhorWinrate.winrate) : "—"}
                rotulo={melhorWinrate ? nomeDe(melhorWinrate) : "sem dados"}
                acento="terciaria"
              >
                <div className="mt-space-md h-2 w-full overflow-hidden rounded-full bg-surface-container-lowest">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-tertiary-container to-tertiary"
                    style={{ width: `${melhorWinrate?.winrate ?? 0}%` }}
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta="Heróis assinatura"
                canto="DIVERSIDADE"
                valor={fmtNumero(
                  new Set(
                    lista.map((j) => j.personagem_assinatura).filter(Boolean),
                  ).size,
                )}
                rotulo="Heróis distintos como principal"
                acento="primaria"
                notaVariacao="entre os jogadores do recorte"
              />
            </section>
          );
        }}
      </Consulta>

      {/* ==================== PODIO ==================== */}
      {podio.length > 0 && (
        <Painel
          icone="military_tech"
          titulo={`Destaques por ${ORDENACOES.find((o) => o.valor === ordenacao)?.rotulo}`}
          descricao="Os três primeiros da ordenação escolhida abaixo."
          meta={<Selo cor="primario">Top 3</Selo>}
        >
          <div className="grid grid-cols-1 gap-space-base lg:grid-cols-3">
            {podio.map((jogador, indice) => (
              <CartaoMvp
                key={jogador.id_jogador}
                jogador={jogador}
                posicao={indice}
                jogo={jogo}
              />
            ))}
          </div>
        </Painel>
      )}

      {/* ==================== TABELA ==================== */}
      <Painel
        icone="table_rows"
        titulo="Ranking de jogadores"
        descricao="A mesma agregação do pódio, com todas as colunas."
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
        <Consulta estado={jogadores} vazio="Nenhum jogador atinge esse mínimo.">
          {() =>
            daPagina.length === 0 ? (
              <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                Nenhum jogador bate com a busca.
              </p>
            ) : (
              <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                      <th className="px-space-md py-space-sm">#</th>
                      <th className="px-space-md py-space-sm">Jogador</th>
                      <th className="px-space-md py-space-sm">Herói assinatura</th>
                      <th className="px-space-md py-space-sm text-right">Partidas</th>
                      <th className="px-space-md py-space-sm text-right">Vitórias</th>
                      <th className="px-space-md py-space-sm">Winrate</th>
                      <th className="px-space-md py-space-sm text-right">KDA</th>
                      <th className="px-space-md py-space-sm text-right">GPM</th>
                    </tr>
                  </thead>

                  <tbody className="font-body-md text-body-sm">
                    {daPagina.map((jogador, indice) => {
                      const posicao = (pagina - 1) * porPagina + indice;
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
                              <span
                                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-container-high font-title-code text-title-code text-on-surface-variant"
                                aria-hidden
                              >
                                {nomeDe(jogador).charAt(0).toUpperCase()}
                              </span>
                              <span className="font-headline-sm text-headline-sm text-on-surface">
                                {nomeDe(jogador)}
                              </span>
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
                              <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-container-highest">
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-primary-container to-tertiary"
                                  style={{ width: `${jogador.winrate}%` }}
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
          pagina={pagina}
          totalPaginas={totalPaginas}
          porPagina={porPagina}
          aoMudarPagina={setPagina}
          aoMudarPorPagina={setPorPagina}
          resumo={<>{fmtNumero(ordenados.length)} jogadores no recorte</>}
        />
      </Painel>
    </>
  );
}
