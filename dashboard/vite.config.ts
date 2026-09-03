import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// O proxy /api evita CORS no desenvolvimento e faz o dashboard funcionar
// tambem quando servido pela mesma origem da API em producao.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // /docs e /openapi.json entram junto para o link da documentacao da API
      // funcionar a partir do dashboard, sem depender da porta do backend.
      // /health entra porque o rodape da barra lateral mede a latencia dele:
      // fora do proxy, o Vite devolveria o index.html da SPA e o indicador
      // de status ficaria vermelho com a API no ar.
      "^/(api|docs|redoc|health|openapi.json)": {
        target: process.env.VITE_API_ALVO ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
