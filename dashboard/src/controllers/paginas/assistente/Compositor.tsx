/**
 * O campo de pergunta e as sugestoes.
 *
 * Textarea e nao input: as perguntas que este assistente responde bem sao
 * frases inteiras ("o Cyberpunk 2077 esta no nosso banco? o que a Steam diz
 * dele?"), e um campo de uma linha so esconde o que a pessoa escreveu. Enter
 * envia, Shift+Enter quebra linha.
 */

import { useEffect, useRef, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { Icone } from "@views/componentes/base";
import { Pilula } from "@views/componentes/hud";

/** Chaves das perguntas que exercitam blocos de contexto diferentes. */
const CHAVES_SUGESTOES = [
  "winrate",
  "emAlta",
  "recomendacao",
  "precisao",
  "menorPreco",
  "quantosJogos",
  "piorRecepcao",
] as const;

export function sugestoesDe(t: TFunction): { rotulo: string; pergunta: string; icone: string }[] {
  const icones: Record<(typeof CHAVES_SUGESTOES)[number], string> = {
    winrate: "swords",
    emAlta: "trending_up",
    recomendacao: "stadia_controller",
    precisao: "target",
    menorPreco: "sell",
    quantosJogos: "inventory_2",
    piorRecepcao: "thumb_down",
  };
  return CHAVES_SUGESTOES.map((chave) => ({
    rotulo: t(`assistente.sugestoes.${chave}.rotulo`),
    pergunta: t(`assistente.sugestoes.${chave}.pergunta`),
    icone: icones[chave],
  }));
}

/** Abaixo disso a pergunta nao tem o que casar com nenhum bloco de contexto. */
const MINIMO_CARACTERES = 3;

export function Compositor({
  valor,
  aoMudar,
  aoEnviar,
  ocupado,
  fontesDisponiveis,
  atualizadoEm,
}: {
  valor: string;
  aoMudar: (texto: string) => void;
  aoEnviar: () => void;
  ocupado: boolean;
  /** Quantas fontes o coletor tem no banco - real, de `/api/visao-geral`. */
  fontesDisponiveis: number | null;
  /** Texto pronto tipo "há 4 minutos", ou `null` enquanto nao se sabe. */
  atualizadoEm: string | null;
}) {
  const { t } = useTranslation();
  const campo = useRef<HTMLTextAreaElement>(null);
  const podeEnviar = valor.trim().length >= MINIMO_CARACTERES && !ocupado;
  const sugestoes = sugestoesDe(t);

  // Auto-resize: a textarea cresce com o texto ate um teto e depois rola.
  // Zerar a altura antes de ler `scrollHeight` e obrigatorio - sem isso ela
  // so cresce, nunca encolhe quando a pessoa apaga.
  useEffect(() => {
    const el = campo.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [valor]);

  function aoTeclar(evento: KeyboardEvent<HTMLTextAreaElement>) {
    if (evento.key === "Enter" && !evento.shiftKey) {
      evento.preventDefault();
      if (podeEnviar) aoEnviar();
    }
  }

  return (
    <div className="flex flex-col gap-space-base">
      <div className="rounded-xl bg-surface-container-low/90 p-space-base shadow-2xl ring-1 ring-outline-variant/25 transition-colors focus-within:ring-primary/50">
        <label htmlFor="pergunta-assistente" className="sr-only">
          {t("assistente.compositor.campoLabel")}
        </label>
        <textarea
          id="pergunta-assistente"
          ref={campo}
          rows={1}
          value={valor}
          onChange={(evento) => aoMudar(evento.target.value)}
          onKeyDown={aoTeclar}
          disabled={ocupado}
          placeholder={t("assistente.compositor.placeholder")}
          className="rolagem-discreta w-full resize-none bg-transparent font-body-lg text-body-lg text-on-surface outline-none placeholder:text-outline disabled:text-outline"
        />

        <div className="mt-space-sm flex flex-wrap items-center justify-between gap-space-sm border-t border-outline-variant/20 pt-space-sm">
          <div className="flex flex-wrap items-center gap-space-md font-badge-status text-badge-status uppercase tracking-wider text-outline">
            <span className="flex items-center gap-space-xxs">
              <span
                className="h-1.5 w-1.5 rounded-full bg-tertiary shadow-[0_0_6px_rgba(22,239,122,0.8)]"
                aria-hidden
              />
              {t("assistente.compositor.dadosDisponiveis")}
            </span>
            {fontesDisponiveis !== null && (
              <span className="flex items-center gap-space-xxs">
                <Icone nome="database" className="text-[14px]" />
                {t("assistente.compositor.fontes", { n: fontesDisponiveis })}
              </span>
            )}
            {atualizadoEm && (
              <span className="flex items-center gap-space-xxs">
                <Icone nome="schedule" className="text-[14px]" />
                {atualizadoEm}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={aoEnviar}
            disabled={!podeEnviar}
            className={[
              "flex items-center gap-space-xs rounded px-space-base py-space-xs font-title-code text-title-code transition-all",
              podeEnviar
                ? "bg-primary-container text-on-primary shadow-[0_0_14px_rgba(90,140,255,0.35)] hover:brightness-110"
                : "cursor-not-allowed bg-surface-container text-outline/60",
            ].join(" ")}
          >
            <Icone nome={ocupado ? "hourglass_top" : "send"} className="text-[16px]" />
            {ocupado ? t("assistente.compositor.analisando") : t("assistente.compositor.analisar")}
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-space-xs">
        <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
          {t("assistente.compositor.sugestoesTitulo")}
        </span>
        <div className="flex flex-wrap gap-space-xs">
          {sugestoes.map((sugestao) => (
            <Pilula
              key={sugestao.rotulo}
              icone={sugestao.icone}
              desabilitada={ocupado}
              titulo={sugestao.pergunta}
              // Preenche o campo e NAO envia: a sugestao e um ponto de
              // partida para editar, nao um botao que gasta tokens sozinho.
              aoClicar={() => {
                aoMudar(sugestao.pergunta);
                campo.current?.focus();
              }}
            >
              {sugestao.rotulo}
            </Pilula>
          ))}
        </div>
      </div>
    </div>
  );
}
