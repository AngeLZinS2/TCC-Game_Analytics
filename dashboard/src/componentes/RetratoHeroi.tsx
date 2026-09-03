/**
 * O retrato de um heroi do Dota.
 *
 * Mesma ideia da `CapaJogo`: a CDN da Valve serve a arte num caminho
 * deterministico, aqui derivado do `nome_interno` que ja esta em
 * `dim_personagem` (`npc_dota_hero_razor` -> `razor.png`). Nada a coletar,
 * nada a guardar.
 *
 * `nome_interno` e nulo quando a dimensao foi preenchida so pelo fato, sem o
 * endpoint /heroes ter rodado - por isso o retrato precisa de um substituto.
 */

import { useState } from "react";

// `heroes/icons/<nome>.png` e a versao quadrada; `heroes/<nome>.png` e o
// banner 256x144, que num quadrado de 24px vira uma fatia do meio da arte.
const CDN =
  "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/icons";
const PREFIXO = "npc_dota_hero_";

export function RetratoHeroi({
  nome,
  nomeInterno,
  className = "h-6 w-6",
}: {
  nome: string;
  nomeInterno: string | null;
  className?: string;
}) {
  const [falhou, setFalhou] = useState(false);
  const curto = nomeInterno?.startsWith(PREFIXO)
    ? nomeInterno.slice(PREFIXO.length)
    : null;

  if (!curto || falhou) {
    return (
      <div
        className={`flex shrink-0 items-center justify-center overflow-hidden rounded border border-outline-variant bg-surface-container-high font-label-caps text-label-caps text-outline ${className}`}
        aria-hidden
      >
        {nome.charAt(0).toUpperCase()}
      </div>
    );
  }

  return (
    <div
      className={`shrink-0 overflow-hidden rounded border border-outline-variant ${className}`}
    >
      <img
        src={`${CDN}/${curto}.png`}
        alt=""
        // Sem `loading="lazy"`: dentro do grafico divergente o Chrome nunca
        // chegava a disparar o pedido - a imagem ficava pendente para sempre,
        // e com ela nem o retrato nem o substituto apareciam, porque `onError`
        // so dispara quando o pedido FALHA, nao quando ele nao acontece.
        onError={() => setFalhou(true)}
        className="h-full w-full object-cover"
      />
    </div>
  );
}
