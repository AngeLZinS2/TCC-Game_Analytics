/**
 * Cliente HTTP da API.
 *
 * Em desenvolvimento `VITE_API_URL` fica vazia e o proxy do Vite manda /api
 * para o backend - assim o navegador so ve uma origem e nao ha CORS no caminho.
 */

const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export class ErroApi extends Error {
  constructor(
    readonly status: number,
    readonly detalhe: string,
  ) {
    super(detalhe);
    this.name = "ErroApi";
  }
}

type Parametros = Record<string, string | number | boolean | undefined | null>;

function montarUrl(caminho: string, parametros?: Parametros): string {
  const url = `${BASE}${caminho}`;
  if (!parametros) return url;

  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(parametros)) {
    if (valor === undefined || valor === null || valor === "") continue;
    busca.set(chave, String(valor));
  }
  const consulta = busca.toString();
  return consulta ? `${url}?${consulta}` : url;
}

export async function buscar<T>(caminho: string, parametros?: Parametros): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(montarUrl(caminho, parametros), {
      headers: { Accept: "application/json" },
    });
  } catch {
    // Rede fora / API no ar? A distincao importa para a mensagem na tela.
    throw new ErroApi(0, "Nao foi possivel falar com a API. Ela esta rodando?");
  }

  if (!resposta.ok) {
    let detalhe = `${resposta.status} ${resposta.statusText}`;
    try {
      const corpo = await resposta.json();
      if (typeof corpo?.detail === "string") detalhe = corpo.detail;
    } catch {
      /* resposta sem corpo JSON: fica a mensagem padrao */
    }
    throw new ErroApi(resposta.status, detalhe);
  }

  return (await resposta.json()) as T;
}

/**
 * POST com corpo JSON.
 *
 * Compartilha com `buscar` o tratamento de erro e a montagem de URL - a
 * diferenca e so o metodo e o corpo. Duplicar o `catch` da rede em dois lugares
 * faria as duas mensagens divergirem na primeira vez que uma delas mudasse.
 */
export async function enviar<T>(
  caminho: string,
  corpo: unknown,
  parametros?: Parametros,
): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(montarUrl(caminho, parametros), {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
  } catch {
    throw new ErroApi(0, "Nao foi possivel falar com a API. Ela esta rodando?");
  }

  if (!resposta.ok) {
    let detalhe = `${resposta.status} ${resposta.statusText}`;
    try {
      const json = await resposta.json();
      if (typeof json?.detail === "string") detalhe = json.detail;
    } catch {
      /* resposta sem corpo JSON: fica a mensagem padrao */
    }
    throw new ErroApi(resposta.status, detalhe);
  }

  return (await resposta.json()) as T;
}
