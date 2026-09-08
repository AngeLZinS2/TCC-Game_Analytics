/**
 * Design system "PlayDB · Instrumento".
 *
 * A base era o "Apex Broadcast Engine" exportado do Stitch — ciano sobre preto,
 * Space Grotesk. Esta versao troca a casca inteira: fundo grafite morno (a
 * "caixa" do instrumento), AZUL para o que e clicavel, e um AMBAR reservado ao
 * que o modelo estima (o token `secondary`, que quase so aparece em previsao e
 * grafico). Os NOMES dos tokens sao os mesmos — os valores mudaram —, entao os
 * componentes herdam o visual novo sem tocar em classe.
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // --- grafite morno: a "caixa" ---
        "background": "#0f1114",
        "surface": "#0f1114",
        "surface-dim": "#0d0f12",
        "surface-container-lowest": "#0c0e12",
        "surface-container-low": "#14171e",
        "surface-container": "#16191e",
        "surface-container-high": "#1e222a",
        "surface-container-highest": "#252a33",
        "surface-bright": "#2b313b",
        "surface-variant": "#252a33",
        "inverse-surface": "#eceef2",
        "inverse-on-surface": "#1e222a",

        // --- tinta ---
        "on-surface": "#eceef2",
        "on-background": "#eceef2",
        "on-surface-variant": "#9aa2ae",
        "outline": "#6a7280",
        "outline-variant": "#2e333d",

        // --- azul: o que e clicavel / ativo ---
        "primary": "#a9c2ff",
        "primary-container": "#5a8cff",
        "primary-fixed": "#c4d4ff",
        "primary-fixed-dim": "#4c86ff",
        "surface-tint": "#5a8cff",
        "on-primary": "#0a1633",
        "on-primary-container": "#1b3a8c",
        "on-primary-fixed": "#08122e",
        "on-primary-fixed-variant": "#2a4faa",
        "inverse-primary": "#2456d6",

        // --- ambar: o que o MODELO estima (era o roxo "secondary") ---
        "secondary": "#f6c87d",
        "secondary-container": "#463818",
        "secondary-fixed": "#fadfae",
        "secondary-fixed-dim": "#f3b13b",
        "on-secondary": "#2c2412",
        "on-secondary-fixed": "#241c0a",
        "on-secondary-container": "#f0c885",
        "on-secondary-fixed-variant": "#7a5c1e",

        // --- verde: semantico (vitoria / ok) ---
        "tertiary": "#8fe8c6",
        "tertiary-container": "#40d19e",
        "tertiary-fixed": "#7ce6bf",
        "tertiary-fixed-dim": "#3fcf8e",
        "on-tertiary": "#062c1f",
        "on-tertiary-container": "#12583b",
        "on-tertiary-fixed": "#04231a",
        "on-tertiary-fixed-variant": "#1f7a5a",

        // --- vermelho: semantico (derrota / erro) ---
        "error": "#ff8a8a",
        "error-container": "#5a1f1f",
        "on-error": "#3a0808",
        "on-error-container": "#ffd9d9"
      },
      borderRadius: {
        "DEFAULT": "0.25rem",
        "lg": "0.5rem",
        "xl": "0.75rem",
        "full": "9999px"
      },
      spacing: {
        "space-xxs": "0.125rem",
        "gutter-desktop": "1rem",
        "margin-mobile": "1rem",
        "space-md": "0.75rem",
        "margin-desktop": "1.5rem",
        "space-base": "1rem",
        "space-3xl": "3rem",
        "gutter-mobile": "0.75rem",
        "space-sm": "0.5rem",
        "space-xl": "1.5rem",
        "space-lg": "1.25rem",
        "space-xs": "0.25rem",
        "space-2xl": "2rem"
      },
      fontFamily: {
        // `title-code` carrega número, timestamp e rótulo tabular — vira mono.
        "title-code": ["IBM Plex Mono", "ui-monospace", "monospace"],
        // Interface, títulos e rótulos: Schibsted Grotesk (era Space Grotesk).
        "display-hero": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        "display-hero-mobile": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        "headline-kpi": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        "headline-kpi-mobile": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        "headline-lg": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        "headline-md": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        "headline-sm": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        "badge-status": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        "label-caps": ["Schibsted Grotesk", "system-ui", "sans-serif"],
        // Corpo de texto: IBM Plex Sans.
        "body-lg": ["IBM Plex Sans", "system-ui", "sans-serif"],
        "body-md": ["IBM Plex Sans", "system-ui", "sans-serif"],
        "body-sm": ["IBM Plex Sans", "system-ui", "sans-serif"]
      },
      fontSize: {
        "title-code": [
          "13px",
          {
            "lineHeight": "18px",
            "letterSpacing": "0.01em",
            "fontWeight": "500"
          }
        ],
        "body-lg": [
          "16px",
          {
            "lineHeight": "24px",
            "letterSpacing": "0em",
            "fontWeight": "400"
          }
        ],
        "display-hero-mobile": [
          "32px",
          {
            "lineHeight": "38px",
            "letterSpacing": "-0.02em",
            "fontWeight": "700"
          }
        ],
        // --- Tipografia fluida (ajuste de responsividade, fora do export do Stitch) ---
        // O Stitch exporta um par fixo por token (ex.: `display-hero` 48px e
        // `display-hero-mobile` 32px), mas o codigo so usa a versao desktop e
        // ela estoura no celular. `clamp()` faz um token so escalar entre os
        // dois extremos, sem tocar nas ~25 chamadas. O maximo do clamp e o
        // valor original, entao o desktop nao muda. `lineHeight` vira razao
        // sem unidade para acompanhar a fonte.
        "headline-kpi": [
          "clamp(1.75rem, 1rem + 3.6vw, 2.25rem)",
          {
            "lineHeight": "1.1",
            "letterSpacing": "-0.02em",
            "fontWeight": "700"
          }
        ],
        "headline-lg": [
          "clamp(1.35rem, 1.05rem + 1.5vw, 1.5rem)",
          {
            "lineHeight": "1.2",
            "letterSpacing": "-0.01em",
            "fontWeight": "600"
          }
        ],
        "body-md": [
          "14px",
          {
            "lineHeight": "20px",
            "letterSpacing": "0em",
            "fontWeight": "400"
          }
        ],
        "badge-status": [
          "10px",
          {
            "lineHeight": "12px",
            "letterSpacing": "0.15em",
            "fontWeight": "700"
          }
        ],
        "headline-sm": [
          "16px",
          {
            "lineHeight": "22px",
            "letterSpacing": "0.02em",
            "fontWeight": "600"
          }
        ],
        "headline-kpi-mobile": [
          "26px",
          {
            "lineHeight": "32px",
            "letterSpacing": "-0.01em",
            "fontWeight": "700"
          }
        ],
        "body-sm": [
          "12px",
          {
            "lineHeight": "16px",
            "letterSpacing": "0.01em",
            "fontWeight": "400"
          }
        ],
        "display-hero": [
          "clamp(2rem, 1rem + 5vw, 3rem)",
          {
            "lineHeight": "1.08",
            "letterSpacing": "-0.03em",
            "fontWeight": "700"
          }
        ],
        "headline-md": [
          "20px",
          {
            "lineHeight": "26px",
            "letterSpacing": "0em",
            "fontWeight": "600"
          }
        ],
        "label-caps": [
          "11px",
          {
            "lineHeight": "14px",
            "letterSpacing": "0.12em",
            "fontWeight": "700"
          }
        ]
      },
    },
  },
  plugins: [],
};
