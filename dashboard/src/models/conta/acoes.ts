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

import { auth } from "./cliente";

const MENSAGENS: Record<string, string> = {
  "auth/invalid-email": "E-mail inválido.",
  "auth/user-disabled": "Esta conta foi desativada.",
  "auth/user-not-found": "Não existe conta com este e-mail.",
  "auth/wrong-password": "Senha incorreta.",
  "auth/invalid-credential": "E-mail ou senha incorretos.",
  "auth/email-already-in-use": "Já existe uma conta com este e-mail.",
  "auth/weak-password": "A senha precisa ter pelo menos 6 caracteres.",
  "auth/too-many-requests": "Muitas tentativas seguidas. Aguarde um pouco e tente de novo.",
  "auth/network-request-failed": "Sem conexão com o Firebase. Confira sua internet.",
  "auth/popup-closed-by-user": "Janela fechada antes de terminar o login.",
  "auth/popup-blocked": "O navegador bloqueou a janela de login. Permita pop-ups para este site.",
  "auth/cancelled-popup-request": "Login cancelado — só uma janela por vez.",
  "auth/account-exists-with-different-credential":
    "Já existe uma conta com este e-mail, criada com outro método de login (senha, Google ou GitHub).",
  "auth/operation-not-allowed":
    "Este método de login ainda não foi habilitado no Firebase.",
};

export function mensagemErroConta(erro: unknown): string {
  if (erro instanceof FirebaseError) {
    return MENSAGENS[erro.code] ?? "Não foi possível completar a ação. Tente de novo.";
  }
  return "Não foi possível completar a ação. Tente de novo.";
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
