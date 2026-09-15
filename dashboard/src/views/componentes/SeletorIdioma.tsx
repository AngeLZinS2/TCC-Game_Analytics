/**
 * Troca manual de idioma (PT/EN/ES) - sobrepõe a detecção automática do
 * navegador (`@i18n/index.ts`) porque quem troca aqui claramente tem uma
 * preferência, mesmo que o navegador diga outro idioma. `i18n.changeLanguage`
 * já persiste a escolha sozinho (mesmo localStorage do detector).
 *
 * Mesmo padrão de clique-fora/Escape do `SeletorFiltro` e do `SeletorDeJogo`,
 * só que compacto (3 opções fixas, sem busca).
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { IDIOMAS, type Idioma } from "@i18n/index";
import { Icone } from "./base";

const NOMES: Record<Idioma, string> = {
  pt: "PT",
  en: "EN",
  es: "ES",
};

export function SeletorIdioma({ compacto = false }: { compacto?: boolean }) {
  const { t, i18n } = useTranslation();
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    function aoClicarFora(evento: MouseEvent) {
      if (!raiz.current?.contains(evento.target as Node)) setAberto(false);
    }
    function aoTeclarEscape(evento: KeyboardEvent) {
      if (evento.key === "Escape") setAberto(false);
    }
    document.addEventListener("mousedown", aoClicarFora);
    document.addEventListener("keydown", aoTeclarEscape);
    return () => {
      document.removeEventListener("mousedown", aoClicarFora);
      document.removeEventListener("keydown", aoTeclarEscape);
    };
  }, [aberto]);

  const atual = (i18n.resolvedLanguage ?? "pt") as Idioma;

  function escolher(idioma: Idioma) {
    void i18n.changeLanguage(idioma);
    setAberto(false);
  }

  return (
    <div ref={raiz} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={aberto}
        title={t("idioma.nome")}
        onClick={() => setAberto((estava) => !estava)}
        className={`flex items-center gap-space-xxs rounded-lg px-space-sm py-[9px] font-title-code text-title-code text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface ${
          compacto ? "h-10 w-10 justify-center px-0" : ""
        }`}
      >
        <Icone nome="language" className="text-[18px]" />
        {!compacto && <span>{NOMES[atual]}</span>}
      </button>

      {aberto && (
        <div className="absolute right-0 top-full z-30 pt-space-xxs">
          <div
            role="listbox"
            aria-label={t("idioma.nome")}
            className="flex w-40 flex-col gap-space-xxs rounded-lg border border-outline-variant/30 bg-surface-container-low p-space-xs shadow-2xl"
          >
            {IDIOMAS.map((idioma) => (
              <button
                key={idioma}
                type="button"
                role="option"
                aria-selected={atual === idioma}
                onClick={() => escolher(idioma)}
                className={`flex items-center justify-between rounded px-space-sm py-space-xs text-left font-title-code text-title-code transition-colors ${
                  atual === idioma
                    ? "bg-surface-container-high text-primary"
                    : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                }`}
              >
                {t(`idioma.${{ pt: "portugues", en: "ingles", es: "espanhol" }[idioma]}`)}
                {atual === idioma && <Icone nome="check" className="text-[16px]" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
