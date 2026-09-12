/**
 * Aba Xbox do catalogo — vitrine da Xbox Store (mercado BR).
 *
 * Rasa de proposito: a Microsoft nao publica CCU nem texto de avaliacao em API
 * gratuita, entao aqui e ficha + preco + selo do Game Pass. A estrutura segue a
 * aba Steam (busca, dropdowns de genero e categoria, pilulas de ordenacao,
 * KPIs, tabela), sem o ranking de jogadores nem o grafico de telemetria, que
 * nao tem fonte.
 *
 * O catalogo tem ~800 jogos: a lista inteira vem da API (capada em 500) e a
 * tela mostra 25/50 por vez (`usePaginacaoLocal`). O leitor escolhe entre
 * tabela (rola de lado no celular) e grade de cartoes (empilha).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { usePaginacaoLocal } from "@models/hooks/paginacao";
import {
  useBuscaCatalogoXbox,
  useCategoriasXbox,
  useColetarJogoXbox,
  useGenerosXbox,
  useJogosXbox,
  useVisaoGeral,
} from "@models/api/consultas";
import type { AgregadoGenero, CandidatoJogoXbox, JogoXbox } from "@models/api/tipos";
import { Consulta, Icone, MensagemErro, TabelaRolavel } from "@views/componentes/base";
import { CapaXbox } from "@views/componentes/CapaXbox";
import { CartaoJogoXbox } from "@views/componentes/CartaoJogoXbox";
import {
  KpiHud,
  Paginacao,
  Pilula,
  SeletorFiltro,
  SeletorModo,
  useModoPersistente,
} from "@views/componentes/hud";
import { PALETA_POLOS, TOKENS, corDoGenero } from "@views/tema";
import { fmtDecimal, fmtMoeda, fmtNumero, paraNumero } from "@util/formatos";

type Ordenacao = "game_pass" | "nome" | "preco" | "nota";

const ORDENACOES: { valor: Ordenacao; rotulo: string; icone?: string }[] = [
  { valor: "game_pass", rotulo: "Game Pass primeiro", icone: "featured_seasonal_and_gifts" },
  { valor: "nota", rotulo: "Nota", icone: "star" },
  { valor: "nome", rotulo: "Nome" },
  { valor: "preco", rotulo: "Preço" },
];

const MODOS_CATALOGO = [
  { id: "tabela", icone: "table_rows", rotulo: "Tabela" },
  { id: "cartoes", icone: "grid_view", rotulo: "Cartões" },
] as const;
type ModoCatalogo = (typeof MODOS_CATALOGO)[number]["id"];

/** Verde de 4 pra cima, âmbar no meio, apagado abaixo de 3 — igual polaridade. */
function corDaNota(nota: number): string {
  if (nota >= 4) return PALETA_POLOS.positivo;
  if (nota >= 3) return TOKENS.secundaria;
  return TOKENS.textoSuave;
}

/** ★ 3,8 com a contagem ao lado — ou "—" quando a loja não tem avaliação. */
function Nota({ jogo }: { jogo: JogoXbox }) {
  const nota = paraNumero(jogo.nota);
  if (nota === null) return <span className="text-outline">—</span>;
  const recente = paraNumero(jogo.nota_recente);
  const tendencia =
    recente !== null && Math.abs(recente - nota) >= 0.4
      ? recente > nota
        ? "north"
        : "south"
      : null;
  return (
    <span className="inline-flex items-center gap-space-xxs whitespace-nowrap">
      <span
        className="inline-flex items-center gap-space-xxs font-title-code text-title-code font-bold"
        style={{ color: corDaNota(nota) }}
      >
        <Icone nome="star" className="text-[13px]" />
        {fmtDecimal(nota, 1)}
      </span>
      {jogo.numero_avaliacoes ? (
        <span className="font-label-caps text-label-caps text-outline">
          ({fmtNumero(jogo.numero_avaliacoes)})
        </span>
      ) : null}
      {tendencia && (
        <span
          className="inline-flex text-[12px]"
          style={{
            color: tendencia === "north" ? PALETA_POLOS.positivo : PALETA_POLOS.negativo,
          }}
          title={tendencia === "north" ? "subindo nos últimos 7 dias" : "caindo nos últimos 7 dias"}
        >
          <Icone nome={tendencia} className="text-[12px]" />
        </span>
      )}
    </span>
  );
}

/**
 * "Não achou? Busque na loja" — o catálogo Xbox só acompanha quem está no
 * Game Pass agora ou numa semente fixa (ver `xbox_collector.py`). Um jogo à
 * venda mas fora dos dois (ex.: "Grand Theft Auto V", que saiu do Game Pass)
 * nunca aparece na tabela principal por mais que exista na Xbox Store de
 * verdade — este painel busca ao vivo na Microsoft Store e deixa adicionar
 * ao catálogo com um clique. Mesmo desenho da `BuscaDeJogo` da Steam.
 */
function BuscaNaLojaXbox({ termo }: { termo: string }) {
  const navegar = useNavigate();
  const catalogo = useBuscaCatalogoXbox(termo);
  const coletar = useColetarJogoXbox();

  if (termo.trim().length < 2) return null;

  const resultados = catalogo.data ?? [];

  function adicionar(candidato: CandidatoJogoXbox) {
    if (candidato.coletado) {
      navegar(`/xbox/${candidato.product_id}`);
      return;
    }
    coletar.mutate(candidato.product_id, {
      onSuccess: (resumo) => navegar(`/xbox/${resumo.product_id}`),
    });
  }

  return (
    <div className="space-y-space-sm rounded-xl bg-surface-container-low/60 p-space-base">
      <div className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
        <Icone nome="travel_explore" className="text-[16px] text-primary" />
        Não achou no catálogo coletado? Resultados da Microsoft Store
      </div>

      {coletar.isError && <MensagemErro erro={coletar.error} />}

      {catalogo.isFetching && resultados.length === 0 ? (
        <div className="h-16 animate-pulse rounded-lg bg-surface-container-high/60" />
      ) : resultados.length === 0 ? (
        <p className="font-body-sm text-body-sm text-on-surface-variant">
          Nenhum jogo da Xbox Store bate com essa busca.
        </p>
      ) : (
        <div className="rolagem-discreta flex gap-space-sm overflow-x-auto pb-space-xs">
          {resultados.map((candidato) => (
            <button
              key={candidato.product_id}
              type="button"
              onClick={() => adicionar(candidato)}
              disabled={coletar.isPending && coletar.variables === candidato.product_id}
              className="flex w-48 shrink-0 flex-col gap-space-xs rounded-lg bg-surface-container-lowest p-space-sm text-left transition-colors hover:bg-surface-container disabled:opacity-60"
            >
              <div className="aspect-[3/4] w-full overflow-hidden rounded bg-surface-container-high">
                {candidato.imagem && (
                  <img
                    src={candidato.imagem}
                    alt=""
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                )}
              </div>
              <span className="truncate font-title-code text-title-code font-bold text-on-surface">
                {candidato.nome}
              </span>
              <span className="truncate font-body-sm text-body-sm text-on-surface-variant">
                {candidato.publicadora ?? "—"}
              </span>
              <span className="flex items-center justify-between font-badge-status text-badge-status uppercase">
                <span className="text-primary">{candidato.preco_texto ?? "—"}</span>
                {candidato.coletado ? (
                  <span className="text-tertiary">já no catálogo</span>
                ) : coletar.isPending && coletar.variables === candidato.product_id ? (
                  <span className="text-outline">adicionando…</span>
                ) : (
                  <span className="text-outline">+ adicionar</span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function XboxCatalogo() {
  const navegar = useNavigate();
  const campoBusca = useRef<HTMLInputElement>(null);

  const [busca, setBusca] = useState("");
  const [termoBuscado, setTermoBuscado] = useState("");
  const [genero, setGenero] = useState("");
  const [categoria, setCategoria] = useState("");
  const [ordenacao, setOrdenacao] = useState<Ordenacao>("game_pass");
  const [modo, setModo] = useModoPersistente<ModoCatalogo>(
    "playdb:xbox-modo",
    ["tabela", "cartoes"],
    "tabela",
  );

  useEffect(() => {
    const relogio = setTimeout(() => setTermoBuscado(busca.trim()), 450);
    return () => clearTimeout(relogio);
  }, [busca]);

  const jogos = useJogosXbox({
    busca: termoBuscado || undefined,
    genero: genero || undefined,
    categoria: categoria || undefined,
    ordenar_por: ordenacao,
    // O catálogo inteiro de uma vez — a paginação é no cliente. O Game Pass no
    // BR tem ~800–1000 jogos; 1500 dá folga pro catálogo crescer.
    limite: 1500,
  });
  const generos = useGenerosXbox();
  const categorias = useCategoriasXbox();
  const visaoGeral = useVisaoGeral();

  const totalCatalogo = visaoGeral.data?.jogos_xbox ?? 0;

  const lista = useMemo<JogoXbox[]>(() => jogos.data ?? [], [jogos.data]);
  const paginacao = usePaginacaoLocal(lista, {
    porPaginaInicial: { mobile: 5, desktop: 25 },
    chaveReset: `${termoBuscado}|${genero}|${categoria}|${ordenacao}`,
  });

  return (
    <>
      {/* ---------- busca e ordenacao ---------- */}
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
              placeholder="Buscar jogo por título ou publicadora…"
              aria-label="Buscar jogo"
              className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-4 font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
            />
          </div>

          {/* Gênero (Ação e aventura, RPG, Tiro...) e categoria (recursos:
              Co-op online, 4K, Otimizado p/ Series X|S...) no mesmo dropdown
              que o catálogo Steam usa - a lista aberta de um `<select>`
              nativo é o navegador quem desenha, sem nada do tema escuro. */}
          <SeletorFiltro
            rotulo="Gênero"
            valor={genero}
            aoEscolher={setGenero}
            rotuloTudo={`Todos (${totalCatalogo || 0})`}
            opcoes={(generos.data ?? []).map((item: AgregadoGenero) => ({
              valor: item.genero,
              rotulo: `${item.genero} (${item.jogos})`,
            }))}
          />

          <SeletorFiltro
            rotulo="Categoria"
            valor={categoria}
            aoEscolher={setCategoria}
            rotuloTudo="Todas"
            buscavel
            opcoes={(categorias.data ?? []).map((item) => ({
              valor: item.categoria,
              rotulo: `${item.categoria} (${item.jogos})`,
            }))}
          />

          <div className="flex flex-wrap items-center gap-space-xs">
            <span className="mr-space-xs hidden font-label-caps text-label-caps uppercase text-outline sm:inline">
              Ordenar:
            </span>
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
        </div>
      </section>

      <BuscaNaLojaXbox termo={termoBuscado} />

      {/* ---------- KPIs (sobre a lista inteira, nunca a página) ---------- */}
      <Consulta estado={jogos} altura={160} vazio="Catálogo do Xbox ainda não coletado.">
        {(todos: JogoXbox[]) => {
          const noGamePass = todos.filter((j) => j.no_game_pass).length;
          const pagos = todos
            .map((j) => paraNumero(j.preco_no_momento))
            .filter((p): p is number => p !== null && p > 0);
          const precoMedio = pagos.length
            ? pagos.reduce((t, p) => t + p, 0) / pagos.length
            : null;
          const notas = todos
            .map((j) => paraNumero(j.nota))
            .filter((n): n is number => n !== null);
          const notaMedia = notas.length
            ? notas.reduce((t, n) => t + n, 0) / notas.length
            : null;

          return (
            <section className="grid grid-cols-1 gap-space-base md:grid-cols-3">
              <KpiHud
                etiqueta="XBOX_STORE // CATÁLOGO"
                canto={
                  genero || categoria
                    ? `FILTRO: ${[genero, categoria].filter(Boolean).join(" + ").toUpperCase()}`
                    : "MERCADO BR"
                }
                valor={fmtNumero(totalCatalogo || todos.length)}
                valorNumerico={totalCatalogo || todos.length}
                formatarValor={fmtNumero}
                rotulo="Jogos no catálogo coletado"
                acento="primaria"
              />

              <KpiHud
                etiqueta="NOTA MÉDIA // CATÁLOGO"
                canto={`${fmtNumero(noGamePass)} NO GAME PASS`}
                valor={notaMedia === null ? "—" : `★ ${fmtDecimal(notaMedia, 1)}`}
                valorNumerico={notaMedia}
                formatarValor={(v) => `★ ${fmtDecimal(v, 1)}`}
                rotulo={`${fmtNumero(notas.length)} jogos avaliados na loja`}
                acento="terciaria"
              />

              <KpiHud
                etiqueta="PREÇO MÉDIO // PAGOS"
                canto="BRL"
                valor={precoMedio === null ? "—" : fmtMoeda(precoMedio, "BRL")}
                valorNumerico={precoMedio}
                formatarValor={(v) => fmtMoeda(v, "BRL")}
                rotulo={`${fmtNumero(pagos.length)} jogos com preço de balcão`}
                acento="secundaria"
              />
            </section>
          );
        }}
      </Consulta>

      {/* ---------- lista (tabela ou cartões) ---------- */}
      <section className="space-y-space-md rounded-xl bg-surface-container-low p-space-base shadow-2xl">
        <div className="flex flex-col justify-between gap-space-base lg:flex-row lg:items-center">
          <h2 className="flex items-center gap-space-xs font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
            <Icone nome="grid_view" className="text-[20px] text-primary-container" />
            Catálogo da Xbox Store
          </h2>
          <div className="flex flex-wrap items-center gap-space-md">
            <span className="font-title-code text-title-code text-outline">
              Fonte: catálogo público da Microsoft · mercado BR · não-oficial
            </span>
            <SeletorModo modos={MODOS_CATALOGO} valor={modo} aoMudar={setModo} />
          </div>
        </div>

        <Consulta estado={jogos} vazio="Catálogo do Xbox ainda não coletado.">
          {() =>
            modo === "tabela" ? (
              <TabelaRolavel minLargura="52rem">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                      <th className="px-space-md py-space-sm">Jogo</th>
                      <th className="px-space-md py-space-sm">Gêneros</th>
                      <th className="px-space-md py-space-sm">Game Pass</th>
                      <th className="px-space-md py-space-sm">Nota</th>
                      <th className="px-space-md py-space-sm">Preço</th>
                      <th className="px-space-md py-space-sm text-right">Loja</th>
                    </tr>
                  </thead>

                  <tbody className="font-body-md text-body-sm">
                    {paginacao.fatia.map((jogo, indice) => (
                      <tr
                        key={jogo.product_id}
                        onClick={() => navegar(`/xbox/${jogo.product_id}`)}
                        className={`cursor-pointer transition-colors hover:bg-surface-container-high/60 ${
                          indice % 2 ? "bg-surface-container-low/40" : ""
                        }`}
                      >
                        <td className="px-space-md py-space-sm">
                          <div className="flex items-center gap-space-sm">
                            <CapaXbox
                              nome={jogo.nome}
                              imagemUrl={jogo.imagem_capa ?? jogo.imagem_header}
                            />
                            <div className="flex min-w-0 flex-col">
                              <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">
                                {jogo.nome}
                              </span>
                              <span className="truncate font-title-code text-title-code text-outline">
                                {jogo.publicadora ?? jogo.desenvolvedora ?? "—"}
                              </span>
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
                          {jogo.no_game_pass ? (
                            <span className="inline-flex items-center gap-space-xxs rounded bg-tertiary/10 px-space-sm py-space-xxs font-badge-status text-badge-status uppercase text-tertiary">
                              <Icone nome="check" className="text-[13px]" />
                              Game Pass
                            </span>
                          ) : (
                            <span className="text-outline">—</span>
                          )}
                        </td>

                        <td className="px-space-md py-space-sm">
                          <Nota jogo={jogo} />
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

                        <td className="px-space-md py-space-sm text-right">
                          {jogo.url_loja ? (
                            <a
                              href={jogo.url_loja}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(evento) => evento.stopPropagation()}
                              className="inline-flex items-center gap-space-xxs font-title-code text-title-code text-primary hover:underline"
                            >
                              abrir <Icone nome="open_in_new" className="text-[13px]" />
                            </a>
                          ) : (
                            <span className="text-outline">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TabelaRolavel>
            ) : (
              <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 xl:grid-cols-3">
                {paginacao.fatia.map((jogo) => (
                  <CartaoJogoXbox key={jogo.product_id} jogo={jogo} />
                ))}
              </div>
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
          resumo={
            <>
              Exibindo {fmtNumero(paginacao.fatia.length)} de {fmtNumero(lista.length)}
            </>
          }
        />
      </section>
    </>
  );
}
