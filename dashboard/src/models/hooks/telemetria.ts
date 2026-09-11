/**
 * Pageview + heartbeat de acesso ao site, pro painel admin.
 *
 * Um beacon "dispara e esquece" pro `POST /api/telemetria/acesso`: no
 * carregamento, a cada troca de rota, e num intervalo enquanto a aba fica
 * aberta (é isso que vira "quantas pessoas estão no site agora" -
 * `services/ml/telemetria_site.py`). Nunca aparece pro usuário se falhar -
 * telemetria é acessório, não pode competir com a experiência real da tela.
 *
 * `visitante_id` é um UUID gerado no navegador e guardado no localStorage -
 * identifica o MESMO visitante entre páginas sem cookie e sem nada que
 * identifique uma pessoa de verdade (não é IP, nome, nem e-mail).
 */

import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { urlApi } from "@models/api/cliente";

const CHAVE_VISITANTE = "playdb:visitante-id";
//: Um pouco abaixo da janela de "online agora" do backend (90s) — garante
//: pelo menos um heartbeat dentro da janela mesmo com uma chamada perdida.
const INTERVALO_HEARTBEAT_MS = 45_000;

function visitanteId(): string {
  try {
    let id = localStorage.getItem(CHAVE_VISITANTE);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(CHAVE_VISITANTE, id);
    }
    return id;
  } catch {
    // localStorage bloqueado (aba privada, etc.): um id novo por carregamento
    // - não quebra nada, só conta como visitante "novo" a cada vez.
    return crypto.randomUUID();
  }
}

function enviarBeacon(rota: string): void {
  const corpo = JSON.stringify({ visitante_id: visitanteId(), rota });
  const url = urlApi("/api/telemetria/acesso");

  try {
    // `sendBeacon` não bloqueia navegação e sobrevive à troca/fechamento de
    // página - ideal pra telemetria. `fetch` com `keepalive` é o fallback.
    if (navigator.sendBeacon?.(url, new Blob([corpo], { type: "application/json" }))) {
      return;
    }
  } catch {
    /* cai pro fetch abaixo */
  }

  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: corpo,
    keepalive: true,
  }).catch(() => {
    /* best-effort - telemetria nunca aparece pro usuário */
  });
}

/** Chamar uma vez, na raiz do app (`App.tsx`). */
export function useTelemetriaAcesso(): void {
  const rota = useLocation().pathname;

  // A rota "atual" pro heartbeat, sem reiniciar o intervalo a cada troca -
  // um `[rota]` na dependência do `setInterval` reiniciaria a contagem dos
  // 45s toda vez que a pessoa navegasse, e o heartbeat quase nunca disparia
  // num uso ativo da tela.
  const rotaAtual = useRef(rota);
  rotaAtual.current = rota;

  useEffect(() => {
    enviarBeacon(rota);
  }, [rota]);

  useEffect(() => {
    const intervalo = setInterval(() => enviarBeacon(rotaAtual.current), INTERVALO_HEARTBEAT_MS);
    return () => clearInterval(intervalo);
  }, []);
}
