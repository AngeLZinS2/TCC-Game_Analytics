/**
 * Inicializacao do i18next - importado uma vez em `main.tsx`, antes do
 * primeiro render, para o idioma ja estar resolvido quando a arvore monta.
 *
 * Deteccao: primeiro o que a pessoa ja escolheu manualmente (localStorage),
 * senao o idioma do navegador, senao portugues (o padrao do site). A escolha
 * manual (`SeletorIdioma`, em `@views/componentes/SeletorIdioma`) grava no
 * mesmo localStorage via `i18n.changeLanguage`, e o detector cuida de
 * persistir sozinho.
 */
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "./locales/en";
import es from "./locales/es";
import pt from "./locales/pt";

export const IDIOMAS = ["pt", "en", "es"] as const;
export type Idioma = (typeof IDIOMAS)[number];

//: Mesma chave em toda a pilha (detector le/escreve, `SeletorIdioma` le pra
//: destacar o idioma ativo).
export const CHAVE_LOCALSTORAGE = "playdb:idioma";

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      pt: { translation: pt },
      en: { translation: en },
      es: { translation: es },
    },
    fallbackLng: "pt",
    supportedLngs: IDIOMAS,
    // "en-US"/"pt-BR" do navegador caem no idioma base correspondente, sem
    // precisar cadastrar cada variante regional.
    nonExplicitSupportedLngs: true,
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: CHAVE_LOCALSTORAGE,
    },
    interpolation: {
      // O JSX do React ja escapa por conta propria - escapar de novo aqui
      // trocaria acentos por entidades HTML literais na tela.
      escapeValue: false,
    },
  });

export default i18n;
