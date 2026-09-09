/**
 * Historico de perguntas do assistente.
 *
 * O backend NAO persiste conversa: `/api/assistente/perguntar` e sem estado -
 * recebe uma pergunta, monta o contexto, devolve a resposta e esquece. Entao o
 * historico mora no navegador, e isso e uma escolha declarada, nao um
 * disfarce: nada aqui inventa pergunta que a pessoa nao fez, e a lista comeca
 * vazia de verdade em vez de nascer com exemplos plausiveis.
 *
 * A forma de `EntradaHistorico` ja e a que um endpoint de historico devolveria
 * (id, pergunta, momento, feedback). No dia em que o backend guardar isso,
 * troca-se a implementacao do hook e a tela nao muda.
 */

import { useCallback, useEffect, useState } from "react";

/** Uma pergunta que a pessoa realmente enviou, com o retorno que ela deu. */
export interface EntradaHistorico {
  id: string;
  pergunta: string;
  /** ISO 8601, em hora local do navegador. */
  em: string;
  /** `null` enquanto ninguem avaliou a resposta. */
  util: boolean | null;
}

const CHAVE = "playdb.assistente.historico";

/**
 * Teto de itens guardados.
 *
 * Nao e por espaco (sao poucos bytes), e por leitura: uma lateral com 500
 * perguntas deixa de ser historico e vira arquivo morto. 50 cobre semanas de
 * uso e ainda cabe na tela com rolagem curta.
 */
const MAXIMO = 50;

function ler(): EntradaHistorico[] {
  try {
    const bruto = window.localStorage.getItem(CHAVE);
    if (!bruto) return [];
    const dados: unknown = JSON.parse(bruto);
    if (!Array.isArray(dados)) return [];
    // Filtra em vez de confiar: o conteudo do localStorage pode ter sido
    // escrito por uma versao anterior desta tela, com outro formato.
    return dados.filter(
      (item): item is EntradaHistorico =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as EntradaHistorico).id === "string" &&
        typeof (item as EntradaHistorico).pergunta === "string" &&
        typeof (item as EntradaHistorico).em === "string",
    );
  } catch {
    // Modo anonimo, cota estourada, JSON corrompido: sem historico e um
    // estado valido da tela, nao um erro que valha interromper a pessoa.
    return [];
  }
}

function gravar(entradas: EntradaHistorico[]) {
  try {
    window.localStorage.setItem(CHAVE, JSON.stringify(entradas));
  } catch {
    // Idem: perder o historico e aceitavel, quebrar a pergunta nao.
  }
}

export function useHistoricoAssistente() {
  const [entradas, setEntradas] = useState<EntradaHistorico[]>([]);
  // Existe para a lateral distinguir "ainda nao li o armazenamento" de
  // "li e esta vazio" - sao dois estados visuais diferentes.
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    setEntradas(ler());
    setCarregando(false);
  }, []);

  const registrar = useCallback((pergunta: string) => {
    setEntradas((atuais) => {
      // Repetir a mesma pergunta nao cria linha nova - sobe a existente, que
      // e o que a pessoa espera de uma lista "recentes".
      const semRepetida = atuais.filter(
        (e) => e.pergunta.toLowerCase() !== pergunta.toLowerCase(),
      );
      const proximas = [
        { id: crypto.randomUUID(), pergunta, em: new Date().toISOString(), util: null },
        ...semRepetida,
      ].slice(0, MAXIMO);
      gravar(proximas);
      return proximas;
    });
  }, []);

  /** Guarda o polegar da resposta na pergunta correspondente. */
  const avaliar = useCallback((pergunta: string, util: boolean | null) => {
    setEntradas((atuais) => {
      const proximas = atuais.map((e) => (e.pergunta === pergunta ? { ...e, util } : e));
      gravar(proximas);
      return proximas;
    });
  }, []);

  const limpar = useCallback(() => {
    gravar([]);
    setEntradas([]);
  }, []);

  return { entradas, carregando, registrar, avaliar, limpar };
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
