/**
 * Perfil: dados da conta + a atividade pessoal que ela acumula - por
 * enquanto so o historico de perguntas ao Assistente de IA, a unica
 * atividade que o site liga a uma conta ate aqui (Fase 31).
 *
 * Exige conta - a tela so renderiza dentro de `RotaProtegida` (`App.tsx`).
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import { usePerfilUsuario } from "@models/api/consultas";
import { sairDaConta } from "@models/conta/acoes";
import { useUsuario } from "@models/conta/contexto";
import { Botao, Icone, MensagemErro } from "@views/componentes/base";
import { KpiHud, Painel } from "@views/componentes/hud";
import { fmtData, fmtNumero } from "@util/formatos";
import { agruparPorDia, useHistoricoAssistente } from "./assistente/historico";

function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function PerfilPagina() {
  const { usuario } = useUsuario();
  const perfil = usePerfilUsuario();
  const historico = useHistoricoAssistente();
  const [saindo, setSaindo] = useState(false);

  async function sair() {
    setSaindo(true);
    try {
      await sairDaConta();
    } finally {
      setSaindo(false);
    }
  }

  const grupos = agruparPorDia(historico.entradas);

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-space-sm">
        <h1 className="flex items-center gap-space-xs font-headline-lg text-headline-lg uppercase tracking-wide text-on-surface">
          <Icone nome="account_circle" className="text-[24px] text-primary" />
          Perfil
        </h1>
        <Botao icone="logout" aoClicar={sair} desabilitado={saindo}>
          Sair
        </Botao>
      </header>

      <Painel icone="badge" titulo="Sua conta">
        {perfil.isError ? (
          <MensagemErro erro={perfil.error} />
        ) : (
          <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2">
            <div className="flex flex-col gap-space-xxs rounded-lg bg-surface-container-lowest p-space-base">
              <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                E-mail
              </span>
              <span className="font-body-md text-body-md text-on-surface">
                {usuario?.email ?? perfil.data?.email ?? "—"}
              </span>
            </div>
            <div className="flex flex-col gap-space-xxs rounded-lg bg-surface-container-lowest p-space-base">
              <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Membro desde
              </span>
              <span className="font-body-md text-body-md text-on-surface">
                {perfil.data ? fmtData(perfil.data.membro_desde) : "—"}
              </span>
            </div>
          </div>
        )}
      </Painel>

      <Painel
        icone="smart_toy"
        titulo="Perguntas ao Assistente de IA"
        descricao="As perguntas que você já fez — só o texto da pergunta, não a resposta."
        meta={
          perfil.data && (
            <div className="min-w-[10rem]">
              <KpiHud
                etiqueta="Total"
                valor={fmtNumero(perfil.data.total_perguntas_assistente)}
                valorNumerico={perfil.data.total_perguntas_assistente}
                formatarValor={fmtNumero}
                rotulo="perguntas"
                acento="primaria"
              />
            </div>
          )
        }
      >
        {historico.carregando ? (
          <div className="flex flex-col gap-space-xs" aria-hidden>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-surface-container-high/60" />
            ))}
          </div>
        ) : grupos.length === 0 ? (
          <p className="font-body-sm text-body-sm text-outline">
            Nenhuma pergunta ainda. Vá até o{" "}
            <Link to="/assistente" className="text-primary hover:underline">
              Assistente de IA
            </Link>{" "}
            e pergunte algo sobre os dados do PlayDB.
          </p>
        ) : (
          <div className="flex flex-col gap-space-sm">
            {grupos.map((grupo) => (
              <div key={grupo.dia}>
                <div className="pb-space-xxs font-badge-status text-badge-status uppercase tracking-wider text-outline/70">
                  {grupo.dia}
                </div>
                <ul className="flex flex-col gap-space-xxs">
                  {grupo.itens.map((entrada) => (
                    <li
                      key={entrada.id}
                      className="flex items-center gap-space-sm rounded bg-surface-container-lowest px-space-sm py-space-xs"
                    >
                      <Icone
                        nome={
                          entrada.util === true
                            ? "thumb_up"
                            : entrada.util === false
                              ? "thumb_down"
                              : "chat_bubble"
                        }
                        className="shrink-0 text-[14px] text-outline"
                      />
                      <span className="min-w-0 flex-1 truncate font-body-sm text-body-sm text-on-surface-variant">
                        {entrada.pergunta}
                      </span>
                      <span className="shrink-0 font-badge-status text-badge-status tabular-nums text-outline">
                        {hora(entrada.em)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            <button
              type="button"
              onClick={historico.limpar}
              className="mt-space-xs flex items-center justify-center gap-space-xs self-start rounded border border-outline-variant/30 px-space-base py-space-xs font-title-code text-title-code text-outline transition-colors hover:border-error/40 hover:text-error"
            >
              <Icone nome="delete" className="text-[16px]" />
              Limpar histórico
            </button>
          </div>
        )}
      </Painel>
    </>
  );
}
