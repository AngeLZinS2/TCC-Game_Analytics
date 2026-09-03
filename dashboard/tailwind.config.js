/**
 * Tokens do design system 'Apex Broadcast Engine', exportados do Google Stitch.
 *
 * O arquivo e uma copia fiel do `tailwind.config` que o Stitch embute em cada
 * tela gerada - as 10 telas do projeto compartilham exatamente este objeto.
 * Editar aqui a mao desalinha o codigo do desenho: o caminho e mudar o design
 * system no Stitch e reexportar.
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "on-primary-fixed": "#001f24",
        "error": "#ffb4ab",
        "surface-bright": "#363941",
        "primary-fixed-dim": "#00daf3",
        "on-secondary-fixed": "#1a0063",
        "background": "#10131a",
        "on-primary-container": "#00626e",
        "outline-variant": "#3b494c",
        "primary-container": "#00e5ff",
        "on-primary-fixed-variant": "#004f58",
        "on-primary": "#00363d",
        "primary-fixed": "#9cf0ff",
        "tertiary-container": "#16ef7a",
        "surface-container-low": "#191b23",
        "surface-container-highest": "#32353d",
        "secondary": "#c9bfff",
        "inverse-on-surface": "#2d3038",
        "surface-tint": "#00daf3",
        "on-surface": "#e1e2ec",
        "tertiary": "#afffbd",
        "on-secondary": "#2e009c",
        "surface-container": "#1d1f27",
        "on-tertiary-fixed-variant": "#005225",
        "on-tertiary": "#003918",
        "on-secondary-fixed-variant": "#441cc8",
        "inverse-surface": "#e1e2ec",
        "tertiary-fixed-dim": "#00e473",
        "secondary-container": "#4720ca",
        "secondary-fixed": "#e5deff",
        "error-container": "#93000a",
        "outline": "#849396",
        "secondary-fixed-dim": "#c9bfff",
        "on-tertiary-fixed": "#00210b",
        "on-tertiary-container": "#006730",
        "surface-container-high": "#272a32",
        "tertiary-fixed": "#63ff95",
        "surface-variant": "#32353d",
        "inverse-primary": "#006875",
        "surface-container-lowest": "#0b0e15",
        "on-error-container": "#ffdad6",
        "on-background": "#e1e2ec",
        "on-surface-variant": "#bac9cc",
        "primary": "#c3f5ff",
        "on-secondary-container": "#baaeff",
        "on-error": "#690005",
        "surface": "#10131a",
        "surface-dim": "#10131a"
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
        "title-code": [
          "Space Grotesk"
        ],
        "body-lg": [
          "IBM Plex Sans"
        ],
        "display-hero-mobile": [
          "Space Grotesk"
        ],
        "headline-kpi": [
          "Space Grotesk"
        ],
        "headline-lg": [
          "Space Grotesk"
        ],
        "body-md": [
          "IBM Plex Sans"
        ],
        "badge-status": [
          "Space Grotesk"
        ],
        "headline-sm": [
          "Space Grotesk"
        ],
        "headline-kpi-mobile": [
          "Space Grotesk"
        ],
        "body-sm": [
          "IBM Plex Sans"
        ],
        "display-hero": [
          "Space Grotesk"
        ],
        "headline-md": [
          "Space Grotesk"
        ],
        "label-caps": [
          "Space Grotesk"
        ]
      },
      fontSize: {
        "title-code": [
          "14px",
          {
            "lineHeight": "18px",
            "letterSpacing": "0.08em",
            "fontWeight": "600"
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
        "headline-kpi": [
          "36px",
          {
            "lineHeight": "40px",
            "letterSpacing": "-0.02em",
            "fontWeight": "700"
          }
        ],
        "headline-lg": [
          "24px",
          {
            "lineHeight": "30px",
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
          "48px",
          {
            "lineHeight": "52px",
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
