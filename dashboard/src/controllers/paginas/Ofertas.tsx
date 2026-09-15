/**
 * Ofertas — promoções ABERTAS agora na própria Steam (Fase 35).
 *
 * Primeiro-partido: preço/desconto vêm do nosso próprio `steam_promocoes`,
 * nunca de uma chamada ao vivo à Steam nem de uma heurística de "fração do
 * catálogo em desconto" apresentada como evento oficial — a Steam não expõe
 * calendário de sales, então esta tela não inventa um. O que ela mostra é
 * sempre uma transição real de desconto observada num jogo específico.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useOfertasSteam } from "@models/api/consultas";
import type { OfertaSteam } from "@models/api/tipos";
import type { FiltrosOfertasSteam } from "@models/api/consultas";
import { Consulta } from "@views/componentes/base";
import { Pilula } from "@views/componentes/hud";
import { ArteJogo } from "@views/componentes/CapaJogo";
import { fmtMoeda, fmtRelativo } from "@util/formatos";

const LIMIARES_DESCONTO = [0, 10, 25, 50, 75] as const;

export function OfertasPagina() {
  const { t } = useTranslation();
  const [descontoMinimo, setDescontoMinimo] = useState<number>(0);
  const [ordenarPor, setOrdenarPor] =
    useState<FiltrosOfertasSteam["ordenar_por"]>("desconto_desc");

  const ofertas = useOfertasSteam({
    desconto_minimo: descontoMinimo,
    ordenar_por: ordenarPor,
    limite: 60,
  });

  return (
    <div className="space-y-space-xl">
      <div className="flex flex-col gap-space-base border-b border-outline-variant/30 pb-space-base pt-space-base">
        <span className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface-variant">
          {t("ofertas.titulo")}
        </span>
        <p className="max-w-2xl font-body-sm text-body-sm text-on-surface-variant">
          {t("ofertas.descricao")}
        </p>

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
        {(linhas) => (
          <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {linhas.map((oferta) => (
              <CartaoOferta key={oferta.app_id} oferta={oferta} />
            ))}
          </div>
        )}
      </Consulta>
    </div>
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
        className="h-32 w-full rounded-none"
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
