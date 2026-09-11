/**
 * Historico de perguntas do assistente - por conta (Fase 31), nao mais por
 * navegador.
 *
 * Ate aqui isto vivia so no `localStorage` (ver o comentario antigo, ainda
 * valido sobre o resto: o backend responde uma pergunta e esquece, o texto
 * puro da resposta nunca foi guardado, so a pergunta). Com conta de verdade,
 * a pessoa pediu pra isso passar a acompanhar ela entre navegadores -
 * `usePerguntarAssistente` grava a pergunta no servidor assim que a resposta
 * chega, e este hook so le/avalia/limpa contra `/api/usuario/historico-assistente`.
 *
 * A forma devolvida e a mesma de antes (`entradas`, `carregando`, `avaliar`,
 * `limpar`) pra `PainelHistorico`/`AssistenteIA` nao precisarem mudar.
 */

import { useCallback } from "react";

import {
  useAvaliarPerguntaAssistente,
  useHistoricoAssistenteServidor,
  useLimparHistoricoAssistente,
} from "@models/api/consultas";
import type { EntradaHistoricoAssistente } from "@models/api/tipos";

/** Alias mantido pelo nome antigo - so os consumidores desta tela usam. */
export type EntradaHistorico = EntradaHistoricoAssistente;

export function useHistoricoAssistente() {
  const consulta = useHistoricoAssistenteServidor();
  const avaliarMutacao = useAvaliarPerguntaAssistente();
  const limparMutacao = useLimparHistoricoAssistente();

  const entradas = consulta.data ?? [];

  /** Casa por texto (nao por id): e como a tela ja identificava "a pergunta
   * atual" antes de existir id nenhum, e continua funcionando porque o
   * backend nao deduplica pergunta repetida no historico. */
  const avaliar = useCallback(
    (pergunta: string, util: boolean | null) => {
      const entrada = entradas.find((e) => e.pergunta === pergunta);
      if (entrada) avaliarMutacao.mutate({ id: entrada.id, util });
    },
    [entradas, avaliarMutacao],
  );

  const limpar = useCallback(() => {
    limparMutacao.mutate();
  }, [limparMutacao]);

  return {
    entradas,
    carregando: consulta.isPending,
    avaliar,
    limpar,
  };
}

/** O rotulo do grupo de uma entrada: "Hoje", "Ontem" ou a data. */
export function grupoDoDia(iso: string): string {
  const data = new Date(iso);
  const hoje = new Date();
  const ontem = new Date();
  ontem.setDate(hoje.getDate() - 1);

  const mesmoDia = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (mesmoDia(data, hoje)) return "Hoje";
  if (mesmoDia(data, ontem)) return "Ontem";
  return data.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

/** Agrupa preservando a ordem (mais recente primeiro) que a lista ja tem. */
export function agruparPorDia(
  entradas: EntradaHistorico[],
): { dia: string; itens: EntradaHistorico[] }[] {
  const grupos: { dia: string; itens: EntradaHistorico[] }[] = [];
  for (const entrada of entradas) {
    const dia = grupoDoDia(entrada.em);
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.dia === dia) ultimo.itens.push(entrada);
    else grupos.push({ dia, itens: [entrada] });
  }
  return grupos;
}
