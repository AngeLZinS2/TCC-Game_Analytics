/**
 * Recomendacoes por reviews: o que o publico da Steam achou de um jogo.
 *
 * A TELA se chama "Recomendacoes por Reviews" porque e isso que ela mostra - a
 * recomendacao do publico. O MODELO por tras continua sendo um classificador de
 * sentimento (`ml/sentimento.py`, `/api/ml/sentimento/*`): esse e o nome
 * tecnico da tecnica, e renomear tambem o backend misturaria as duas coisas.
 *
 * A tela abre num jogo em destaque - arte, ficha e a recepcao do publico, no
 * mesmo formato que a loja da Steam usa - e uma busca troca qual jogo esta em
 * foco. Todo o resto da tela (tendencia, aspectos, avaliacoes) segue o jogo
 * escolhido.
 *
 * A tela separa duas coisas que se parecem e nao sao:
 *
 * * **Observado** - o destaque, a tendencia e os aspectos contam o
 *   `recomendado`, que e o polegar que o proprio autor deu. Nao passa pelo
 *   modelo.
 * * **Previsto** - o classificador ao vivo e a coluna de probabilidade na lista
 *   de avaliacoes. Ai sim e o modelo falando.
 *
 * Cada bloco diz de qual dos dois ele e. Misturar daria ao modelo credito por
 * um dado que veio observado.
 */

import { useEffect, useMemo, useState } from "react";

import {
  useAvaliacoesClassificadas,
  useBuscaCatalogo,
  useColetarJogo,
  useClassificarSentimento,
  useComparacaoSentimento,
  useJogosSteam,
  usePanoramaSentimento,
} from "../api/consultas";
import type {
  AvaliacaoClassificada,
  ComparacaoSentimento,
  JogoSentimento,
  JogoSteam,
  PanoramaSentimento,
} from "../api/tipos";
import { Consulta, Icone, MensagemErro, Selo } from "../componentes/base";
import { ArteJogo, CapaJogo } from "../componentes/CapaJogo";
import { AreaNeon } from "../componentes/graficos/AreaNeon";
import { BarraFina, KpiHud, Painel, Pilula } from "../componentes/hud";
import { PALETA_POLOS, TOKENS } from "../tema";
import {
  classificacaoSteam,
  fmtCurto,
  fmtDataCurta,
  fmtDataHora,
  fmtDecimal,
  fmtMoeda,
  fmtNumero,
  fmtPercentual,
  fmtRelativo,
} from "../utilitarios/formatos";

/** Exemplos que mostram o modelo funcionando e falhando. */
const EXEMPLOS = [
  "absolutely amazing game, best combat i have played in years",
  "crashes every 10 minutes, terrible optimization and the devs do not care",
  "great game if you enjoy suffering and losing all your friends",
];

/** Abaixo disso, uma porcentagem de aspecto é ruído. */
const MINIMO_POR_ASPECTO = 5;

const CHIP_CLASSIFICACAO = {
  positiva: "bg-tertiary/10 text-tertiary",
  neutra: "bg-surface-container-highest text-on-surface-variant",
  negativa: "bg-error/10 text-error",
} as const;

/** A cor de uma taxa de positividade, na escala divergente dos 50%. */
function corDaTaxa(percentual: number): string {
  if (percentual >= 60) return PALETA_POLOS.positivo;
  if (percentual <= 45) return PALETA_POLOS.negativo;
  return TOKENS.contorno;
}

/**
 * O que a faixa de busca mostra: um jogo, venha ele do banco ou do catálogo.
 *
 * `coletado` diz de onde veio, e é a única diferença de comportamento.
 */
type ResultadoBusca = {
  app_id: number;
  nome: string;
  coletado: boolean;
  /** A capa real: `imagem_header` para quem já está no banco, `tiny_image`
   *  da busca da loja para o resto. Sem ela, o palpite de CDN dá 404 nos
   *  jogos novos e o resultado aparece só com a inicial do nome. */
  imagem: string | null;
};

/**
 * Um cartão da faixa de busca.
 *
 * **O mesmo cartão serve para os dois casos**, e isso é deliberado. Quem abre
 * esta tela quer ver a recepção de um jogo — não administrar um pipeline. O
 * botão "Coletar" que existia aqui era uma etapa que só existia porque o
 * sistema precisava dela, não a pessoa: ela já havia dito o que queria ao
 * clicar. Agora o clique dispara a coleta por baixo e seleciona o jogo quando
 * ela termina.
 *
 * O que NÃO se esconde é a espera. Um jogo que já está no banco responde na
 * hora; um que vem da Steam leva alguns segundos, porque nesse intervalo o
 * sistema está buscando as avaliações de verdade. Por isso o estado de carga
 * toma o cartão inteiro em vez de um spinner discreto: a demora é real e fingir
 * que não existe deixaria a tela parecendo travada.
 */
function CardJogo({
  resultado,
  selecionado,
  carregando,
  aoClicar,
}: {
  resultado: ResultadoBusca;
  selecionado: boolean;
  carregando: boolean;
  aoClicar: () => void;
}) {
  return (
    <button
      type="button"
      onClick={aoClicar}
      disabled={carregando}
      title={resultado.nome}
      aria-busy={carregando}
      className={`relative flex w-40 shrink-0 flex-col gap-space-xs rounded-lg p-space-sm text-left transition-colors ${
        selecionado
          ? "bg-surface-container ring-1 ring-primary-container"
          : "bg-surface-container-lowest hover:bg-surface-container"
      }`}
    >
      <CapaJogo
        appId={resultado.app_id}
        nome={resultado.nome}
        imagemUrl={resultado.imagem}
        className="h-14 w-full"
      />
      <span className="truncate font-title-code text-title-code text-on-surface">
        {resultado.nome}
      </span>

      {carregando && (
        <span className="absolute inset-0 flex flex-col items-center justify-center gap-space-xxs rounded-lg bg-surface-container-lowest/90">
          <Icone
            nome="progress_activity"
            className="animate-spin text-[22px] text-primary-container"
          />
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            buscando avaliações
          </span>
        </span>
      )}
    </button>
  );
}

/**
 * A busca de jogo, sobre o catálogo COMPLETO da Steam.
 *
 * Duas fontes ao mesmo tempo, e de propósito a tela não as distingue:
 *
 * * **O que já está no banco** aparece sem digitar nada e responde na hora.
 * * **O catálogo da Steam** entra a partir de dois caracteres — ali estão os
 *   ~200 mil apps da loja.
 *
 * Trazer os 200 mil para dentro não é opção: seriam milhões de avaliações e
 * semanas de coleta, para um banco em que a maior parte nunca seria consultada.
 * A saída é inverter a ordem — em vez de coletar tudo e depois deixar buscar,
 * a busca é que decide o que coletar, e coleta **só o jogo pedido, no momento
 * em que é pedido**.
 *
 * A busca no catálogo é debounced: cada tecla dispararia uma chamada à loja da
 * Steam, e ela tem limite de taxa por IP.
 */
function BuscaDeJogo({
  selecionado,
  aoSelecionar,
}: {
  selecionado: number | null;
  aoSelecionar: (appId: number) => void;
}) {
  const [texto, setTexto] = useState("");
  const [termoBuscado, setTermoBuscado] = useState("");

  // 450ms: o suficiente para uma palavra inteira ser digitada antes da chamada.
  useEffect(() => {
    const relogio = setTimeout(() => setTermoBuscado(texto.trim()), 450);
    return () => clearTimeout(relogio);
  }, [texto]);

  const coletados = useJogosSteam({
    busca: texto.trim() || undefined,
    ordenar_por: "jogadores",
    limite: 40,
  });
  const catalogo = useBuscaCatalogo(termoBuscado);
  const coletar = useColetarJogo();

  const naBase = coletados.data ?? [];
  const idsNaBase = new Set(naBase.map((jogo) => jogo.app_id));

  // Uma lista só. O `filter` evita o mesmo jogo aparecendo duas vezes, uma por
  // fonte; o que está no banco vem primeiro porque responde na hora.
  const resultados: ResultadoBusca[] = [
    ...naBase.map((jogo: JogoSteam) => ({
      app_id: jogo.app_id,
      nome: jogo.nome,
      coletado: true,
      imagem: jogo.imagem_header,
    })),
    ...(catalogo.data ?? [])
      .filter((candidato) => !idsNaBase.has(candidato.app_id))
      .map((candidato) => ({
        app_id: candidato.app_id,
        nome: candidato.nome,
        coletado: candidato.coletado,
        imagem: candidato.imagem,
      })),
  ];

  const buscando = termoBuscado.length >= 2 && catalogo.isFetching;

  function abrir(resultado: ResultadoBusca) {
    if (resultado.coletado) {
      aoSelecionar(resultado.app_id);
      return;
    }
    // Ainda não está no banco: busca as avaliações agora e só então seleciona,
    // senão a tela mudaria de jogo para mostrar um vazio.
    coletar.mutate(resultado.app_id, {
      onSuccess: (resumo) => aoSelecionar(resumo.app_id),
    });
  }

  return (
    <div className="space-y-space-md">
      <div className="relative">
        <Icone
          nome="manage_search"
          className="absolute left-space-sm top-1/2 -translate-y-1/2 text-[20px] text-primary-container"
        />
        <input
          type="search"
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          placeholder="Buscar qualquer jogo da Steam pelo nome…"
          aria-label="Buscar jogo"
          className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-space-sm font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
        />
        {buscando && (
          <span className="absolute right-space-sm top-1/2 -translate-y-1/2 font-label-caps text-label-caps uppercase tracking-widest text-outline">
            buscando na Steam…
          </span>
        )}
      </div>

      {coletar.isError && <MensagemErro erro={coletar.error} />}

      <div className="rolagem-discreta flex gap-space-sm overflow-x-auto pb-space-xs">
        {resultados.map((resultado) => (
          <CardJogo
            key={resultado.app_id}
            resultado={resultado}
            selecionado={resultado.app_id === selecionado}
            carregando={coletar.isPending && coletar.variables === resultado.app_id}
            aoClicar={() => abrir(resultado)}
          />
        ))}
      </div>

      {resultados.length === 0 && !buscando && (
        <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
          {termoBuscado.length < 2
            ? "Digite ao menos dois caracteres para buscar no catálogo da Steam."
            : "Nenhum jogo da Steam bate com essa busca."}
        </p>
      )}
    </div>
  );
}

/**
 * O cartão de destaque, no formato da loja da Steam.
 *
 * Mostra lado a lado duas leituras que costumam ser confundidas: a
 * classificação da Steam, que agrega TODAS as avaliações do jogo (milhões), e a
 * nossa, que agrega só as coletadas (centenas). Quando divergem, a diferença é
 * amostra — e a tela diz isso em vez de escolher uma.
 */
function DestaqueDoJogo({
  jogo,
  coletadas,
}: {
  jogo: JogoSteam;
  coletadas: JogoSentimento | undefined;
}) {
  const classificacao = classificacaoSteam(jogo.classificacao_steam);

  return (
    <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[460px_1fr]">
      <ArteJogo
        appId={jogo.app_id}
        nome={jogo.nome}
        imagemUrl={jogo.imagem_header}
        className="h-52 w-full"
      />

      <div className="flex flex-col justify-between gap-space-base">
        <div>
          <h2 className="font-display-hero text-display-hero uppercase leading-none tracking-tight text-on-surface">
            {jogo.nome}
          </h2>

          <p className="mt-space-sm font-title-code text-title-code uppercase text-outline">
            DEV:{" "}
            <span className="text-on-surface-variant">
              {jogo.desenvolvedora ?? "—"}
            </span>{" "}
            · APPID: <span className="text-on-surface-variant">{jogo.app_id}</span>
          </p>

          <div className="mt-space-sm flex flex-wrap gap-space-xs">
            {jogo.gratuito && <Selo cor="positivo">Gratuito</Selo>}
            {jogo.generos.slice(0, 4).map((genero) => (
              <span
                key={genero}
                className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-secondary"
              >
                {genero}
              </span>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-space-base sm:grid-cols-3">
          <div className="rounded-lg bg-surface-container-lowest p-space-base">
            <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Avaliações na Steam
            </div>
            {classificacao ? (
              <span
                className={`mt-space-xs inline-flex rounded px-space-sm py-space-xxs font-badge-status text-badge-status uppercase ${
                  CHIP_CLASSIFICACAO[classificacao.polaridade]
                }`}
              >
                {classificacao.texto}
              </span>
            ) : (
              <span className="text-outline">—</span>
            )}
            <div className="mt-space-xs font-title-code text-title-code text-on-surface-variant">
              {fmtPercentual(jogo.nota_avaliacoes, 0)} de{" "}
              {fmtCurto(jogo.numero_avaliacoes)} análises
            </div>
          </div>

          <div className="rounded-lg bg-surface-container-lowest p-space-base">
            <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Nas avaliações coletadas
            </div>
            <div
              className="mt-space-xs font-headline-md text-headline-md leading-none"
              style={{
                color: coletadas
                  ? corDaTaxa(coletadas.percentual_positivo)
                  : TOKENS.contorno,
              }}
            >
              {coletadas ? fmtPercentual(coletadas.percentual_positivo) : "—"}
            </div>
            <div className="mt-space-xs font-title-code text-title-code text-on-surface-variant">
              {coletadas
                ? `${fmtNumero(coletadas.positivas)} de ${fmtNumero(coletadas.avaliacoes)} com texto`
                : "nenhuma coletada"}
            </div>
          </div>

          <div className="rounded-lg bg-surface-container-lowest p-space-base">
            <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Preço · jogadores agora
            </div>
            <div className="mt-space-xs font-headline-md text-headline-md leading-none text-primary">
              {fmtMoeda(jogo.preco_no_momento, jogo.moeda)}
            </div>
            <div className="mt-space-xs font-title-code text-title-code text-on-surface-variant">
              {fmtNumero(jogo.jogadores_simultaneos)} simultâneos
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** O classificador ao vivo: um texto entra, uma probabilidade sai. */
function Classificador({ modelo }: { modelo?: string }) {
  const [texto, setTexto] = useState(EXEMPLOS[0]);
  const resultado = useClassificarSentimento(texto, modelo);

  const probabilidade = resultado.data?.probabilidade_positiva;
  const positiva = (probabilidade ?? 0.5) >= 0.5;

  return (
    <div className="space-y-space-base">
      <textarea
        value={texto}
        onChange={(evento) => setTexto(evento.target.value)}
        rows={4}
        aria-label="Texto da avaliação"
        placeholder="Escreva ou cole uma avaliação em inglês…"
        className="w-full resize-y rounded bg-surface-container-lowest p-space-md font-body-md text-body-md text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
      />

      <div className="flex flex-wrap gap-space-xs">
        {EXEMPLOS.map((exemplo, indice) => (
          <Pilula key={exemplo} ativa={texto === exemplo} aoClicar={() => setTexto(exemplo)}>
            Exemplo {indice + 1}
          </Pilula>
        ))}
      </div>

      {resultado.isError ? (
        <MensagemErro erro={resultado.error} />
      ) : probabilidade === undefined ? (
        <p className="font-body-sm text-body-sm text-outline">
          Escreva pelo menos três caracteres.
        </p>
      ) : (
        <div className="rounded-lg bg-surface-container-lowest p-space-lg">
          <div className="flex items-end justify-between gap-space-base">
            <div>
              <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Probabilidade de recomendação
              </div>
              <div
                className="font-display-hero text-display-hero leading-none tracking-tight"
                style={{ color: positiva ? PALETA_POLOS.positivo : PALETA_POLOS.negativo }}
              >
                {fmtPercentual(probabilidade * 100)}
              </div>
            </div>
            <Selo cor={positiva ? "positivo" : "negativo"}>
              {positiva ? "Positiva" : "Negativa"}
            </Selo>
          </div>

          <div className="mt-space-base">
            <BarraFina
              largura={probabilidade * 100}
              cor={positiva ? PALETA_POLOS.positivo : PALETA_POLOS.negativo}
              altura="h-2"
            />
          </div>

          {resultado.data?.curto && (
            <p className="mt-space-sm flex items-start gap-space-xs font-body-sm text-body-sm text-outline">
              <Icone nome="warning" className="mt-[2px] text-[16px] text-error" />
              Texto mais curto que o mínimo usado no treino — a resposta sai, mas vale
              menos: o modelo nunca viu frases desse tamanho.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function RecomendacoesReviewsPagina() {
  const [modelo, setModelo] = useState<string | undefined>();
  const [appId, setAppId] = useState<number | null>(null);
  const [apenasErros, setApenasErros] = useState(false);

  const comparacao = useComparacaoSentimento();
  const panoramaGeral = usePanoramaSentimento(null);
  const panorama = usePanoramaSentimento(appId);
  const avaliacoes = useAvaliacoesClassificadas(appId, apenasErros, modelo);
  const catalogo = useJogosSteam({ ordenar_por: "jogadores", limite: 200 });

  // Abre no jogo com mais avaliacoes coletadas: e o que tem mais o que mostrar.
  useEffect(() => {
    if (appId !== null || !panoramaGeral.data?.por_jogo.length) return;
    setAppId(panoramaGeral.data.por_jogo[0].app_id);
  }, [appId, panoramaGeral.data]);

  const jogoSelecionado = useMemo(
    () => (catalogo.data ?? []).find((jogo) => jogo.app_id === appId),
    [catalogo.data, appId],
  );
  const coletadasDoJogo = useMemo(
    () => panoramaGeral.data?.por_jogo.find((jogo) => jogo.app_id === appId),
    [panoramaGeral.data, appId],
  );

  if (comparacao.isError) {
    return (
      <Painel icone="sentiment_satisfied" titulo="Sentimento de reviews">
        <MensagemErro erro={comparacao.error} />
        <p className="mt-space-base font-body-md text-body-md text-on-surface-variant">
          Colete o texto das avaliações e treine com{" "}
          <code className="rounded bg-surface-container px-space-xs py-space-xxs font-title-code text-title-code text-primary">
            python cli.py collect steam
          </code>{" "}
          e{" "}
          <code className="rounded bg-surface-container px-space-xs py-space-xxs font-title-code text-title-code text-primary">
            python cli.py train-sentimento
          </code>
          .
        </p>
      </Painel>
    );
  }

  const ativo = modelo ?? comparacao.data?.modelo_ativo;
  const metricas = comparacao.data?.modelos.find((m) => m.chave === ativo);
  const comTermos = comparacao.data?.modelos.find((m) => m.termos?.positivos?.length);

  return (
    <Consulta estado={comparacao} altura={320}>
      {(relatorio: ComparacaoSentimento) => (
        <>
          {/* ==================== CABECALHO ==================== */}
          <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-col gap-space-xs">
              <div className="flex flex-wrap items-center gap-space-sm">
                <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-primary drop-shadow-[0_0_12px_rgba(0,229,255,0.4)]">
                  Recomendações por Reviews
                </h1>
                <Selo cor="primario">NLP</Selo>
                <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
                  ML // Deck 07
                </span>
              </div>

              <p className="font-body-sm text-body-sm text-on-surface-variant">
                O rótulo não foi anotado à mão: é o <strong>polegar do próprio autor</strong>{" "}
                (<code className="text-primary">voted_up</code>). O modelo aprende a relação
                entre o texto escrito e o voto de quem escreveu — treinado sobre{" "}
                {fmtNumero(relatorio.conjunto.avaliacoes)} avaliações em {relatorio.idioma},
                de {relatorio.conjunto.jogos} jogos.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-space-xs">
              <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Modelo:
              </span>
              {relatorio.modelos.map((m) => (
                <Pilula
                  key={m.chave}
                  ativa={ativo === m.chave}
                  aoClicar={() => setModelo(m.chave)}
                  titulo={m.descricao}
                >
                  {m.nome}
                </Pilula>
              ))}
            </div>
          </section>

          {/* ==================== BUSCA + DESTAQUE ==================== */}
          <Painel
            icone="storefront"
            titulo="Jogo em destaque"
            descricao="Busque um jogo para ver a recepção do público e as estatísticas dele."
            meta={
              coletadasDoJogo ? (
                <Selo cor="primario">
                  {fmtNumero(coletadasDoJogo.avaliacoes)} avaliações coletadas
                </Selo>
              ) : undefined
            }
          >
            <BuscaDeJogo selecionado={appId} aoSelecionar={setAppId} />

            {jogoSelecionado ? (
              <DestaqueDoJogo jogo={jogoSelecionado} coletadas={coletadasDoJogo} />
            ) : (
              <div className="h-52 animate-pulse rounded-lg bg-surface-container-high/60" />
            )}
          </Painel>

          {/* ==================== KPIS DO JOGO ==================== */}
          <Consulta estado={panorama} altura={160}>
            {(dados: PanoramaSentimento) => {
              const taxa =
                (dados.positivas / Math.max(dados.avaliacoes, 1)) * 100;
              const geral = panoramaGeral.data
                ? (panoramaGeral.data.positivas /
                    Math.max(panoramaGeral.data.avaliacoes, 1)) *
                  100
                : null;

              const piorAspecto = [...dados.aspectos]
                .filter((a) => a.avaliacoes >= MINIMO_POR_ASPECTO)
                .sort((a, b) => a.percentual_positivo - b.percentual_positivo)[0];

              return (
                <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
                  <KpiHud
                    etiqueta="Recomendação observada"
                    canto="RÓTULO REAL"
                    valor={fmtPercentual(taxa)}
                    valorNumerico={taxa}
                    formatarValor={(v) => fmtPercentual(v)}
                    rotulo={jogoSelecionado?.nome ?? "jogo selecionado"}
                    acento="terciaria"
                    variacao={geral === null ? null : taxa - geral}
                    notaVariacao="vs. média do catálogo"
                  />
                  <KpiHud
                    etiqueta="Avaliações com texto"
                    canto="COLETADAS"
                    valor={fmtNumero(dados.avaliacoes)}
                    valorNumerico={dados.avaliacoes}
                    formatarValor={fmtNumero}
                    rotulo={`${fmtNumero(dados.positivas)} recomendam`}
                    acento="primaria"
                    notaVariacao={`${fmtNumero(dados.avaliacoes - dados.positivas)} não recomendam`}
                  />
                  <KpiHud
                    etiqueta="Aspecto mais criticado"
                    canto="PALAVRA-CHAVE"
                    valor={
                      piorAspecto ? fmtPercentual(piorAspecto.percentual_positivo, 0) : "—"
                    }
                    valorNumerico={piorAspecto?.percentual_positivo ?? null}
                    formatarValor={(v) => fmtPercentual(v, 0)}
                    rotulo={piorAspecto?.aspecto ?? "amostra insuficiente"}
                    acento="secundaria"
                    notaVariacao={
                      piorAspecto
                        ? `${fmtNumero(piorAspecto.avaliacoes)} avaliações citam`
                        : undefined
                    }
                  />
                  <KpiHud
                    etiqueta="ROC-AUC do modelo"
                    canto="ORDENAÇÃO"
                    valor={metricas ? fmtDecimal(metricas.roc_auc, 3) : "—"}
                    valorNumerico={metricas?.roc_auc ?? null}
                    formatarValor={(v) => fmtDecimal(v, 3)}
                    rotulo={metricas?.familia ?? ""}
                    acento="primaria"
                    notaVariacao={
                      metricas
                        ? `balanceada ${fmtPercentual(metricas.acuracia_balanceada * 100)}`
                        : undefined
                    }
                  />
                </section>
              );
            }}
          </Consulta>

          {/* ==================== TENDENCIA + ASPECTOS ==================== */}
          <Consulta estado={panorama} altura={280}>
            {(dados: PanoramaSentimento) => (
              <section className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
                <Painel
                  icone="show_chart"
                  titulo="Tendência de recomendação"
                  descricao="Percentual de avaliações positivas por dia de publicação. Contagem sobre o rótulo real."
                  meta={<Selo>{dados.por_dia.length} dias</Selo>}
                >
                  {dados.por_dia.length < 2 ? (
                    <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                      Só há {dados.por_dia.length} dia com avaliação publicada para este
                      jogo — a série ganha forma conforme a coleta cresce.
                    </p>
                  ) : (
                    <AreaNeon
                      pontos={dados.por_dia.map((ponto) => ({
                        rotulo: fmtDataCurta(ponto.dia),
                        valor: ponto.percentual_positivo,
                        detalhe: `${fmtPercentual(ponto.percentual_positivo)} de ${fmtNumero(ponto.avaliacoes)} avaliações`,
                      }))}
                      formatarValor={(valor) => `${Math.round(valor)}%`}
                      rodapeEsquerda={
                        <>
                          Média do período:{" "}
                          <strong className="font-title-code text-title-code text-on-surface">
                            {fmtPercentual(
                              (dados.positivas / Math.max(dados.avaliacoes, 1)) * 100,
                            )}
                          </strong>
                        </>
                      }
                      rodapeDireita={jogoSelecionado?.nome ?? ""}
                    />
                  )}
                </Painel>

                <Painel
                  icone="donut_large"
                  titulo="Recomendação por aspecto"
                  descricao="Entre as avaliações deste jogo que mencionam cada tema, quantas recomendam."
                  meta={<Selo>Filtro por palavra-chave</Selo>}
                >
                  <div className="space-y-space-sm">
                    {dados.aspectos.map((aspecto) => {
                      const poucos = aspecto.avaliacoes < MINIMO_POR_ASPECTO;

                      return (
                        <div
                          key={aspecto.aspecto}
                          className="flex items-center gap-space-sm"
                          title={`Termos: ${aspecto.termos.join(", ")}`}
                        >
                          <span className="w-32 shrink-0 truncate font-body-sm text-body-sm text-on-surface-variant">
                            {aspecto.aspecto}
                          </span>
                          <div className="flex-1">
                            <BarraFina
                              largura={aspecto.percentual_positivo}
                              cor={
                                poucos
                                  ? TOKENS.contornoSuave
                                  : corDaTaxa(aspecto.percentual_positivo)
                              }
                              opacidade={poucos ? 0.6 : 1}
                              altura="h-2"
                            />
                          </div>
                          <span
                            className="w-14 shrink-0 text-right font-title-code text-title-code tabular-nums"
                            style={{
                              color: poucos
                                ? TOKENS.contorno
                                : corDaTaxa(aspecto.percentual_positivo),
                            }}
                          >
                            {fmtPercentual(aspecto.percentual_positivo, 0)}
                          </span>
                          <span className="w-14 shrink-0 text-right font-label-caps text-label-caps text-outline">
                            {fmtNumero(aspecto.avaliacoes)}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  <p className="font-body-sm text-body-sm text-outline">
                    Aspectos com menos de {MINIMO_POR_ASPECTO} avaliações aparecem
                    apagados: com três menções, uma delas muda a porcentagem em 33 pontos.
                    E isto <strong>não é</strong> análise de sentimento por aspecto — é um
                    filtro por lista de palavras sobre o rótulo real, então ironia não é
                    detectada e uma avaliação que cita dois temas conta nos dois.
                  </p>
                </Painel>
              </section>
            )}
          </Consulta>

          {/* ==================== AVALIACOES DO JOGO ==================== */}
          <Painel
            icone="reviews"
            titulo={
              jogoSelecionado
                ? `Avaliações de ${jogoSelecionado.nome}`
                : "Avaliações classificadas"
            }
            descricao="Avaliações reais, com a previsão do modelo ao lado do voto que o autor deu."
            meta={
              <Pilula
                ativa={apenasErros}
                icone="error"
                aoClicar={() => setApenasErros((atual) => !atual)}
              >
                Só os erros
              </Pilula>
            }
          >
            <Consulta
              estado={avaliacoes}
              vazio={
                apenasErros
                  ? "O modelo acertou todas as avaliações desta amostra."
                  : "Nenhuma avaliação com texto para este jogo."
              }
            >
              {(lista: AvaliacaoClassificada[]) => (
                <div className="space-y-space-sm">
                  {lista.map((avaliacao) => {
                    const previstaPositiva = avaliacao.probabilidade_positiva >= 0.5;
                    const cor = previstaPositiva
                      ? PALETA_POLOS.positivo
                      : PALETA_POLOS.negativo;

                    return (
                      <article
                        key={avaliacao.id_externo}
                        className="rounded-lg bg-surface-container-lowest p-space-base"
                        style={{ boxShadow: `inset 3px 0 0 ${cor}` }}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-space-sm">
                          <div className="flex flex-wrap items-center gap-space-xs">
                            <Selo cor={avaliacao.recomendado ? "positivo" : "negativo"}>
                              Autor: {avaliacao.recomendado ? "recomenda" : "não recomenda"}
                            </Selo>
                            <span
                              className="inline-flex items-center gap-space-xxs rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase"
                              style={{ background: `${cor}1a`, color: cor }}
                            >
                              Modelo:{" "}
                              {fmtPercentual(avaliacao.probabilidade_positiva * 100, 0)}{" "}
                              positiva
                            </span>
                            {avaliacao.acertou ? (
                              <Selo cor="positivo">Acertou</Selo>
                            ) : (
                              <Selo cor="negativo">Errou</Selo>
                            )}
                          </div>

                          <span
                            className="font-label-caps text-label-caps uppercase tracking-widest text-outline"
                            title={fmtDataHora(avaliacao.criada_em)}
                          >
                            {fmtRelativo(avaliacao.criada_em)}
                            {avaliacao.minutos_jogados
                              ? ` · ${fmtNumero(Math.round(avaliacao.minutos_jogados / 60))}h jogadas`
                              : ""}
                          </span>
                        </div>

                        <p className="mt-space-sm whitespace-pre-line font-body-md text-body-md text-on-surface-variant">
                          {avaliacao.texto.length > 420
                            ? `${avaliacao.texto.slice(0, 420)}…`
                            : avaliacao.texto}
                        </p>
                      </article>
                    );
                  })}
                </div>
              )}
            </Consulta>

            <p className="font-body-sm text-body-sm text-outline">
              O filtro de erro existe para a tela não virar folheto: é onde dá para ver o
              que o modelo não aprendeu — ironia, avaliação misturando idiomas, elogio
              escrito com palavrão. Só avaliações em {relatorio.idioma} aparecem aqui, que
              é o idioma em que o modelo foi treinado.
            </p>
          </Painel>

          {/* ==================== O MODELO ==================== */}
          <section className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
            <Painel
              icone="model_training"
              titulo="Classificador ao vivo"
              descricao={`Texto novo, avaliado por ${metricas?.nome ?? "modelo ativo"}. Aqui é previsão, não contagem.`}
            >
              <Classificador modelo={ativo} />
            </Painel>

            <Painel
              icone="format_quote"
              titulo="Termos que o modelo aprendeu"
              descricao="Os pesos da regressão logística, que é o único dos três em que cada palavra tem um peso legível."
              meta={comTermos ? <Selo cor="primario">{comTermos.nome}</Selo> : undefined}
            >
              {comTermos ? (
                <div className="grid grid-cols-2 gap-space-base">
                  {(["positivos", "negativos"] as const).map((lado) => (
                    <div key={lado}>
                      <div
                        className="mb-space-sm font-label-caps text-label-caps uppercase tracking-widest"
                        style={{
                          color:
                            lado === "positivos"
                              ? PALETA_POLOS.positivo
                              : PALETA_POLOS.negativo,
                        }}
                      >
                        Puxam para {lado === "positivos" ? "positivo" : "negativo"}
                      </div>
                      <div className="flex flex-wrap gap-space-xs">
                        {comTermos.termos[lado].map(([termo, peso]) => (
                          <span
                            key={termo}
                            title={`peso ${peso}`}
                            className="rounded px-space-xs py-space-xxs font-title-code text-title-code"
                            style={{
                              background:
                                lado === "positivos"
                                  ? `${PALETA_POLOS.positivo}1a`
                                  : `${PALETA_POLOS.negativo}1a`,
                              color:
                                lado === "positivos"
                                  ? PALETA_POLOS.positivo
                                  : PALETA_POLOS.negativo,
                            }}
                          >
                            {termo}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="font-body-md text-body-md text-outline">
                  Nenhum modelo com peso por palavra treinado.
                </p>
              )}
            </Painel>
          </section>

          {/* ==================== COMPARATIVO ENTRE JOGOS ==================== */}
          <Consulta estado={panoramaGeral} altura={200}>
            {(geral: PanoramaSentimento) => (
              <Painel
                icone="leaderboard"
                titulo="Recepção por jogo"
                descricao="Todos os jogos monitorados, pelo rótulo real. Clique para colocar em destaque."
              >
                <div className="space-y-space-sm">
                  {geral.por_jogo.map((jogo) => (
                    <button
                      key={jogo.app_id}
                      type="button"
                      onClick={() => setAppId(jogo.app_id)}
                      className={`flex w-full items-center gap-space-sm rounded px-space-md py-space-sm text-left transition-colors ${
                        jogo.app_id === appId
                          ? "bg-surface-container ring-1 ring-primary-container"
                          : "hover:bg-surface-container-high/60"
                      }`}
                    >
                      <CapaJogo
                        appId={jogo.app_id}
                        nome={jogo.jogo}
                        className="h-8 w-16"
                      />
                      <span className="w-44 shrink-0 truncate font-headline-sm text-headline-sm text-on-surface">
                        {jogo.jogo}
                      </span>
                      <div className="flex-1">
                        <BarraFina
                          largura={jogo.percentual_positivo}
                          cor={corDaTaxa(jogo.percentual_positivo)}
                          altura="h-2"
                        />
                      </div>
                      <span
                        className="w-16 shrink-0 text-right font-title-code text-title-code tabular-nums"
                        style={{ color: corDaTaxa(jogo.percentual_positivo) }}
                      >
                        {fmtPercentual(jogo.percentual_positivo, 0)}
                      </span>
                      <span className="w-20 shrink-0 text-right font-label-caps text-label-caps text-outline">
                        {fmtNumero(jogo.avaliacoes)}
                      </span>
                    </button>
                  ))}
                </div>
              </Painel>
            )}
          </Consulta>
        </>
      )}
    </Consulta>
  );
}
