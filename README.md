# Gaming Analytics

Sistema de coleta, armazenamento e análise de dados do universo gamer/esports, desenvolvido como TCC.

Não é um jogo: é uma plataforma de dados que coleta periodicamente de quatro fontes, normaliza em
PostgreSQL, expõe uma API analítica própria e alimenta um dashboard.

```
[APIs externas] → [Coletores] → [Payload bruto (JSON)] → [ETL] → [PostgreSQL] → [API FastAPI] → [Dashboard React]
```

## Dois domínios de dados

O projeto trabalha com dois modelos **separados de propósito** — forçar um schema único entre eles
destruiria informação:

| Domínio | Fontes | Granularidade | Status |
|---|---|---|---|
| **Catálogo / mercado** | Steam | por jogo, ao longo do tempo | Fase 1 — pronto |
| **Partidas (esports)** | Dota 2, LoL, Valorant | por jogador dentro de uma partida | Fase 2+ |
| **Série de partida** | Dota 2 | por minuto dentro de uma partida | Fase 6 — alimenta o modelo |
| **Texto de avaliação** | Steam | uma avaliação escrita | Fase 7 — alimenta o modelo |
| **Equipes** | Dota 2 | uma equipe profissional | Fase 9 — alimenta o modelo |
| **Agenda** | Liquipedia | um confronto futuro | Fase 10 — calendário, não fato |

## Princípios de design

- **O payload bruto é gravado antes de qualquer normalização.** Cada resposta de API vai para
  `data/raw/<fonte>/<endpoint>/<data>/` e é registrada em `raw_data`. Quando o ETL muda, dá para
  reprocessar tudo sem gastar rate limit chamando a API de novo.
- **Cada coletor é independente**, com a mesma interface (`collect()` / `save_raw()` / `parse()` /
  `load()`), definida em `collectors/base.py`. Adicionar ou remover uma fonte não afeta as outras.
- **Idempotência:** rodar um coletor duas vezes não duplica registros. Tudo é upsert por chave natural.
- **Rate limiting e backoff exponencial** por fonte, em `collectors/http_client.py`.
- **Nenhuma credencial em código.** Tudo vem de variáveis de ambiente (`config.py`).

## Pré-requisitos

- Docker Desktop
- Python 3.11+ (testado em 3.14)
- Node.js 20+ (só para desenvolver o dashboard; no Docker ele é embutido)

## Como rodar

### 1. Subir o banco

```powershell
docker compose up -d postgres
```

O Postgres é publicado em **`localhost:55432`** (porta alta de propósito, para não conflitar com um
Postgres instalado na máquina, que costuma ocupar a 5432).

### 2. Configurar o ambiente

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

O `.env` já vem com valores que funcionam com o `docker-compose.yml`. Nenhuma chave de API é
necessária para a Fase 1.

> **Usando um Postgres local em vez do Docker:** ajuste `POSTGRES_PORT`, `POSTGRES_USER` e
> `POSTGRES_PASSWORD` no `.env` e rode `init-db`. Nenhuma mudança de código é necessária.
> O `.env` está no `.gitignore` — credenciais nunca são versionadas.

### 3. Criar o schema

```powershell
.\.venv\Scripts\python.exe cli.py init-db
```

Aplica as migrations do Alembic (`db/migrations/versions/`). As migrations são a fonte da verdade do
schema; `db/schema.sql` é só uma referência de leitura.

### 4. Subir tudo junto (API e dashboard incluídos)

```powershell
docker compose up -d
```

| Serviço | Endereço | O que é |
|---|---|---|
| Dashboard | <http://localhost:3000> | interface React |
| API | <http://localhost:8000> | docs interativas em `/docs`, health check em `/health` |
| Postgres | `localhost:55432` | banco |

O nginx do dashboard repassa `/api` e `/docs` para o serviço `api`, então em produção tudo sai
da mesma origem e **não há CORS envolvido**. Mude a porta publicada com `DASHBOARD_PORT` no `.env`.

### 5. Desenvolver o dashboard

```powershell
cd dashboard
npm install
npm run dev
```

Abre em <http://localhost:5173>. O dev server do Vite tem um proxy de `/api` para
`http://localhost:8000`, então o backend pode estar rodando no Docker enquanto o frontend roda
na máquina, sem configurar nada. `VITE_API_ALVO` muda o alvo do proxy; `VITE_API_URL` aponta o
dashboard para uma API em outra origem (aí o CORS entra, e a origem precisa estar em
`CORS_ORIGINS`).

## API

Endpoints analíticos, todos somente leitura. A resposta completa de cada um está em `/docs`.

| Endpoint | Devolve |
|---|---|
| `GET /health` | status da API e do banco |
| `GET /api/visao-geral` | contagens dos dois domínios + última coleta por fonte |
| `GET /api/steam/jogos` | catálogo + snapshot mais recente de cada jogo (`busca`, `genero`, `ordenar_por`, `ordem`, `limite`) |
| `GET /api/steam/jogos/{app_id}` | um jogo e toda a série temporal dele |
| `GET /api/steam/generos` | agregação por gênero |
| `GET /api/steam/catalogo` | busca no catálogo **completo** da Steam (`termo`), marcando o que já foi coletado |
| `POST /api/steam/coletar` | coleta um jogo agora, com o texto das avaliações (`app_id`) |
| `GET /api/partidas` | partidas, com o lado vencedor resolvido (`jogo`, `liga`, `desde`, `limite`, `deslocamento`) |
| `GET /api/partidas/{id}` | placar completo da partida |
| `GET /api/partidas/resumo` | KPIs + histograma de duração |
| `GET /api/partidas/por-dia` | volume de partidas por dia |
| `GET /api/partidas/personagens` | winrate e médias por herói (`min_partidas`, `ordenar_por`) |
| `GET /api/partidas/jogadores` | agregação por jogador |
| `GET /api/partidas/jogos` | jogos do star schema e quanto já foi coletado de cada um |
| `GET /api/partidas/filtros` | ligas, modos e patches que existem de fato (monta os dropdowns) |
| `GET /api/steam/serie-total` | jogadores simultâneos somados sobre todo o catálogo, por janela |

As rotas de partidas aceitam `?jogo=` (padrão `dota2`) e leem o discriminador `dim_jogo.codigo`.
Quando a Fase 3 popular o LoL, **os mesmos endpoints e as mesmas telas passam a servi-lo** sem
mudança de código.

Duas decisões que aparecem em quase toda consulta:

- **`DISTINCT ON (app_id)`** no domínio Steam: a tela quer o estado agora, que é o snapshot mais
  recente de cada jogo, não a série inteira.
- **Janela numerada (`row_number`)** em dois lugares: no Steam para achar a coleta *anterior*
  de cada jogo (sem ela não existe variação para mostrar, só um número solto sem referência),
  e em jogadores para o herói mais escolhido — "a primeira linha de cada jogador quando
  ordenado por contagem" é exatamente o que a função responde, numa varredura só.
- **`min_partidas`** nas agregações de partidas: um herói com 2 jogos e 2 vitórias tem 100% de
  winrate e nenhum significado estatístico — sem o corte ele lidera qualquer ranking.

## Dashboard

React 19 + TypeScript, com Vite, Tailwind CSS, React Router e TanStack Query.
Fica em `dashboard/`.

**Não há biblioteca de gráficos.** O desenho do Stitch desenha cada visualização como SVG
inline — curva com gradiente de traço, brilho por `drop-shadow`, coluna modal destacada,
barras divergentes em torno de um eixo central. Reproduzir isso por cima do Recharts dava
mais trabalho do que desenhar, e prendia o resultado ao que a biblioteca deixa customizar.
Os gráficos vivem em `src/componentes/graficos/` e `src/componentes/hud.tsx`; o que o mockup
chama de "tooltip simulado" aqui responde ao ponteiro de verdade.

O visual sai do **Google Stitch**: o design system "Apex Broadcast Engine" (projeto
`Esports Gaming Analytics Dashboard`) e as telas foram desenhados lá, e o
`tailwind.config.js` é uma cópia fiel dos tokens que o Stitch embute em cada tela
gerada — cor, tipografia, espaçamento e raio. Para mudar a aparência, o caminho é
alterar o design system no Stitch e reexportar esse arquivo, não editá-lo à mão.

| Tela | O que mostra |
|---|---|
| Visão geral | KPIs dos dois domínios, top de jogadores simultâneos, partidas por dia |
| Jogos da Steam (busca em toda a loja) | ranking pela métrica escolhida + tabela do catálogo, com filtro de busca e gênero |
| Detalhe do jogo | série temporal de jogadores simultâneos e todos os snapshots coletados |
| Partidas | KPIs, histograma de duração, volume por dia e a lista paginada |
| Detalhe da partida | placar por equipe + as métricas que só existem no Dota (`metricas_extras`) |
| Heróis | winrate contra a linha de 50%, em barras divergentes, e a tabela completa |

As onze telas são porte fiel do projeto do Stitch (`Esports Gaming Analytics Dashboard`):
mesma estrutura de seções, mesmas classes, mesmos tokens. Onde o mockup mostra um dado que
o projeto não coleta, a decisão foi **não inventar o número**: "Trending 24h" fica
desabilitado até existir uma segunda coleta, a variação aparece como travessão, e busca
global, notificações e avatar de usuário ficaram fora porque não há endpoint para nenhum.
Capas de jogo e retratos de herói saem da CDN da Valve por caminho determinístico
(`app_id` e `nome_interno`), então não custam coleta nem armazenamento.

O jogo do domínio de partidas (Dota 2 / LoL / Valorant) é escolhido nos chips da barra
superior e vale para Partidas, Heróis e Jogadores ao mesmo tempo. Ele vive na URL
(`?jogo=`), então um link continua apontando para o mesmo recorte quando alguém o cola.
| Jogadores | volume e desempenho por jogador identificado, com pódio dos três primeiros |
| Previsão de confronto | próximos confrontos da agenda, qual time vence, ranking de força e os fatores por trás |
| Recomendações por reviews | destaque de um jogo no formato da loja, busca em toda a Steam, tendência, recorte por aspecto e as avaliações onde o modelo erra |
| Assistente de dados | perguntas em português, com o contexto consultado exibido ao lado da resposta |

Decisões de visualização que valem menção na monografia:

- **A cor codifica o trabalho do dado, não a estética.** Ranking de magnitude usa uma série e uma
  cor só — colorir cada barra conforme o valor duplicaria em cor o que o comprimento já diz.
  Winrate usa um par divergente em torno dos 50%, porque ali a pergunta é de polaridade
  ("de que lado da linha?"), não de identidade.
- **A paleta foi validada, não escolhida no olho.** Os tons passam nos limiares de separação para
  daltonismo (ΔE ≥ 8 em OKLab) e de contraste contra o fundo, nos dois temas.
- **Todo gráfico tem a tabela equivalente** na mesma tela: nenhum valor existe só dentro de um
  tooltip ou só codificado em cor.
- **O painel é escuro e só escuro.** O design system do Stitch declara `colorMode: DARK` e
  traz uma paleta só; inventar um segundo conjunto de cores para fundo claro seria decidir
  no código uma coisa que é do desenho. Por isso não há seletor de tema.
- **Nenhum KPI é calculado fora do envelope da consulta.** Uma média sobre `dados ?? []`
  imprime `0` quando a verdade é "não deu para carregar" — e um zero é uma afirmação sobre
  os dados, não um estado de carregamento.
- **Uma tela desenhada continua sem backend** (Perfil): ela depende de autenticação, que o
  projeto não tem. Aparece na navegação desabilitada e marcada, em vez de existir com
  dados fixos no código — uma tela com dado inventado é pior que uma tela ausente, porque
  parece pronta. *Toxicidade em Chat* foi desenhada no Stitch e **removida do produto**: o
  campo `chat` das partidas profissionais só traz *chatwheel* (sons pré-definidos), então
  a tela não tinha texto para analisar.

Build de produção:

```powershell
cd dashboard
npm run build        # tsc -b && vite build, saída em dist/
npm run preview      # serve o build em http://localhost:4173
```

## Fases

### Fase 1 — Steam (catálogo / mercado)

Coleta de três endpoints públicos da Steam, **nenhum exige chave de API**:

| Endpoint | Uso |
|---|---|
| `store.steampowered.com/api/appdetails` | nome, gêneros, desenvolvedora, preço, Metacritic |
| `store.steampowered.com/appreviews/<id>` | resumo agregado das avaliações |
| `api.steampowered.com/.../GetNumberOfCurrentPlayers` | jogadores simultâneos |

Os dois primeiros dividem o mesmo host e o mesmo balde de rate limit (~200 req / 5 min por IP), então
compartilham o mesmo cliente HTTP.

Rodar isoladamente:

```powershell
.\.venv\Scripts\python.exe cli.py collect steam                    # lista semente
.\.venv\Scripts\python.exe cli.py collect steam --apps 570,730     # apps específicos
.\.venv\Scripts\python.exe cli.py collect steam --steamspy-top 50  # top 50 do SteamSpy
.\.venv\Scripts\python.exe cli.py collect steam --no-load          # coleta sem gravar no banco
.\.venv\Scripts\python.exe cli.py collect steam --from-raw         # reprocessa o disco, sem rede
```

Ou dentro do Docker:

```powershell
docker compose run --rm collector collect steam
```

A lista de jogos monitorados fica em `collectors/seeds/steam_apps.json` — edite à vontade.

**Tabelas:** `dim_jogo_steam` (atributos estáveis) e `fato_snapshot_jogo_steam` (série temporal:
jogadores simultâneos, avaliações e preço a cada coleta).

A chave de idempotência do snapshot é `(app_id, janela_coleta)`, onde `janela_coleta` é o instante da
coleta truncado em `SNAPSHOT_BUCKET_MINUTES` (padrão: 60 min). Duas coletas dentro da mesma hora
atualizam a mesma linha em vez de inflar a série.

Validar:

```powershell
.\.venv\Scripts\python.exe cli.py stats
```

```sql
SELECT d.nome, f.jogadores_simultaneos, f.nota_avaliacoes, f.preco_no_momento
FROM dim_jogo_steam d
JOIN fato_snapshot_jogo_steam f USING (app_id)
ORDER BY f.jogadores_simultaneos DESC;
```

### Fase 2 — OpenDota (Dota 2)

Constrói o star schema de partidas e o valida com Dota 2 antes de replicá-lo para LoL na Fase 3.
A API do OpenDota é pública e **não exige chave**: o limite gratuito é de 60 requisições por minuto
e ~3.000 por dia.

| Endpoint | Uso |
|---|---|
| `/api/heroes` | `dim_personagem` |
| `/api/proMatches` | descobre os `match_id` das partidas profissionais (paginado) |
| `/api/matches/{id}` | `dim_partida`, `dim_jogador` e o fato |

Rodar isoladamente:

```powershell
.\.venv\Scripts\python.exe cli.py collect opendota                  # 100 partidas
.\.venv\Scripts\python.exe cli.py collect opendota --limite 300
.\.venv\Scripts\python.exe cli.py collect opendota --recoletar      # nao pula as ja coletadas
.\.venv\Scripts\python.exe cli.py collect opendota --from-raw       # reprocessa o disco, sem rede
```

Como o detalhe custa **uma chamada por partida**, o coletor consulta `dim_partida` antes e pula o
que já foi coletado. Isso torna a segunda execução seguida praticamente gratuita: na prática, 100
partidas já coletadas custam 2 chamadas em vez de 101.

**Tabelas:** `dim_jogo`, `dim_tempo`, `dim_jogador`, `dim_personagem`, `dim_partida` e
`fato_partida_jogador` (uma linha por jogador por partida).

Duas decisões de normalização que valem menção na monografia:

- **`pontos_objetivo`** é a métrica genérica de objetivos. No Dota é `towers_killed + roshan_kills`;
  no LoL será torres + dragões + barão; no Valorant, spikes plantadas/desarmadas. Sem esse campo
  genérico, cada jogo exigiria colunas próprias e a comparação entre eles ficaria impossível.
- **`metricas_extras`** (JSONB) guarda o que só existe em um jogo (`lane_efficiency_pct`,
  `net_worth`, `roshan_kills`...). A alternativa — criar colunas que LoL e Valorant nunca
  preencheriam — é exatamente o "schema único forçado" que o projeto evita.

Jogadores anônimos (`account_id` nulo, comum fora do circuito profissional) geram linha de fato com
`id_jogador` nulo: o KDA e o herói continuam analisáveis mesmo sem identificar quem jogou.

Validar:

```sql
-- winrate por herói
SELECT p.nome AS heroi, count(*) AS partidas,
       round(100.0 * sum(f.vitoria::int) / count(*), 1) AS winrate,
       round(avg(f.economia_por_minuto)) AS gpm_medio
FROM fato_partida_jogador f
JOIN dim_personagem p USING (id_personagem)
JOIN dim_jogo j ON j.id_jogo = f.id_jogo AND j.codigo = 'dota2'
GROUP BY p.nome HAVING count(*) >= 15
ORDER BY winrate DESC;

-- nenhum fato órfão (deve retornar 0)
SELECT count(*) FROM fato_partida_jogador f
LEFT JOIN dim_partida d USING (id_partida) WHERE d.id_partida IS NULL;
```

### Fase 6 — Previsão de partida por minuto (removida do produto)

> **Esta fase saiu do produto.** As telas *Simulador ao Vivo* e *Comparação de Modelos*
> foram removidas, e com elas `ml/treino.py`, `ml/dataset.py`, `api/routers/ml.py`, o
> comando `cli.py train` e os artefatos do modelo. **O dado continua:** a tabela
> `fato_minuto_partida` segue sendo preenchida pelo ETL, a migration `0003` continua
> aplicada, e `data/raw/` guarda os payloads que a originam — refazer o treino é reescrever
> o treinador, não recoletar nada. A seção fica como registro do que foi feito e medido.

**Por que saiu.** A pergunta que ela respondia — "quem está ganhando esta partida agora?"
— é útil para narrar, não para decidir. A previsão que restou no produto é a da
[Fase 9](#fase-9--previsão-de-confronto-entre-equipes): quem vence **antes** de a partida
começar, que é onde a resposta ainda muda alguma coisa.

**O grão era o minuto, não a partida.** O `fato_partida_jogador` guarda o placar *final* de
cada jogador; ele responde "como a partida terminou". A migration `0003` criou o
`fato_minuto_partida`, que responde outra pergunta: "como a partida estava indo no minuto
N". As 100 partidas coletadas viraram **3.959 amostras rotuladas**, montadas a partir de
`radiant_gold_adv` / `radiant_xp_adv` (que a OpenDota já publica indexados por minuto) e
dos eventos de `objectives`, acumulados até cada minuto. Nada disso exigiu rede: os
payloads já estavam em `data/raw/`, e o `cli.py collect opendota --from-raw` reprocessou o
disco.

| Modelo | Família | Acurácia | ROC-AUC | Log-loss |
|---|---|---|---|---|
| Regressão Logística | Linear | 75,5% | 0,8531 | **0,4653** |
| Random Forest | Ensemble (bagging) | **75,8%** | 0,8491 | 0,4835 |
| Gradient Boosting | Ensemble (boosting) | 74,5% | 0,8380 | 0,4830 |

A taxa base era 52,6% — o que um chute constante acertaria.

Quatro decisões que valem menção na monografia, e que valem independentemente de a tela
existir:

- **O split é agrupado por partida (`GroupShuffleSplit`), não por linha.** As 3.959
  amostras vinham de 100 partidas, e minutos da mesma partida são quase o mesmo ponto.
  Embaralhar linhas colocaria o minuto 12 no treino e o 13 no teste: o modelo decoraria o
  desfecho e a acurácia mediria memória, não previsão. É a decisão que mais afeta o
  número, e a que menos aparece quando está errada.
- **O modelo servido era o de menor log-loss, não o de maior acurácia.** A tela mostrava
  uma *probabilidade*; log-loss e Brier são as métricas que punem confiança errada.
  Escolher por acurácia entregaria o modelo que mais acerta o lado e menos sabe o quanto
  tem certeza.
- **A importância das features era permutation importance, não coeficiente.** Cada família
  expõe importância numa escala própria, e comparar coeficiente de regressão com ganho de
  impureza de árvore não significa nada. Embaralhar uma coluna e medir quanto o ROC-AUC
  piora é o mesmo procedimento para as três.
- **Três famílias diferentes, não três variações da mesma.** Comparar hiperparâmetros
  responderia "qual configuração é melhor"; comparar linear contra ensembles responde se o
  problema pede fronteira não-linear.

Um efeito observado que vale registrar: com tudo zerado no minuto 20, a regressão previa
72% para o Radiant e as duas árvores ficavam perto de 44%. É um estado que quase não existe
nos dados (ninguém chega ao minuto 20 sem perder torre), e o modelo linear extrapola onde
as árvores não extrapolam. Divergência grande entre famílias é sinal de região incerta, não
de bug — e foi o que motivou o painel de consenso que a tela mostrava.

O que sobreviveu no código: `etl/transform_dota.py::parse_serie_minutos`, a carga em
`etl/load_dota.py`, o modelo `FatoMinutoPartida` e `tests/test_serie_minutos.py`, que segue
sendo o contrato com o formato da OpenDota.

### Fase 7 — Recomendações por reviews (NLP)

A tela **Recomendações por Reviews**, servida por um classificador treinado sobre o texto
das avaliações da Steam.

**A tela e o modelo têm nomes diferentes de propósito.** A tela se chama *recomendação*
porque é isso que ela mostra a quem olha: se o público recomenda o jogo. O modelo por trás
continua sendo um **classificador de sentimento** (`ml/sentimento.py`, `/api/ml/sentimento/*`)
— esse é o nome técnico da técnica, e renomear também o backend misturaria a pergunta do
usuário com o método que a responde.

**O rótulo não foi anotado à mão.** É o `voted_up` da própria avaliação — o polegar que
o autor deu ao escrever. Isso elimina a etapa mais cara de um projeto de NLP e muda a
natureza do problema: não há juiz humano no meio, e o que o modelo aprende é a relação
entre o texto que a pessoa escreveu e o voto que ela mesma deu.

Duas mudanças no coletor tornaram isso possível:

- `num_per_page` passou de `0` para 100. O mesmo endpoint que já trazia o resumo agregado
  passa a trazer a lista de avaliações — **os campos do `query_summary` vêm iguais com ou
  sem texto**, então a mesma chamada serve aos dois grãos e o snapshot não mudou.
- **Paginação por cursor** (`steam_reviews_paginas`). Com uma página só o corpus tinha 304
  avaliações em inglês e o modelo ficava em ROC-AUC 0,70. Com dez páginas são 2.864, e o
  ROC-AUC sobe para 0,857 — a diferença entre um modelo que não serve e um que serve.

```powershell
.\.venv\Scripts\python.exe cli.py collect steam        # com STEAM_REVIEWS_PAGINAS no .env
.\.venv\Scripts\python.exe cli.py train-sentimento     # treina os tres classificadores
```

| Modelo | Acurácia | Balanceada | ROC-AUC | F1 (negativa) |
|---|---|---|---|---|
| TF-IDF + Regressão Logística | 79,3% | **77,4%** | 0,8522 | **0,648** |
| TF-IDF de caracteres + SVM | **82,3%** | 71,8% | **0,8568** | 0,594 |
| TF-IDF + Complement Naive Bayes | 78,6% | 63,1% | 0,7934 | 0,427 |

A taxa base é 74,1% — 3 em cada 4 avaliações são positivas.

Decisões que valem menção:

- **A classe é desbalanceada, então acurácia sozinha engana.** Prever "positivo" sempre já
  acerta 74%. Por isso o relatório traz acurácia balanceada, F1 da classe negativa e
  ROC-AUC, e os modelos usam `class_weight="balanced"`.
- **O split é estratificado, não agrupado** — o oposto da Fase 6. Lá, minutos da mesma
  partida eram quase o mesmo ponto e precisavam ficar do mesmo lado. Aqui a unidade é uma
  avaliação escrita por uma pessoa, independente das outras.
- **Avaliações com menos de 20 caracteres saem do treino.** Abaixo disso o texto é quase
  sempre uma palavra solta ("good", "trash"): o modelo acertaria por memorização de token,
  e a métrica subiria sem significar nada. Foram 1.892 descartadas.
- **Um idioma só.** Treinar sobre a mistura produziria um vocabulário em que "хорошая" e
  "good" são tokens sem relação, e o modelo aprenderia a detectar o idioma junto com o
  sentimento. O treino usa o idioma mais coletado (inglês, 2.864 de 11.946).
- **A tela separa observado de previsto.** A tendência por dia, o recorte por aspecto e o
  ranking por jogo são contagens sobre `recomendado` — não passam pelo modelo. Só o
  classificador ao vivo e a coluna de probabilidade são previsão. Misturar os dois daria
  ao modelo crédito por um dado que veio observado.
- **O recorte por aspecto é um filtro por palavra-chave, não um modelo.** "Entre as
  avaliações que mencionam desempenho, quantas recomendam". A tela diz isso com todas as
  letras; chamar de *aspect-based sentiment analysis* seria vender o que não existe.

A tela é **centrada num jogo**: uma busca escolhe qual, e o destaque o apresenta no
formato da loja da Steam — arte, ficha e recepção do público. Todo o resto (tendência,
aspectos, avaliações) segue o jogo em foco.

#### Coleta sob demanda: a busca decide o que entra no banco

**O problema.** As telas precisam de dados de jogo, e a Steam tem ~200 mil apps. Trazer
todos para dentro não é opção: seriam milhões de avaliações e semanas de coleta, para um
banco em que a maior parte nunca seria consultada. Mas restringir a busca ao que já foi
coletado é pior ainda — quem procura um jogo que não está entre os coletados recebe
"nenhum resultado", que é uma resposta sobre o nosso banco fingindo ser uma resposta sobre
a Steam.

**A saída é inverter a ordem.** Em vez de coletar tudo e depois deixar buscar, a busca é
que decide o que coletar — e coleta **só o jogo pedido, no momento em que é pedido**. O
catálogo inteiro fica pesquisável sem estar armazenado.

A busca tem então duas fontes ao mesmo tempo. O que já está no banco aparece sem digitar
nada e responde na hora. A partir de dois caracteres entra o **catálogo da Steam** via
`storesearch`, com 450 ms de *debounce*, porque uma chamada por tecla bateria no limite de
taxa da loja.

**A coleta não é uma etapa do usuário.** Não há botão "coletar": clicar num jogo que ainda
não está no banco dispara `POST /api/steam/coletar` por baixo — `SteamCollector` síncrono
sobre aquele `app_id`, três páginas de avaliações, ~6 segundos — e a tela abre o jogo
quando termina. Um botão ali seria uma etapa que existe porque o *sistema* precisa dela,
não a pessoa: ela já disse o que queria ao clicar. O que **não** se esconde é a espera — o
cartão (ou a linha da tabela) mostra o estado de carga, porque a demora é real e fingir que
não existe deixaria a tela parecendo travada.

É o **único endpoint do projeto que escreve chamando uma API externa**, e é síncrono de
propósito: quem clicou está esperando na tela, e uma fila só adicionaria a pergunta "já
terminou?" a uma operação de seis segundos. O caminho bruto-primeiro continua valendo — o
payload vai para `data/raw/steam/` antes de ser normalizado, exatamente como na coleta em
lote, então um jogo trazido pela tela é reprocessável com `--from-raw`.

**Nas duas telas, com respostas diferentes.** Em *Recomendações por Reviews* o resultado é
um cartão, e o mesmo cartão serve para as duas procedências — a tela não distingue de onde
o jogo veio. Em *Jogos da Steam* o resultado é uma linha da tabela, e ali a distinção é
necessária: as células de telemetria vêm com **travessão, não com zero**, e um chip `DA
LOJA` marca a linha. Um zero em "jogadores simultâneos" seria uma afirmação sobre o jogo;
o travessão é uma afirmação sobre o nosso banco, que é a verdadeira. Pelo mesmo motivo, os
KPIs e o ranking daquela tela — que agregam só o que foi coletado — dizem "sem telemetria
para esta busca" em vez de "nenhum jogo bate com o filtro", que seria falso com a tabela
cheia logo abaixo.

Duas limitações honestas: a coleta sob demanda usa `filter=recent`, então a tendência de um
jogo recém-trazido cobre poucos dias — o histórico longo vem da coleta em lote, repetida ao
longo do tempo. E o modelo **não é retreinado** a cada coleta: ele classifica o texto novo
com o que aprendeu no último `train-sentimento`, que é justamente o teste mais honesto —
texto de um jogo que ele nunca viu. Elden Ring, trazido pela busca, saiu com 80,4% de
recomendação observada e o aspecto mais criticado em Monetização.

**A `STEAM_API_KEY` não habilita nada disto.** O `storesearch`, o `appdetails` e o
`appreviews` são todos públicos e sem chave. A chave serve aos endpoints autenticados de
dados de JOGADOR (inventário, biblioteca, amigos), que este projeto não usa; ela fica
configurada para fases futuras.

O destaque mostra lado a lado duas leituras que costumam ser confundidas: a
**classificação da Steam**, que agrega todas as avaliações do jogo (milhões), e a **nossa**,
que agrega só as coletadas (centenas). Em Counter-Strike 2 elas divergem bastante — 86% na
Steam contra 68,3% no que foi coletado. A diferença é amostra, e a tela mostra as duas em
vez de escolher uma.

Aspectos com menos de 5 avaliações aparecem apagados: com três menções, uma delas move a
porcentagem em 33 pontos.

O painel **"só os erros"** existe para a tela não virar folheto — é onde aparece o que o
modelo não aprendeu. Um exemplo real do corpus: *"not fun but i keep playing cause its
fun"*, com polegar para baixo e 60% de probabilidade positiva.

| Endpoint | Devolve |
|---|---|
| `GET /api/ml/sentimento/comparacao` | o relatório do último treino |
| `POST /api/ml/sentimento/classificar` | a probabilidade de recomendação para um texto |
| `GET /api/ml/sentimento/avaliacoes` | avaliações reais com previsão e rótulo lado a lado (`apenas_erros`) |
| `GET /api/ml/sentimento/panorama` | contagens do rótulo real: por jogo, por dia e por aspecto |

### Fase 8 — Assistente de dados (LLM)

A tela **Assistente de IA**: perguntas em português sobre os dados coletados, respondidas
por um modelo do OpenRouter.

**A arquitetura foi decidida por um teste, não por preferência.** A ideia inicial era dar
ferramentas ao modelo e deixá-lo consultar o que precisasse. Os modelos gratuitos do
OpenRouter ignoram `tools` — e ignoram inclusive `tool_choice: "required"`. Perguntado
quantos jogos da Steam estavam sendo monitorados, um deles respondeu **20.285** com toda a
confiança, sem chamar nada. O número verdadeiro é 12.

Num projeto cujo propósito é a integridade do dado, um assistente que inventa número é
pior que assistente nenhum. Daí as três decisões:

1. **A recuperação acontece antes, em Python.** `ml/assistente.py` monta o contexto com
   SQL escrito à mão, escolhendo os blocos por palavra-chave da pergunta. **Não há
   texto-para-SQL nem execução de consulta gerada pelo modelo** — o que também elimina a
   superfície de ataque que isso abriria.
2. **O contexto volta junto da resposta** e aparece ao lado dela na tela, recolhível por
   bloco. Todo número exibido pode ser conferido contra a fonte sem sair da página.
3. **A instrução proíbe extrapolar**, e a temperatura é 0,2 — a tarefa é reproduzir
   números do contexto, não variar a redação.

O resultado, nas mesmas perguntas:

| Pergunta | Sem contexto (tool calling) | Com contexto montado |
|---|---|---|
| "Quantos jogos da Steam?" | 20.285 ❌ | 12 ✅ (à época; hoje o número acompanha a coleta) |
| "Qual herói tem o pior winrate?" | — | Night Stalker, 14,3% em 7 partidas ✅ |
| "Quem ganhou a Copa de 2022?" | — | "não está no contexto" ✅ |

Os blocos disponíveis são `geral`, `steam`, `partidas`, `herois`, `sentimento` e
`modelos`. Quando nenhuma palavra-chave casa, todos entram — vale gastar contexto para não
responder "não sei" tendo o dado.

#### O chão foi alargado, não removido

O desenho acima tem um limite óbvio: se o assistente só sabe o que está no banco, e o
banco não pode conter a Steam inteira (muito menos os jogos que nem são da Steam),
perguntar sobre um jogo não coletado devolvia "não sei" — uma limitação do nosso
*armazenamento* vestida de resposta sobre o *mundo*.

A correção não foi soltar o modelo. Foi dar **uma segunda fonte ao contexto**, e obrigar
cada bloco a declarar de onde veio:

| Nível | Fonte | O que pode aparecer |
|---|---|---|
| 1 | `banco` — o que a plataforma coletou e mediu | qualquer número |
| 2 | `steam` — a loja consultada **no instante da pergunta** | qualquer número, marcado como externo |
| 3 | nenhuma — jogo de console ou de outra loja | **só qualitativo**, prefixado com "Fora dos dados:" |

O nível 3 é a linha exata, e ela vem do próprio incidente que originou a arquitetura: o
que quebrou o assistente não foi ele *falar de jogos*, foi ele **inventar "20.285" com
cara de medição**. Descrever o que é Zelda não corre esse risco; dizer quantas cópias
Zelda vendeu corre. Por isso a regra numérica não afrouxou em nada — todo número continua
tendo de estar literalmente no contexto — enquanto a regra qualitativa abriu, com marca
obrigatória.

**Como o jogo é identificado na pergunta.** Não há reconhecimento de entidade: é subtração
seguida de recorte. Tira-se da pergunta o vocabulário de pergunta e o do nosso próprio
domínio, e os **trechos contíguos** que sobram viram candidatos, do mais longo ao mais
curto. O recorte em trechos é o que faz funcionar: juntar as sobras soltas numa string só
transformava *"o Cyberpunk 2077 vale a pena? ele está no banco?"* em `cyberpunk 2077 ele`,
que a loja não acha; em trechos, o mesmo texto dá `["cyberpunk 2077"]`.

Cada candidato é então **confirmado**: o nome devolvido pela loja precisa aparecer inteiro
e contíguo dentro da pergunta. É a mesma contenção do casamento de times em
`etl/load_liquipedia.py`, e pelo mesmo motivo — sem ela, perguntar de partidas de Dota
traria a ficha de *Dota Underlords*, e a resposta sairia confiante sobre o jogo errado.
Quando nada confirma, o bloco simplesmente não entra: perder o bloco custa uma resposta
mais pobre, um bloco errado custa uma resposta falsa.

As três respostas reais, depois da mudança:

| Pergunta | Blocos usados | Resposta |
|---|---|---|
| "Quantas avaliações do Hollow Knight temos, e quantas ele tem na Steam?" | `banco` + `steam` | "299 no nosso banco... segundo a loja da Steam, agora, 559.683 no total" ✅ |
| "O Cyberpunk 2077 está no nosso banco?" | `banco` + `steam` | "não está... R$ 199,90, 977.449 avaliações, Very Positive" ✅ |
| "O que é Zelda Breath of the Wild?" | só `banco` | "Fora dos dados: é um jogo da Nintendo... não pode ser monitorado por aqui" ✅ |

A segunda linha é a que responde à pergunta original; a primeira é a que mostra o valor do
campo `fonte`, porque a resposta **separa** os 299 que medimos dos 559.683 que lemos. A
tela pinta os dois blocos de forma diferente — ícone de loja e chip `FORA DO BANCO` — pelo
mesmo motivo: um número nosso é reproduzível consultando o banco de novo, um número da
loja não.

`collectors/steam_loja.py` faz essas consultas e **não grava nada** — é o oposto do
`steam_collector`. Não tem cache de propósito: guardar a resposta tornaria o número
possivelmente velho enquanto a tela afirma "consultada agora", e é justamente a afirmação
de procedência que dá valor ao bloco.

```powershell
# .env (nao versionado)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=minimax/minimax-m3:free
```

| Endpoint | Devolve |
|---|---|
| `GET /api/assistente/status` | se há chave configurada e qual o modelo |
| `POST /api/assistente/perguntar` | a resposta e os blocos de contexto que a geraram |

Sem chave, o endpoint responde 503 e a tela explica o que falta — **o resto do projeto
funciona sem LLM nenhum**. É a única parte que depende de um provedor externo, e a única
que custa dinheiro quando sai do plano gratuito.

**Uma tela do Stitch continua sem backend:** *Perfil* precisaria de autenticação.
*Toxicidade em Chat* saiu do produto — o campo `chat` das partidas profissionais só traz
*chatwheel* (sons pré-definidos, sem texto livre), então não havia o que classificar.

### Fase 9 — Previsão de confronto entre equipes

A tela **Previsão de Confronto** responde a pergunta que se faz *antes* da partida: qual
time tem mais chance de vencer, e por quê. É diferente da Fase 6, que olha o mapa com a
partida já em curso — as duas convivem, em telas separadas.

Isso exigiu uma dimensão nova. A OpenDota traz `radiant_team` / `dire_team` nos payloads
que já estavam em disco: `dim_equipe` (migration `0005`) mais duas FKs em `dim_partida`, e
`collect opendota --from-raw` reprocessou tudo **sem tocar na rede**. Resultado: 53
equipes e **71 confrontos** com os dois lados identificados.

**Por que Bradley-Terry e não um classificador com features.** Dos 71 confrontos, só 44
têm histórico prévio para os dois lados — o mínimo para uma feature de forma existir sem
olhar o futuro. Um classificador com meia dúzia de features sobre 44 linhas produz uma
acurácia com variância enorme: uma partida a mais ou a menos no teste move a métrica em
quase 10 pontos. Bradley-Terry é o modelo desenhado para exatamente este caso —
comparações par-a-par com poucas observações por participante. Na prática é uma regressão
logística sobre uma matriz de indicadores (+1 para o time do lado A, −1 para o do lado B),
o que traz duas propriedades úteis:

- **A regularização funciona como prior.** Com `C` baixo, um time de duas partidas é
  puxado para a média e sua previsão tende a 50% — que é o certo quando não se sabe nada
  sobre ele. É o mesmo raciocínio do `min_partidas` na tela de heróis.
- **O intercepto é a vantagem de lado**, separada da qualidade do time. Nos dados
  coletados ela é praticamente nula: 49,8% para o Radiant entre times de força igual.

```powershell
.\.venv\Scripts\python.exe cli.py train-confronto
```

**O resultado é negativo, e a tela diz isso.** A validação é *walk-forward*: para cada
partida do período de teste, as forças são reajustadas só com o que aconteceu antes dela.

| Métrica | Valor |
|---|---|
| Acurácia | 52,6% ± 22,4% |
| Taxa base | 57,9% |
| ROC-AUC | 0,636 |
| Partidas avaliadas | 19 |

**Com 71 confrontos o modelo não supera o chute.** O ROC-AUC acima de 0,5 sugere algum
sinal na ordenação, mas 19 partidas de teste não decidem isso — e a margem de ±22 pontos
diz o quanto o número vale. A tela exibe esse aviso no topo, acima da probabilidade, e
descreve o resultado como *leitura do histórico*, não como aposta validada. O que muda o
quadro é coletar mais partidas, não trocar de algoritmo.

**O `C` é escolhido por validação cruzada dentro da janela de treino, nunca olhando o
teste.** Durante o desenvolvimento, escolher o `C` pela métrica de teste dava 63,2% de
acurácia — um número melhor e sem valor, porque o hiperparâmetro já teria visto as
partidas que ele é julgado a prever.

| Endpoint | Devolve |
|---|---|
| `GET /api/ml/confronto/relatorio` | método, regularização e a validação temporal |
| `GET /api/ml/confronto/ranking` | equipes por força, com corte de amostra (`min_partidas`) |
| `GET /api/ml/confronto/prever` | probabilidade do confronto e os fatores por trás |
| `GET /api/ml/confronto/ligas` | campeonatos presentes nos dados |

**Não há partidas futuras aqui.** A OpenDota publica partidas encerradas; o endpoint de
jogos ao vivo (`/live`) esteve fora — 522 em toda a API — durante a construção desta tela,
e apoiar a tela nele deixaria a página vazia na maior parte do tempo. O modelo estima o
confronto entre dois times a partir do que já aconteceu, o que vale para um jogo que ainda
vai ocorrer desde que os dois já tenham histórico coletado.

### Fase 10 — Agenda de partidas futuras (Liquipedia)

O que faltava para prever partidas que **ainda vão acontecer** não era o modelo — Bradley-Terry
já recebe dois times e devolve a probabilidade. Faltava o **calendário**.

Nenhuma fonte já usada tem agenda. Verificado na prática:

| Fonte | Resposta | Serve? |
|---|---|---|
| OpenDota `/proMatches` | 200 (quando no ar) | Partidas **encerradas** |
| OpenDota `/live` | — | Partidas **em andamento** |
| Steam `GetLiveLeagueGames` | 403 sem chave | Também só ao vivo |
| PandaScore | 403 | Tem agenda, exige token |
| **Liquipedia** (MediaWiki API) | **200** | **Sim** |

A página `Liquipedia:Matches` agrega os confrontos futuros de todos os torneios ativos:
**83 partidas, 58 times, 8 torneios** numa única requisição.

Dois requisitos da política deles, ambos cumpridos no coletor: `Accept-Encoding: gzip`
(sem ele a API responde **406**, não 200 com dado ruim) e um User-Agent que identifique o
projeto. O intervalo entre chamadas é 3s, com folga sobre os 2s pedidos.

```powershell
.\.venv\Scripts\python.exe cli.py collect liquipedia
```

**É o único ponto do projeto que faz parsing de HTML** — a Liquipedia devolve a página
renderizada, não JSON. Daí o `beautifulsoup4` nas dependências: regex sobre markup de wiki
quebra em silêncio quando a estrutura muda; um parser quebra alto, no seletor que deixou
de existir. E os testes usam dois blocos reais como fixture, justamente para essa quebra
aparecer no CI e não como "nenhum jogo agendado" na tela.

**A reconciliação de nomes é o trabalho de verdade.** Não há chave comum entre as fontes:
a Liquipedia escreve "Power Rangers", a OpenDota cadastrou "_PowerRangers". A estratégia é
uma escada, do mais seguro ao mais frouxo:

1. Nome exato.
2. Nome normalizado — minúsculo, sem acento, sem pontuação. Resolve `_PowerRangers` e
   `Pipsqueak + 4`.
3. Nome sem enfeites — o parêntese que a wiki usa para desambiguar página
   (`DYNASTY (stack)`) e sufixos de organização (`Direborn Esports` → `DIREBORN`). Só
   entra quando a chave reduzida não colide com outro time: entre não casar e casar
   errado, não casar é a opção certa.

Resultado: **48 dos 83 confrontos** com os dois times reconciliados. Os outros 35 são
times de torneios que a coleta nunca amostrou — a FK fica nula, e a tela mostra a partida
com "sem histórico coletado" em vez de escondê-la. Esconder daria a impressão de que a
agenda é menor do que é, e o motivo é informação útil: diz onde a coleta precisa crescer.

**Não há casamento por similaridade aproximada.** Um par errado produziria uma previsão
confiante sobre a dupla errada, que é pior que previsão nenhuma. O que a escada não pega
vai para o dicionário `APELIDOS`, versionado — cresce quando alguém olha os não casados e
reconhece um par.

| Endpoint | Devolve |
|---|---|
| `GET /api/ml/confronto/agenda` | próximos confrontos com a previsão de cada um |

Na tela, a agenda é um **kanban com uma coluna por dia** — um calendário é naturalmente
uma sequência de dias, e uma tabela única obriga a ler a coluna de data para saber quando
cada jogo acontece. Clicar num card abre o detalhe: probabilidade, força de cada lado e os
fatores por trás. Cards sem previsão abrem também, explicando qual dos times ainda não tem
histórico — a informação de onde a coleta precisa crescer.

O detalhe é **um componente montado em dois lugares** (o modal do kanban e a seção de
confronto hipotético). Duas implementações do mesmo "por quê" divergiriam na primeira vez
que uma delas mudasse.

### Fase 11 — Equipes pela API MediaWiki da Liquipedia

A Fase 10 trouxe a agenda, mas com um buraco: **um terço dos confrontos não conseguia
previsão** porque o nome que a Liquipedia exibe não casava com nenhuma linha de
`dim_equipe`. Eram 89 confrontos, 25 sem a equipe A ligada e 33 sem a B.

#### O que a API oferece de verdade, medido antes de escrever código

| Tentativa | Resultado |
|---|---|
| `action=cargoquery` (tabelas estruturadas) | **não existe** — `Unrecognized value for parameter "action"`; a extensão Cargo não está instalada |
| `action=query&prop=revisions` na página da agenda | **inútil** — `Liquipedia:Matches` tem 234 caracteres de wikitexto, só um `{{#invoke:Lua ... Match/Ticker/Container}}` |
| `action=query&prop=revisions` nas páginas de equipe | **funciona** — o `{{Infobox team}}` está no fonte |
| `action=query&list=categorymembers` | **funciona** — `Category:Teams` lista as 962 equipes |

A primeira linha derrubou o plano original. A segunda é a mais informativa: a página da
agenda é montada por Lua a partir da base interna deles, então **ler HTML renderizado ali
não era atalho nosso — é a única via pelo MediaWiki**. A Fase 10 já estava certa.

#### O que muda: identificador em vez de semelhança

O `{{Infobox team}}` traz `|teamid=7119388`, e esse é **o mesmo número que a OpenDota
publica** em `radiant_team.team_id`, já gravado em `dim_equipe.id_externo`. O vínculo deixa
de ser casamento de texto e vira `WHERE id_externo = :teamid`.

Isso é o oposto do que `load_liquipedia.py` faz com os nomes da agenda, e de propósito: lá
a fonte não publica identificador, e por isso aquele módulo recusa casamento difuso. Aqui a
fonte publica. **Quando a fonte dá a chave, usar a chave é a única coisa sensata.**

```powershell
.\.venv\Scripts\python.exe cli.py collect liquipedia-times
.\.venv\Scripts\python.exe cli.py collect liquipedia-times --limite-equipes 30  # teste
```

Resultado medido de uma rodada completa: 962 títulos no índice → **633 equipes com
`teamid`** → 593 inseridas e 11 enriquecidas (essas já vinham da OpenDota), em 66,8 s.

E o efeito na agenda, reprocessando do disco sem rede:

| Confrontos com **as duas** equipes resolvidas, sobre 89 | |
|---|---|
| só com a dimensão da OpenDota | 37 (42%) |
| com as equipes da Liquipedia | **52 (58%)** |

#### Decisões que valem menção

- **`rvsection=0`, não a página inteira.** Medido: 20 páginas de equipe completas pesam
  126,6 KB; só a seção inicial, 13,3 KB. São 10% do tráfego para 100% do dado que
  interessa — o resto é histórico de line-up e referências.
- **A categoria, não uma lista escrita à mão.** `Category:Teams` é mantida pelos editores
  da wiki; uma lista nossa nasceria desatualizada e a primeira equipe nova ficaria de fora
  sem ninguém notar.
- **Um parser por profundidade, não um regex.** A primeira tentativa foi
  `\|\s*disbanded\s*=\s*([^\n|]*)`, e ela devolveu `}}` para uma equipe **ativa**: o campo
  vazio faz o padrão engolir o fechamento do template. Valores de infobox também contêm
  `[[links|com pipe]]` e `{{templates|aninhados}}`, que um regex parte ao meio. O parser
  caminha contando profundidade de `{{}}` e `[[]]` e só corta em `|` do nível de cima.
- **O nome vindo da OpenDota não é sobrescrito.** As duas fontes nomeiam a mesma equipe de
  formas diferentes, e trocar o nome faria a tela de partidas mostrar um rótulo e o ranking
  outro, para a mesma linha. A wiki entra com o que a OpenDota não tem.
- **`ativa` é anulável de propósito.** `NULL` significa "a wiki nunca falou desta equipe";
  `False` significa "a wiki diz que foi dissolvida". Colapsar os dois em `False` afirmaria
  algo que ninguém verificou sobre 42 equipes.
- **Data parcial vira `NULL`.** A wiki aceita `2014-??-??` — o editor sabia o ano e não o
  dia. Completar o `??` com `01` inventaria precisão que a fonte não tem.

#### Um defeito que isto expôs

Reprocessar a agenda com `--from-raw` passou a estourar
`CardinalityViolation: ON CONFLICT DO UPDATE command cannot affect row a second time`. A
causa não era o código novo: desde que o **agendador** passou a coletar a agenda de hora em
hora, `ler_ultima_coleta` devolve vários payloads da mesma janela, e o mesmo confronto
aparece em mais de um com o mesmo `id_externo`. O Postgres recusa duas linhas com a mesma
chave no mesmo `INSERT ... ON CONFLICT`. `load_liquipedia.py` agora deduplica por
`id_externo` antes do upsert, ficando com a leitura mais recente.

#### O que ficou de fora, e por quê

O **tier do torneio** seria o complemento natural — é a informação que diria quais das
nossas 100 partidas são de fato de alto nível (a OpenDota rotula todas como
`professional`, o que não discrimina nada: as ligas coletadas são qualificatórias e eventos
regionais). Mas as páginas de torneio da Liquipedia usam subpáginas (`BLAST/Slam/8/Europe`)
e `action=opensearch` não resolve o nome que a OpenDota nos dá — buscar "BLAST Slam VII"
devolve lista vazia. Resolver isso exige um mapeamento de nomes que é exatamente o tipo de
casamento difuso que este projeto recusa em outros lugares. Fica registrado como próximo
passo, não como algo meio-feito.

### Fase 12 — As 73 wikis da Liquipedia

A Liquipedia mantém uma wiki por jogo, cada uma com a sua API MediaWiki. O projeto usava
uma: `dota2`. Esta fase abre as outras.

#### O registro saiu de uma varredura, não de uma lista

Cada wiki foi perguntada sobre as duas coisas que o nosso pipeline consome — se
`Liquipedia:Matches` existe e se `Category:Teams` tem membros — numa requisição por wiki.
O resultado está em `collectors/seeds/liquipedia_wikis.json`:

| situação | quantas | exemplos |
|---|---|---|
| agenda **e** times | 64 | dota2, counterstrike, valorant, leagueoflegends |
| só times | 7 | fighters, starcraft2, smash, starcraft, fortnite, formula1, brawlhalla |
| só agenda | 2 | sideswipe, wildcard |
| nenhum dos dois | 1 | illuvium — fica de fora |

Os sete "só times" têm uma explicação comum: são **competições individuais**. Em Smash,
StarCraft, Fighting Games e Formula 1 quem se enfrenta é pessoa, não equipe, e a wiki
organiza o calendário de outro jeito. A ausência da página não é falha da varredura — é o
formato do esporte aparecendo no esquema. Há um teste que falha se algum deles passar a ter
agenda, avisando que o registro precisa ser regerado.

Ficam de fora `commons`, `hub`, `lab`, `esports` e `dota2gamearchive`: são wikis meta,
internas ou de arquivo. Entrariam em `dim_jogo` e apareceriam num seletor de jogos
prometendo uma tela que nunca teria dado.

```powershell
.\.venv\Scripts\python.exe cli.py seed-jogos                              # 73 linhas em dim_jogo
.\.venv\Scripts\python.exe cli.py collect liquipedia --wiki counterstrike
.\.venv\Scripts\python.exe cli.py collect liquipedia-times --wiki valorant
```

#### A armadilha que quase passou: `teamid` só existe no Dota

A [Fase 11](#fase-11--equipes-pela-api-mediawiki-da-liquipedia) ligou equipe e partida pelo
`|teamid=` do infobox, que é o mesmo número que a OpenDota publica. Ao abrir as outras
wikis, medi o mesmo infobox em counterstrike, valorant, leagueoflegends e rocketleague:

```
counterstrike:  100 Thieves   campos: name, region, location, created, disbanded
valorant:       100 Thieves   campos: name, region, location
```

**Não há `teamid` fora do Dota.** O parser da Fase 11 exigia esse campo, então teria
descartado 100% das equipes das outras 70 wikis — e **em silêncio**: o coletor reportaria
"0 equipes" e nada pareceria quebrado.

A identidade passou a ter duas formas, decididas pela fonte:

- **com `teamid`** (Dota 2): o número, que mantém o vínculo com as partidas da OpenDota;
- **sem `teamid`** (as outras 70): o **título da página**, que a MediaWiki garante único por
  wiki e é para onde os links da agenda apontam.

Não é improviso — é usar o identificador que cada fonte de fato publica. Improviso seria
inventar um id nosso e perder o vínculo com o link. A migration `0008` alargou
`dim_equipe.id_externo` de 32 para 200 caracteres, porque título de página não cabe em 32,
e `dim_jogo.codigo` de 16 para 32 (`leagueoflegends` tem 15 — passava raspando).

#### Resultado medido

| jogo | equipes | agenda | confrontos com as duas equipes |
|---|---|---|---|
| dota2 | 675 | 90 | 52 (58%) |
| counterstrike | **1.409** | 54 | **44 (81%)** |
| valorant | 0 | 72 | 0 |

O Counter-Strike casa melhor que o Dota, e o motivo é instrutivo: a dimensão dele veio
inteira da mesma fonte que a agenda, então os nomes coincidem. No Dota a dimensão é mistura
de OpenDota e Liquipedia, e a diferença de grafia entre as duas cobra o seu preço.

#### O que 73 jogos **não** significa

`dim_jogo` tem 73 linhas, mas **só o Dota 2 tem partidas no star schema**
(`dim_partida`/`fato_partida_jogador`). A coleta de resultado JOGADOR A JOGADOR vem da
OpenDota, que é específica de Dota — as outras 72 wikis entram com agenda e equipes, não
com esse nível de detalhe. As telas de Partidas, Heróis e Jogadores continuam vazias para
elas, e isso é o estado correto, não um bug.

(A Fase 13 abre uma trilha diferente — `agenda_partida` com vencedor e placar, também da
Liquipedia — que basta para o Bradley-Terry da Previsão de Confronto, mas não é o star
schema completo: não tem GPM, XPM, KDA nem qualquer dado por jogador.)

Por isso `GET /api/partidas/jogos` ganhou `apenas_com_dados`, ligado por padrão: devolver as
73 faria o seletor de jogo listar 73 opções, a maioria levando a telas vazias — ele
viraria uma lista de promessas. O endpoint também passou a devolver `equipes` e `agenda`
junto de `partidas`, porque um jogo com 1.409 equipes e 54 confrontos agendados não está
vazio; está esperando outra fonte.

#### Custo e cortesia com a fonte

| varredura | chamadas | tempo |
|---|---|---|
| agenda de todas as wikis | 66 (uma por wiki) | ~3,5 min |
| equipes de **uma** wiki | 3 a 30 (lotes de 50 títulos) | 67 s (dota2, 962) a 97 s (counterstrike, 1.410) |
| equipes das 71 | ~2.000 | passaria de 1h30 |

A última linha é o motivo de o agendador fazer **rodízio** nas equipes em vez de varredura
completa: `AGENDADOR_EQUIPES_POR_RODADA` (padrão 10) pega as próximas N a cada rodada
diária e volta ao início. Uma varredura completa leva cerca de uma semana — rápido para um
dado que muda em meses, e educado com um serviço público e gratuito. A agenda, por ser uma
chamada por wiki, é varrida inteira a cada rodada.

Uma wiki fora do ar não derruba a varredura: cada uma roda dentro do seu `try`, e o
resultado agregado é sucesso se **alguma** respondeu. Exigir todas faria uma wiki dormente
reagendar a varredura inteira para cinco minutos depois.

#### O que a Fase 12 quebrou, e o conserto

Abrir 73 jogos expôs três defeitos que só existiam porque o projeto era de um jogo só.

**O chip do jogo era desabilitado por `partidas === 0`.** Counter-Strike tem 1.409 equipes
e 54 confrontos agendados, e zero partidas coletadas — o chip aparecia inerte e não havia
como abrir a agenda que existe. Era literalmente impossível selecionar o jogo. Hoje "vazio"
significa vazio em todas as fontes, e o `title` do chip diz o que cada jogo tem.

**O artefato do modelo de confronto era um arquivo só.** `carregar_relatorio()` lia
`metricas_confronto.json` sem olhar de qual jogo ele era, então
`/api/ml/confronto/relatorio?jogo=counterstrike` devolvia o relatório do Dota 2 — com
`"jogo": "dota2"` dentro do corpo da resposta. Número certo respondendo a pergunta errada,
que é o pior tipo de erro num projeto sobre integridade de dado. Agora é
`metricas_confronto_<jogo>.json`, e um jogo sem ajuste responde 503 explicando o que falta.

**A tela de confronto ignorava o jogo selecionado** — nenhum dos cinco hooks enviava
`jogo`, embora a API sempre tenha aceitado o parâmetro. E, como a página inteira vivia
dentro de um `<Consulta estado={relatorio}>`, um jogo sem modelo não mostrava nada: nem o
calendário, que vem de outra fonte e funciona. Agora a ausência do modelo esconde só o que
depende dele (ranking de força, confronto hipotético, campeonatos); a agenda continua na
tela, com os cards marcados **sem modelo para este jogo** em vez do enganoso "sem histórico
coletado" — porque ali não falta o histórico *daquele time*, falta o ajuste do jogo inteiro.

O endpoint `/agenda` deixou de exigir relatório pelo mesmo motivo: o calendário existe para
os 66 jogos com agenda, o ajuste só para os que têm partidas com resultado.

### Fase 13 — Previsão de confronto para os outros 72 jogos

A Fase 12 abriu as 73 wikis, mas só resolveu agenda e equipes. A previsão continuava
Dota-only: `ml/confronto.py` só sabia ler `dim_partida`/`fato_partida_jogador`, que é
star schema da OpenDota — e a OpenDota só cobre Dota 2. Selecionar Counter-Strike na tela
mostrava o calendário certo (Fase 12 já resolvia isso) e nenhuma previsão.

#### A fonte já estava ali, sendo descartada

`Liquipedia:Matches` não é uma agenda pura — é um **ticker**. Medido em counterstrike: de
57 blocos numa consulta, 42 já tinham vencedor marcado. O parser da Fase 10 já capturava
qualquer bloco com horário válido, passado ou futuro (nunca filtrou por tempo) — só não
lia a parte do resultado, porque na época só a agenda importava.

O markup do vencedor é explícito, não precisa ser inferido do placar:

```html
<div class="match-info-header-opponent match-info-header-opponent-left match-info-header-winner">
  ...3DMAX...
</div>
...
<div class="match-info-header-opponent match-info-header-loser">...HOTU...</div>
```

`etl/transform_liquipedia.py` ganhou `_vencedor()` (lê a classe `match-info-header-winner`
no bloco do adversário — nenhum marcado ou os dois marcados viram `None`, nunca um chute) e
`_placar()`. Três colunas novas em `agenda_partida` (migration `0009`): `vitoria_a`,
`placar_a`, `placar_b`, todas nulas até o confronto acontecer.

#### Duas fontes de confronto, uma por jogo

`ml/confronto.py::_carregar_confrontos` bifurca por `jogo`: Dota 2 continua na OpenDota
(mais rica — dá GPM/XPM/KDA por time); todo outro jogo lê `agenda_partida` filtrando
`vitoria_a IS NOT NULL`. O Bradley-Terry não vê diferença — só precisa de quem venceu. O
que muda é o "por quê": para os outros jogos, `gpm_medio`/`xpm_medio`/`kda_medio` ficam
`None` (a Liquipedia dá o placar final, não telemetria por jogador), e a tela já tratava
isso como travessão — nenhuma mudança de schema foi necessária ali.

Uma consequência não óbvia: sem stats de jogador, `Equipe.partidas` não tinha de onde vir
para os jogos novos. A contagem para Dota sai como efeito colateral do laço que soma
GPM/XPM (`_carregar_equipes`); sem esse laço, toda equipe ficaria com `partidas=0` — e
`estado()` descarta equipe com `partidas=0` (`if equipe.partidas`), o que zeraria o
ranking inteiro mesmo com confrontos reais no banco. `_preencher_partidas_liquipedia`
conta as duas pontas (`id_equipe_a`, `id_equipe_b`) direto de `agenda_partida`.

#### Backfill sem rede

O ticker só guarda uma janela de ~5-9 dias — mas o projeto grava o payload bruto de toda
coleta. Uma partida "sem resultado" numa coleta de manhã pode aparecer "decidida" numa de
tarde. Reprocessar os arquivos em `data/raw/liquipedia/matches-*/` em ordem cronológica (é
a ordem que `RawStorage.ler()` já devolve) e deixar o upsert atualizar cada linha recuperou
**1.195 linhas em 24 arquivos, sem chamar a API** — puro reaproveitamento do raw-first.

#### Resultado medido: primeira previsão real fora do Dota

```powershell
.\.venv\Scripts\python.exe cli.py train-confronto --jogo counterstrike
```

```
34 confrontos entre 31 equipes (C=0.08, escolhido por CV no treino)
vantagem do lado A: +0.1176 log-odds = 52.9% entre times de forca igual

validacao walk-forward em 6 partidas:
  acuracia 50.0% +/- 40.0%  (taxa base 33.3%)

forcas mais altas:
  Imperial Esports    +0.112  4/6 (67%)
  MOUZ                +0.110  3/3 (100%)
  3DMAX               +0.105  3/4 (75%)
  Team Vitality       +0.080  3/4 (75%)
  Team Spirit         +0.074  2/2 (100%)
```

O ranking reconhece times reais do circuito (MOUZ, Vitality, Spirit, G2) — um sinal de que
a reconciliação de nomes (Fase 10) e o Bradley-Terry estão produzindo algo sensato, não só
rodando sem erro. Pela API, `/api/ml/confronto/agenda?jogo=counterstrike` devolveu
previsão real para partidas reais: Team Falcons 52,7% × G2 Esports 47,3%; FURIA 51,8% ×
Team Vitality 48,2%. A validação com 6 partidas de teste é honesta sobre ser pouca amostra
— mesmo espírito da validação de Dota, que também não esconde a incerteza.

#### Um efeito colateral sério: rate limit da própria Liquipedia

Escrever esta fase expôs um bug de pacing que já existia desde a Fase 12 e piorou tudo: os
laços que varrem várias wikis (`_coletar_liquipedia`, `_coletar_equipes` em `agendador.py`)
criam um `LiquipediaCollector`/`LiquipediaWikiCollector` **novo a cada wiki**, e cada um
constrói o próprio `RateLimitedClient` do zero. O intervalo mínimo entre chamadas
(`liquipedia_rate_limit_seconds`) só vale *dentro* de uma instância — nunca *entre* wikis
do mesmo laço. Sem throttle nenhum, uma varredura de 66 wikis saía a ~1 chamada/segundo, e
foi exatamente isso que aconteceu: a Liquipedia bloqueou o IP com **HTTP 429 por mais de
uma hora**, visível nos logs do agendador em toda tentativa subsequente — inclusive nas do
rodízio de equipes, que é o que ainda falta rodar para popular `dim_equipe` de VALORANT,
Chess e os demais.

A correção foi um `time.sleep(settings.liquipedia_rate_limit_seconds)` explícito entre
iterações dos dois laços — não resolve um bloqueio já em curso (isso só passa com o tempo,
fora do nosso controle), mas impede o agendador de piorá-lo a cada rodada. Dado que o
rodízio já cobre `AGENDADOR_EQUIPES_POR_RODADA` wikis por dia, os demais jogos do catálogo
devem ganhar `dim_equipe` — e portanto previsão — ao longo dos próximos dias, sem
intervenção manual.

#### Dois defeitos de tela que só apareciam fora do Dota

Testar a Previsão de Confronto para Counter-Strike no navegador revelou dois bugs que a
tela nunca tinha exercitado, porque nunca tinha existido um segundo jogo com modelo:

- **"Lado A (Radiant)" / "Lado B (Dire)" apareciam em toda previsão**, inclusive de
  Counter-Strike — nomenclatura que só existe no mapa de Dota. Virou
  `rotuloDoLado(jogo, lado)`: o parêntese só aparece quando `jogo === "dota2"`.
- **O modal de um confronto do kanban podia travar no esqueleto de carregamento para
  sempre.** O ranking é filtrado por `min_partidas` (padrão 3); um card pode envolver um
  time com menos partidas que isso — ele tem previsão (`/agenda` só exige `partidas > 0`),
  mas não está no array `equipes` filtrado. O efeito que escolhe um par padrão via
  `useEffect` desfazia a seleção do clique no mesmo ciclo, porque validava contra esse
  array filtrado. A correção foi uma guarda (`if (aberto) return`): uma seleção explícita
  do kanban vence o par padrão, que só se aplica quando nada foi escolhido ainda.

### Fase 14 — Fechando as lacunas de previsão fora do Dota

A Fase 13 entregou a previsão para os outros jogos e terminou com uma aposta: *"os demais
jogos do catálogo devem ganhar `dim_equipe` — e portanto previsão — ao longo dos próximos
dias, sem intervenção manual"*, via o rodízio de equipes. Na prática não fechou. O relato do
usuário foi direto: **"tem muitos jogos que já tiveram 100% antes de confronto só que ainda
o sistema não consegue trazer"** — partidas decididas, times conhecidos, e nenhuma previsão.

#### Medição: o buraco tinha 11 jogos de largura

```
== agenda_partida: fk / decididos / treináveis (antes) ==
  counterstrike  decididos=111  treináveis=59
  dota2          decididos= 55  treináveis=37
  valorant       decididos= 50  treináveis= 0   ← 50 partidas decididas, zero treináveis
  brawlstars     decididos= 50  treináveis= 0
  callofduty     decididos= 50  treináveis= 0
  clashroyale    decididos= 50  treináveis= 0
  clashofclans   decididos= 50  treináveis= 0
  chess          decididos= 37  treináveis= 0
  … (mais 5 assim)
```

A causa: `dim_equipe` estava **vazia** para todos esses jogos (só counterstrike e dota2
tinham equipes — o rodízio de `liquipedia-times` roda 10 wikis/dia e não tinha chegado nas
outras). E `etl/load_liquipedia.py::carregar` só **casava** nome de agenda com equipe
_já existente_: sem `dim_equipe`, todo `id_equipe_a`/`id_equipe_b` ficava nulo, e
`_carregar_confrontos_liquipedia` filtra `id_equipe_a IS NOT NULL` — as 50 partidas
decididas de VALORANT eram invisíveis ao Bradley-Terry.

#### Correção 1 (estrutural): a agenda passa a criar a equipe que falta

Fora do Dota 2, a identidade de uma equipe na Liquipedia **é** o título da página dela — o
mesmo texto que o ticker e o bracket usam para nomear os lados. Não há reconciliação a
fazer. Então `_garantir_equipes` (`etl/load_liquipedia.py`): o que a escada de casamento
não resolve vira linha nova em `dim_equipe`, com `id_externo = nome = título`. Quando o
`liquipedia-times` finalmente passar naquela wiki, ele casa pela mesma chave
(`uq_equipe_jogo_externo`) e só **acrescenta** região, país e datas — não duplica.

É exatamente o que `load_dota` já fazia: a dimensão ganha o time na primeira vez que ele
aparece, venha do fato (OpenDota) ou da agenda (Liquipedia). O Dota 2 fica de fora da regra
— lá `id_externo` é o `team_id` numérico da OpenDota, e inventar uma linha de chave textual
partiria o histórico do time em dois.

O que continua proibido: casar por similaridade aproximada. Uma previsão confiante sobre a
dupla errada é pior que nenhuma previsão.

#### Correção 2 (fonte mais profunda): coletor de bracket de torneio

O ticker é uma janela de ~5-9 dias. A página de um torneio (`BLAST/Open/2026/Fall`) tem o
**bracket inteiro** — todas as fases. `collectors/liquipedia_bracket_collector.py` e
`etl/transform_liquipedia_bracket.py`:

- **A lista de torneios se autoconstrói.** `torneios_conhecidos(jogo)` roda
  `SELECT DISTINCT agenda_partida.torneio` — sem lista escrita a mão. Um torneio só entra
  depois que o ticker o mencionou ao menos uma vez, e o nome que o ticker gravou **é** o
  título da página do bracket.
- **Parser separado, não reuso.** O bracket usa `div.brkts-match` como raiz, `aria-label`
  para o nome do time e `.brkts-opponent-win` para o vencedor — markup diferente do ticker
  (`div.match-info`). Rodar `parse_agenda()` numa página de torneio devolve zero. Mas a
  função de hash (`_identificador`) é a mesma: se as duas fontes virem a mesma partida, a
  chave bate e o upsert atualiza a linha em vez de duplicar.
- **Rodízio no agendador.** Nova tarefa `brackets` (`AGENDADOR_BRACKETS_MINUTOS`, diário):
  varre `AGENDADOR_BRACKETS_POR_RODADA` wikis por rodada, e para cada uma pede o bracket de
  cada torneio conhecido, com `sleep` entre wikis (mesma disciplina de rate limit da
  Fase 13).

#### Um bug de `--from-raw` no caminho

`cli.py::_cmd_collect`, no ramo `--from-raw`, chamava `_carregador(fonte)(resultado)` sem
`jogo=` — todas as três fontes Liquipedia caíam no padrão `jogo="dota2"` do próprio
`carregar()`. Um `--from-raw --wiki counterstrike` reprocessava os dados certos e gravava
tudo como se fosse Dota 2. Corrigido antes de qualquer backfill real usar o caminho.

#### Resultado medido: de 2 jogos com modelo para 13

Reprocessando o raw histórico do ticker e do bracket pelo loader novo (zero rede) e
retreinando:

```
== treináveis (depois) ==
  valorant     0 → 63        callofduty   0 → 50
  counterstrike 59 → 67      clashroyale  0 → 50
  clashofclans 0 → 50        arenafps     0 → 50
  brawlstars   0 → 50        crossfire    0 → 44
  artifact     0 → 50        chess        0 → 37
                             battlerite   0 → 24
```

Todo confronto decidido fora do Dota agora tem as duas FKs — há um teste que trava se algum
não tiver (`test_partida_decidida_fora_do_dota_nunca_fica_sem_equipe`).

**A honestidade da Fase 13 continua.** Com amostras de 8-15 partidas de teste, a maioria
dos modelos novos ainda não supera a taxa base — `train-confronto` diz isso em voz alta
(`AVISO: a acuracia nao supera a taxa base`). Call of Duty deu 78,6% de acurácia
walk-forward, Battlerite 100% (com 8 partidas — ruído), VALORANT ficou na taxa base. O
sistema agora **produz** previsão para 13 jogos; ela fica boa quando houver histórico, e
diz quando não há. Equipes criadas pela agenda entram sem região/país até o
`liquipedia-times` passar — a previsão não depende desses campos, só o filtro de liga da
tela de ranking.

### Fase 3 — Riot API (LoL)

Próxima fase. O star schema já tem o discriminador (`dim_jogo.codigo`), as rotas de partidas
aceitam `?jogo=`, e o seletor de jogo (`componentes/SeletorDeJogo.tsx`) já lista qualquer
código que a API devolva — hoje Dota 2, VALORANT e Counter-Strike.

**O que isso prova e o que não prova, para ser preciso:** está provado que os endpoints leem
o discriminador, porque é o mesmo código que serve Dota 2 hoje. **Não** está provado que
"as mesmas telas passam a servir LoL sem mudança de código" — isso só se sabe quando houver
uma linha de LoL no banco, e hoje há zero. As entidades do LoL não são as do Dota (não há
Radiant/Dire, e o equivalente de "herói" tem outra estrutura de atributos), então a
expectativa honesta é de *alguma* mudança, não de nenhuma. Selecionar LoL nos chips hoje
mostra telas vazias — que é o comportamento correto para um domínio sem dado, mas não é
evidência de portabilidade.

## Ingestão periódica

Até a Fase 10 a coleta só acontecia quando alguém digitava `cli.py collect`. O efeito disso
estava medido no próprio banco: **3 janelas de coleta da Steam cobrindo 16 horas**, com dois
snapshots por jogo. Um `fato_snapshot_jogo_steam` desenhado para série temporal, com uma
série que não existia — e por consequência a ordenação por *trending* desabilitada, o KPI
"vs. coleta anterior" em travessão e a tela de detalhe dizendo *"só existe uma coleta até
agora"*.

O serviço `agendador` (`agendador.py`, no `docker-compose.yml`) resolve isso:

| Fonte | Intervalo | Por quê |
|---|---|---|
| Steam | 60 min | acompanha `SNAPSHOT_BUCKET_MINUTES`: coletar mais rápido cairia na mesma janela e viraria `UPDATE` da linha anterior, não um ponto novo |
| OpenDota | 6 h | partidas terminam ao longo do dia e só são publicadas depois de encerradas; o limite aqui é cortesia com a API pública |
| Liquipedia (ticker) | 12 h | o calendário de campeonato muda em dias, e eles bloqueiam por IP quem abusa |
| Liquipedia (equipes) | 24 h, 10 wikis/rodada | página de equipe muda em meses; uma varredura completa das ~66 wikis leva ~1 semana |
| Liquipedia (brackets) | 24 h, 10 wikis/rodada | bracket de torneio decidido não muda; o que cresce é a lista de torneios conhecidos e as fases de torneios em andamento |

```powershell
docker compose up -d agendador
docker compose logs -f agendador
```

Decisões que valem menção:

- **Serviço separado, não um `APScheduler` dentro da API.** Coleta é trabalho de lote:
  demorada, dependente de rede alheia, e que não deve nada ao ciclo de vida de um servidor
  HTTP. Junto da API, uma coleta longa competiria com o dashboard e um deploy interromperia
  a ingestão.
- **Laço próprio, não `cron` do sistema.** O cron seria menos código, mas viveria fora do
  projeto: não apareceria no compose, não seria versionado junto, e dependeria de
  configuração manual em cada máquina.
- **Ele monitora o que está no banco, não a semente.** O `SteamCollector` sem `app_ids` cai
  na lista fixa de `collectors/seeds/`. Para o agendador isso seria um bug silencioso: todo
  jogo trazido pela busca da tela ficaria com o único snapshot do dia em que entrou, e a
  série dele nunca cresceria — sem nada parecer quebrado. Foi o primeiro defeito que
  apareceu ao subir o serviço: 12 apps coletados com 20 no banco.
- **Uma fonte fora do ar não derruba as outras.** Cada tarefa roda dentro de um `try`, e a
  que falha é reagendada para 5 minutos em vez do intervalo cheio — sem isso, um timeout de
  dez segundos na Liquipedia custaria meio dia de agenda. Isso foi exercitado sem querer na
  primeira execução: a OpenDota respondeu **HTTP 522** (Cloudflare, origem fora do ar,
  confirmado com `curl` direto), a Steam seguiu normal e o laço sobreviveu.
- **Repetir é seguro.** `(app_id, janela_coleta)` é único com a janela truncada por hora, e
  a coleta da OpenDota pula partidas já no banco. Por isso o agendador pode coletar assim
  que sobe (`AGENDADOR_RODAR_AO_INICIAR`) sem que um ciclo de restart suje o dado.
- **O desligamento é limpo entre tarefas, não dentro de uma.** O SIGTERM acorda a espera na
  hora (`Event.wait`, não `sleep`), mas uma coleta em curso vai até o fim. Medido: com os
  10s padrão do Docker, parar durante uma coleta dava **exit 137** (SIGKILL). Daí o
  `stop_grace_period: 180s` — uma passada leva ~3s por jogo monitorado. Se o prazo estourar
  mesmo assim, o dano é zero: os payloads já estão em `data/raw/` e a carga é transacional.

Primeira execução real: **60 payloads, 1.953 linhas carregadas, 60,3 s** para 20 jogos.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Os testes cobrem os parsers/transforms, que são a parte mais frágil do sistema: mudanças de schema
nas APIs externas quebram silenciosamente. As fixtures em `tests/fixtures/` são payloads reais
reduzidos e funcionam como contrato — se a Steam mudar um campo, o teste falha antes de dado sujo
chegar ao banco.

`tests/test_api.py` cobre o outro contrato, o da API com o dashboard: as chaves que cada tela lê,
o intervalo do winrate, o 404 de recurso inexistente. Ele **precisa do Postgres de pé** (as
consultas usam `DISTINCT ON`, `unnest` e `percentile_cont`, que não existem no SQLite — testar
contra outro banco testaria outro SQL). Sem banco disponível, o módulo é pulado, não falha.

O frontend é verificado pelo compilador:

```powershell
cd dashboard
npm run lint         # tsc -b --noEmit
```

**Use `npm run lint`, não `npx tsc --noEmit`.** O `tsconfig.json` da raiz é do tipo
*solution* (`"files": []` mais `references`), e nesse formato `tsc --noEmit` não verifica
nada — sai com código 0 sem olhar um arquivo. É um no-op que parece um teste passando. O
`-b` (build mode) é o que segue as referências e checa `src/` de verdade; o
`npm run build` do Docker já usa `tsc -b`, então o erro aparece no build mesmo quando o
comando manual mente.

## Estrutura

```
gaming-analytics/
├── collectors/          # um módulo por fonte, interface comum em base.py
│   ├── base.py          # BaseCollector, RawRecord, CollectionResult
│   ├── http_client.py   # rate limiting + backoff exponencial
│   ├── seeds/           # semente da Steam e o registro das 73 wikis da Liquipedia
│   ├── steam_collector.py
│   ├── steam_loja.py    # consulta pontual a loja, sem gravar nada
│   └── liquipedia_wiki_collector.py
├── etl/
│   ├── raw_storage.py   # grava/relê os payloads brutos
│   ├── transform_*.py   # funções puras: payload → modelo validado
│   └── load_*.py        # upserts idempotentes
├── db/
│   ├── models.py        # SQLAlchemy
│   ├── migrations/      # Alembic (fonte da verdade do schema)
│   └── schema.sql       # referência de leitura
├── api/                 # FastAPI
│   ├── main.py          # app, CORS e montagem dos routers
│   ├── schemas.py       # contrato de resposta (Pydantic)
│   └── routers/         # meta, steam, catalogo, dota, sentimento, confronto, assistente
├── dashboard/           # frontend React (Vite + TypeScript)
│   ├── src/api/         # cliente HTTP, tipos e hooks de consulta
│   ├── src/componentes/ # blocos de UI e os gráficos
│   ├── src/paginas/     # uma tela por rota
│   ├── src/tema.ts      # a paleta, em hex resolvido (o painel é escuro e só escuro)
│   ├── Dockerfile       # build + nginx
│   └── nginx.conf       # fallback de SPA e proxy para a API
├── ml/                  # sentimento (Fase 7), confronto (Fase 9), assistente (Fase 8)
├── tests/
├── agendador.py         # laço de ingestão periódica (serviço do compose)
├── cli.py               # init-db, seed-jogos, collect, stats, train-sentimento, train-confronto
└── docker-compose.yml
```

## Configuração

Todas as variáveis estão documentadas em `.env.example`. As mais relevantes:

| Variável | Padrão | Para quê |
|---|---|---|
| `POSTGRES_PORT` | `55432` | porta publicada pelo compose |
| `STEAM_STORE_RATE_LIMIT_SECONDS` | `1.5` | intervalo mínimo entre chamadas à store |
| `SNAPSHOT_BUCKET_MINUTES` | `60` | janela de deduplicação dos snapshots |
| `LOG_FORMAT` | `json` | `json` para ingestão, `text` para desenvolvimento |
| `CORS_ORIGINS` | `localhost:5173,4173` | origens liberadas para o dashboard em desenvolvimento |
| `AGENDADOR_STEAM_MINUTOS` | `60` | intervalo da coleta automática da Steam (acompanha a janela do snapshot) |
| `AGENDADOR_OPENDOTA_MINUTOS` | `360` | intervalo da coleta automática de partidas |
| `AGENDADOR_LIQUIPEDIA_MINUTOS` | `720` | intervalo da leitura da agenda futura |
| `AGENDADOR_EQUIPES_MINUTOS` | `1440` | intervalo da leitura das páginas de equipe da wiki |
| `AGENDADOR_EQUIPES_POR_RODADA` | `10` | quantas wikis por rodada (as 71 juntas passariam de 1h30) |
| `DASHBOARD_PORT` | `3000` | porta publicada pelo dashboard no compose |
| `RIOT_API_KEY` | — | Fase 3 (LoL) |
