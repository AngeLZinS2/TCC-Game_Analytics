/**
 * Acoes de conta (entrar/criar/sair/redefinir senha) - fininas por cima do
 * SDK do Firebase, so traduzindo o `error.code` pra uma mensagem que faz
 * sentido na tela. O backend nunca entra nesse fluxo: e tudo direto
 * navegador <-> Firebase.
 */

import { FirebaseError } from "firebase/app";
import {
  createUserWithEmailAndPassword,
  GithubAuthProvider,
  GoogleAuthProvider,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from "firebase/auth";
import type { TFunction } from "i18next";

import { auth } from "./cliente";

export function mensagemErroConta(erro: unknown, t: TFunction): string {
  const mensagens: Record<string, string> = {
    "auth/invalid-email": t("conta.erros.invalidEmail"),
    "auth/user-disabled": t("conta.erros.userDisabled"),
    "auth/user-not-found": t("conta.erros.userNotFound"),
    "auth/wrong-password": t("conta.erros.wrongPassword"),
    "auth/invalid-credential": t("conta.erros.invalidCredential"),
    "auth/email-already-in-use": t("conta.erros.emailInUse"),
    "auth/weak-password": t("conta.erros.weakPassword"),
    "auth/too-many-requests": t("conta.erros.tooManyRequests"),
    "auth/network-request-failed": t("conta.erros.networkFailed"),
    "auth/popup-closed-by-user": t("conta.erros.popupClosed"),
    "auth/popup-blocked": t("conta.erros.popupBlocked"),
    "auth/cancelled-popup-request": t("conta.erros.popupCancelled"),
    "auth/account-exists-with-different-credential": t("conta.erros.accountExists"),
    "auth/operation-not-allowed": t("conta.erros.operationNotAllowed"),
  };

  if (erro instanceof FirebaseError) {
    return mensagens[erro.code] ?? t("comum.erroGenerico");
  }
  return t("comum.erroGenerico");
}

export function entrarComEmailSenha(email: string, senha: string) {
  return signInWithEmailAndPassword(auth, email, senha);
}

export function criarContaComEmailSenha(email: string, senha: string) {
  return createUserWithEmailAndPassword(auth, email, senha);
}

export function sairDaConta() {
  return signOut(auth);
}

export function redefinirSenhaPorEmail(email: string) {
  return sendPasswordResetEmail(auth, email);
}

/**
 * Google e GitHub via popup - `signInWithPopup` cria a conta na hora se for
 * a primeira vez, entao "entrar" e "criar conta" sao o mesmo botao aqui. Sem
 * `redirect` de proposito: o popup mantem o estado da SPA intacto (nao
 * recarrega a pagina), e o projeto ja nao suporta nenhum outro fluxo que
 * dependa de voltar de um redirect.
 */
export function entrarComGoogle() {
  return signInWithPopup(auth, new GoogleAuthProvider());
}

export function entrarComGithub() {
  return signInWithPopup(auth, new GithubAuthProvider());
}
