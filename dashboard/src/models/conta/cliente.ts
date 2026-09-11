/**
 * Inicializacao do Firebase (Authentication) para o PlayDB.
 *
 * A `apiKey` do SDK do navegador NAO e segredo — o proprio Firebase publica
 * isso como configuracao publica, embutida no bundle de qualquer app web
 * dele (a seguranca vem das regras do backend/console, nao de esconder isto).
 * Por isso fica hardcoded aqui, sem passar por `.env`/build-arg: e o mesmo
 * raciocinio de outros valores publicos do projeto (ex.: nomes de rota),
 * so que vindo do console do Firebase em vez do nosso codigo.
 */

import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const app = initializeApp({
  apiKey: "AIzaSyANeJq17ugYoUU8wTxINfcNwGoipvDDDL0",
  authDomain: "playdb-d9b04.firebaseapp.com",
  projectId: "playdb-d9b04",
  storageBucket: "playdb-d9b04.firebasestorage.app",
  messagingSenderId: "821853279885",
  appId: "1:821853279885:web:9d870cf9389f9227a2f4c4",
});

export const auth = getAuth(app);

/**
 * Cabecalho `Authorization` com o ID token da sessao atual - `getIdToken()`
 * renova sozinho quando o token (validade de 1h) esta perto de expirar, sem
 * precisar de logica de refresh nossa. Objeto vazio quando ninguem esta
 * logado - o backend devolve 401 do mesmo jeito que sem o cabecalho.
 */
export async function cabecalhoAuthUsuario(): Promise<Record<string, string>> {
  const usuario = auth.currentUser;
  if (!usuario) return {};
  const token = await usuario.getIdToken();
  return { Authorization: `Bearer ${token}` };
}
