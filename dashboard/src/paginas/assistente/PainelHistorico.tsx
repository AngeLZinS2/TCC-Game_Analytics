/**
 * A lateral esquerda: as perguntas que ESTA pessoa fez, neste navegador.
 *
 * Nao ha historico no servidor (ver `historico.ts`), e a lista comeca vazia de
 * verdade - com um estado vazio que explica por que, em vez de cinco perguntas
 * de exemplo que dariam a impressao de um uso que nunca houve.
 */

import { useMemo, useState } from "react";

import { Icone } from "../../componentes/base";
import { agruparPorDia, type EntradaHistorico } from "./historico";

function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PainelHistorico({
  entradas,
  carregando,
  perguntaAtual,
  aoEscolher,
  aoLimpar,
}: {
  entradas: EntradaHistorico[];
  carregando: boolean;
  perguntaAtual: string | null;
  aoEscolher: (pergunta: string) => void;
  aoLimpar: () => void;
}) {
  const [busca, setBusca] = useState("");

  // O filtro e local e a lista tem teto de 50 - nao precisa de debounce nem
  // de virtualizacao; seria complexidade sem problema para resolver.
  const grupos = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    const filtradas = termo
      ? entradas.filter((e) => e.pergunta.toLowerCase().includes(termo))
      : entradas;
    return agruparPorDia(filtradas);
  }, [entradas, busca]);

  return (
    <div className="flex h-full flex-col gap-space-sm rounded-xl bg-surface-container-low/90 p-space-base shadow-2xl">
      <div className="flex items-center justify-between gap-space-xs">
        <h2 className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
          Histórico
        </h2>
        <span className="font-badge-status text-badge-status uppercase text-outline/70">
          {entradas.length ? `${entradas.length}` : ""}
        </span>
      </div>

      {entradas.length > 0 && (
        <div className="flex items-center gap-space-xs rounded bg-surface-container px-space-sm py-space-xxs">
          <Icone nome="search" className="text-[16px] text-outline" />
          <input
            type="search"
            value={busca}
            onChange={(evento) => setBusca(evento.target.value)}
            placeholder="Buscar"
            aria-label="Buscar no histórico"
            className="w-full bg-transparent py-space-xxs font-body-sm text-body-sm text-on-surface outline-none placeholder:text-outline"
          />
        </div>
      )}

      <div className="rolagem-discreta -mx-space-xs flex-1 overflow-y-auto px-space-xs">
        {carregando ? (
          <div className="flex flex-col gap-space-xs" aria-hidden>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-8 animate-pulse rounded bg-surface-container/60" />
            ))}
          </div>
        ) : grupos.length === 0 ? (
          <p className="py-space-base font-body-sm text-body-sm text-outline">
            {busca
              ? "Nenhuma pergunta com esse termo."
              : "Suas perguntas aparecem aqui. Ficam só neste navegador — o assistente não guarda conversa no servidor."}
          </p>
        ) : (
          grupos.map((grupo) => (
            <div key={grupo.dia} className="mb-space-sm">
              <div className="py-space-xxs font-badge-status text-badge-status uppercase tracking-wider text-outline/70">
                {grupo.dia}
              </div>
              <ul className="flex flex-col gap-space-xxs">
                {grupo.itens.map((entrada) => {
                  const ativa = entrada.pergunta === perguntaAtual;
                  return (
                    <li key={entrada.id}>
                      <button
                        type="button"
                        onClick={() => aoEscolher(entrada.pergunta)}
                        aria-current={ativa ? "true" : undefined}
                        className={[
                          "flex w-full items-center gap-space-xs rounded px-space-xs py-space-xs text-left transition-colors",
                          ativa
                            ? "bg-primary-container/15 text-primary ring-1 ring-primary/30"
                            : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
                        ].join(" ")}
                      >
                        <Icone
                          nome={
                            entrada.util === true
                              ? "thumb_up"
                              : entrada.util === false
                                ? "thumb_down"
                                : "chat_bubble"
                          }
                          className="shrink-0 text-[14px] opacity-70"
                        />
                        <span className="min-w-0 flex-1 truncate font-body-sm text-body-sm">
                          {entrada.pergunta}
                        </span>
                        <span className="shrink-0 font-badge-status text-badge-status tabular-nums text-outline">
                          {hora(entrada.em)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </div>

      {entradas.length > 0 && (
        <button
          type="button"
          onClick={aoLimpar}
          className="flex items-center justify-center gap-space-xs rounded border border-outline-variant/30 py-space-xs font-title-code text-title-code text-outline transition-colors hover:border-error/40 hover:text-error"
        >
          <Icone nome="delete" className="text-[16px]" />
          Limpar histórico
        </button>
      )}
    </div>
  );
}
