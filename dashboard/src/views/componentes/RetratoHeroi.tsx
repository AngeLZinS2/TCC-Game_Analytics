/**
 * O retrato quadrado de um personagem — herói, agente ou campeão.
 *
 * A URL vem PRONTA do backend (`ResumoPersonagem.icone`), que sabe a CDN de
 * cada jogo: Valve para Dota, Community Dragon para LoL, valorant-api para os
 * agentes. Antes o componente só sabia derivar o caminho da Valve a partir de
 * `npc_dota_hero_*`, então agente e campeão caíam no quadrado cinza com a
 * inicial.
 *
 * `nomeInterno` ainda é aceito como fonte alternativa para as telas que não
 * passam pelo endpoint de personagens (o placar de uma partida de Dota).
 * `nome` é o rótulo do substituto e o `alt`.
 */

import { useEffect, useState } from "react";

const CDN_DOTA =
  "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/icons";
const PREFIXO_DOTA = "npc_dota_hero_";

export function RetratoHeroi({
  nome,
  nomeInterno = null,
  icone = null,
  className = "h-6 w-6",
}: {
  nome: string;
  nomeInterno?: string | null;
  icone?: string | null;
  className?: string;
}) {
  const [falhou, setFalhou] = useState(false);

  // `icone` do backend tem prioridade; o derivado do `npc_dota_hero_*` é o
  // fallback para quem não passa por lá.
  const curtoDota = nomeInterno?.startsWith(PREFIXO_DOTA)
    ? nomeInterno.slice(PREFIXO_DOTA.length)
    : null;
  const src = icone ?? (curtoDota ? `${CDN_DOTA}/${curtoDota}.png` : null);

  // Uma URL nova (trocar de jogo na tabela) tem que rearmar o `onError`: sem
  // isso, um retrato que falhou uma vez ficava como quadrado para sempre.
  useEffect(() => setFalhou(false), [src]);

  if (!src || falhou) {
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
        src={src}
        alt=""
        // Sem `loading="lazy"`: dentro do gráfico divergente o Chrome nunca
        // chegava a disparar o pedido — a imagem ficava pendente para sempre,
        // e com ela nem o retrato nem o substituto apareciam, porque `onError`
        // só dispara quando o pedido FALHA, não quando ele não acontece.
        onError={() => setFalhou(true)}
        className="h-full w-full object-cover"
      />
    </div>
  );
}
