/**
 * Ofertas — promoções ABERTAS agora na própria Steam (Fase 35).
 *
 * Primeiro-partido: preço/desconto vêm do nosso próprio `steam_promocoes`,
 * nunca de uma chamada ao vivo à Steam nem de uma heurística de "fração do
 * catálogo em desconto" apresentada como evento oficial — a Steam não expõe
 * calendário de sales, então esta tela não inventa um. O que ela mostra é
 * sempre uma transição real de desconto observada num jogo específico.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useOfertasSteam } from "@models/api/consultas";
import type { OfertaSteam } from "@models/api/tipos";
import type { FiltrosOfertasSteam } from "@models/api/consultas";
import { Consulta, Icone } from "@views/componentes/base";
import { BannerDestaque } from "@views/componentes/BannerDestaque";
import { Paginacao, Pilula } from "@views/componentes/hud";
import { ArteJogo } from "@views/componentes/CapaJogo";
import { fmtMoeda, fmtNumero, fmtRelativo } from "@util/formatos";

const LIMIARES_DESCONTO = [0, 10, 25, 50, 75] as const;
const OPCOES_POR_PAGINA = [24, 48, 96];

export function OfertasPagina() {
  const { t } = useTranslation();
  const campoBusca = useRef<HTMLInputElement>(null);

  const [busca, setBusca] = useState("");
  const [termoBuscado, setTermoBuscado] = useState("");
  const [descontoMinimo, setDescontoMinimo] = useState<number>(0);
  const [ordenarPor, setOrdenarPor] =
    useState<FiltrosOfertasSteam["ordenar_por"]>("desconto_desc");
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(24);

  // Mesmo debounce do catálogo Xbox - 20 mil ofertas não aguentam uma
  // requisição por tecla digitada.
  useEffect(() => {
    const relogio = setTimeout(() => setTermoBuscado(busca.trim()), 450);
    return () => clearTimeout(relogio);
  }, [busca]);

  // A varredura completa (Fase 35.1) fez o catálogo crescer de dezenas pra
  // ~20 mil ofertas - paginado no SERVIDOR, ao contrário do catálogo Xbox
  // (~800 jogos, `usePaginacaoLocal` busca tudo de uma vez).
  useEffect(() => {
    setPagina(1);
  }, [termoBuscado, descontoMinimo, ordenarPor, porPagina]);

  const ofertas = useOfertasSteam({
    busca: termoBuscado || undefined,
    desconto_minimo: descontoMinimo,
    ordenar_por: ordenarPor,
    limite: porPagina,
    offset: (pagina - 1) * porPagina,
  });

  const total = ofertas.data?.total ?? 0;
  const totalPaginas = Math.max(1, Math.ceil(total / porPagina));

  // As mesmas capas que a grade logo abaixo mostra - sem chamada extra.
  const imagensHero = (ofertas.data?.itens ?? [])
    .map((o) => o.imagem_header)
    .filter((url): url is string => Boolean(url))
    .slice(0, 8);

  return (
    <div className="space-y-space-xl">
      <BannerDestaque imagens={imagensHero}>
        <span className="flex items-center gap-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-primary">
          <Icone nome="auto_awesome" className="text-[15px]" />
          {t("ofertas.hero.eyebrow")}
        </span>
        <h1 className="max-w-xl font-headline-lg text-headline-lg font-bold text-on-surface">
          {t("ofertas.hero.titulo")}
          <span className="text-tertiary">{t("ofertas.hero.tituloDestaque")}</span>
        </h1>
        <p className="max-w-lg font-body-sm text-body-sm text-on-surface-variant">
          {t("ofertas.hero.descricao")}
        </p>
        <div className="flex flex-wrap gap-space-xs pt-space-xs">
          <ChipHero icone="schedule" texto={t("ofertas.hero.chipTempoReal")} />
          <ChipHero icone="verified" texto={t("ofertas.hero.chipPrimeiroPartido")} />
          {total > 0 && (
            <ChipHero
              icone="local_fire_department"
              texto={t("ofertas.hero.chipTotal", { total: fmtNumero(total) })}
            />
          )}
        </div>
      </BannerDestaque>

      <div className="flex flex-col gap-space-base border-b border-outline-variant/30 pb-space-base pt-space-base">
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

        <div className="flex flex-wrap items-center gap-space-sm">
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("ofertas.descontoMinimo")}
          </span>
          <div className="flex flex-wrap gap-space-xxs">
            {LIMIARES_DESCONTO.map((limiar) => (
              <Pilula
                key={limiar}
                ativa={descontoMinimo === limiar}
                aoClicar={() => setDescontoMinimo(limiar)}
              >
                {limiar === 0 ? t("ofertas.todos") : `${limiar}%+`}
              </Pilula>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-space-sm">
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("ofertas.ordenarPor")}
          </span>
          <div className="flex gap-space-xxs">
            <Pilula
              ativa={ordenarPor === "desconto_desc"}
              aoClicar={() => setOrdenarPor("desconto_desc")}
              icone="local_fire_department"
            >
              {t("ofertas.maiorDesconto")}
            </Pilula>
            <Pilula
              ativa={ordenarPor === "preco_asc"}
              aoClicar={() => setOrdenarPor("preco_asc")}
              icone="payments"
            >
              {t("ofertas.menorPreco")}
            </Pilula>
          </div>
        </div>
      </div>

      <Consulta estado={ofertas} vazio={t("ofertas.nenhumaOferta")}>
        {(resposta) =>
          resposta.itens.length === 0 ? (
            <p className="py-space-xl text-center font-body-md text-body-md text-on-surface-variant">
              {t("ofertas.nenhumaOferta")}
            </p>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {resposta.itens.map((oferta) => (
                  <CartaoOferta key={oferta.app_id} oferta={oferta} />
                ))}
              </div>

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

function ChipHero({ icone, texto }: { icone: string; texto: string }) {
  return (
    <span className="inline-flex items-center gap-space-xxs rounded-full bg-surface-container-lowest/80 px-space-sm py-space-xxs font-badge-status text-badge-status text-on-surface-variant ring-1 ring-outline-variant/30 backdrop-blur-sm">
      <Icone nome={icone} className="text-[13px] text-primary" />
      {texto}
    </span>
  );
}

function CartaoOferta({ oferta }: { oferta: OfertaSteam }) {
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
      className="flex cursor-pointer flex-col overflow-hidden rounded-xl border border-outline-variant/15 bg-surface-container-low transition-colors hover:bg-surface-container-high/60"
    >
      <ArteJogo
        appId={oferta.app_id}
        nome={oferta.nome}
        imagemUrl={oferta.imagem_header}
        className="h-20 w-full rounded-none"
      />
      <div className="flex flex-1 flex-col gap-space-xs p-space-base">
        <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">
          {oferta.nome}
        </span>
        <span className="font-label-caps text-label-caps text-outline">
          {fmtRelativo(oferta.iniciada_em)}
        </span>

        <div className="mt-auto flex items-center justify-between gap-space-xs pt-space-sm">
          <div className="flex items-baseline gap-space-xs">
            <span className="font-title-code text-title-code text-outline line-through">
              {fmtMoeda(oferta.preco_original, oferta.moeda)}
            </span>
            <span className="font-headline-sm text-headline-sm font-bold text-tertiary">
              {fmtMoeda(oferta.preco_final, oferta.moeda)}
            </span>
          </div>
          <span className="shrink-0 rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status font-bold text-tertiary">
            -{oferta.desconto_percentual}%
          </span>
        </div>

        <span className="pt-space-xs font-title-code text-title-code uppercase tracking-wide text-primary">
          {t("ofertas.verJogo")} →
        </span>
      </div>
    </article>
  );
}
