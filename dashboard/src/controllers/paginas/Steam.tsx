/**
 * Catalogo Steam.
 *
 * Porte da tela "Jogos da Steam" do Stitch. A estrutura segue o desenho:
 * cabecalho com identificador de pipeline, busca + pilulas de ordenacao,
 * dropdowns de genero e categoria, tres KPIs, o ranking em barras de
 * gradiente e a tabela de telemetria.
 *
 * Genero (Acao, Terror, Aventura...) e categoria (Single-player, Co-op,
 * Conquistas...) eram uma fileira de chips - virou dropdown pelo mesmo
 * motivo dos dois: o catalogo tem ~15 generos e 50+ categorias, e esse
 * volume em chip virava parede de scroll horizontal em vez de filtro.
 *
 * O que o desenho mostra e o projeto ainda nao tem ficou de fora, nao virou
 * numero fixo: "Trending 24h" depende de variacao entre coletas e so acende
 * quando existe uma segunda coleta; o ping da Valve Web API nao existe (o que
 * existe e a latencia da NOSSA API, e e ela que aparece).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { usePaginacaoLocal } from "@models/hooks/paginacao";
import {
  useBuscaCatalogo,
  useCategoriasSteam,
  useColetarJogo,
  useGenerosSteam,
  useJogosSteam,
  useSaude,
  useSerieTotalSteam,
  useSeriesJogadoresSteam,
  useVisaoGeral,
} from "@models/api/consultas";
import type {
  AgregadoGenero,
  CandidatoJogo,
  JogoSteam,
  LinhaCatalogo,
  PontoSerieTotal,
} from "@models/api/tipos";
import {
  Botao,
  Consulta,
  Icone,
  MensagemErro,
  TabelaRolavel,
} from "@views/componentes/base";
import { CapaJogo } from "@views/componentes/CapaJogo";
import { CartaoJogoSteam } from "@views/componentes/CartaoJogoSteam";
import { RankingJogos } from "@views/componentes/RankingJogos";
import {
  BarraFina,
  KpiHud,
  Paginacao,
  Pilula,
  Segmentos,
  SeletorFiltro,
  SeletorModo,
  Sparkline,
  useModoPersistente,
} from "@views/componentes/hud";
import { corDoGenero } from "@views/tema";
import {
  classificacaoSteam,
  fmtCurto,
  fmtDataHora,
  fmtMoeda,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
  paraNumero,
} from "@util/formatos";

//: Dez linhas, cinco por coluna no desktop - o ranking é uma leitura rápida do
//: topo, não a lista inteira (que é a tabela de telemetria logo abaixo).
const NO_RANKING = 10;

type Ordenacao = "jogadores" | "avaliacoes" | "preco" | "trending";

const ORDENACOES: { valor: Ordenacao; icone?: string }[] = [
  { valor: "jogadores", icone: "trending_up" },
  { valor: "avaliacoes" },
  { valor: "preco" },
  { valor: "trending", icone: "local_fire_department" },
];

const MODOS_CATALOGO = [
  { id: "tabela", icone: "table_rows" },
  { id: "cartoes", icone: "grid_view" },
] as const;
type ModoCatalogo = (typeof MODOS_CATALOGO)[number]["id"];

const CHIP_CLASSIFICACAO = {
  positiva: "bg-tertiary/10 text-tertiary",
  neutra: "bg-surface-container-highest text-on-surface-variant",
  negativa: "bg-error/10 text-error",
} as const;

export function SteamPagina({ periodo }: { periodo?: number } = {}) {
  const { t } = useTranslation();
  const navegar = useNavigate();
  const campoBusca = useRef<HTMLInputElement>(null);

  const [busca, setBusca] = useState("");
  const [genero, setGenero] = useState("");
  const [categoria, setCategoria] = useState("");
  const [ordenacao, setOrdenacao] = useState<Ordenacao>("jogadores");

  // "Trending" nao existe no backend: ele ordena pela variacao, que e calculada
  // aqui sobre a lista ja carregada. Para a API, a consulta continua sendo a
  // mesma de "mais jogados".
  const jogos = useJogosSteam({
    busca: busca.trim() || undefined,
    genero: genero || undefined,
    categoria: categoria || undefined,
    ordenar_por: ordenacao === "trending" ? "jogadores" : ordenacao,
    limite: 500,
  });
  const [modo, setModo] = useModoPersistente<ModoCatalogo>(
    "playdb:steam-catalogo-modo",
    ["tabela", "cartoes"],
    "tabela",
  );
  const generos = useGenerosSteam();
  const categorias = useCategoriasSteam();
  // O total do catalogo vem da contagem real da dimensao. Antes saia de
  // `Math.max` das contagens por genero - e um jogo conta em TODOS os
  // generos dele, entao o maior genero nunca foi o catalogo. Com 45 jogos
  // e 37 de Action, a tela dizia "exibindo 45 de 37".
  const visaoGeral = useVisaoGeral();
  const serieTotal = useSerieTotalSteam(periodo);
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

  // O topo do ranking e a serie de cada linha. `useMemo` porque a lista de
  // ids vira a chave da consulta em lote - recalcular a cada render dispararia
  // uma requisicao nova por render.
  const topoRanking = useMemo(
    () => lista.filter((j) => j.jogadores_simultaneos !== null).slice(0, NO_RANKING),
    [lista],
  );
  const idsRanking = useMemo(() => topoRanking.map((j) => j.app_id), [topoRanking]);
  const seriesRanking = useSeriesJogadoresSteam(idsRanking, periodo);
  const seriesPorJogo = useMemo(
    () => new Map((seriesRanking.data ?? []).map((s) => [s.app_id, s.valores])),
    [seriesRanking.data],
  );

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

  const paginacao = usePaginacaoLocal(linhas, {
    porPaginaInicial: { mobile: 5, desktop: 25 },
    chaveReset: `${termoBuscado}|${genero}|${categoria}|${ordenacao}`,
  });

  //: O vazio dos paineis de telemetria.
  //:
  //: Os KPIs e o ranking agregam SO o que foi coletado - jogo da loja nao tem
  //: jogadores nem historico para somar. Quando a busca nao acha nada no banco
  //: mas acha na loja, dizer "nenhum jogo bate com esse filtro" seria falso: a
  //: tabela logo abaixo esta cheia. A mensagem tem de dizer que o que falta e a
  //: TELEMETRIA, e apontar para onde os resultados estao.
  const vazioDaTelemetria =
    daLoja.length > 0
      ? t("catalogoSteam.tabela.semTelemetria")
      : t("catalogoSteam.tabela.nenhumJogo");

  const modosCatalogo = MODOS_CATALOGO.map((modo) => ({
    ...modo,
    rotulo: t(`catalogoSteam.modos.${modo.id}`),
  }));

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

  // Os MONITORADOS (com ficha), nao a dimensao inteira: desde a varredura
  // de ofertas ela tem ~18 mil apps sem ficha, que esta tela nao lista.
  const totalCatalogo = visaoGeral.data?.jogos_steam_monitorados ?? 0;

  return (
    <>
      {/* ==================== BUSCA, ORDENAÇÃO E GÊNEROS ====================

          O cabeçalho display-hero ("JOGOS DA STEAM" + status do pipeline) saiu
          daqui: a barra de contexto do `CatalogoLayout` já diz onde estamos, e
          dois títulos empilhados só empurravam a tabela pra baixo. Sobrou o
          que a pessoa de fato usa — buscar, ordenar, filtrar por gênero. */}
      <section className="space-y-space-md">
        <div className="flex flex-col justify-between gap-space-md lg:flex-row lg:items-center">
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
              placeholder={t("catalogoSteam.buscarPlaceholder")}
              aria-label={t("catalogoSteam.buscarAriaLabel")}
              className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-20 font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
            />
            <kbd className="absolute right-space-sm top-1/2 -translate-y-1/2 rounded bg-surface-container px-space-xs py-space-xxs font-label-caps text-label-caps text-outline">
              Ctrl+K
            </kbd>
          </div>

          {/* Gênero (Ação, Terror, Aventura...) e categoria (`recursos`:
              Single-player, Co-op, Conquistas...) são os dois filtros de
              característica do catálogo. `SeletorFiltro` em vez de `<select>`
              nativo: a lista aberta de um `<select>` é o navegador quem
              desenha (painel branco do sistema, sem nada do tema escuro) -
              com as 50+ categorias da Steam isso ficava feio o bastante para
              destoar da tela inteira. */}
          <SeletorFiltro
            rotulo={t("catalogoSteam.genero")}
            valor={genero}
            aoEscolher={setGenero}
            rotuloTudo={t("catalogoSteam.todos", { contagem: totalCatalogo || 0 })}
            opcoes={(generos.data ?? []).map((item: AgregadoGenero) => ({
              valor: item.genero,
              rotulo: `${item.genero} (${item.jogos})`,
            }))}
          />

          <SeletorFiltro
            rotulo={t("catalogoSteam.categoria")}
            valor={categoria}
            aoEscolher={setCategoria}
            rotuloTudo={t("catalogoSteam.todas")}
            buscavel
            opcoes={(categorias.data ?? []).map((item) => ({
              valor: item.categoria,
              rotulo: `${item.categoria} (${item.jogos})`,
            }))}
          />

          <div className="flex flex-wrap items-center gap-space-xs">
            <span className="mr-space-xs hidden font-label-caps text-label-caps uppercase text-outline sm:inline">
              {t("catalogoSteam.ordenar")}
            </span>
            {ORDENACOES.map((opcao) => {
              const indisponivel = opcao.valor === "trending" && !temVariacao;
              return (
                <Pilula
                  key={opcao.valor}
                  ativa={ordenacao === opcao.valor}
                  desabilitada={indisponivel}
                  titulo={indisponivel ? t("catalogoSteam.trendingIndisponivel") : undefined}
                  icone={opcao.icone}
                  corIcone={opcao.valor === "trending" ? "text-error" : undefined}
                  aoClicar={() => setOrdenacao(opcao.valor)}
                >
                  {t(`catalogoSteam.ordenacoes.${opcao.valor}`)}
                </Pilula>
              );
            })}
          </div>
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

          // Série de "jogos com telemetria por janela" - o mesmo payload de
          // `serie-total`, segunda coluna. Não é uma segunda chamada.
          const valoresJogos = serie.map((p) => p.jogos ?? 0);
          const variacaoJogos =
            valoresJogos.length > 1 && valoresJogos.at(-2)
              ? ((valoresJogos.at(-1)! - valoresJogos.at(-2)!) / valoresJogos.at(-2)!) * 100
              : null;

          return (
            <section className="grid grid-cols-1 gap-space-base sm:grid-cols-2 xl:grid-cols-4">
              <KpiHud
                etiqueta={t("catalogoSteam.kpis.concurrentUsers")}
                canto={
                  genero || categoria
                    ? t("catalogoSteam.kpis.filtro", {
                        filtro: [genero, categoria].filter(Boolean).join(" + ").toUpperCase(),
                      })
                    : t("catalogoSteam.kpis.catalogoInteiro")
                }
                valor={fmtNumero(somaJogadores)}
                valorNumerico={somaJogadores}
                formatarValor={fmtNumero}
                rotulo={t("catalogoSteam.kpis.jogadoresConectados")}
                variacao={variacaoTotal}
                notaVariacao={t("catalogoSteam.kpis.vsColetaAnterior")}
                acento="primaria"
              >
                <Sparkline valores={valoresSerie} />
              </KpiHud>

              <KpiHud
                etiqueta={t("catalogoSteam.kpis.indexedEntities")}
                canto={saude.data?.status === "ok" ? t("catalogoSteam.kpis.ok") : t("catalogoSteam.kpis.semContato")}
                valor={fmtNumero(emTela.length)}
                valorNumerico={emTela.length}
                formatarValor={fmtNumero}
                rotulo={t("catalogoSteam.kpis.jogosMonitoradosAtivos")}
                variacao={variacaoJogos}
                notaVariacao={t("catalogoSteam.kpis.vsColetaAnterior")}
                acento="secundaria"
              >
                <Sparkline valores={valoresJogos} className="text-secondary" />
              </KpiHud>

              <KpiHud
                etiqueta={t("catalogoSteam.kpis.peakCcu")}
                canto={t("catalogoSteam.kpis.somaDosPicos")}
                valor={fmtCurto(somaPicos)}
                valorNumerico={somaPicos}
                formatarValor={fmtCurto}
                rotulo={t("catalogoSteam.kpis.maiorAudiencia")}
                acento="terciaria"
                notaVariacao={
                  somaJogadores && somaPicos
                    ? t("catalogoSteam.kpis.agoraNoPico", {
                        percentual: ((somaJogadores / somaPicos) * 100).toFixed(0),
                      })
                    : undefined
                }
              >
                <div className="mt-space-md">
                  <BarraFina
                    largura={somaPicos ? Math.min(100, (somaJogadores / somaPicos) * 100) : 0}
                    className="bg-gradient-to-r from-tertiary-container to-tertiary"
                    altura="h-2"
                  />
                </div>
              </KpiHud>

              {/* Cobertura da coleta: quantos dos jogos em tela chegaram a ter
                  uma janela de telemetria. `Segmentos` em vez de sparkline
                  porque é uma proporção de agora, não uma série no tempo. */}
              <KpiHud
                etiqueta={t("catalogoSteam.kpis.cobertura")}
                canto={t("catalogoSteam.kpis.gratuitos", { contagem: gratuitos })}
                valor={fmtPercentual(
                  emTela.length
                    ? (emTela.filter((j) => j.janela_coleta).length / emTela.length) * 100
                    : null,
                  0,
                )}
                rotulo={t("catalogoSteam.kpis.comTelemetria", {
                  contagem: emTela.filter((j) => j.janela_coleta).length,
                })}
                acento="primaria"
              >
                <Segmentos
                  acesos={Math.round(
                    (emTela.filter((j) => j.janela_coleta).length /
                      Math.max(emTela.length, 1)) *
                      6,
                  )}
                />
              </KpiHud>
            </section>
          );
        }}
      </Consulta>

      {/* ==================== RANKING ==================== */}
      <section className="space-y-space-md rounded-xl bg-surface-container-low p-space-base shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-space-sm">
          <div className="flex flex-col">
            <h2 className="flex items-center gap-space-xs font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
              <Icone nome="leaderboard" className="text-[20px] text-primary-container" />
              {t("catalogoSteam.ranking.titulo")}
            </h2>
            <span className="mt-0.5 font-title-code text-title-code text-outline">
              {t("catalogoSteam.ranking.subtitulo")}
            </span>
          </div>
          <div className="flex items-center gap-space-md">
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {t("catalogoSteam.ranking.maxReferencia")}{" "}
              <span className="text-primary">
                {fmtNumero(lista[0]?.jogadores_simultaneos)}
              </span>
            </span>
            {/* "Ver todos" leva à lista completa, que é a tabela logo abaixo:
                ordena por jogadores e rola até ela. Não há uma terceira tela de
                ranking para onde apontar - e inventar uma rota morta seria pior
                que o link não existir. */}
            <button
              type="button"
              onClick={() => {
                setOrdenacao("jogadores");
                document
                  .getElementById("telemetria-catalogo")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className="flex shrink-0 items-center gap-space-xxs rounded font-title-code text-title-code text-primary transition-colors hover:text-primary-container focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
            >
              {t("catalogoSteam.ranking.verTodos")}
              <Icone nome="arrow_forward" className="text-[14px]" />
            </button>
          </div>
        </div>

        <Consulta estado={jogos} vazio={vazioDaTelemetria}>
          {() =>
            topoRanking.length === 0 ? (
              <p className="py-space-lg text-center font-body-sm text-body-sm text-on-surface-variant">
                {vazioDaTelemetria}
              </p>
            ) : (
              <RankingJogos
                itens={topoRanking.map((jogo) => ({
                  app_id: jogo.app_id,
                  nome: jogo.nome,
                  imagem_header: jogo.imagem_header,
                  generos: jogo.generos,
                  jogadores_simultaneos: jogo.jogadores_simultaneos,
                  variacao: jogo.variacao_jogadores,
                  serie: seriesPorJogo.get(jogo.app_id) ?? [],
                }))}
                aoAbrir={(appId) => navegar(`/steam/${appId}`)}
              />
            )
          }
        </Consulta>
      </section>

      {/* ==================== TABELA DE TELEMETRIA ==================== */}
      <section
        id="telemetria-catalogo"
        className="scroll-mt-space-lg space-y-space-md rounded-xl bg-surface-container-low p-space-base shadow-2xl"
      >
        <div className="flex flex-col justify-between gap-space-base lg:flex-row lg:items-center">
          <div className="flex flex-col">
            <h2 className="flex items-center gap-space-xs font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
              <Icone nome="table_rows" className="text-[20px] text-primary-container" />
              {t("catalogoSteam.tabela.titulo")}
            </h2>
            <span className="mt-0.5 font-title-code text-title-code text-outline">
              {t("catalogoSteam.tabela.exibindo", {
                lista: lista.length,
                total: totalCatalogo || lista.length,
              })}
              {daLoja.length > 0 &&
                t("catalogoSteam.tabela.maisDaLoja", { contagem: daLoja.length })}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-space-sm">
            <SeletorModo modos={modosCatalogo} valor={modo} aoMudar={setModo} />
            <Botao icone="file_download" aoClicar={() => exportarCsv(lista)}>
              {t("catalogoSteam.tabela.exportarCsv")}
            </Botao>
          </div>
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
              ? t("catalogoSteam.tabela.buscandoNaLoja")
              : t("catalogoSteam.tabela.nenhumJogo")
          }
        >
          {() =>
            modo === "cartoes" ? (
              <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 xl:grid-cols-3">
                {paginacao.fatia.map((linha) => (
                  <CartaoJogoSteam
                    key={linha.tipo === "loja" ? `l${linha.candidato.app_id}` : linha.jogo.app_id}
                    linha={linha}
                    aoClicar={() => abrir(linha)}
                    carregando={
                      linha.tipo === "loja" &&
                      coletar.isPending &&
                      coletar.variables === linha.candidato.app_id
                    }
                  />
                ))}
              </div>
            ) : (
            <TabelaRolavel minLargura="60rem">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                    <th className="px-space-md py-space-sm">{t("catalogoSteam.tabela.colunas.jogo")}</th>
                    <th className="px-space-md py-space-sm">{t("catalogoSteam.tabela.colunas.generos")}</th>
                    <th className="px-space-md py-space-sm">{t("catalogoSteam.tabela.colunas.jogadoresSimultaneos")}</th>
                    <th className="px-space-md py-space-sm">{t("catalogoSteam.tabela.colunas.avaliacoes")}</th>
                    <th className="px-space-md py-space-sm">{t("catalogoSteam.tabela.colunas.classificacao")}</th>
                    <th className="px-space-md py-space-sm">{t("catalogoSteam.tabela.colunas.preco")}</th>
                    <th className="px-space-md py-space-sm">{t("catalogoSteam.tabela.colunas.ultimaColeta")}</th>
                    <th className="px-space-md py-space-sm text-right">{t("catalogoSteam.tabela.colunas.acoes")}</th>
                  </tr>
                </thead>

                <tbody className="font-body-md text-body-sm">
                  {paginacao.fatia.map((linha, indice) => {
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
                            <CapaJogo appId={jogo.app_id} nome={jogo.nome} imagemUrl={jogo.imagem_header} />
                            <div className="flex min-w-0 flex-col">
                              <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">
                                {jogo.nome}
                              </span>
                              <div className="flex items-center gap-space-xs font-title-code text-title-code text-outline">
                                <span>{t("catalogoSteam.tabela.appId")}</span>
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
                              {t("catalogoSteam.tabela.pico", { contagem: fmtNumero(jogo.pico_jogadores) })}
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
                              className="h-2 w-2 rounded-full bg-tertiary-container shadow-[0_0_4px_#40d19e]"
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
            </TabelaRolavel>
            )
          }
        </Consulta>

        <Paginacao
          pagina={paginacao.pagina}
          totalPaginas={paginacao.totalPaginas}
          porPagina={paginacao.porPagina}
          opcoesPorPagina={[5, 15, 25, 50]}
          aoMudarPagina={paginacao.setPagina}
          aoMudarPorPagina={paginacao.setPorPagina}
          resumo={t("catalogoSteam.paginacao.exibindo", {
            fatia: fmtNumero(paginacao.fatia.length),
            total: fmtNumero(linhas.length),
          })}
        />

        <div className="flex flex-wrap items-center justify-between gap-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span>
            {t("catalogoSteam.rodape.pipeline")}{" "}
            <span className={saude.data?.status === "ok" ? "text-tertiary" : "text-error"}>
              {saude.data?.status === "ok" ? t("catalogoSteam.rodape.ativo") : t("catalogoSteam.rodape.semContato")}
            </span>
          </span>
          <span>
            {t("catalogoSteam.rodape.ingest", {
              contagem: serieTotal.data?.length ?? 0,
              palavra: t(
                serieTotal.data?.length === 1
                  ? "catalogoSteam.rodape.coleta"
                  : "catalogoSteam.rodape.coletas",
              ),
            })}
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
  const { t } = useTranslation();
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
          <CapaJogo appId={candidato.app_id} nome={candidato.nome} imagemUrl={candidato.imagem} />
          <div className="flex min-w-0 flex-col">
            <span className="flex items-center gap-space-xs">
              <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">
                {candidato.nome}
              </span>
              <span className="shrink-0 rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-outline">
                {t("catalogoSteam.tabela.daLoja")}
              </span>
            </span>
            <div className="flex items-center gap-space-xs font-title-code text-title-code text-outline">
              <span>{t("catalogoSteam.tabela.appId")}</span>
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
          {carregando ? t("catalogoSteam.tabela.buscandoDados") : t("catalogoSteam.tabela.semColeta")}
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
