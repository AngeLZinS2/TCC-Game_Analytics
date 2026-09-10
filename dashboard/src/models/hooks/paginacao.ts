/**
 * Paginacao client-side: renderiza um pedaco de uma lista ja carregada.
 *
 * As listas do PlayDB tem centenas de linhas, nao milhares - a API ja devolve
 * o recorte inteiro (capado em 200-500) e a tela mostra 25/50 por vez. Isso
 * evita o scroll infinito de uma tabela de 500 linhas sem gastar um endpoint
 * paginado no backend.
 *
 * O padrao ja existia solto em `Jogadores.tsx` (slice + `useEffect` que volta
 * pra pagina 1 quando o filtro muda). Aqui vira um hook para as telas de
 * catalogo e reviews compartilharem a mesma logica.
 *
 * `chaveReset` e a assinatura dos filtros da tela (ex.
 * `` `${busca}|${genero}|${ordem}` ``): quando ela muda, a lista mudou de
 * conteudo e a pagina volta pra 1. `pagina` sai sempre travada dentro de
 * `[1, totalPaginas]`, entao trocar um filtro que encolhe a lista nao deixa a
 * tela numa pagina vazia.
 *
 * `porPaginaInicial` aceita um numero ou `{ mobile, desktop }`: no celular a
 * tela comeca com poucas linhas (5) pra nao virar um rolo sem fim; o leitor
 * troca pra 15/25 se quiser. So o VALOR INICIAL depende do tamanho da tela -
 * depois que o leitor escolhe, a escolha vale ate ele mudar de novo.
 */

import { useEffect, useState } from "react";

import { useEhMobile } from "@models/hooks/media";

export interface PaginacaoLocal<T> {
  /** Base 1, ja travada em `[1, totalPaginas]`. */
  pagina: number;
  porPagina: number;
  totalPaginas: number;
  /** Os itens da pagina atual. */
  fatia: T[];
  setPagina: (pagina: number) => void;
  setPorPagina: (quantidade: number) => void;
}

export function usePaginacaoLocal<T>(
  itens: T[],
  opcoes: {
    porPaginaInicial?: number | { mobile: number; desktop: number };
    chaveReset?: string;
  } = {},
): PaginacaoLocal<T> {
  const { porPaginaInicial = { mobile: 5, desktop: 25 }, chaveReset = "" } =
    opcoes;
  const ehMobile = useEhMobile();

  const inicial =
    typeof porPaginaInicial === "number"
      ? porPaginaInicial
      : ehMobile
        ? porPaginaInicial.mobile
        : porPaginaInicial.desktop;

  const [pagina, setPagina] = useState(1);
  // `useState` guarda o primeiro valor; `inicial` ja vem certo no primeiro
  // render (o `useEhMobile` le o `matchMedia` de forma sincrona).
  const [porPagina, setPorPagina] = useState(inicial);

  // Volta pra pagina 1 quando o filtro muda ou quando muda linhas/pagina.
  useEffect(() => {
    setPagina(1);
  }, [chaveReset, porPagina]);

  const totalPaginas = Math.max(1, Math.ceil(itens.length / porPagina));
  const paginaSegura = Math.min(Math.max(1, pagina), totalPaginas);
  const fatia = itens.slice(
    (paginaSegura - 1) * porPagina,
    paginaSegura * porPagina,
  );

  return {
    pagina: paginaSegura,
    porPagina,
    totalPaginas,
    fatia,
    setPagina,
    setPorPagina,
  };
}
