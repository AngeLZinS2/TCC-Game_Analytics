/**
 * "Sua chave de IA": cada conta pode cadastrar a propria chave do
 * OpenRouter - o Assistente de IA passa a usar ELA so nas perguntas dessa
 * conta, sem disputar a cota da chave compartilhada do site (a mesma que
 * fica rate-limited quando muita gente usa ao mesmo tempo).
 *
 * A chave nunca volta do backend em texto puro - so a mascara
 * (`chave_ia_mascarada`, os ultimos 4 caracteres). Trocar significa cadastrar
 * uma nova por cima, nao "editar" a antiga.
 */

import { useState, type FormEvent } from "react";

import { useRemoverChaveIA, useSalvarChaveIA } from "@models/api/consultas";
import type { PerfilUsuario } from "@models/api/tipos";
import { Icone, MensagemErro } from "@views/componentes/base";
import { CAMPO, Painel } from "@views/componentes/hud";

export function PainelChaveIA({ perfil }: { perfil: PerfilUsuario | undefined }) {
  const salvar = useSalvarChaveIA();
  const remover = useRemoverChaveIA();
  const [chave, setChave] = useState("");
  const [editando, setEditando] = useState(false);

  const temChave = perfil?.tem_chave_ia_propria ?? false;
  const mostrarForm = !temChave || editando;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (chave.trim().length < 10) return;
    await salvar.mutateAsync(chave.trim());
    setChave("");
    setEditando(false);
  }

  return (
    <Painel
      icone="vpn_key"
      titulo="Sua chave de IA"
      descricao="Opcional. Cadastre sua própria chave do OpenRouter e o Assistente de IA passa a usar ela só nas suas perguntas, em vez da chave compartilhada do site."
    >
      {temChave && !editando && (
        <div className="flex flex-wrap items-center justify-between gap-space-sm rounded-lg bg-surface-container-lowest p-space-base">
          <span className="flex items-center gap-space-xs font-body-md text-body-sm text-on-surface">
            <Icone nome="check_circle" className="text-[18px] text-tertiary" />
            Usando sua chave —{" "}
            <code className="text-on-surface-variant">{perfil?.chave_ia_mascarada}</code>
          </span>
          <div className="flex items-center gap-space-xs">
            <button
              type="button"
              onClick={() => setEditando(true)}
              className="font-title-code text-title-code text-primary hover:underline"
            >
              Trocar
            </button>
            <button
              type="button"
              onClick={() => remover.mutate()}
              disabled={remover.isPending}
              className="font-title-code text-title-code text-outline transition-colors hover:text-error disabled:cursor-not-allowed disabled:opacity-50"
            >
              Remover
            </button>
          </div>
        </div>
      )}

      {mostrarForm && (
        <form onSubmit={enviar} className="flex flex-col gap-space-sm">
          <div className="flex flex-col gap-space-xs sm:flex-row">
            <input
              type="password"
              value={chave}
              onChange={(evento) => setChave(evento.target.value)}
              placeholder="sk-or-v1-…"
              className={CAMPO + " flex-1"}
              autoComplete="off"
            />
            <button
              type="submit"
              disabled={salvar.isPending || chave.trim().length < 10}
              className="flex min-h-[44px] items-center justify-center gap-space-xs rounded bg-primary-container px-space-base py-space-xs font-title-code text-title-code text-on-primary transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-0"
            >
              {salvar.isPending ? (
                <Icone nome="progress_activity" className="animate-spin text-[16px]" />
              ) : (
                <Icone nome="save" className="text-[16px]" />
              )}
              Salvar
            </button>
            {editando && (
              <button
                type="button"
                onClick={() => {
                  setEditando(false);
                  setChave("");
                }}
                className="font-title-code text-title-code text-outline hover:text-on-surface"
              >
                Cancelar
              </button>
            )}
          </div>

          {salvar.isError && <MensagemErro erro={salvar.error} />}

          <p className="font-body-sm text-body-sm text-outline">
            Chave gratuita em{" "}
            <a
              href="https://openrouter.ai/keys"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              openrouter.ai/keys
            </a>
            . Fica cifrada no banco — nunca reaparece em texto puro, nem pra você.
          </p>
        </form>
      )}
    </Painel>
  );
}
