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

/** Caminho -> URL completa, respeitando `VITE_API_URL` — pra quem precisa
 * montar a chamada na mão (ex.: `navigator.sendBeacon`, que não passa por
 * `buscar`/`enviar`). */
export function urlApi(caminho: string): string {
  return `${BASE}${caminho}`;
}

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

export async function buscar<T>(
  caminho: string,
  parametros?: Parametros,
  cabecalhos?: Record<string, string>,
): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(montarUrl(caminho, parametros), {
      headers: { Accept: "application/json", ...cabecalhos },
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
  cabecalhos?: Record<string, string>,
): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(montarUrl(caminho, parametros), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...cabecalhos,
      },
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

  // Alguns POSTs (ex.: favoritar) respondem 204 sem corpo - `.json()` num
  // corpo vazio lanca SyntaxError, o que fazia a mutacao "falhar" pro
  // TanStack Query mesmo com a escrita bem-sucedida no servidor (o
  // `onSuccess` que invalida o cache nunca rodava, e a estrela de favorito
  // so atualizava depois de um F5).
  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

/**
 * PATCH/DELETE com corpo opcional - o historico de perguntas do Assistente
 * (Fase 31) e o primeiro caso que precisa de um metodo alem de GET/POST.
 * Separado de `enviar` (que sempre serializa `corpo`, mesmo `undefined`, e
 * sempre espera um corpo JSON de volta) porque um DELETE devolve 204 sem
 * corpo nenhum.
 */
export async function chamar<T = void>(
  caminho: string,
  metodo: "PATCH" | "DELETE",
  corpo?: unknown,
  cabecalhos?: Record<string, string>,
): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(urlApi(caminho), {
      method: metodo,
      headers: {
        Accept: "application/json",
        ...(corpo !== undefined ? { "Content-Type": "application/json" } : {}),
        ...cabecalhos,
      },
      body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
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

  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}
