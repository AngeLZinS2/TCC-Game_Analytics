/**
 * Porta de entrada da conta: entrar, criar conta ou recuperar senha - tudo
 * num so formulario que troca de modo. E o que qualquer rota protegida
 * (`RotaProtegida.tsx`) mostra no lugar do conteudo quando ninguem esta
 * logado.
 *
 * Autenticacao de verdade, via Firebase: cria a conta, guarda a senha (com
 * hash, do lado deles) e confere a credencial no login - nada disso passa
 * pelo nosso backend.
 */

import { useState, type FormEvent } from "react";

import {
  criarContaComEmailSenha,
  entrarComEmailSenha,
  mensagemErroConta,
  redefinirSenhaPorEmail,
} from "@models/conta/acoes";
import { Icone } from "@views/componentes/base";
import { CAMPO } from "@views/componentes/hud";

type Modo = "entrar" | "cadastro" | "recuperar";

const TEXTOS: Record<Modo, { titulo: string; acao: string; icone: string }> = {
  entrar: { titulo: "Entrar", acao: "Entrar", icone: "login" },
  cadastro: { titulo: "Criar conta", acao: "Criar conta", icone: "person_add" },
  recuperar: { titulo: "Recuperar senha", acao: "Enviar e-mail", icone: "mail" },
};

export function EntrarOuCriarConta({
  titulo = "Entre para continuar",
  descricao = "Esta área é exclusiva para quem tem conta no PlayDB.",
}: {
  titulo?: string;
  descricao?: string;
}) {
  const [modo, setModo] = useState<Modo>("entrar");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [emailEnviado, setEmailEnviado] = useState(false);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (!email || (modo !== "recuperar" && !senha)) return;

    setEnviando(true);
    setErro(null);
    try {
      if (modo === "entrar") {
        await entrarComEmailSenha(email, senha);
      } else if (modo === "cadastro") {
        await criarContaComEmailSenha(email, senha);
      } else {
        await redefinirSenhaPorEmail(email);
        setEmailEnviado(true);
      }
    } catch (excecao) {
      setErro(mensagemErroConta(excecao));
    } finally {
      setEnviando(false);
    }
  }

  function trocarModo(proximo: Modo) {
    setModo(proximo);
    setErro(null);
    setEmailEnviado(false);
  }

  const texto = TEXTOS[modo];

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="w-full max-w-sm rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl">
        <div className="flex flex-col items-center gap-space-xs text-center">
          <Icone nome="account_circle" className="text-[32px] text-primary" />
          <h1 className="font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
            {titulo}
          </h1>
          <p className="font-body-sm text-body-sm text-outline">{descricao}</p>
        </div>

        {emailEnviado ? (
          <div className="mt-space-lg flex flex-col items-center gap-space-sm text-center">
            <Icone nome="mark_email_read" className="text-[28px] text-tertiary" />
            <p className="font-body-md text-body-sm text-on-surface-variant">
              Enviamos um link de redefinição de senha para <strong>{email}</strong>.
            </p>
            <button
              type="button"
              onClick={() => trocarModo("entrar")}
              className="font-title-code text-title-code text-primary hover:underline"
            >
              Voltar para o login
            </button>
          </div>
        ) : (
          <form onSubmit={enviar} className="mt-space-lg flex flex-col gap-space-base">
            <label className="flex flex-col gap-space-xxs">
              <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                E-mail
              </span>
              <input
                type="email"
                autoFocus
                value={email}
                onChange={(evento) => setEmail(evento.target.value)}
                className={CAMPO}
                placeholder="voce@exemplo.com"
                autoComplete="email"
              />
            </label>

            {modo !== "recuperar" && (
              <label className="flex flex-col gap-space-xxs">
                <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  Senha
                </span>
                <input
                  type="password"
                  value={senha}
                  onChange={(evento) => setSenha(evento.target.value)}
                  className={CAMPO}
                  placeholder="••••••••"
                  autoComplete={modo === "cadastro" ? "new-password" : "current-password"}
                  minLength={modo === "cadastro" ? 6 : undefined}
                />
              </label>
            )}

            {erro && (
              <p className="flex items-start gap-space-xs font-body-sm text-body-sm text-error">
                <Icone nome="error" className="mt-[2px] text-[15px]" />
                {erro}
              </p>
            )}

            <button
              type="submit"
              disabled={enviando || !email || (modo !== "recuperar" && !senha)}
              className="flex min-h-[44px] items-center justify-center gap-space-xs rounded bg-primary-container px-space-base py-space-xs font-title-code text-title-code text-on-primary transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {enviando ? (
                <Icone nome="progress_activity" className="animate-spin text-[18px]" />
              ) : (
                <Icone nome={texto.icone} className="text-[18px]" />
              )}
              {texto.acao}
            </button>

            <div className="flex flex-col items-center gap-space-xs pt-space-xs font-body-sm text-body-sm">
              {modo === "entrar" && (
                <>
                  <button
                    type="button"
                    onClick={() => trocarModo("recuperar")}
                    className="text-outline hover:text-primary hover:underline"
                  >
                    Esqueci minha senha
                  </button>
                  <span className="text-on-surface-variant">
                    Não tem conta?{" "}
                    <button
                      type="button"
                      onClick={() => trocarModo("cadastro")}
                      className="text-primary hover:underline"
                    >
                      Criar conta
                    </button>
                  </span>
                </>
              )}
              {modo !== "entrar" && (
                <span className="text-on-surface-variant">
                  Já tem conta?{" "}
                  <button
                    type="button"
                    onClick={() => trocarModo("entrar")}
                    className="text-primary hover:underline"
                  >
                    Entrar
                  </button>
                </span>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
