/**
 * "Sua chave de IA": cada conta pode cadastrar a propria chave - OpenRouter,
 * Anthropic (Claude) ou Google (Gemini) - e escolher o modelo. O Assistente
 * de IA passa a usar ELA so nas perguntas dessa conta, sem disputar a cota
 * da chave compartilhada do site.
 *
 * O OpenRouter sozinho ja da acesso a Claude/Gemini por baixo da mesma
 * chave - a diferenca de ter Anthropic/Google aqui como provedores proprios
 * e nao depender do OpenRouter no meio: quem so tem chave da Anthropic
 * cadastra ela direto.
 *
 * A chave nunca volta do backend em texto puro - so a mascara
 * (`chave_ia_mascarada`, os ultimos 4 caracteres). Trocar significa cadastrar
 * uma nova por cima, nao "editar" a antiga.
 *
 * O modelo e um `<select>`, nao texto livre: o id exato muda de provedor pra
 * provedor (`anthropic/claude-sonnet-5` no OpenRouter, `claude-sonnet-5` na
 * API direta) e um typo ali nao falha no cadastro - falha depois, na
 * pergunta, parecendo chave invalida. A lista vem de
 * `/api/assistente/modelos` (viva, no caso do OpenRouter), e "Outro" mantem o
 * texto livre pra quem quer um modelo recem-lancado.
 */

import { useMemo, useState, type FormEvent } from "react";

import { useModelosIA, useRemoverChaveIA, useSalvarChaveIA } from "@models/api/consultas";
import type { ModeloIA, PerfilUsuario, ProvedorIA } from "@models/api/tipos";
import { Icone, MensagemErro } from "@views/componentes/base";
import { CAMPO, Painel, Pilula } from "@views/componentes/hud";

const PROVEDORES: Record<
  ProvedorIA,
  { rotulo: string; linkChave: string; placeholderModelo: string; icone: string }
> = {
  openrouter: {
    rotulo: "OpenRouter",
    linkChave: "https://openrouter.ai/keys",
    placeholderModelo: "ex.: anthropic/claude-sonnet-5",
    icone: "hub",
  },
  anthropic: {
    rotulo: "Anthropic (Claude)",
    linkChave: "https://console.anthropic.com/settings/keys",
    placeholderModelo: "ex.: claude-sonnet-5",
    icone: "smart_toy",
  },
  google: {
    rotulo: "Google (Gemini)",
    linkChave: "https://aistudio.google.com/apikey",
    placeholderModelo: "ex.: gemini-3.8-flash",
    icone: "smart_toy",
  },
};

/** Valor do `<option>` que revela o campo de texto livre.
 *
 * A lista vem do catálogo do provedor (viva, no caso do OpenRouter), mas
 * modelo novo aparece toda semana — sem esta saída, quem quisesse um
 * lançamento ficaria esperando a gente atualizar a lista. */
const OUTRO = "__outro__";

export const ROTULO_PROVEDOR: Record<ProvedorIA, string> = {
  openrouter: "OpenRouter",
  anthropic: "Anthropic",
  google: "Google",
};

export function PainelChaveIA({ perfil }: { perfil: PerfilUsuario | undefined }) {
  const salvar = useSalvarChaveIA();
  const remover = useRemoverChaveIA();
  const catalogo = useModelosIA();
  const [provedor, setProvedor] = useState<ProvedorIA>("openrouter");
  const [chave, setChave] = useState("");
  const [escolha, setEscolha] = useState("");
  const [modeloLivre, setModeloLivre] = useState("");
  const [editando, setEditando] = useState(false);

  const temChave = perfil?.tem_chave_ia_propria ?? false;
  const mostrarForm = !temChave || editando;
  const modelos = catalogo.data?.[provedor] ?? [];

  // Um `<optgroup>` por grupo, na ordem em que o backend mandou - ele já
  // ordena por relevância (gratuitos primeiro, depois as famílias).
  const grupos = useMemo(() => {
    const porGrupo = new Map<string, ModeloIA[]>();
    for (const modelo of modelos) {
      const lista = porGrupo.get(modelo.grupo) ?? [];
      lista.push(modelo);
      porGrupo.set(modelo.grupo, lista);
    }
    return [...porGrupo.entries()];
  }, [modelos]);

  const modelo = escolha === OUTRO ? modeloLivre.trim() : escolha;

  function trocarProvedor(novo: ProvedorIA) {
    setProvedor(novo);
    // O id é de outro provedor - "claude-sonnet-5" não existe no OpenRouter,
    // lá é "anthropic/claude-sonnet-5". Manter a escolha ao trocar de aba
    // salvaria um modelo que a chave nova não aceita.
    setEscolha("");
    setModeloLivre("");
  }

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (chave.trim().length < 10) return;
    await salvar.mutateAsync({
      provedor,
      chave: chave.trim(),
      modelo: modelo || undefined,
    });
    setChave("");
    setEscolha("");
    setModeloLivre("");
    setEditando(false);
  }

  return (
    <Painel
      icone="vpn_key"
      titulo="Sua chave de IA"
      descricao="Opcional. Cadastre sua própria chave — OpenRouter, Anthropic (Claude) ou Google (Gemini) — e o Assistente de IA passa a usar ela só nas suas perguntas, em vez da chave compartilhada do site."
    >
      {temChave && !editando && perfil && (
        <div className="flex flex-wrap items-center justify-between gap-space-sm rounded-lg bg-surface-container-lowest p-space-base">
          <span className="flex items-center gap-space-xs font-body-md text-body-sm text-on-surface">
            <Icone nome="check_circle" className="text-[18px] text-tertiary" />
            Usando sua chave da{" "}
            <strong className="text-on-surface">
              {perfil.chave_ia_provedor ? ROTULO_PROVEDOR[perfil.chave_ia_provedor] : "—"}
            </strong>
            {perfil.chave_ia_modelo && (
              <>
                {" "}
                · <code className="text-on-surface-variant">{perfil.chave_ia_modelo}</code>
              </>
            )}{" "}
            — <code className="text-on-surface-variant">{perfil.chave_ia_mascarada}</code>
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
          <div className="flex flex-wrap items-center gap-space-xs">
            {(Object.keys(PROVEDORES) as ProvedorIA[]).map((p) => (
              <Pilula
                key={p}
                ativa={provedor === p}
                aoClicar={() => trocarProvedor(p)}
                icone={PROVEDORES[p].icone}
              >
                {PROVEDORES[p].rotulo}
              </Pilula>
            ))}
          </div>

          <div className="flex flex-col gap-space-xs sm:flex-row">
            <input
              type="password"
              value={chave}
              onChange={(evento) => setChave(evento.target.value)}
              placeholder="cole a chave aqui"
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
                  setEscolha("");
                  setModeloLivre("");
                }}
                className="font-title-code text-title-code text-outline hover:text-on-surface"
              >
                Cancelar
              </button>
            )}
          </div>

          <label className="flex flex-col gap-space-xs">
            <span className="font-title-code text-title-code text-on-surface-variant">
              Modelo
            </span>
            <select
              value={escolha}
              onChange={(evento) => setEscolha(evento.target.value)}
              className={CAMPO + " w-full"}
              disabled={catalogo.isLoading}
            >
              <option value="">
                {provedor === "openrouter"
                  ? "Padrão do site"
                  : "Padrão do provedor (modelo atual e equilibrado)"}
              </option>
              {grupos.map(([grupo, itens]) => (
                <optgroup key={grupo} label={grupo}>
                  {itens.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.nome}
                      {item.gratuito ? " — grátis" : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
              <option value={OUTRO}>Outro — digitar o ID…</option>
            </select>
          </label>

          {escolha === OUTRO && (
            <input
              type="text"
              value={modeloLivre}
              onChange={(evento) => setModeloLivre(evento.target.value)}
              placeholder={PROVEDORES[provedor].placeholderModelo}
              className={CAMPO + " w-full"}
              autoComplete="off"
              autoFocus
            />
          )}

          {catalogo.isError && (
            <p className="font-body-sm text-body-sm text-outline">
              Não deu para carregar a lista de modelos agora — escolha "Outro" e digite o
              ID, ou deixe no padrão.
            </p>
          )}

          {salvar.isError && <MensagemErro erro={salvar.error} />}

          <p className="font-body-sm text-body-sm text-outline">
            Chave gratuita em{" "}
            <a
              href={PROVEDORES[provedor].linkChave}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              {PROVEDORES[provedor].linkChave.replace("https://", "")}
            </a>
            . Fica cifrada no banco — nunca reaparece em texto puro, nem pra você.
            {provedor !== "openrouter" && (
              <> A busca na web do assistente não está disponível com chave direta — só via OpenRouter.</>
            )}
          </p>
        </form>
      )}
    </Painel>
  );
}
