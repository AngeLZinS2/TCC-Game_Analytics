/**
 * A capa de um jogo da Steam.
 *
 * A imagem nao e coletada: a CDN da Valve serve a capsula num caminho
 * deterministico a partir do `app_id`, entao ela sai de graca do dado que ja
 * temos, sem gastar linha na lista (ver `imagem_header` em `FichaJogoSteam`).
 * Mas Valve vem migrando jogos novos pra um caminho com hash de conteudo
 * (`store_item_assets/.../header_alt_assets_2.jpg?t=...`), e nesses o
 * caminho deterministico da 404 - so a ficha do jogo (que ja fez a chamada
 * real na API da Steam) sabe a URL de verdade. Por isso `imagemUrl`: quando
 * a tela ja tem a ficha carregada (detalhe do jogo), ela manda a URL real e
 * essa vence; quando so ha o `app_id` (linha de tabela, resultado de busca),
 * cai no palpite deterministico de sempre.
 *
 * Nem todo app tem capsula publicada. Quando a imagem falha (dos dois jeitos),
 * o lugar dela e ocupado pela inicial do jogo - o desenho conta com um bloco
 * de 48px ali, e deixar o buraco desalinharia a linha inteira da tabela.
 */

import { useState } from "react";

const CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps";

export function CapaJogo({
  appId,
  nome,
  imagemUrl,
  className = "h-12 w-12",
}: {
  appId: number;
  nome: string;
  /** URL real da ficha (Steam API), quando ja disponivel. Vence o palpite de CDN. */
  imagemUrl?: string | null;
  className?: string;
}) {
  const [falhou, setFalhou] = useState(false);

  if (falhou) {
    return (
      <div
        className={`flex shrink-0 items-center justify-center rounded bg-surface-container-high font-headline-md text-headline-md text-outline ${className}`}
        aria-hidden
      >
        {nome.charAt(0).toUpperCase()}
      </div>
    );
  }

  return (
    <img
      src={imagemUrl || `${CDN}/${appId}/capsule_231x87.jpg`}
      alt=""
      loading="lazy"
      onError={() => setFalhou(true)}
      className={`shrink-0 rounded bg-surface-container object-cover shadow-md ${className}`}
    />
  );
}

/**
 * A arte de destaque do jogo - a mesma que a loja da Steam usa no topo da
 * pagina de um jogo (`header.jpg`, 460x215).
 *
 * Serve a um proposito diferente da `CapaJogo`: aquela e a miniatura de uma
 * linha de tabela, esta e o cartao de destaque de UM jogo. Por isso a proporcao
 * larga e o `object-cover`.
 */
export function ArteJogo({
  appId,
  nome,
  imagemUrl,
  className = "h-40 w-full",
}: {
  appId: number;
  nome: string;
  /** URL real da ficha (Steam API), quando ja disponivel. Vence o palpite de CDN. */
  imagemUrl?: string | null;
  className?: string;
}) {
  const [falhou, setFalhou] = useState(false);

  if (falhou) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg bg-surface-container-high font-display-hero text-display-hero text-outline ${className}`}
        aria-hidden
      >
        {nome.charAt(0).toUpperCase()}
      </div>
    );
  }

  return (
    <img
      src={imagemUrl || `${CDN}/${appId}/header.jpg`}
      alt=""
      onError={() => setFalhou(true)}
      className={`rounded-lg object-cover shadow-lg ${className}`}
    />
  );
}
