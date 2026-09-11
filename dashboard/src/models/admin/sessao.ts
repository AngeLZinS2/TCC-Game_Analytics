/**
 * Sessão do painel admin — token no localStorage, sem cookie e sem sistema
 * de contas (só uma senha, ver `controllers/routers/admin.py`). Um wrapper
 * fino: guardar/ler/limpar o token, e montar o header `Authorization` pros
 * hooks de `consultas.ts`.
 */

const CHAVE_TOKEN = "playdb:admin-token";

export function tokenAdmin(): string | null {
  try {
    return localStorage.getItem(CHAVE_TOKEN);
  } catch {
    return null;
  }
}

export function salvarTokenAdmin(token: string): void {
  try {
    localStorage.setItem(CHAVE_TOKEN, token);
  } catch {
    /* localStorage bloqueado (aba privada etc.) — a sessão só não sobrevive a um reload. */
  }
}

export function limparTokenAdmin(): void {
  try {
    localStorage.removeItem(CHAVE_TOKEN);
  } catch {
    /* ignore */
  }
}

export function cabecalhoAuthAdmin(): Record<string, string> {
  const token = tokenAdmin();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
