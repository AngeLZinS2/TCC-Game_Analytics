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

import { usePerfilEsporte, usePersonagens, useSaude } from "../api/consultas";
import type { ResumoPersonagem } from "../api/tipos";
import { Botao, Consulta, Icone, Selo } from "../componentes/base";
import { RetratoHeroi } from "../componentes/RetratoHeroi";
import {
  BarraFina,
  BarraSegmentada,
  CAMPO,
  KpiHud,
  Painel,
  Pilula,
  Segmentos,
} from "../componentes/hud";
import { SeletorDeJogo } from "../componentes/SeletorDeJogo";
import { useJogoAtual } from "../layout/JogoAtual";
import { PALETA_POLOS } from "../tema";
import { desvioConfiavel, intervaloWilson } from "../utilitarios/estatistica";
import { fmtDecimal, fmtNumero, fmtPercentual } from "../utilitarios/formatos";

/** "IC 95%: 52,2–53,2% · 35.616 partidas" — o rótulo de incerteza de um KPI. */
function rotuloIntervalo(personagem: ResumoPersonagem): string {
  const { minimo, maximo } = intervaloWilson(
    personagem.vitorias,
    personagem.partidas,
  );
  return (
    `IC 95%: ${fmtDecimal(minimo * 100, 1)}–${fmtDecimal(maximo * 100, 1)}% · ` +
    `${fmtNumero(personagem.partidas)} partidas`
  );
}

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
 *
 * `itens` chega ordenado por winrate (a API ordena). Antes de fatiar as
 * pontas, tira quem NAO se afasta dos 50% com confianca: um heroi a 78% em 9
 * partidas tem intervalo [45%, 94%] e o ponto dele so parece extremo. Sem esse
 * filtro o grafico virava um ranking de amostras pequenas com sorte.
 *
 * Filtra SEMPRE, mesmo que sobrem menos de `quantidade`: com a coleta atual de
 * Dota (17 partidas no maximo por heroi) o grafico honesto tem 5 barras, nao
 * 10. Zero barras cai no estado vazio, que explica o porque.
 */
function extremos(itens: ResumoPersonagem[], quantidade: number): ResumoPersonagem[] {
  const confiaveis = itens.filter(
    (h) => desvioConfiavel(h.vitorias, h.partidas) !== 0,
  );
  if (confiaveis.length <= quantidade) return confiaveis;
  const metade = Math.floor(quantidade / 2);
  return [
    ...confiaveis.slice(0, quantidade - metade),
    ...confiaveis.slice(-metade),
  ];
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

  const intervalo = intervaloWilson(heroi.vitorias, heroi.partidas);

  return (
    <div
      className="group flex h-8 w-full items-center"
      title={
        `${heroi.nome}: ${fmtPercentual(heroi.winrate)} em ` +
        `${fmtNumero(heroi.partidas)} partidas — IC 95%: ` +
        `${fmtDecimal(intervalo.minimo * 100, 1)}–${fmtDecimal(intervalo.maximo * 100, 1)}%`
      }
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
  const { jogo } = useJogoAtual();
  const [minPartidas, setMinPartidas] = useState(5);
  const [ordenacao, setOrdenacao] = useState<Ordenacao>("winrate");
  const [busca, setBusca] = useState("");

  // O vocabulário do esporte: como ele chama seus personagens e o que mede.
  const perfil = usePerfilEsporte(jogo);
  const personagens = usePersonagens({
    jogo,
    min_partidas: minPartidas,
    ordenar_por: "winrate",
    limite: 200,
  });
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
    // `kda` pela chave genérica: ela existe em Dota e em Valorant, mas com
    // origens diferentes, e ler um campo fixo do schema só funcionava enquanto
    // o schema fosse o do Dota.
    const chave = (h: ResumoPersonagem) =>
      ordenacao === "partidas"
        ? h.partidas
        : ordenacao === "kda"
          ? (h.metricas.kda ?? 0)
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
              {(perfil.data?.substantivo_plural ?? "Personagens").toUpperCase()}
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
        {/*
          O padrão exige `partidas > 0`, que é a fonte por jogador. Esta
          tela também serve o esporte cujo elenco vem com estatística
          agregada: Valorant tem 29 agentes com HS%, ADR e KDA e zero linha
          em `fato_partida_jogador`.
        */}
        <SeletorDeJogo
          disponivel={(j) => j.partidas > 0 || j.personagens > 0}
          listar={(j) => j.personagens > 0}
        />

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

          // argmax/argmin explicitos, nao `lista[0]`/`lista.at(-1)`: a KPI de
          // superlativo tem que bater com a linha de topo da tabela SEMPRE,
          // independente da ordem em que a API devolveu. Foi o descasamento
          // exato que a tela mostrava - "maior winrate: Kai'Sa 49,4%" (o mais
          // jogado) contra a tabela liderada por outro campeao a 52,7%.
          const maiorWr = lista.length
            ? lista.reduce((a, b) => (b.winrate > a.winrate ? b : a))
            : null;
          const menorWr = lista.length
            ? lista.reduce((a, b) => (b.winrate < a.winrate ? b : a))
            : null;

          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta={`${perfil.data?.substantivo_plural ?? "Personagens"} no recorte`}
                canto={`MÍN. ${minPartidas}`}
                valor={fmtNumero(lista.length)}
                valorNumerico={lista.length}
                formatarValor={fmtNumero}
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
                valorNumerico={acima}
                formatarValor={fmtNumero}
                rotulo={`${perfil.data?.substantivo_plural ?? "Personagens"} com mais vitórias que derrotas`}
                acento="terciaria"
                notaVariacao={`${fmtNumero(lista.length - acima)} abaixo ou na linha`}
              >
                <div className="mt-space-md">
                  <BarraSegmentada
                    fracaoA={lista.length ? acima / lista.length : 0}
                  />
                </div>
              </KpiHud>

              <KpiHud
                etiqueta="Maior winrate"
                canto="TOPO"
                valor={maiorWr ? fmtPercentual(maiorWr.winrate) : "—"}
                rotulo={maiorWr ? maiorWr.nome : "sem dados"}
                acento="secundaria"
                notaVariacao={maiorWr ? rotuloIntervalo(maiorWr) : undefined}
              />

              <KpiHud
                etiqueta="Menor winrate"
                canto="CAUDA"
                valor={menorWr ? fmtPercentual(menorWr.winrate) : "—"}
                rotulo={menorWr ? menorWr.nome : "sem dados"}
                acento="primaria"
                notaVariacao={menorWr ? rotuloIntervalo(menorWr) : undefined}
              />
            </section>
          );
        }}
      </Consulta>

      {/* ==================== DISTRIBUICAO DIVERGENTE ==================== */}
      <Painel
        icone="compare_arrows"
        titulo={`Distribuição de winrate // ${
          noGrafico.length && noGrafico.length < NO_GRAFICO ? noGrafico.length : `top ${NO_GRAFICO}`
        } ${perfil.data?.substantivo_plural ?? "personagens"}`}
        descricao="Distância até os 50%: à direita, mais vitórias que derrotas; à esquerda, o contrário. Só entram os que se afastam dos 50% com 95% de confiança — winrate alto em poucas partidas fica de fora."
        meta={
          <span className="font-badge-status text-badge-status tracking-widest text-outline">
            LOC: {jogo.toUpperCase()}-META // H-01
          </span>
        }
      >
        <Consulta
          estado={personagens}
          vazio={`Nenhum ${
            perfil.data?.substantivo ?? "personagem"
          } atinge esse mínimo de partidas.`}
        >
          {() =>
            noGrafico.length === 0 ? (
              <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                {filtrados.length === 0
                  ? "Nenhum personagem bate com a busca."
                  : "Nenhum se afasta dos 50% com 95% de confiança neste recorte — as amostras são pequenas demais. Aumente o mínimo de partidas para um recorte mais estável, ou aguarde mais coleta."}
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
          <span className="flex items-center gap-space-base">
            {noGrafico.length < NO_GRAFICO && (
              <span>
                <span className="text-primary">{noGrafico.length}</span> com
                margem — os demais têm amostra curta
              </span>
            )}
            <span>
              Escala simétrica · ±
              <span className="text-primary">{fmtDecimal(limite, 1)} pontos</span>
            </span>
          </span>
        </div>
      </Painel>

      {/* ==================== MATRIZ DE TELEMETRIA ==================== */}
      <Painel
        icone="table_rows"
        titulo="Matriz de telemetria"
        // A procedência muda com o esporte, e afirmá-la errada é o mesmo
        // defeito de rotular dado de terceiro como medição nossa: as
        // médias do Dota são nossas, as do Valorant são do OP.GG.
        descricao={
          perfil.data?.nota_fonte
            ? `${perfil.data.nota_fonte} No recorte de filtros acima.`
            : "Médias no recorte de filtros acima."
        }
        meta={
          <div className="flex flex-wrap items-center gap-space-xs">
            {/* Só onde a API reordena de verdade. No agregado a ordem vem
                pronta da fonte, por volume, e uma pílula que não reordena
                nada é pior que pílula nenhuma. */}
            {(perfil.data?.ordenavel ?? true) &&
              ORDENACOES.map((opcao) => (
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
                    <th className="px-space-md py-space-sm">
                      {perfil.data?.substantivo ?? "Personagem"}
                    </th>
                    <th className="px-space-md py-space-sm text-right">Partidas</th>
                    <th className="px-space-md py-space-sm text-right">Vitórias</th>
                    <th className="px-space-md py-space-sm">Winrate</th>
                    {/*
                      As colunas vêm do perfil do esporte. Eram "KDA / K / D / A
                      / GPM / XPM" fixas — o vocabulário do Dota —, e um agente
                      de Valorant não tem ouro por minuto: a coluna vazia
                      sugeriria dado faltando quando o número não existe no jogo.
                    */}
                    {(perfil.data?.metricas ?? []).map((m) => (
                      <th
                        key={m.chave}
                        className="px-space-md py-space-sm text-right"
                        title={m.descricao}
                      >
                        {m.rotulo}
                      </th>
                    ))}
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
                            <div className="w-16">
                              <BarraFina largura={heroi.winrate} cor={cor} />
                            </div>
                            <span
                              className="font-title-code text-title-code tabular-nums"
                              style={{ color: cor }}
                            >
                              {fmtPercentual(heroi.winrate)}
                            </span>
                          </div>
                        </td>

                        {(perfil.data?.metricas ?? []).map((m, i) => {
                          const valor = heroi.metricas[m.chave];
                          return (
                            <td
                              key={m.chave}
                              className={`px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums ${
                                i === 0 ? "text-primary" : "text-on-surface-variant"
                              }`}
                            >
                              {/* Sem valor é "—", não zero: a fonte pode não
                                  publicar aquela métrica para aquele personagem. */}
                              {valor === null || valor === undefined
                                ? "—"
                                : `${fmtDecimal(valor, m.casas)}${m.unidade}`}
                            </td>
                          );
                        })}
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
