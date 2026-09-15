/**
 * Ofertas — promoções ABERTAS agora na própria Steam (Fase 35).
 *
 * Primeiro-partido: preço/desconto vêm do nosso próprio `steam_promocoes`,
 * nunca de uma chamada ao vivo à Steam nem de uma heurística de "fração do
 * catálogo em desconto" apresentada como evento oficial — a Steam não expõe
 * calendário de sales, então esta tela não inventa um. O que ela mostra é
 * sempre uma transição real de desconto observada num jogo específico.
 *
 * Layout inspirado numa referência trazida pelo usuário — paleta e tokens
 * seguem os do próprio projeto, não os da referência.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  useDesfavoritarJogo,
  useFavoritarJogo,
  useFavoritosJogos,
  useOfertasSteam,
} from "@models/api/consultas";
import type { OfertaSteam } from "@models/api/tipos";
import type { FiltrosOfertasSteam } from "@models/api/consultas";
import { Consulta, Icone } from "@views/componentes/base";
import { BannerDestaque } from "@views/componentes/BannerDestaque";
import { BotaoFavoritar } from "@views/componentes/BotaoFavoritar";
import { Paginacao, Pilula, SeletorModo, useModoPersistente } from "@views/componentes/hud";
import { ArteJogo, CapaJogo } from "@views/componentes/CapaJogo";
import { fmtMoeda, fmtNumero, fmtRelativo } from "@util/formatos";

const LIMIARES_DESCONTO = [0, 90, 75, 50, 25, 10] as const;
const OPCOES_POR_PAGINA = [24, 48, 96];
const MODOS = [
  { id: "cartoes", icone: "grid_view" },
  { id: "lista", icone: "view_list" },
] as const;
type Modo = (typeof MODOS)[number]["id"];

export function OfertasPagina() {
  const { t } = useTranslation();
  const campoBusca = useRef<HTMLInputElement>(null);

  const [busca, setBusca] = useState("");
  const [termoBuscado, setTermoBuscado] = useState("");
  const [descontoMinimo, setDescontoMinimo] = useState<number>(0);
  const [mostrarMais, setMostrarMais] = useState(false);
  const [precoMaximo, setPrecoMaximo] = useState("");
  const [precoMaximoAplicado, setPrecoMaximoAplicado] = useState<number | undefined>(undefined);
  const [ordenarPor, setOrdenarPor] =
    useState<FiltrosOfertasSteam["ordenar_por"]>("desconto_desc");
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(24);
  const [modo, setModo] = useModoPersistente<Modo>("playdb:ofertas-modo", ["cartoes", "lista"], "cartoes");

  const favoritosJogos = useFavoritosJogos();
  const favoritar = useFavoritarJogo();
  const desfavoritar = useDesfavoritarJogo();

  // Mesmo debounce do catálogo Xbox - 20 mil ofertas não aguentam uma
  // requisição por tecla digitada.
  useEffect(() => {
    const relogio = setTimeout(() => setTermoBuscado(busca.trim()), 450);
    return () => clearTimeout(relogio);
  }, [busca]);

  useEffect(() => {
    const relogio = setTimeout(() => {
      const numero = Number(precoMaximo.replace(",", "."));
      setPrecoMaximoAplicado(precoMaximo.trim() && !Number.isNaN(numero) && numero > 0 ? numero : undefined);
    }, 450);
    return () => clearTimeout(relogio);
  }, [precoMaximo]);

  // A varredura completa (Fase 35.1) fez o catálogo crescer de dezenas pra
  // ~20 mil ofertas - paginado no SERVIDOR, ao contrário do catálogo Xbox
  // (~800 jogos, `usePaginacaoLocal` busca tudo de uma vez).
  useEffect(() => {
    setPagina(1);
  }, [termoBuscado, descontoMinimo, precoMaximoAplicado, ordenarPor, porPagina]);

  const ofertas = useOfertasSteam({
    busca: termoBuscado || undefined,
    desconto_minimo: descontoMinimo,
    preco_maximo: precoMaximoAplicado,
    ordenar_por: ordenarPor,
    limite: porPagina,
    offset: (pagina - 1) * porPagina,
  });

  const total = ofertas.data?.total ?? 0;
  const totalPaginas = Math.max(1, Math.ceil(total / porPagina));

  function limparFiltros() {
    setBusca("");
    setDescontoMinimo(0);
    setPrecoMaximo("");
    setMostrarMais(false);
    setOrdenarPor("desconto_desc");
  }

  function alternarFavorito(oferta: OfertaSteam) {
    const jaFavoritado = favoritosJogos.data?.some(
      (f) => f.fonte === "steam" && f.jogo_id === String(oferta.app_id),
    );
    if (jaFavoritado) {
      desfavoritar.mutate({ fonte: "steam", jogo_id: String(oferta.app_id) });
    } else {
      favoritar.mutate({ fonte: "steam", jogo_id: String(oferta.app_id) });
    }
  }

  // As mesmas capas que a grade logo abaixo mostra - sem chamada extra.
  const imagensHero = (ofertas.data?.itens ?? [])
    .map((o) => o.imagem_header)
    .filter((url): url is string => Boolean(url))
    .slice(0, 8);

  return (
    <div className="space-y-space-xl">
      <BannerDestaque imagens={imagensHero}>
        <div className="flex flex-wrap items-start justify-between gap-space-lg">
          <div className="flex max-w-xl flex-col gap-space-sm">
            <span className="flex items-center gap-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-primary">
              <Icone nome="local_fire_department" className="text-[15px]" />
              {t("ofertas.hero.eyebrow")}
            </span>
            <h1 className="font-headline-lg text-headline-lg font-bold text-on-surface">
              {t("ofertas.hero.titulo")}
              <span className="text-tertiary">{t("ofertas.hero.tituloDestaque")}</span>
            </h1>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              {t("ofertas.hero.descricao")}
            </p>
            <button
              type="button"
              onClick={() => {
                limparFiltros();
                document.getElementById("grade-ofertas")?.scrollIntoView({ behavior: "smooth" });
              }}
              className="mt-space-xs inline-flex w-fit items-center gap-space-xxs rounded-full bg-primary-container px-space-md py-space-sm font-title-code text-title-code font-bold text-on-primary transition-colors hover:brightness-110"
            >
              {t("ofertas.hero.cta")}
              <Icone nome="arrow_forward" className="text-[16px]" />
            </button>
          </div>

          <div className="flex flex-wrap gap-space-sm">
            <ChipHero icone="schedule" titulo={t("ofertas.hero.chip1Titulo")} sub={t("ofertas.hero.chip1Sub")} />
            <ChipHero icone="savings" titulo={t("ofertas.hero.chip2Titulo")} sub={t("ofertas.hero.chip2Sub")} />
            <ChipHero icone="storefront" titulo={t("ofertas.hero.chip3Titulo")} sub={t("ofertas.hero.chip3Sub")} />
          </div>
        </div>
      </BannerDestaque>

      <div id="grade-ofertas" className="flex flex-col gap-space-base border-b border-outline-variant/30 pb-space-base pt-space-base">
        <div className="relative max-w-md">
          <Icone
            nome="manage_search"
            className="absolute left-space-sm top-1/2 -translate-y-1/2 text-[20px] text-primary-container"
          />
          <input
            ref={campoBusca}
            type="search"
            value={busca}
            onChange={(evento) => setBusca(evento.target.value)}
            placeholder={t("ofertas.buscarPlaceholder")}
            aria-label={t("ofertas.buscarAriaLabel")}
            className="w-full rounded bg-surface-container-lowest py-space-sm pl-10 pr-4 font-title-code text-title-code text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-space-sm">
          <div className="flex flex-wrap items-center gap-space-xxs">
            {LIMIARES_DESCONTO.map((limiar) => (
              <Pilula
                key={limiar}
                ativa={descontoMinimo === limiar}
                aoClicar={() => setDescontoMinimo(limiar)}
              >
                {limiar === 0
                  ? total > 0
                    ? t("ofertas.todosContagem", { contagem: fmtNumero(total) })
                    : t("ofertas.todos")
                  : `-${limiar}%`}
              </Pilula>
            ))}
            <Pilula ativa={mostrarMais} aoClicar={() => setMostrarMais((m) => !m)} icone="expand_more">
              {t("ofertas.mais")}
            </Pilula>
          </div>

          <div className="flex flex-wrap items-center gap-space-sm">
            <span className="hidden font-label-caps text-label-caps uppercase tracking-widest text-outline sm:inline">
              {t("ofertas.ordenarPor")}
            </span>
            <div className="relative">
              <select
                value={ordenarPor}
                onChange={(evento) =>
                  setOrdenarPor(evento.target.value as FiltrosOfertasSteam["ordenar_por"])
                }
                className="appearance-none rounded border border-outline-variant/40 bg-surface-container-lowest py-space-xs pl-space-sm pr-space-lg font-title-code text-title-code text-on-surface focus:outline-none"
              >
                <option value="desconto_desc">{t("ofertas.maiorDesconto")}</option>
                <option value="preco_asc">{t("ofertas.menorPreco")}</option>
              </select>
              <Icone
                nome="expand_more"
                className="pointer-events-none absolute right-space-xs top-1/2 -translate-y-1/2 text-[16px] text-outline"
              />
            </div>
            <SeletorModo
              modos={MODOS.map((m) => ({ ...m, rotulo: t(`ofertas.modo${m.id === "cartoes" ? "Cartoes" : "Lista"}`) }))}
              valor={modo}
              aoMudar={setModo}
            />
          </div>
        </div>

        {mostrarMais && (
          <div className="flex items-center gap-space-sm rounded bg-surface-container-lowest/60 px-space-sm py-space-xs">
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {t("ofertas.precoMaximo")}
            </span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={precoMaximo}
              onChange={(evento) => setPrecoMaximo(evento.target.value)}
              placeholder={t("ofertas.precoMaximoPlaceholder")}
              className="w-32 rounded border border-outline-variant/40 bg-surface-container-lowest px-space-sm py-space-xxs font-title-code text-title-code text-on-surface focus:outline-none"
            />
            {precoMaximo && (
              <button
                type="button"
                onClick={() => setPrecoMaximo("")}
                className="text-outline hover:text-on-surface"
                aria-label={t("ofertas.limparPrecoMaximo")}
              >
                <Icone nome="close" className="text-[16px]" />
              </button>
            )}
          </div>
        )}
      </div>

      <Consulta estado={ofertas} vazio={t("ofertas.nenhumaOferta")}>
        {(resposta) =>
          resposta.itens.length === 0 ? (
            <p className="py-space-xl text-center font-body-md text-body-md text-on-surface-variant">
              {t("ofertas.nenhumaOferta")}
            </p>
          ) : (
            <>
              {modo === "cartoes" ? (
                <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
                  {resposta.itens.map((oferta) => (
                    <CartaoOferta
                      key={oferta.app_id}
                      oferta={oferta}
                      favoritado={Boolean(
                        favoritosJogos.data?.some(
                          (f) => f.fonte === "steam" && f.jogo_id === String(oferta.app_id),
                        ),
                      )}
                      ocupado={favoritar.isPending || desfavoritar.isPending}
                      aoFavoritar={() => alternarFavorito(oferta)}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col gap-space-xs">
                  {resposta.itens.map((oferta) => (
                    <LinhaOferta
                      key={oferta.app_id}
                      oferta={oferta}
                      favoritado={Boolean(
                        favoritosJogos.data?.some(
                          (f) => f.fonte === "steam" && f.jogo_id === String(oferta.app_id),
                        ),
                      )}
                      ocupado={favoritar.isPending || desfavoritar.isPending}
                      aoFavoritar={() => alternarFavorito(oferta)}
                    />
                  ))}
                </div>
              )}

              <Paginacao
                pagina={Math.min(pagina, totalPaginas)}
                totalPaginas={totalPaginas}
                porPagina={porPagina}
                opcoesPorPagina={OPCOES_POR_PAGINA}
                aoMudarPagina={setPagina}
                aoMudarPorPagina={setPorPagina}
                resumo={t("ofertas.paginacao.exibindo", {
                  fatia: fmtNumero(resposta.itens.length),
                  total: fmtNumero(resposta.total),
                })}
              />
            </>
          )
        }
      </Consulta>
    </div>
  );
}

function ChipHero({ icone, titulo, sub }: { icone: string; titulo: string; sub: string }) {
  return (
    <div className="flex w-64 items-center gap-space-sm rounded-xl bg-surface-container-lowest/85 p-space-sm ring-1 ring-outline-variant/25 backdrop-blur-sm">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-container/20 text-primary">
        <Icone nome={icone} className="text-[18px]" />
      </span>
      <div className="flex min-w-0 flex-col">
        <span className="truncate font-title-code text-title-code font-bold text-on-surface">{titulo}</span>
        <span className="truncate font-badge-status text-badge-status text-on-surface-variant">{sub}</span>
      </div>
    </div>
  );
}

function CartaoOferta({
  oferta,
  favoritado,
  ocupado,
  aoFavoritar,
}: {
  oferta: OfertaSteam;
  favoritado: boolean;
  ocupado: boolean;
  aoFavoritar: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const irParaJogo = () => navigate(`/steam/${oferta.app_id}`);

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={irParaJogo}
      onKeyDown={(evento) => {
        if (evento.key === "Enter" || evento.key === " ") {
          evento.preventDefault();
          irParaJogo();
        }
      }}
      className="group flex cursor-pointer flex-col overflow-hidden rounded-xl border border-outline-variant/15 bg-surface-container-low transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:bg-surface-container-high/60 hover:shadow-lg hover:shadow-primary/5 focus-visible:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <div className="relative">
        <ArteJogo
          appId={oferta.app_id}
          nome={oferta.nome}
          imagemUrl={oferta.imagem_header}
          className="h-24 w-full rounded-none transition-transform duration-200 group-hover:scale-105"
        />
        <div
          className="absolute right-space-xs top-space-xs"
          onClick={(evento) => evento.stopPropagation()}
          onKeyDown={(evento) => evento.stopPropagation()}
        >
          <BotaoFavoritar favoritado={favoritado} aoAlternar={aoFavoritar} ocupado={ocupado} tamanho="sm" />
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-space-xs p-space-base">
        <span className="line-clamp-2 font-headline-sm text-headline-sm font-bold text-primary">
          {oferta.nome}
        </span>

        <div className="flex items-center justify-between gap-space-xs">
          <span className="flex items-center gap-space-xxs font-label-caps text-label-caps text-outline">
            <Icone nome="schedule" className="text-[13px]" />
            {fmtRelativo(oferta.iniciada_em)}
          </span>
          <span className="shrink-0 rounded-full bg-tertiary/15 px-space-xs py-space-xxs font-badge-status text-badge-status font-bold text-tertiary">
            -{oferta.desconto_percentual}%
          </span>
        </div>

        <div className="mt-auto flex items-center justify-between gap-space-xs pt-space-sm">
          <div className="flex items-baseline gap-space-xxs">
            <span className="font-title-code text-title-code text-outline line-through">
              {fmtMoeda(oferta.preco_original, oferta.moeda)}
            </span>
            <span className="font-headline-sm text-headline-sm font-bold text-tertiary">
              {fmtMoeda(oferta.preco_final, oferta.moeda)}
            </span>
          </div>
          <span className="shrink-0 rounded border border-outline-variant/40 px-space-sm py-space-xxs font-title-code text-title-code uppercase tracking-wide text-primary">
            {t("ofertas.verJogo")} →
          </span>
        </div>
      </div>
    </article>
  );
}

function LinhaOferta({
  oferta,
  favoritado,
  ocupado,
  aoFavoritar,
}: {
  oferta: OfertaSteam;
  favoritado: boolean;
  ocupado: boolean;
  aoFavoritar: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const irParaJogo = () => navigate(`/steam/${oferta.app_id}`);

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={irParaJogo}
      onKeyDown={(evento) => {
        if (evento.key === "Enter" || evento.key === " ") {
          evento.preventDefault();
          irParaJogo();
        }
      }}
      className="flex cursor-pointer items-center gap-space-sm rounded-lg border border-outline-variant/15 bg-surface-container-low p-space-sm transition-all duration-200 hover:border-primary/30 hover:bg-surface-container-high/60 hover:shadow-md hover:shadow-primary/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <CapaJogo appId={oferta.app_id} nome={oferta.nome} imagemUrl={oferta.imagem_header} className="h-14 w-14 shrink-0" />

      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">{oferta.nome}</span>
        <span className="flex items-center gap-space-xxs font-label-caps text-label-caps text-outline">
          <Icone nome="schedule" className="text-[13px]" />
          {fmtRelativo(oferta.iniciada_em)}
        </span>
      </div>

      <span className="hidden shrink-0 items-baseline gap-space-xxs sm:flex">
        <span className="font-title-code text-title-code text-outline line-through">
          {fmtMoeda(oferta.preco_original, oferta.moeda)}
        </span>
        <span className="font-headline-sm text-headline-sm font-bold text-tertiary">
          {fmtMoeda(oferta.preco_final, oferta.moeda)}
        </span>
      </span>

      <span className="shrink-0 rounded-full bg-tertiary/15 px-space-sm py-space-xxs font-badge-status text-badge-status font-bold text-tertiary">
        -{oferta.desconto_percentual}%
      </span>

      <span
        onClick={(evento) => evento.stopPropagation()}
        onKeyDown={(evento) => evento.stopPropagation()}
      >
        <BotaoFavoritar favoritado={favoritado} aoAlternar={aoFavoritar} ocupado={ocupado} tamanho="sm" />
      </span>

      <span className="hidden shrink-0 items-center gap-space-xxs rounded border border-outline-variant/40 px-space-sm py-space-xxs font-title-code text-title-code uppercase tracking-wide text-primary md:inline-flex">
        {t("ofertas.verJogo")} →
      </span>
    </article>
  );
}
