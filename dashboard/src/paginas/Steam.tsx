/**
 * Catalogo Steam.
 *
 * Porte da tela "Jogos da Steam" do Stitch. A estrutura segue o desenho:
 * cabecalho com identificador de pipeline, busca + pilulas de ordenacao, chips
 * de genero com contagem, tres KPIs, o ranking em barras de gradiente e a
 * tabela de telemetria.
 *
 * O que o desenho mostra e o projeto ainda nao tem ficou de fora, nao virou
 * numero fixo: "Trending 24h" depende de variacao entre coletas e so acende
 * quando existe uma segunda coleta; o ping da Valve Web API nao existe (o que
 * existe e a latencia da NOSSA API, e e ela que aparece).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  useBuscaCatalogo,
  useColetarJogo,
  useGenerosSteam,
  useJogosSteam,
  useSaude,
  useSerieTotalSteam,
} from "../api/consultas";
import type {
  AgregadoGenero,
  CandidatoJogo,
  JogoSteam,
  PontoSerieTotal,
} from "../api/tipos";
import { Botao, Consulta, Icone, MensagemErro } from "../componentes/base";
import { CapaJogo } from "../componentes/CapaJogo";
import {
  BarraRanking,
  ChipContagem,
  KpiHud,
  Pilula,
  Segmentos,
  Sparkline,
} from "../componentes/hud";
import { PALETA_SERIES } from "../tema";
import {
  classificacaoSteam,
  fmtCurto,
  fmtDataHora,
  fmtMoeda,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
  paraNumero,
} from "../utilitarios/formatos";

const NO_RANKING = 8;

type Ordenacao = "jogadores" | "avaliacoes" | "preco" | "trending";

const ORDENACOES: { valor: Ordenacao; rotulo: string; icone?: string }[] = [
  { valor: "jogadores", rotulo: "Mais Jogados (CCU)", icone: "trending_up" },
  { valor: "avaliacoes", rotulo: "Melhor Avaliados" },
  { valor: "preco", rotulo: "Preço" },
  { valor: "trending", rotulo: "Trending 24h", icone: "local_fire_department" },
];

/**
 * Cor de um genero, estavel entre renders e entre telas.
 *
 * O desenho pinta os chips de genero em cores diferentes. Como a lista de
 * generos vem da coleta e nao de uma constante, a cor sai de um hash do nome:
 * "FPS" e sempre da mesma cor, sem precisar de um mapa que teria de ser mantido
 * a mao toda vez que um jogo novo trouxer um genero novo.
 */
function corDoGenero(genero: string): string {
  let hash = 0;
  for (let i = 0; i < genero.length; i += 1) {
    hash = (hash * 31 + genero.charCodeAt(i)) | 0;
  }
  return PALETA_SERIES[Math.abs(hash) % PALETA_SERIES.length];
}

const CHIP_CLASSIFICACAO = {
  positiva: "bg-tertiary/10 text-tertiary",
  neutra: "bg-surface-container-highest text-on-surface-variant",
  negativa: "bg-error/10 text-error",
} as const;

/**
 * Uma linha da tabela.
 *
 * A tabela passou a ter duas procedencias, e o tipo diz qual: `coletado` e um
 * jogo que o pipeline ja trouxe, com telemetria e historico; `loja` e um jogo
 * que existe na Steam e ainda nao entrou. Um union em vez de um `JogoSteam`
 * com tudo nulo, porque as duas linhas nao respondem as mesmas perguntas - e
 * preencher as celulas de telemetria com zero afirmaria algo falso.
 */
type LinhaCatalogo =
  | { tipo: "coletado"; jogo: JogoSteam }
  | { tipo: "loja"; candidato: CandidatoJogo };

export function SteamPagina() {
  const navegar = useNavigate();
  const campoBusca = useRef<HTMLInputElement>(null);

  const [busca, setBusca] = useState("");
  const [genero, setGenero] = useState("");
  const [ordenacao, setOrdenacao] = useState<Ordenacao>("jogadores");

  // "Trending" nao existe no backend: ele ordena pela variacao, que e calculada
  // aqui sobre a lista ja carregada. Para a API, a consulta continua sendo a
  // mesma de "mais jogados".
  const jogos = useJogosSteam({
    busca: busca.trim() || undefined,
    genero: genero || undefined,
    ordenar_por: ordenacao === "trending" ? "jogadores" : ordenacao,
    limite: 200,
  });
  const generos = useGenerosSteam();
  const serieTotal = useSerieTotalSteam();
  const saude = useSaude();

  // A busca do banco cobre os jogos monitorados. A partir de dois caracteres
  // entra tambem a loja inteira, para que buscar um jogo que nunca foi coletado
  // devolva o jogo em vez de "nenhum resultado".
  const [termoBuscado, setTermoBuscado] = useState("");
  useEffect(() => {
    const relogio = setTimeout(() => setTermoBuscado(busca.trim()), 450);
    return () => clearTimeout(relogio);
  }, [busca]);

  const catalogo = useBuscaCatalogo(termoBuscado);
  const coletar = useColetarJogo();

  // Ctrl+K foca a busca, como o `kbd` do desenho promete. Uma dica de atalho
  // que nao funciona e pior que nenhuma.
  useEffect(() => {
    function aoTeclar(evento: KeyboardEvent) {
      if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "k") {
        evento.preventDefault();
        campoBusca.current?.focus();
      }
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, []);

  const lista = useMemo(() => {
    const dados = jogos.data ?? [];
    if (ordenacao !== "trending") return dados;
    return [...dados].sort(
      (a, b) => (b.variacao_jogadores ?? -Infinity) - (a.variacao_jogadores ?? -Infinity),
    );
  }, [jogos.data, ordenacao]);

  // Sem segunda coleta, nenhum jogo tem variacao - e a ordenacao por tendencia
  // devolveria a mesma lista fingindo ter ordenado.
  const temVariacao = (jogos.data ?? []).some((j) => j.variacao_jogadores !== null);

  const idsNaBase = new Set(lista.map((jogo) => jogo.app_id));

  //: Resultados da loja que o banco ainda nao tem. O filtro evita o mesmo jogo
  //: em duas linhas, uma com telemetria e outra sem.
  const daLoja = (catalogo.data ?? []).filter(
    (candidato) => !candidato.coletado && !idsNaBase.has(candidato.app_id),
  );

  const linhas: LinhaCatalogo[] = [
    ...lista.map((jogo) => ({ tipo: "coletado" as const, jogo })),
    ...daLoja.map((candidato) => ({ tipo: "loja" as const, candidato })),
  ];

  //: O vazio dos paineis de telemetria.
  //:
  //: Os KPIs e o ranking agregam SO o que foi coletado - jogo da loja nao tem
  //: jogadores nem historico para somar. Quando a busca nao acha nada no banco
  //: mas acha na loja, dizer "nenhum jogo bate com esse filtro" seria falso: a
  //: tabela logo abaixo esta cheia. A mensagem tem de dizer que o que falta e a
  //: TELEMETRIA, e apontar para onde os resultados estao.
  const vazioDaTelemetria =
    daLoja.length > 0
      ? "Sem telemetria: os jogos desta busca existem na loja da Steam, mas ainda não foram coletados. Abra um deles na tabela abaixo."
      : "Nenhum jogo bate com esse filtro.";

  /**
   * Abre um jogo, coletando primeiro se ele ainda nao estiver no banco.
   *
   * A pessoa nao precisa saber de qual das duas listas a linha veio: ela
   * clicou num jogo, e o que ela espera e a tela do jogo. Quando falta o dado,
   * ele e buscado agora - e a navegacao espera a coleta terminar, porque abrir
   * a tela de detalhe antes mostraria um vazio que sumiria sozinho.
   */
  function abrir(linha: LinhaCatalogo) {
    if (linha.tipo === "coletado") {
      navegar(`/steam/${linha.jogo.app_id}`);
      return;
    }
    coletar.mutate(linha.candidato.app_id, {
      onSuccess: (resumo) => navegar(`/steam/${resumo.app_id}`),
    });
  }

  const totalCatalogo = generos.data
    ? Math.max(...generos.data.map((g) => g.jogos), 0)
    : 0;

  return (
    <>
      {/* ==================== CABECALHO E STATUS DO PIPELINE ==================== */}
      <section className="relative overflow-hidden rounded-xl bg-surface-container-low p-space-lg shadow-2xl">
        <div
          className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary-container/10 blur-3xl"
          aria-hidden
        />

        <div className="relative z-10 flex flex-col justify-between gap-space-base lg:flex-row lg:items-start">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-space-sm">
              <span className="font-title-code text-title-code uppercase tracking-wider text-outline">
                SYS. ID: STEAM // PIPE 01
              </span>
              <span
                className={`inline-flex items-center gap-space-xxs rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${
                  saude.data?.status === "ok"
                    ? "bg-error/10 text-error"
                    : "bg-surface-container-highest text-outline"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    saude.data?.status === "ok" ? "animate-pulse bg-error" : "bg-outline"
                  }`}
                  aria-hidden
                />
                {saude.data?.status === "ok" ? "Ao vivo" : "Sem contato"}
              </span>
            </div>

            <h1 className="mt-space-xs font-display-hero text-display-hero uppercase leading-none tracking-tight text-on-surface">
              Jogos da
              <br />
              Steam
            </h1>

            <p className="mt-space-sm flex items-center gap-space-xs font-title-code text-title-code text-outline">
              <Icone nome="sync" className="text-[16px] text-primary-container" />
              Última sincronização:{" "}
              <span className="text-on-surface-variant">
                {serieTotal.data?.length
                  ? fmtRelativo(serieTotal.data.at(-1)!.janela_coleta)
                  : "—"}
              </span>
            </p>
          </div>

          <div className="flex shrink-0 flex-col items-start gap-space-sm lg:items-end">
            <span className="font-title-code text-title-code uppercase text-outline">
              // Telemetria de mercado [Steam Web API]
            </span>
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Latência da API:{" "}
              <span className="text-primary">
                {saude.data ? `${saude.data.latenciaMs}ms` : "—"}
              </span>
            </span>
            <Botao
              icone="refresh"
              variante="primario"
              aoClicar={() => jogos.refetch()}
              desabilitado={jogos.isFetching}
            >
              {jogos.isFetching ? "Sincronizando…" : "Sincronizar"}
            </Botao>
          </div>
        </div>

        {/* ---------- Busca e ordenacao ---------- */}
        <div className="relative z-10 mt-space-lg flex flex-col justify-between gap-space-md pt-space-md lg:flex-row lg:items-center">
          <div className="relative max-w-xl flex-1">
            <Icone
              nome="manage_search"
              className="absolute left-space-sm top-1/2 -translate-y-1/2 text-[20px] text-primary-container"
            />
            <input
              ref={campoBusca}
              type="search"
              value={busca}
              onChange={(evento) => setBusca(evento.target.value)}
              placeholder="Buscar jogo por título ou desenvolvedora…"
              aria-label="Buscar jogo"
              className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-20 font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
            />
            <kbd className="absolute right-space-sm top-1/2 -translate-y-1/2 rounded bg-surface-container px-space-xs py-space-xxs font-label-caps text-label-caps text-outline">
              Ctrl+K
            </kbd>
          </div>

          <div className="flex flex-wrap items-center gap-space-xs">
            <span className="mr-space-xs hidden font-label-caps text-label-caps uppercase text-outline sm:inline">
              Ordenar:
            </span>
            {ORDENACOES.map((opcao) => {
              const indisponivel = opcao.valor === "trending" && !temVariacao;
              return (
                <Pilula
                  key={opcao.valor}
                  ativa={ordenacao === opcao.valor}
                  desabilitada={indisponivel}
                  titulo={
                    indisponivel
                      ? "Precisa de pelo menos duas coletas para haver tendência"
                      : undefined
                  }
                  icone={opcao.icone}
                  corIcone={opcao.valor === "trending" ? "text-error" : undefined}
                  aoClicar={() => setOrdenacao(opcao.valor)}
                >
                  {opcao.rotulo}
                </Pilula>
              );
            })}
          </div>
        </div>

        {/* ---------- Chips de genero ---------- */}
        <div className="rolagem-discreta relative z-10 mt-space-md flex items-center gap-space-xs overflow-x-auto pb-space-xs pt-space-xs">
          <ChipContagem
            ativo={genero === ""}
            contagem={totalCatalogo || undefined}
            aoClicar={() => setGenero("")}
          >
            TODOS
          </ChipContagem>

          {generos.data?.map((item: AgregadoGenero) => (
            <ChipContagem
              key={item.genero}
              ativo={genero === item.genero}
              contagem={item.jogos}
              cor={corDoGenero(item.genero)}
              aoClicar={() => setGenero(genero === item.genero ? "" : item.genero)}
            >
              {item.genero}
            </ChipContagem>
          ))}
        </div>
      </section>

      {/* ==================== TRES KPIS ==================== */}
      <Consulta estado={jogos} altura={160} vazio={vazioDaTelemetria}>
        {(emTela: JogoSteam[]) => {
          const somaJogadores = emTela.reduce(
            (t, j) => t + (j.jogadores_simultaneos ?? 0),
            0,
          );
          const somaPicos = emTela.reduce((t, j) => t + (j.pico_jogadores ?? 0), 0);
          const gratuitos = emTela.filter((j) => j.gratuito).length;

          const serie = (serieTotal.data ?? []) as PontoSerieTotal[];
          const valoresSerie = serie.map((p) => p.jogadores_simultaneos ?? 0);

          // Variacao do catalogo inteiro: ultima janela contra a anterior.
          const variacaoTotal =
            valoresSerie.length > 1 && valoresSerie.at(-2)
              ? ((valoresSerie.at(-1)! - valoresSerie.at(-2)!) / valoresSerie.at(-2)!) *
                100
              : null;

          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-3">
              <KpiHud
                etiqueta="VALVE_CONCURRENT_USERS // AGORA"
                canto={genero ? `FILTRO: ${genero.toUpperCase()}` : "CATÁLOGO INTEIRO"}
                valor={fmtNumero(somaJogadores)}
                rotulo="Jogadores conectados agora"
                variacao={variacaoTotal}
                notaVariacao="vs. coleta anterior"
                acento="primaria"
              >
                <Sparkline valores={valoresSerie} />
              </KpiHud>

              <KpiHud
                etiqueta="INDEXED_ENTITIES // CATÁLOGO"
                canto={saude.data?.status === "ok" ? "100% OK" : "SEM CONTATO"}
                valor={fmtNumero(emTela.length)}
                rotulo="Jogos monitorados ativos"
                acento="secundaria"
                notaVariacao={`${gratuitos} gratuitos`}
              >
                <Segmentos
                  acesos={Math.round(
                    (emTela.filter((j) => j.janela_coleta).length /
                      Math.max(emTela.length, 1)) *
                      6,
                  )}
                />
              </KpiHud>

              <KpiHud
                etiqueta="PEAK_CCU // HISTÓRICO"
                canto="SOMA DOS PICOS"
                valor={fmtCurto(somaPicos)}
                rotulo="Maior audiência já coletada"
                acento="terciaria"
                notaVariacao={
                  somaJogadores && somaPicos
                    ? `agora em ${((somaJogadores / somaPicos) * 100).toFixed(0)}% do pico`
                    : undefined
                }
              >
                <div className="mt-space-md h-2 w-full overflow-hidden rounded-full bg-surface-container-lowest">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-tertiary-container to-tertiary"
                    style={{
                      width: `${somaPicos ? Math.min(100, (somaJogadores / somaPicos) * 100) : 0}%`,
                    }}
                  />
                </div>
              </KpiHud>
            </section>
          );
        }}
      </Consulta>

      {/* ==================== RANKING ==================== */}
      <section className="space-y-space-md rounded-xl bg-surface-container-low p-space-base shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-space-sm">
          <h2 className="flex items-center gap-space-xs font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
            <Icone nome="leaderboard" className="text-[20px] text-primary-container" />
            Top jogos por jogadores simultâneos
          </h2>
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            Máx. referência{" "}
            <span className="text-primary">
              {fmtNumero(lista[0]?.jogadores_simultaneos)}
            </span>
          </span>
        </div>

        <Consulta estado={jogos} vazio={vazioDaTelemetria}>
          {() => {
            const topo = lista
              .filter((j) => j.jogadores_simultaneos !== null)
              .slice(0, NO_RANKING);
            const maximo = topo[0]?.jogadores_simultaneos || 1;

            return (
              <div className="grid gap-space-xs">
                {topo.map((jogo, indice) => (
                  <BarraRanking
                    key={jogo.app_id}
                    posicao={indice + 1}
                    etiqueta={jogo.generos[0]}
                    corEtiqueta={jogo.generos[0] ? corDoGenero(jogo.generos[0]) : undefined}
                    nome={jogo.nome}
                    valor={fmtNumero(jogo.jogadores_simultaneos)}
                    variacao={jogo.variacao_jogadores}
                    proporcao={(jogo.jogadores_simultaneos ?? 0) / maximo}
                    aoClicar={() => navegar(`/steam/${jogo.app_id}`)}
                  />
                ))}
              </div>
            );
          }}
        </Consulta>
      </section>

      {/* ==================== TABELA DE TELEMETRIA ==================== */}
      <section className="space-y-space-md rounded-xl bg-surface-container-low p-space-base shadow-2xl">
        <div className="flex flex-col justify-between gap-space-base lg:flex-row lg:items-center">
          <div className="flex flex-col">
            <h2 className="flex items-center gap-space-xs font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
              <Icone nome="table_rows" className="text-[20px] text-primary-container" />
              Catálogo de telemetria e mercado
            </h2>
            <span className="mt-0.5 font-title-code text-title-code text-outline">
              Exibindo {lista.length} de {totalCatalogo || lista.length} jogos
              monitorados na Valve Store
              {daLoja.length > 0 && ` · +${daLoja.length} da loja, sem coleta ainda`}
            </span>
          </div>

          <Botao icone="file_download" aoClicar={() => exportarCsv(lista)}>
            Exportar CSV
          </Botao>
        </div>

        {coletar.isError && <MensagemErro erro={coletar.error} />}

        {/* O `data` trocado pelas linhas combinadas mantem o envelope cuidando
            de carga e erro da consulta ao banco, mas deixa a tabela viva quando
            o banco nao tem nada e a loja tem: ali a resposta certa e a linha da
            loja, nao "nenhum jogo bate com esse filtro". */}
        <Consulta
          estado={{ ...jogos, data: linhas }}
          vazio={
            termoBuscado.length >= 2 && catalogo.isFetching
              ? "Buscando na loja da Steam…"
              : "Nenhum jogo bate com esse filtro."
          }
        >
          {() => (
            <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                    <th className="px-space-md py-space-sm">Jogo &amp; AppID</th>
                    <th className="px-space-md py-space-sm">Gêneros</th>
                    <th className="px-space-md py-space-sm">Jogadores simultâneos</th>
                    <th className="px-space-md py-space-sm">% Avaliações</th>
                    <th className="px-space-md py-space-sm">Classificação Steam</th>
                    <th className="px-space-md py-space-sm">Preço</th>
                    <th className="px-space-md py-space-sm">Última coleta</th>
                    <th className="px-space-md py-space-sm text-right">Ações</th>
                  </tr>
                </thead>

                <tbody className="font-body-md text-body-sm">
                  {linhas.map((linha, indice) => {
                    if (linha.tipo === "loja") {
                      return (
                        <LinhaDaLoja
                          key={linha.candidato.app_id}
                          candidato={linha.candidato}
                          listrada={indice % 2 === 1}
                          carregando={
                            coletar.isPending &&
                            coletar.variables === linha.candidato.app_id
                          }
                          aoClicar={() => abrir(linha)}
                        />
                      );
                    }

                    const jogo = linha.jogo;
                    const classificacao = classificacaoSteam(jogo.classificacao_steam);
                    const nota = paraNumero(jogo.nota_avaliacoes);

                    return (
                      <tr
                        key={jogo.app_id}
                        onClick={() => abrir(linha)}
                        className={`cursor-pointer transition-colors hover:bg-surface-container-high/60 ${
                          indice % 2 ? "bg-surface-container-low/40" : ""
                        }`}
                      >
                        <td className="px-space-md py-space-sm">
                          <div className="flex items-center gap-space-sm">
                            <CapaJogo appId={jogo.app_id} nome={jogo.nome} />
                            <div className="flex min-w-0 flex-col">
                              <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">
                                {jogo.nome}
                              </span>
                              <div className="flex items-center gap-space-xs font-title-code text-title-code text-outline">
                                <span>AppID:</span>
                                <span className="font-bold text-on-surface-variant">
                                  {jogo.app_id}
                                </span>
                                {jogo.desenvolvedora && <span>/ {jogo.desenvolvedora}</span>}
                              </div>
                            </div>
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm">
                          <div className="flex flex-wrap gap-1">
                            {jogo.generos.slice(0, 3).map((g) => (
                              <span
                                key={g}
                                className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase"
                                style={{ color: corDoGenero(g) }}
                              >
                                {g}
                              </span>
                            ))}
                            {jogo.generos.length > 3 && (
                              <span className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status text-outline">
                                +{jogo.generos.length - 3}
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm">
                          <div className="flex flex-col">
                            <span className="font-headline-sm text-headline-sm font-bold text-tertiary">
                              {fmtNumero(jogo.jogadores_simultaneos)}
                            </span>
                            <span className="font-label-caps text-label-caps text-outline">
                              Pico: {fmtNumero(jogo.pico_jogadores)}
                            </span>
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm">
                          <div className="flex items-center gap-space-xs">
                            <span
                              className={`font-title-code text-title-code font-bold ${
                                nota !== null && nota >= 70
                                  ? "text-tertiary"
                                  : "text-on-surface-variant"
                              }`}
                            >
                              {fmtPercentual(jogo.nota_avaliacoes, 0)}
                            </span>
                            <span className="font-label-caps text-label-caps text-outline">
                              ({fmtCurto(jogo.numero_avaliacoes)})
                            </span>
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm">
                          {classificacao ? (
                            <span
                              className={`rounded px-space-sm py-space-xxs font-badge-status text-badge-status uppercase ${
                                CHIP_CLASSIFICACAO[classificacao.polaridade]
                              }`}
                            >
                              {classificacao.texto}
                            </span>
                          ) : (
                            <span className="text-outline">—</span>
                          )}
                        </td>

                        <td className="px-space-md py-space-sm">
                          <div className="flex items-center gap-space-xs">
                            <span className="font-title-code text-title-code font-bold text-primary">
                              {fmtMoeda(jogo.preco_no_momento, jogo.moeda)}
                            </span>
                            {jogo.desconto_percentual ? (
                              <span className="rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status text-tertiary">
                                -{jogo.desconto_percentual}%
                              </span>
                            ) : null}
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm">
                          <div
                            className="flex items-center gap-space-xs"
                            title={fmtDataHora(jogo.janela_coleta)}
                          >
                            <span
                              className="h-2 w-2 rounded-full bg-tertiary-container shadow-[0_0_4px_#16ef7a]"
                              aria-hidden
                            />
                            <span className="font-title-code text-title-code text-on-surface-variant">
                              {fmtRelativo(jogo.janela_coleta)}
                            </span>
                          </div>
                        </td>

                        <td className="px-space-md py-space-sm text-right">
                          <span
                            className="inline-flex rounded bg-surface-container p-space-xs text-primary transition-colors hover:bg-surface-container-high"
                            aria-hidden
                          >
                            <Icone nome="query_stats" className="text-[18px]" />
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Consulta>

        <div className="flex flex-wrap items-center justify-between gap-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span>
            Pipeline:{" "}
            <span className={saude.data?.status === "ok" ? "text-tertiary" : "text-error"}>
              {saude.data?.status === "ok" ? "ativo" : "sem contato"}
            </span>
          </span>
          <span>
            Steam store ingest · {serieTotal.data?.length ?? 0}{" "}
            {serieTotal.data?.length === 1 ? "coleta" : "coletas"}
          </span>
        </div>
      </section>
    </>
  );
}

/**
 * A linha de um jogo que existe na Steam e ainda nao foi coletado.
 *
 * As celulas de telemetria vem com travessao, nao com zero. Um zero em
 * "jogadores simultaneos" seria uma afirmacao sobre o jogo; o travessao e uma
 * afirmacao sobre o nosso banco, que e a verdadeira. O preco aparece porque a
 * propria busca da loja ja devolve esse campo.
 *
 * O chip DA LOJA existe para a linha nao mentir por omissao ao lado de linhas
 * com historico - mas nao ha botao nenhum: clicar coleta e abre, igual as
 * outras.
 */
function LinhaDaLoja({
  candidato,
  listrada,
  carregando,
  aoClicar,
}: {
  candidato: CandidatoJogo;
  listrada: boolean;
  carregando: boolean;
  aoClicar: () => void;
}) {
  const vazio = <span className="text-outline">—</span>;

  return (
    <tr
      onClick={carregando ? undefined : aoClicar}
      aria-busy={carregando}
      className={`transition-colors ${
        carregando
          ? "cursor-progress bg-surface-container-high/40"
          : "cursor-pointer hover:bg-surface-container-high/60"
      } ${listrada ? "bg-surface-container-low/40" : ""}`}
    >
      <td className="px-space-md py-space-sm">
        <div className="flex items-center gap-space-sm">
          <CapaJogo appId={candidato.app_id} nome={candidato.nome} />
          <div className="flex min-w-0 flex-col">
            <span className="flex items-center gap-space-xs">
              <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">
                {candidato.nome}
              </span>
              <span className="shrink-0 rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-outline">
                da loja
              </span>
            </span>
            <div className="flex items-center gap-space-xs font-title-code text-title-code text-outline">
              <span>AppID:</span>
              <span className="font-bold text-on-surface-variant">
                {candidato.app_id}
              </span>
            </div>
          </div>
        </div>
      </td>

      <td className="px-space-md py-space-sm">{vazio}</td>
      <td className="px-space-md py-space-sm">{vazio}</td>
      <td className="px-space-md py-space-sm">{vazio}</td>
      <td className="px-space-md py-space-sm">{vazio}</td>

      <td className="px-space-md py-space-sm">
        <span className="font-title-code text-title-code font-bold text-primary">
          {candidato.preco_centavos === null || candidato.preco_centavos === undefined
            ? "—"
            : fmtMoeda(candidato.preco_centavos / 100, candidato.moeda ?? undefined)}
        </span>
      </td>

      <td className="px-space-md py-space-sm">
        <span className="font-title-code text-title-code text-outline">
          {carregando ? "buscando dados…" : "sem coleta"}
        </span>
      </td>

      <td className="px-space-md py-space-sm text-right">
        <span className="inline-flex rounded bg-surface-container p-space-xs text-primary">
          <Icone
            nome={carregando ? "progress_activity" : "query_stats"}
            className={`text-[18px] ${carregando ? "animate-spin" : ""}`}
          />
        </span>
      </td>
    </tr>
  );
}

/**
 * Exporta o recorte em tela como CSV.
 *
 * O botao existe no desenho; sem ele fazer nada seria enfeite. Exporta o que
 * ESTA na tela, com os filtros aplicados - exportar o catalogo inteiro
 * ignoraria o recorte que a pessoa acabou de montar.
 */
function exportarCsv(jogos: JogoSteam[]): void {
  const colunas = [
    "app_id",
    "nome",
    "desenvolvedora",
    "generos",
    "jogadores_simultaneos",
    "pico_jogadores",
    "nota_avaliacoes",
    "numero_avaliacoes",
    "classificacao_steam",
    "preco_no_momento",
    "moeda",
    "desconto_percentual",
    "janela_coleta",
  ] as const;

  const escapar = (valor: unknown) => {
    const texto = valor === null || valor === undefined ? "" : String(valor);
    return /[",\n;]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
  };

  const linhas = [
    colunas.join(";"),
    ...jogos.map((jogo) =>
      colunas
        .map((coluna) =>
          escapar(coluna === "generos" ? jogo.generos.join(", ") : jogo[coluna]),
        )
        .join(";"),
    ),
  ];

  // Ponto e virgula e BOM: e o que o Excel em pt-BR abre sem pedir importacao.
  const blob = new Blob(["﻿" + linhas.join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `catalogo-steam-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
