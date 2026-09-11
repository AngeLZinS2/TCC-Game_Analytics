/**
 * Detalhe de um jogo da Xbox Store.
 *
 * Vitrine, nao telemetria: a Microsoft nao publica CCU nem texto de avaliacao
 * em API gratuita. O que da pra mostrar e a ficha da loja (descricao, recursos,
 * classificacao, capturas), a nota agregada (estrela 0-5), o preco atual, a
 * serie que o coletor foi juntando e se o jogo esta no Game Pass. Sem grafico
 * de jogadores, sem modelo de ML - esses vivem na aba Steam.
 */

import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useBuscarResumoSteamXbox,
  useDesfavoritarJogo,
  useFavoritarJogo,
  useFavoritosJogos,
  useJogoXbox,
  useResumoSteamXbox,
} from "@models/api/consultas";
import type { DetalheJogoXbox, PontoSerieXbox } from "@models/api/tipos";
import { Aviso, Consulta, Icone, MensagemErro, Selo } from "@views/componentes/base";
import { BotaoFavoritar } from "@views/componentes/BotaoFavoritar";
import { CapaXbox } from "@views/componentes/CapaXbox";
import { CarrosselMidia } from "@views/componentes/CarrosselMidia";
import { AreaNeon } from "@views/componentes/graficos/AreaNeon";
import { KpiHud, Painel } from "@views/componentes/hud";
import { PALETA_POLOS, TOKENS } from "@views/tema";
import {
  fmtData,
  fmtDataCurta,
  fmtDecimal,
  fmtMoeda,
  fmtNumero,
  fmtRelativo,
  paraNumero,
} from "@util/formatos";

/** Verde de 4 pra cima, âmbar no meio, apagado abaixo de 3. */
function corDaNota(nota: number): string {
  if (nota >= 4) return PALETA_POLOS.positivo;
  if (nota >= 3) return TOKENS.secundaria;
  return TOKENS.textoSuave;
}

/**
 * Resumo por IA cruzado da versão Steam — a Xbox Store não publica texto de
 * avaliação (só a estrela agregada, já mostrada nos KPIs), então quando o
 * mesmo jogo também está no nosso catálogo Steam, mostramos o resumo de lá,
 * com a procedência bem explícita: quem lê precisa saber que é a opinião de
 * quem jogou a versão Steam, não a Xbox.
 */
function ResumoPorIAXbox({ productId }: { productId: string }) {
  const resumo = useResumoSteamXbox(productId);
  const buscar = useBuscarResumoSteamXbox();

  if (resumo.isLoading) {
    return (
      <Painel icone="auto_awesome" titulo="Resumo por IA">
        <div className="h-16 animate-pulse rounded-lg bg-surface-container-high/60" />
      </Painel>
    );
  }

  const dados = buscar.data ?? resumo.data;

  if (!dados) {
    return (
      <Painel
        icone="auto_awesome"
        titulo="Resumo por IA"
        descricao="A Xbox Store não publica texto de avaliação — só a nota agregada, já mostrada acima."
      >
        <Aviso>
          Ainda sem cruzamento pronto com o catálogo Steam. Se este jogo
          também existir lá, dá pra buscar agora.
        </Aviso>

        {buscar.isError && <MensagemErro erro={buscar.error} />}

        <button
          type="button"
          onClick={() => buscar.mutate(productId)}
          disabled={buscar.isPending}
          className="mt-space-sm inline-flex items-center gap-space-xs rounded bg-primary-container px-space-base py-space-xs font-title-code text-title-code text-on-primary transition-[filter] hover:brightness-110 disabled:opacity-60"
        >
          <Icone
            nome={buscar.isPending ? "progress_activity" : "travel_explore"}
            className={`text-[16px] ${buscar.isPending ? "animate-spin" : ""}`}
          />
          {buscar.isPending ? "Buscando na Steam…" : "Buscar avaliações na Steam"}
        </button>
      </Painel>
    );
  }

  const { resumo: r, steam_nome: steamNome } = dados;

  return (
    <Painel
      icone="auto_awesome"
      titulo="Resumo por IA"
      descricao="A Xbox Store não publica texto de avaliação — este resumo é da comunidade da versão Steam do mesmo jogo."
      meta={
        <div className="flex flex-wrap items-center gap-space-xs">
          <Selo cor="neutro">via Steam · {steamNome}</Selo>
          <span
            className="font-label-caps text-label-caps uppercase tracking-widest text-outline"
            title={r.modelo}
          >
            gerado {fmtRelativo(r.gerado_em)} · {fmtNumero(r.avaliacoes_usadas)} avaliações
            na amostra
          </span>
        </div>
      }
    >
      <p className="font-body-md text-[15px] leading-[1.65] text-on-surface">{r.texto}</p>

      {(r.positivos.length > 0 || r.negativos.length > 0) && (
        <div className="mt-space-base grid grid-cols-1 gap-space-base sm:grid-cols-2">
          {r.positivos.length > 0 && (
            <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low/50 p-space-base">
              <div
                className="flex items-center gap-space-xxs font-badge-status text-badge-status uppercase tracking-wide"
                style={{ color: PALETA_POLOS.positivo }}
              >
                <Icone nome="thumb_up" className="text-[13px]" />O que agradou
              </div>
              <ul className="mt-space-sm flex flex-col gap-space-xs">
                {r.positivos.map((ponto, i) => (
                  <li
                    key={i}
                    className="font-body-sm text-body-sm leading-snug text-on-surface-variant"
                  >
                    {ponto}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {r.negativos.length > 0 && (
            <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low/50 p-space-base">
              <div
                className="flex items-center gap-space-xxs font-badge-status text-badge-status uppercase tracking-wide"
                style={{ color: PALETA_POLOS.negativo }}
              >
                <Icone nome="thumb_down" className="text-[13px]" />O que incomodou
              </div>
              <ul className="mt-space-sm flex flex-col gap-space-xs">
                {r.negativos.map((ponto, i) => (
                  <li
                    key={i}
                    className="font-body-sm text-body-sm leading-snug text-on-surface-variant"
                  >
                    {ponto}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Painel>
  );
}

export function JogoXboxPagina() {
  const { productId } = useParams();
  const detalhe = useJogoXbox(productId);
  const favoritosJogos = useFavoritosJogos();
  const favoritar = useFavoritarJogo();
  const desfavoritar = useDesfavoritarJogo();
  const favoritado = favoritosJogos.data?.some(
    (f) => f.fonte === "xbox" && f.jogo_id === productId,
  );

  const precosSerie = useMemo(() => {
    const serie = detalhe.data?.serie ?? [];
    return serie
      .map((ponto: PontoSerieXbox) => ({
        rotulo: fmtDataCurta(ponto.janela_coleta),
        valor: paraNumero(ponto.preco_no_momento),
        detalhe: fmtMoeda(ponto.preco_no_momento, "BRL"),
      }))
      .filter(
        (p): p is { rotulo: string; valor: number; detalhe: string } => p.valor !== null,
      );
  }, [detalhe.data]);

  const notasSerie = useMemo(() => {
    const serie = detalhe.data?.serie ?? [];
    return serie
      .map((ponto: PontoSerieXbox) => ({
        rotulo: fmtDataCurta(ponto.janela_coleta),
        valor: paraNumero(ponto.nota),
        detalhe: `★ ${fmtDecimal(ponto.nota, 1)}`,
      }))
      .filter(
        (p): p is { rotulo: string; valor: number; detalhe: string } => p.valor !== null,
      );
  }, [detalhe.data]);

  return (
    <Consulta estado={detalhe} altura={280}>
      {(dados: DetalheJogoXbox) => {
        const { jogo, serie, midias } = dados;
        const menorPreco = precosSerie.length
          ? Math.min(...precosSerie.map((p) => p.valor))
          : null;
        const nota = paraNumero(jogo.nota);
        const notaRecente = paraNumero(jogo.nota_recente);
        const temFicha =
          jogo.recursos.length > 0 || jogo.tem_conquistas !== null;
        const temClassificacao =
          !!jogo.classificacao_etaria || jogo.descritores_conteudo.length > 0;

        return (
          <>
            {/* ==================== CABECALHO ==================== */}
            <section className="relative overflow-hidden rounded-xl bg-surface-container-low p-space-lg shadow-2xl">
              <div
                className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary-container/10 blur-3xl"
                aria-hidden
              />

              <Link
                to="/catalogo/xbox"
                className="relative z-10 inline-flex items-center gap-space-xxs font-title-code text-title-code text-outline transition-colors hover:text-primary"
              >
                <Icone nome="arrow_back" className="text-[16px]" />
                Voltar para o catálogo
              </Link>

              {/* Identidade à esquerda, galeria à direita — igual à ficha da
                  Steam (mesmo `CarrosselMidia`: trailer primeiro, capturas
                  depois). */}
              <div className="relative z-10 mt-space-sm grid grid-cols-1 items-center gap-space-lg lg:grid-cols-[minmax(0,1fr)_minmax(0,34rem)]">
                <div className="flex min-w-0 items-start gap-space-base">
                  <CapaXbox
                    nome={jogo.nome}
                    imagemUrl={jogo.imagem_capa ?? jogo.imagem_header}
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
                      rotulo="Favoritar jogo"
                      aoAlternar={() =>
                        favoritado
                          ? desfavoritar.mutate({ fonte: "xbox", jogo_id: jogo.product_id })
                          : favoritar.mutate({ fonte: "xbox", jogo_id: jogo.product_id })
                      }
                    />
                  </div>

                  <p className="mt-space-xs font-title-code text-title-code uppercase text-outline">
                    DEV:{" "}
                    <span className="text-on-surface-variant">
                      {jogo.desenvolvedora ?? "—"}
                    </span>{" "}
                    · PUB:{" "}
                    <span className="text-on-surface-variant">
                      {jogo.publicadora ?? "—"}
                    </span>
                    {jogo.data_lancamento && (
                      <>
                        {" "}
                        · LANÇAMENTO:{" "}
                        <span className="text-on-surface-variant">
                          {fmtData(jogo.data_lancamento)}
                        </span>
                      </>
                    )}
                  </p>

                  <div className="mt-space-sm flex flex-wrap items-center gap-space-xs">
                    {jogo.no_game_pass && (
                      <span className="inline-flex items-center gap-space-xxs rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary">
                        <Icone nome="check" className="text-[13px]" />
                        Game Pass
                      </span>
                    )}
                    {jogo.gratuito && (
                      <span className="rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary">
                        Gratuito
                      </span>
                    )}
                    {nota !== null && (
                      <span
                        className="inline-flex items-center gap-space-xxs rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status"
                        style={{ color: corDaNota(nota) }}
                      >
                        <Icone nome="star" className="text-[13px]" />
                        {fmtDecimal(nota, 1)}
                        {jogo.numero_avaliacoes ? (
                          <span className="text-outline">
                            · {fmtNumero(jogo.numero_avaliacoes)} avaliações
                          </span>
                        ) : null}
                      </span>
                    )}
                    {jogo.classificacao_etaria && (
                      <span className="inline-flex min-w-[24px] items-center justify-center rounded border border-outline-variant/40 px-space-xxs py-space-xxs font-badge-status text-badge-status uppercase text-on-surface-variant">
                        {jogo.classificacao_etaria}
                      </span>
                    )}
                    {jogo.generos.map((genero) => (
                      <span
                        key={genero}
                        className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-secondary"
                      >
                        {genero}
                      </span>
                    ))}
                  </div>
                </div>
                </div>

                {midias.length > 0 && <CarrosselMidia midias={midias} />}
              </div>
            </section>

            {/* ==================== KPIS ==================== */}
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-3">
              <KpiHud
                etiqueta="Preço atual"
                canto={jogo.moeda ?? "BRL"}
                valor={fmtMoeda(jogo.preco_no_momento, jogo.moeda)}
                valorNumerico={paraNumero(jogo.preco_no_momento)}
                formatarValor={(v) => fmtMoeda(v, jogo.moeda)}
                rotulo={
                  jogo.desconto_percentual
                    ? `${jogo.desconto_percentual}% de desconto`
                    : "sem desconto"
                }
                acento="primaria"
              />

              <KpiHud
                etiqueta="Menor preço na série"
                canto="COLETADO"
                valor={menorPreco === null ? "—" : fmtMoeda(menorPreco, "BRL")}
                valorNumerico={menorPreco}
                formatarValor={(v) => fmtMoeda(v, "BRL")}
                rotulo={`${fmtNumero(serie.length)} coletas na série`}
                acento="secundaria"
              />

              <KpiHud
                etiqueta="Nota da loja"
                canto="MICROSOFT STORE"
                valor={nota === null ? "—" : `★ ${fmtDecimal(nota, 1)}`}
                valorNumerico={nota}
                formatarValor={(v) => `★ ${fmtDecimal(v, 1)}`}
                rotulo={
                  nota === null
                    ? "sem avaliações na loja"
                    : notaRecente !== null
                      ? `${fmtNumero(jogo.numero_avaliacoes)} avaliações · ★ ${fmtDecimal(
                          notaRecente,
                          1,
                        )} nos últimos 7 dias`
                      : `${fmtNumero(jogo.numero_avaliacoes)} avaliações`
                }
                acento="terciaria"
              />
            </section>

            {/* ==================== SOBRE ==================== */}
            {jogo.descricao && (
              <Painel icone="description" titulo="Sobre">
                <p className="whitespace-pre-line font-body-md text-body-md leading-relaxed text-on-surface-variant">
                  {jogo.descricao}
                </p>
              </Painel>
            )}

            <ResumoPorIAXbox productId={jogo.product_id} />

            {/* ==================== RECURSOS E CLASSIFICAÇÃO ==================== */}
            {(temFicha || temClassificacao) && (
              <Painel icone="tune" titulo="Recursos e classificação">
                {temFicha && (
                  <div className="flex flex-wrap gap-space-xs">
                    {jogo.recursos.map((recurso) => (
                      <span
                        key={recurso}
                        className="rounded bg-surface-container px-space-sm py-space-xxs font-badge-status text-badge-status uppercase text-on-surface-variant"
                      >
                        {recurso}
                      </span>
                    ))}
                    {jogo.tem_conquistas !== null && (
                      <span
                        className={`inline-flex items-center gap-space-xxs rounded px-space-sm py-space-xxs font-badge-status text-badge-status uppercase ${
                          jogo.tem_conquistas
                            ? "bg-tertiary/10 text-tertiary"
                            : "bg-surface-container text-outline"
                        }`}
                      >
                        <Icone
                          nome={jogo.tem_conquistas ? "trophy" : "block"}
                          className="text-[13px]"
                        />
                        {jogo.tem_conquistas ? "Tem conquistas" : "Sem conquistas"}
                      </span>
                    )}
                  </div>
                )}

                {temClassificacao && (
                  <div className="flex flex-wrap items-center gap-space-xs border-t border-outline-variant/20 pt-space-md">
                    {jogo.classificacao_etaria && (
                      <span className="inline-flex min-w-[28px] items-center justify-center rounded border border-outline-variant/40 px-space-xs py-space-xxs font-title-code text-title-code uppercase text-on-surface">
                        {jogo.classificacao_etaria}
                      </span>
                    )}
                    {jogo.descritores_conteudo.map((descritor) => (
                      <span
                        key={descritor}
                        className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status text-outline"
                      >
                        {descritor}
                      </span>
                    ))}
                  </div>
                )}
              </Painel>
            )}

            {/* ==================== SÉRIE DE PREÇO ==================== */}
            <Painel
              icone="payments"
              titulo="Histórico de preço"
              descricao="Um ponto por coleta (padrão: a cada 6 horas), no mercado BR."
            >
              {precosSerie.length < 2 ? (
                <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                  {precosSerie.length === 0
                    ? "Sem preço de balcão coletado — este jogo pode ser vendido só via Game Pass no Brasil."
                    : "Só existe uma coleta até agora — a série ganha forma quando o coletor rodar de novo."}
                </p>
              ) : (
                <AreaNeon
                  pontos={precosSerie}
                  formatarValor={(valor) => fmtMoeda(valor, "BRL")}
                  rodapeDireita="Xbox Store · mercado BR"
                />
              )}
            </Painel>

            {/* ==================== SÉRIE DE NOTA ==================== */}
            {notasSerie.length >= 2 && (
              <Painel
                icone="star"
                titulo="Nota ao longo do tempo"
                descricao="Estrela agregada da Microsoft Store a cada coleta."
              >
                <AreaNeon
                  pontos={notasSerie}
                  formatarValor={(valor) => `★ ${fmtDecimal(valor, 1)}`}
                  rodapeDireita="Microsoft Store"
                />
              </Painel>
            )}

            {/* ==================== ONDE COMPRAR ==================== */}
            <Painel
              icone="sell"
              titulo="Onde comprar"
              descricao="A vitrine puxa da loja pública da Microsoft — a compra acontece lá."
            >
              {jogo.url_loja ? (
                <a
                  href={jogo.url_loja}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-[40px] items-center gap-space-xs rounded bg-primary-container px-space-md py-space-xs font-title-code text-title-code text-on-primary shadow-sm transition-[filter] hover:brightness-110"
                >
                  <Icone nome="open_in_new" className="text-[18px]" />
                  Abrir na Microsoft Store
                </a>
              ) : (
                <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                  Sem link da loja para este jogo.
                </p>
              )}
            </Painel>
          </>
        );
      }}
    </Consulta>
  );
}
