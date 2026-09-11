/**
 * Porta de entrada do painel admin: só uma senha (`ADMIN_SENHA`), sem conta.
 *
 * O token que volta do login é um HMAC assinado pelo backend, guardado em
 * `localStorage` via `sessao.ts` — não há sessão de servidor. Enquanto não
 * existir um sistema de contas de verdade, isto é deliberadamente o mínimo
 * que protege a tela sem fingir ser mais do que é.
 */

import { useState, type FormEvent } from "react";

import { useLoginAdmin } from "@models/api/consultas";
import { ErroApi } from "@models/api/cliente";
import { Icone } from "@views/componentes/base";
import { CAMPO } from "@views/componentes/hud";

export function AdminLogin({ aoAutenticar }: { aoAutenticar: () => void }) {
  const [senha, setSenha] = useState("");
  const login = useLoginAdmin();

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (!senha) return;
    login.mutate(senha, { onSuccess: aoAutenticar });
  }

  const mensagemErro =
    login.error instanceof ErroApi
      ? login.error.status === 401
        ? "Senha incorreta."
        : login.error.status === 503
          ? "Painel admin não configurado (ADMIN_SENHA ausente no servidor)."
          : login.error.detalhe
      : login.isError
        ? "Não foi possível falar com a API."
        : null;

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <form
        onSubmit={enviar}
        className="flex w-full max-w-sm flex-col gap-space-base rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl"
      >
        <div className="flex flex-col items-center gap-space-xs text-center">
          <Icone nome="admin_panel_settings" className="text-[32px] text-primary" />
          <h1 className="font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
            Painel Admin
          </h1>
          <p className="font-body-sm text-body-sm text-outline">
            Estatísticas do site e saúde da VPS. Acesso restrito.
          </p>
        </div>

        <label className="flex flex-col gap-space-xxs">
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            Senha
          </span>
          <input
            type="password"
            autoFocus
            value={senha}
            onChange={(evento) => setSenha(evento.target.value)}
            className={CAMPO}
            placeholder="••••••••"
          />
        </label>

        {mensagemErro && (
          <p className="flex items-start gap-space-xs font-body-sm text-body-sm text-error">
            <Icone nome="error" className="mt-[2px] text-[15px]" />
            {mensagemErro}
          </p>
        )}

        <button
          type="submit"
          disabled={!senha || login.isPending}
          className="flex min-h-[44px] items-center justify-center gap-space-xs rounded bg-primary-container px-space-base py-space-xs font-title-code text-title-code text-on-primary transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {login.isPending ? (
            <Icone nome="progress_activity" className="animate-spin text-[18px]" />
          ) : (
            <Icone nome="login" className="text-[18px]" />
          )}
          Entrar
        </button>
      </form>
    </div>
  );
}
