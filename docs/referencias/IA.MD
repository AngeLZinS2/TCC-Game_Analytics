# NEXUS // HUB — REDESIGN DO ASSISTENTE DE DADOS
## Objetivo: UI/UX Senior++ + Data Intelligence Workspace

Você é um Staff/Senior++ Frontend Engineer + Product Designer especializado em:
- React
- TypeScript
- TailwindCSS
- Design Systems
- Data Visualization
- AI Interfaces
- SaaS/Enterprise UX
- Accessibility
- Performance
- Responsive Design

Sua missão é redesenhar COMPLETAMENTE a tela atual de "ASSISTENTE DE DADOS" do NEXUS // HUB.

IMPORTANTE:
Não quero apenas deixar a tela "mais bonita".
Quero transformar a experiência atual em uma interface premium de DATA INTELLIGENCE, mantendo as funcionalidades existentes e melhorando arquitetura, UX, hierarquia visual e interação.

==================================================
1. PRIMEIRO: ANALISE O PROJETO
==================================================

Antes de modificar qualquer código:

1. Analise a estrutura completa do projeto.
2. Identifique:
   - framework
   - componentes existentes
   - design system
   - rotas
   - hooks
   - services
   - API calls
   - estado global
   - autenticação
   - tema
   - componentes reutilizáveis
3. Localize exatamente a implementação atual da tela:
   "ASSISTENTE DE DADOS"
4. Descubra como as perguntas são enviadas para o backend.
5. Descubra como a resposta da IA é recebida.
6. Descubra como o contexto/fontes é recebido.
7. NÃO substitua APIs reais por mocks se já existirem APIs funcionais.
8. NÃO remova funcionalidades existentes.
9. Preserve contratos existentes com backend.
10. Se houver componentes reutilizáveis, reutilize-os.

Antes de codificar, faça uma breve análise interna da arquitetura atual e então implemente.

==================================================
2. DIREÇÃO VISUAL
==================================================

A referência visual é um dashboard:

"NEXUS // HUB"
"NEXUS // INTELLIGENCE"

Estética:

- Dark futuristic enterprise
- Premium
- Minimalista
- Tecnológica
- Data Intelligence
- Cyber/AI, mas sem aparência infantil
- Visual semelhante a produtos SaaS modernos
- Alta densidade de informação, porém organizada
- Cyan/teal como accent principal
- Background quase preto
- Cards em tons escuros
- Borders extremamente sutis
- Glow muito discreto
- Tipografia limpa
- Elementos técnicos podem utilizar fonte monoespaçada
- Microinterações elegantes

NÃO faça:
- excesso de neon
- excesso de sombras
- glassmorphism exagerado
- gradientes chamativos
- animações exageradas
- cards gigantes
- textos desnecessários
- aparência de template genérico
- visual de chatbot tradicional

A interface deve parecer um produto profissional de Data Intelligence.

==================================================
3. ESTRUTURA PRINCIPAL
==================================================

A tela deve possuir:

--------------------------------------------------
HEADER
--------------------------------------------------

Manter a identidade:

NEXUS // HUB

Navigation icons

Centro:

✦ ASSISTENTE DE DADOS

Direita:

● IA ONLINE
[ Minimax M3 ]
[ OpenRouter ]
[ Avatar ]

Os dados técnicos do modelo devem continuar disponíveis, mas de forma discreta.

Exemplo:

IA ONLINE
Minimax M3
OpenRouter

Não deixar:
"OpenRouter · minimax/minimax-m3:free"

exposto de forma visualmente dominante.

==================================================
4. LAYOUT PRINCIPAL
==================================================

Criar layout de três áreas:

LEFT SIDEBAR
MAIN WORKSPACE
RIGHT CONTEXT PANEL

Desktop:

--------------------------------------------------
| HISTÓRICO | WORKSPACE                | CONTEXTO |
--------------------------------------------------

Mobile:
Transformar sidebars em drawers/offcanvas.

==================================================
5. SIDEBAR ESQUERDA — HISTÓRICO
==================================================

Criar:

HISTÓRICO
[ Search ]

Hoje
--------------------------------

💬 Melhor winrate dos heróis?
21:58

💬 Jogos monitorados
21:15

💬 Cyberpunk no banco?
20:44

💬 Precisão das previsões
19:30

💬 Jogos mais populares
18:22

Ontem
--------------------------------

...

Botão:

[ 🗑 Limpar histórico ]

IMPORTANTE:

Não criar histórico fake se o backend já possuir histórico.

Se ainda não existir persistência:
criar uma camada preparada para isso sem quebrar a aplicação.

Estados:

- vazio
- carregando
- erro
- histórico disponível

==================================================
6. MAIN WORKSPACE
==================================================

Header:

ASSISTENTE DE DADOS

Título principal:

"Pergunte aos seus dados"

Subtítulo:

"Converse com o Nexus e descubra insights reais."

Não utilizar grandes blocos explicativos.

--------------------------------------------------
INPUT PRINCIPAL
--------------------------------------------------

Criar um AI Query Composer premium.

Visual:

┌──────────────────────────────────────────────────────┐
│ ✦ O que você quer descobrir?                         │
│                                                      │
│ Qual herói possui o melhor winrate nos últimos 30d? │
│                                                      │
│ ● Dados disponíveis   12 fontes   Atualizado 4 min │
│                                      [ ANALISAR → ]  │
└──────────────────────────────────────────────────────┘

Características:

- textarea/input grande
- auto resize
- Enter envia
- Shift + Enter quebra linha
- botão disabled quando vazio
- loading state
- keyboard focus
- acessibilidade
- indicador de contexto disponível
- feedback visual durante processamento

Placeholder:

"Ex.: qual herói possui o melhor winrate?"

==================================================
7. SUGESTÕES
==================================================

Criar chips:

[ Melhor winrate ]
[ Comparar heróis ]
[ Jogos em alta ]
[ Precisão das previsões ]
[ Steam preços baixos ]
[ Quantos jogos? ]

As sugestões devem preencher o input.

Não enviar automaticamente.

Hover elegante.

==================================================
8. ESTADO DE PROCESSAMENTO
==================================================

Quando o usuário perguntar:

Não mostrar apenas um spinner.

Mostrar:

✦ Analisando seus dados...

✓ Entendendo pergunta
✓ Recuperando contexto
◌ Validando resultados
○ Gerando resposta

Use skeletons para o conteúdo.

As animações devem ser discretas.

==================================================
9. RESULTADO DA IA
==================================================

O resultado NÃO deve parecer apenas uma mensagem de chat.

Criar um "Data Answer Card".

Exemplo:

┌──────────────────────────────────────┐
│ ✦ RESULTADO                          │
│                                      │
│ Melhor winrate                       │
│ nos últimos 30 dias                  │
│                                      │
│ Phantom                              │
│ 58,3%                                │
│ WINRATE                              │
│                                      │
│ ────────────────────────────────     │
│                                      │
│ 2  Jett                 56,8%        │
│ 3  Raze                 55,9%        │
│ 4  KAY/O                54,7%        │
│ 5  Sage                 53,1%        │
│                                      │
│ 12.482 partidas analisadas           │
└──────────────────────────────────────┘

IMPORTANTE:

Os dados acima são apenas exemplo visual.

Utilize os dados reais retornados pela aplicação.

NÃO invente dados.

==================================================
10. VISUALIZAÇÃO DE DADOS
==================================================

Quando a pergunta permitir comparação numérica, apresentar visualização.

Exemplo:

WINRATE POR HERÓI

60%
55%
50%
45%

Phantom
Jett
Raze
KAY/O
Sage

Utilizar a biblioteca de gráficos que já existir no projeto.

Se não existir:
utilizar uma solução leve e compatível com o stack atual.

Não adicionar uma biblioteca pesada desnecessariamente.

O gráfico deve ser:
- responsivo
- acessível
- tooltip
- labels
- animação sutil
- dark mode
- visual consistente com o design system

IMPORTANTE:

O frontend NÃO deve inventar dados para o gráfico.

O gráfico deve nascer da mesma resposta/contexto real utilizado pela IA.

==================================================
11. RIGHT SIDEBAR — CONTEXTO DA RESPOSTA
==================================================

Criar:

CONTEXTO DA RESPOSTA

📊 Matches
12.482 registros

👤 Heroes
27 heróis

📈 Predictions
8 modelos

◷ Atualizado
há 4 minutos

[ Ver todas as fontes ]

Os valores devem vir dos dados reais disponíveis.

==================================================
12. CONFIANÇA DA RESPOSTA
==================================================

Criar card:

CONFIANÇA DA RESPOSTA

92%

Alta confiança

"Baseada em dados suficientes e atualizados."

IMPORTANTE:

Se o backend fornecer confidence:
usar o valor real.

Se NÃO existir confidence:
NÃO inventar 92%.

Nesse caso, criar uma representação qualitativa baseada apenas em informações disponíveis, ou deixar o componente preparado para receber esse campo posteriormente.

Exemplo:

✓ Alta confiança
✓ Dados suficientes

ou

⚠ Confiança limitada
Base insuficiente para uma conclusão robusta.

==================================================
13. TRANSPARÊNCIA — COMO CHEGAMOS NESSA RESPOSTA
==================================================

Criar uma seção expansível:

"COMO CHEGAMOS NESSA RESPOSTA?"

Fluxo visual:

① Identificamos a entidade
Hero

↓

② Consultamos a fonte
matches

↓

③ Filtramos
últimos 30 dias

↓

④ Calculamos
wins / matches

↓

⑤ Ordenamos
por winrate DESC

↓

⑥ Resultado
Phantom — 58,3%

IMPORTANTE:

Essa informação deve utilizar o contexto real retornado pelo backend.

Não inventar etapas.

Se a aplicação já retorna fontes/contexto, mapear essas informações para esse componente.

==================================================
14. SQL / CONSULTA
==================================================

Adicionar ações:

[ Copiar ]
[ Exportar ]
[ Ver consulta ]
[ Ver dados ]

"Ver consulta" deve ser secundário.

Não expor SQL bruto imediatamente.

Ao abrir:

Modal/Drawer:

CONSULTA UTILIZADA

```sql
...
Com:

[ Copiar consulta ]

Se o backend NÃO fornecer SQL:
não inventar.

Nesse caso, não renderizar "Ver consulta".

==================================================
15. FONTES

Criar visualização de fontes:

FONTES

▣ Matches
▣ Heroes
▣ Predictions

Cada fonte deve poder ser expandida.

Exemplo:

Matches
12.482 registros
Atualizado: 21:58

[ Ver dados ]

Se o backend fornecer URL/identificador:
permitir navegação.

==================================================
16. PERGUNTAS RELACIONADAS

Após uma resposta:

PERGUNTAS RELACIONADAS

[ Qual possui o maior pick rate? → ]

[ Como esse número mudou nos últimos 30 dias? → ]

[ Compare Phantom e Jett → ]

[ Qual mapa favorece esse herói? → ]

[ Qual agente possui maior taxa de vitória? → ]

Essas perguntas devem ser clicáveis.

Ao clicar:
preencher/enviar a nova consulta respeitando o fluxo existente.

==================================================
17. FEEDBACK

No final da resposta:

"Essa resposta foi útil?"

[ 👍 ] [ 👎 ]

Ações:

[ Copiar ]
[ Exportar ]
[ Ver consulta ]
[ Ver dados ]

Se feedback já existir no backend:
integrar.

Se não existir:
implementar UI preparada para integração futura.

==================================================
18. EMPTY STATE

Quando não existir nenhuma pergunta:

Criar uma experiência premium.

Exemplo:

✦

ASSISTENTE DE DADOS

"Seus dados têm respostas."

"Pergunte sobre jogos, partidas, heróis,
previsões, Steam e métricas."

Sugestões:

[ Qual jogo tem mais jogadores? ]
[ Melhor winrate ]
[ Quantos jogos monitorados? ]
[ Precisão das previsões ]

Não mostrar uma tela vazia.

==================================================
19. ERROR STATE

Criar tratamento elegante:

⚠ Não foi possível analisar os dados.

"Não conseguimos obter uma resposta agora."

[ Tentar novamente ]

Mostrar erro técnico detalhado apenas quando apropriado.

Não expor stack trace para usuário.

==================================================
20. RESPONSIVIDADE

Desktop:
3 colunas.

Tablet:
2 colunas.

Mobile:
1 coluna.

Left sidebar:
Drawer.

Right context:
Drawer ou seção colapsável.

O input deve funcionar perfeitamente em:

1920x1080
1440x900
1366x768
1024x768
768x1024
390x844

Não permitir overflow horizontal.

==================================================
21. DESIGN SYSTEM

Crie/refatore tokens para:

background
surface
surface-hover
border
text-primary
text-secondary
text-muted
accent
success
warning
danger

Não espalhar valores arbitrários pelo código.

Utilizar CSS variables/Tailwind config conforme arquitetura existente.

Exemplo conceitual:

--nexus-bg
--nexus-surface
--nexus-border
--nexus-accent
--nexus-text

==================================================
22. TIPOGRAFIA

Hierarquia:

Display:
Pergunte aos seus dados

Heading:
Resultado

Body:
descrições

Technical:
fonte monoespaçada

Evitar usar CAPS em absolutamente tudo.

CAPS somente para:

labels
categorias
informações técnicas
==================================================
23. MICROINTERAÇÕES

Adicionar:

hover
focus
active
loading
skeleton
transitions 150–250ms
fade-in de respostas
animação sutil de gráficos
highlight de resultado
feedback visual no botão

Não utilizar:

bounce
animações exageradas
efeitos constantes que distraiam

Respeitar:

prefers-reduced-motion

==================================================
24. ACESSIBILIDADE

Implementar:

aria-labels
keyboard navigation
focus visible
contraste adequado
sem depender apenas de cor
tooltips acessíveis
botões semanticamente corretos
headings hierárquicos
==================================================
25. PERFORMANCE

Não fazer:

renders desnecessários
chamadas duplicadas
polling desnecessário
bibliotecas pesadas sem necessidade

Utilizar:

memoização quando fizer sentido
debounce no search
lazy loading quando fizer sentido
virtualização caso histórico seja grande
==================================================
26. ARQUITETURA

Não colocar toda a tela em um único componente.

Separar aproximadamente:

DataAssistantPage
├── AssistantHeader
├── QueryComposer
├── SuggestionChips
├── ConversationHistory
├── DataAnswer
│ ├── AnswerSummary
│ ├── AnswerChart
│ ├── AnswerSources
│ ├── ConfidenceCard
│ └── RelatedQuestions
├── ContextPanel
├── ReasoningSteps
└── FeedbackActions

Os nomes podem ser adaptados ao padrão existente do projeto.

==================================================
27. REGRA ABSOLUTA SOBRE DADOS

A interface NUNCA deve fabricar:

números
winrates
quantidade de jogos
nomes de heróis
confiança
fontes
datas
consultas SQL
resultados

Se um dado não existir:

esconder o componente
OU
mostrar estado "não disponível"

Nunca usar números fake para "preencher" a interface.

==================================================
28. PRESERVAR FUNCIONALIDADE EXISTENTE

Muito importante:

Não quebrar:

autenticação
API
perguntas
contexto
respostas
navegação
sidebar
tema
backend
rotas
serviços

O redesign é principalmente de:
UX + UI + apresentação + arquitetura frontend.

==================================================
29. QUALIDADE DE CÓDIGO

Código de nível Senior++.

Evitar:

any
duplicação
componentes gigantes
lógica misturada com apresentação
magic numbers
strings espalhadas
estados inconsistentes
hacks de CSS
!important desnecessário

Utilizar:

TypeScript forte
interfaces/types
componentes reutilizáveis
hooks
funções pequenas
tratamento de erro
loading states
empty states
==================================================
30. VALIDAÇÃO FINAL

Depois de implementar:

Execute lint.
Execute typecheck.
Execute testes existentes.
Faça build.
Corrija erros.
Verifique console.
Verifique network requests.
Teste a pergunta real.
Teste loading.
Teste erro.
Teste empty state.
Teste desktop.
Teste mobile.
Verifique overflow.
Verifique acessibilidade básica.
==================================================
31. NÃO FAÇA UMA CÓPIA ESTÁTICA DO MOCKUP

A imagem de referência serve apenas como:

direção visual
layout
hierarquia
inspiração de UX

Não transforme a tela em uma imagem.

Tudo deve ser:

HTML
React
CSS/Tailwind
componentes reais
dados reais
interativo
==================================================
32. RESULTADO ESPERADO

Quero que a tela final pareça:

"Um produto SaaS profissional de Data Intelligence com IA."

Não:

"Um chatbot bonito."

O usuário deve sentir que está conversando com uma camada inteligente sobre o banco de dados do NEXUS.

A experiência precisa comunicar:

DADOS REAIS
+
IA
+
TRANSPARÊNCIA
+
VISUALIZAÇÃO
+
CONFIABILIDADE
+
EXPERIÊNCIA PREMIUM

==================================================
33. IMPORTANTE — IMPLEMENTE, NÃO APENAS EXPLIQUE

Não me entregue apenas sugestões.

Depois de analisar o projeto:

→ implemente o redesign diretamente no código.

Ao final, informe:

Arquivos modificados
Componentes criados
Funcionalidades preservadas
Funcionalidades novas
Dependências adicionadas, se houver
Testes executados
Resultado do build
Eventuais limitações ou pontos que dependem do backend

Se encontrar algo que precise ser alterado no backend para suportar uma funcionalidade visual, NÃO quebre o frontend.

Implemente o frontend de forma compatível e documente o contrato necessário.

PRIORIDADE:

Funcionalidade existente
Integridade dos dados
UX
Arquitetura
Visual
Performance
Acessibilidade

Comece agora analisando o projeto e localizando a implementação atual do ASSISTENTE DE DADOS.