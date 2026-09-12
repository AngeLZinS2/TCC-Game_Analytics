/**
 * O fundo animado da Home: uma rede de pontos à deriva, com linha entre os
 * que ficam perto — a "rede de dados" que a landing usa no lugar de uma cena
 * 3D de verdade (WebGL entraria 300-600kb de bundle por um efeito que o
 * Canvas 2D já entrega).
 *
 * Desenho próprio, sem lib de partícula: são ~70 pontos, física trivial
 * (posição + velocidade constante, quica na borda), e o único custo real é o
 * `O(n²)` de medir distância par a par pra decidir a linha — em 70 pontos é
 * ~2400 pares por quadro, o que roda liso em qualquer coisa com Canvas 2D.
 *
 * Ignora `prefers-reduced-motion` de propósito, como `useContagem`/
 * `useEntrarNaTela` (`models/hooks/animacao.ts`) já fazem: nesta página a
 * animação É a identidade, não um enfeite por cima dela.
 */

import { useEffect, useRef } from "react";

interface Ponto {
  x: number;
  y: number;
  vx: number;
  vy: number;
  raio: number;
  destaque: boolean;
}

/** Acima disso as linhas somem - a malha não devia cobrir a tela inteira. */
const DISTANCIA_MAX = 150;
const COR_PONTO = "168, 194, 255"; // primaria, em rgb solto pra variar alpha
const COR_DESTAQUE = "243, 177, 59"; // secundaria (âmbar do "modelo")

function criarPontos(largura: number, altura: number, quantidade: number): Ponto[] {
  return Array.from({ length: quantidade }, (_, i) => ({
    x: Math.random() * largura,
    y: Math.random() * altura,
    vx: (Math.random() - 0.5) * 0.25,
    vy: (Math.random() - 0.5) * 0.25,
    raio: Math.random() * 1.5 + 1,
    // 1 em cada 9 pontos pisca em âmbar - o resto é o azul "clicável" padrão
    // do design system. Mistura as duas cores da identidade sem virar confete.
    destaque: i % 9 === 0,
  }));
}

export function FundoParticulas({ className = "" }: { className?: string }) {
  const telaRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const tela = telaRef.current;
    const contexto = tela?.getContext("2d");
    if (!tela || !contexto) return;

    const envolvente = tela.parentElement;
    if (!envolvente) return;

    let pontos: Ponto[] = [];
    let largura = 0;
    let altura = 0;
    let quadro: number;

    function dimensionar() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      largura = envolvente!.clientWidth;
      altura = envolvente!.clientHeight;
      tela!.width = largura * dpr;
      tela!.height = altura * dpr;
      tela!.style.width = `${largura}px`;
      tela!.style.height = `${altura}px`;
      contexto!.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Menos pontos numa tela estreita - o celular não precisa da mesma
      // densidade que um monitor, e menos pontos custa menos CPU nele.
      const quantidade = largura < 640 ? 34 : largura < 1024 ? 52 : 72;
      pontos = criarPontos(largura, altura, quantidade);
    }

    function passo() {
      contexto!.clearRect(0, 0, largura, altura);

      for (const p of pontos) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x <= 0 || p.x >= largura) p.vx *= -1;
        if (p.y <= 0 || p.y >= altura) p.vy *= -1;
      }

      for (let i = 0; i < pontos.length; i += 1) {
        for (let j = i + 1; j < pontos.length; j += 1) {
          const a = pontos[i];
          const b = pontos[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distancia = Math.sqrt(dx * dx + dy * dy);
          if (distancia >= DISTANCIA_MAX) continue;

          const alpha = (1 - distancia / DISTANCIA_MAX) * 0.35;
          contexto!.strokeStyle = `rgba(${COR_PONTO}, ${alpha})`;
          contexto!.lineWidth = 1;
          contexto!.beginPath();
          contexto!.moveTo(a.x, a.y);
          contexto!.lineTo(b.x, b.y);
          contexto!.stroke();
        }
      }

      for (const p of pontos) {
        contexto!.fillStyle = `rgba(${p.destaque ? COR_DESTAQUE : COR_PONTO}, ${p.destaque ? 0.9 : 0.6})`;
        contexto!.beginPath();
        contexto!.arc(p.x, p.y, p.raio, 0, Math.PI * 2);
        contexto!.fill();
      }

      quadro = requestAnimationFrame(passo);
    }

    dimensionar();
    quadro = requestAnimationFrame(passo);

    const observador = new ResizeObserver(dimensionar);
    observador.observe(envolvente);

    return () => {
      cancelAnimationFrame(quadro);
      observador.disconnect();
    };
  }, []);

  return <canvas ref={telaRef} className={className} aria-hidden />;
}
