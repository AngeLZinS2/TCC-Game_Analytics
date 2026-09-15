/**
 * Porta de entrada da conta: entrar, criar conta ou recuperar senha - tudo
 * num so formulario que troca de modo, mais os botoes de Google/GitHub. E o
 * que qualquer rota protegida (`RotaProtegida.tsx`) mostra no lugar do
 * conteudo quando ninguem esta logado.
 *
 * Autenticacao de verdade, via Firebase: cria a conta, guarda a senha (com
 * hash, do lado deles) e confere a credencial no login - nada disso passa
 * pelo nosso backend. Google/GitHub sao a mesma coisa por popup, e criam a
 * conta na primeira vez sozinhos - por isso os dois botoes aparecem tanto em
 * "entrar" quanto em "criar conta" (e some em "recuperar senha", que so faz
 * sentido pra quem tem senha).
 */

import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import {
  criarContaComEmailSenha,
  entrarComEmailSenha,
  entrarComGithub,
  entrarComGoogle,
  mensagemErroConta,
  redefinirSenhaPorEmail,
} from "@models/conta/acoes";
import { Icone } from "@views/componentes/base";
import { CAMPO } from "@views/componentes/hud";
import { MarcaGithub, MarcaGoogle } from "@views/componentes/MarcasOAuth";

type Modo = "entrar" | "cadastro" | "recuperar";
type Provedor = "google" | "github";

function textosDe(t: TFunction): Record<Modo, { titulo: string; acao: string; icone: string }> {
  return {
    entrar: { titulo: t("conta.entrar.titulo"), acao: t("conta.entrar.acao"), icone: "login" },
    cadastro: { titulo: t("conta.cadastro.titulo"), acao: t("conta.cadastro.acao"), icone: "person_add" },
    recuperar: { titulo: t("conta.recuperar.titulo"), acao: t("conta.recuperar.acao"), icone: "mail" },
  };
}

const BOTAO_SOCIAL =
  "flex min-h-[44px] items-center justify-center gap-space-xs rounded border border-outline-variant/40 " +
  "bg-surface-container px-space-base py-space-xs font-title-code text-title-code text-on-surface " +
  "transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50";

export function EntrarOuCriarConta({
  titulo,
  descricao,
}: {
  titulo?: string;
  descricao?: string;
}) {
  const { t } = useTranslation();
  const tituloExibido = titulo ?? t("conta.tituloPadrao");
  const descricaoExibida = descricao ?? t("conta.descricaoPadrao");
  const textos = textosDe(t);
  const [modo, setModo] = useState<Modo>("entrar");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [provedorSocial, setProvedorSocial] = useState<Provedor | null>(null);
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
      setErro(mensagemErroConta(excecao, t));
    } finally {
      setEnviando(false);
    }
  }

  async function entrarComSocial(provedor: Provedor) {
    setErro(null);
    setProvedorSocial(provedor);
    try {
      await (provedor === "google" ? entrarComGoogle() : entrarComGithub());
    } catch (excecao) {
      setErro(mensagemErroConta(excecao, t));
    } finally {
      setProvedorSocial(null);
    }
  }

  function trocarModo(proximo: Modo) {
    setModo(proximo);
    setErro(null);
    setEmailEnviado(false);
  }

  const texto = textos[modo];
  const ocupado = enviando || provedorSocial !== null;

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="w-full max-w-sm rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl">
        <div className="flex flex-col items-center gap-space-xs text-center">
          <Icone nome="account_circle" className="text-[32px] text-primary" />
          <h1 className="font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
            {tituloExibido}
          </h1>
          <p className="font-body-sm text-body-sm text-outline">{descricaoExibida}</p>
        </div>

        {emailEnviado ? (
          <div className="mt-space-lg flex flex-col items-center gap-space-sm text-center">
            <Icone nome="mark_email_read" className="text-[28px] text-tertiary" />
            <p className="font-body-md text-body-sm text-on-surface-variant">
              {t("conta.emailEnviadoPrefixo")} <strong>{email}</strong>
              {t("conta.emailEnviadoSufixo")}
            </p>
            <button
              type="button"
              onClick={() => trocarModo("entrar")}
              className="font-title-code text-title-code text-primary hover:underline"
            >
              {t("conta.voltarParaLogin")}
            </button>
          </div>
        ) : (
          <div className="mt-space-lg flex flex-col gap-space-base">
            {modo !== "recuperar" && (
              <>
                <div className="flex flex-col gap-space-sm">
                  <button
                    type="button"
                    onClick={() => entrarComSocial("google")}
                    disabled={ocupado}
                    className={BOTAO_SOCIAL}
                  >
                    {provedorSocial === "google" ? (
                      <Icone nome="progress_activity" className="animate-spin text-[18px]" />
                    ) : (
                      <MarcaGoogle />
                    )}
                    {t("conta.continuarComGoogle")}
                  </button>
                  <button
                    type="button"
                    onClick={() => entrarComSocial("github")}
                    disabled={ocupado}
                    className={BOTAO_SOCIAL}
                  >
                    {provedorSocial === "github" ? (
                      <Icone nome="progress_activity" className="animate-spin text-[18px]" />
                    ) : (
                      <MarcaGithub />
                    )}
                    {t("conta.continuarComGithub")}
                  </button>
                </div>

                <div className="flex items-center gap-space-sm" aria-hidden>
                  <span className="h-px flex-1 bg-outline-variant/30" />
                  <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                    {t("conta.ouComEmail")}
                  </span>
                  <span className="h-px flex-1 bg-outline-variant/30" />
                </div>
              </>
            )}

            <form onSubmit={enviar} className="flex flex-col gap-space-base">
              <label className="flex flex-col gap-space-xxs">
                <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  {t("conta.email")}
                </span>
                <input
                  type="email"
                  autoFocus
                  value={email}
                  onChange={(evento) => setEmail(evento.target.value)}
                  className={CAMPO}
                  placeholder={t("conta.placeholderEmail")}
                  autoComplete="email"
                />
              </label>

              {modo !== "recuperar" && (
                <label className="flex flex-col gap-space-xxs">
                  <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                    {t("conta.senha")}
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
                disabled={ocupado || !email || (modo !== "recuperar" && !senha)}
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
                      {t("conta.esqueciSenha")}
                    </button>
                    <span className="text-on-surface-variant">
                      {t("conta.naoTemConta")}{" "}
                      <button
                        type="button"
                        onClick={() => trocarModo("cadastro")}
                        className="text-primary hover:underline"
                      >
                        {t("conta.criarConta")}
                      </button>
                    </span>
                  </>
                )}
                {modo !== "entrar" && (
                  <span className="text-on-surface-variant">
                    {t("conta.jaTemConta")}{" "}
                    <button
                      type="button"
                      onClick={() => trocarModo("entrar")}
                      className="text-primary hover:underline"
                    >
                      {t("conta.entrarLink")}
                    </button>
                  </span>
                )}
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
