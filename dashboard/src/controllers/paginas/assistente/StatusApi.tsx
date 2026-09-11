/**
 * Status da API do Assistente, em tempo real.
 *
 * O `/auth/key` do OpenRouter não devolve quanto falta da cota grátis (só
 * custo em dólar, que fica 0 pro modelo `:free` seja qual for o volume) -
 * então isto é telemetria das NOSSAS chamadas (`useSaudeAssistente`, poll de
 * 15s), não do provedor. Existe pra um 429 aparecer como "modelo grátis
 * limitado agora" em vez de parecer bug nosso.
 */

import { useSaudeAssistente } from "@models/api/consultas";
import { Icone } from "@views/componentes/base";
import { PALETA_POLOS, TOKENS } from "@views/tema";
import { fmtRelativo } from "@util/formatos";

export function StatusApiAssistente() {
  const saude = useSaudeAssistente();
  const dados = saude.data;

  // Sem dado ainda (1ª carga) ou assistente não configurado: a tela já
  // explica isso em outro lugar, este painel não repete.
  if (!dados || !dados.configurado) return null;

  const semHistorico = dados.total_recente === 0;
  const cor = semHistorico
    ? TOKENS.contorno
    : dados.rate_limited_recente
      ? PALETA_POLOS.negativo
      : dados.ultima_chamada_sucesso
        ? PALETA_POLOS.positivo
        : PALETA_POLOS.negativo;

  const rotulo = semHistorico
    ? "Ainda sem chamadas nesta sessão"
    : dados.rate_limited_recente
      ? "Rate-limited pelo provedor"
      : dados.ultima_chamada_sucesso
        ? "Operando normalmente"
        : "Com falhas recentes";

  return (
    <div className="flex flex-col gap-space-xs rounded-xl bg-surface-container-low/60 p-space-base">
      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        <div className="flex items-center gap-space-xs">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: cor, boxShadow: `0 0 6px ${cor}99` }}
            aria-hidden
          />
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-on-surface">
            Status da API
          </span>
          <span className="font-body-sm text-body-sm text-on-surface-variant">
            · {rotulo}
          </span>
        </div>

        {!semHistorico && (
          <span
            className="font-badge-status text-badge-status uppercase tracking-wide text-outline"
            title={
              dados.ultima_chamada_em
                ? `última chamada: ${fmtRelativo(dados.ultima_chamada_em)}`
                : undefined
            }
          >
            {dados.sucessos_recente}/{dados.total_recente} ok · últimas chamadas
          </span>
        )}
      </div>

      {!semHistorico && (
        <div className="flex items-center gap-[3px]" aria-hidden>
          {dados.chamadas.map((chamada, i) => (
            <span
              key={i}
              title={`${chamada.sucesso ? "ok" : chamada.rate_limited ? "rate-limited (429)" : `erro${chamada.status_http ? ` ${chamada.status_http}` : ""}`} · ${fmtRelativo(chamada.quando)} · ${chamada.duracao_ms} ms`}
              className="h-3 w-1.5 rounded-full"
              style={{
                backgroundColor: chamada.sucesso
                  ? PALETA_POLOS.positivo
                  : PALETA_POLOS.negativo,
                opacity: 0.45 + 0.55 * ((i + 1) / dados.chamadas.length),
              }}
            />
          ))}
        </div>
      )}

      {dados.rate_limited_recente && (
        <p className="flex items-start gap-space-xs font-body-sm text-body-sm text-on-surface-variant">
          <Icone nome="info" className="mt-[2px] text-[15px] text-primary" />
          O modelo grátis do OpenRouter tem cota compartilhada entre todo
          mundo que usa a chave sem crédito (50 perguntas/dia, 20/min). Tente
          de novo em instantes.
        </p>
      )}
    </div>
  );
}
