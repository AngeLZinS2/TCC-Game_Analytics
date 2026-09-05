"""O que cada esporte mede, e como esse numero se le.

Um MOBA e um tatico nao compartilham estatistica. Dota fala de ouro e
experiencia por minuto porque a economia do mapa e o eixo do jogo; Valorant e
Counter-Strike falam de taxa de headshot e dano por round porque a mira e a
troca de tiro sao o eixo; League fala de taxa de banimento e de rota, que nao
existem nos outros dois. A tela de personagens tinha "KDA / GPM / XPM" escrito
nas colunas, e mostrar isso para um agente de Valorant seria pedir um numero
que o jogo nao produz.

Este modulo e a resposta: cada jogo declara o substantivo dos seus personagens
e a lista de metricas que publica. A tela desenha a partir daqui em vez de
carregar coluna fixa, e um esporte novo entra sem mexer no componente.

**A ausencia tambem esta declarada.** Counter-Strike nao aparece com metricas
porque nao ha fonte que as entregue neste projeto - e isso e diferente de
aparecer com zeros. `perfil()` devolve um perfil sem metricas, e a tela diz que
falta a coleta, nao que o valor e zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Metrica:
    """Uma coluna de estatistica: a chave no dado e como ela se apresenta."""

    #: A chave dentro de `fato_estatistica_personagem.metricas` (ou o campo
    #: correspondente em `ResumoPersonagem`, para Dota).
    chave: str
    #: O nome que o publico do esporte usa. "HS%", nao "taxa_de_headshot".
    rotulo: str
    #: O que o numero significa, para quem nao joga esse esporte.
    descricao: str
    unidade: str = ""
    casas: int = 1
    #: `True` quando MAIOR e melhor. Nem toda metrica e assim - "mortes por
    #: partida" ordena ao contrario -, e a tela usa isso para colorir.
    maior_melhor: bool = True


@dataclass(frozen=True)
class PerfilEsporte:
    """Como um esporte nomeia e mede seus personagens."""

    #: Singular e plural, para a tela nao dizer "heroi" num jogo de agentes.
    substantivo: str
    substantivo_plural: str
    metricas: list[Metrica] = field(default_factory=list)
    #: De onde os numeros vem. Vazio quando nao ha fonte - e a tela diz isso.
    fonte: str = ""
    #: Aviso obrigatorio quando a fonte nao e nossa medicao.
    nota_fonte: str = ""
    #: `True` quando a API reordena de verdade por `ordenar_por`.
    #:
    #: So o caminho por `fato_partida_jogador` reagrega no banco a cada
    #: ordenacao. O agregado ja vem pronto da fonte e sai por volume; a tela
    #: precisa saber disso para nao oferecer um botao que nao faz nada.
    ordenavel: bool = False


_KDA = Metrica(
    chave="kda",
    rotulo="KDA",
    descricao="Abates mais assistências, dividido por mortes",
    casas=2,
)

VOCABULARIO: dict[str, PerfilEsporte] = {
    "dota2": PerfilEsporte(
        substantivo="herói",
        substantivo_plural="heróis",
        fonte="OpenDota",
        nota_fonte="Medido por nós a partir das partidas que coletamos.",
        ordenavel=True,
        metricas=[
            _KDA,
            Metrica(
                chave="kills_media",
                rotulo="Abates",
                descricao="Média de abates por partida",
                casas=1,
            ),
            Metrica(
                chave="deaths_media",
                rotulo="Mortes",
                descricao="Média de mortes por partida",
                casas=1,
                maior_melhor=False,
            ),
            Metrica(
                chave="economia_por_minuto_media",
                rotulo="GPM",
                descricao="Ouro por minuto — o ritmo de economia do herói",
                casas=0,
            ),
            Metrica(
                chave="experiencia_por_minuto_media",
                rotulo="XPM",
                descricao="Experiência por minuto — o ritmo de nível",
                casas=0,
            ),
        ],
    ),
    "valorant": PerfilEsporte(
        substantivo="agente",
        substantivo_plural="agentes",
        fonte="OP.GG",
        nota_fonte=(
            "Do público geral do OP.GG, em partidas com classificação — não é "
            "medição nossa nem do cenário profissional."
        ),
        metricas=[
            Metrica(
                chave="hs",
                rotulo="HS%",
                descricao=(
                    "Proporção de tiros que acertaram a cabeça — a métrica de "
                    "mira do gênero tático"
                ),
                unidade="%",
            ),
            Metrica(
                chave="adr",
                rotulo="ADR",
                descricao="Dano médio por round",
                casas=0,
            ),
            Metrica(
                chave="acs",
                rotulo="ACS",
                descricao="Pontuação de combate média por round",
                casas=0,
            ),
            _KDA,
            Metrica(
                chave="entrada",
                rotulo="1ª morte a favor",
                descricao=(
                    "Duelos de abertura vencidos: primeiros abates sobre "
                    "primeiros abates mais primeiras mortes"
                ),
                unidade="%",
            ),
            Metrica(
                chave="spike",
                rotulo="Spike/round",
                descricao="Plantas mais desarmes por round — jogo de objetivo",
                casas=3,
            ),
        ],
    ),
    # Declarados sem metrica DE PROPOSITO: os personagens existem (ou nem isso),
    # mas nenhuma fonte deste projeto publica estatistica por personagem deles.
    # Um perfil vazio faz a tela dizer o que falta; a ausencia do jogo aqui a
    # faria cair no default de MOBA e pedir GPM de um jogo sem ouro.
    "counterstrike": PerfilEsporte(
        substantivo="agente",
        substantivo_plural="agentes",
    ),
    "leagueoflegends": PerfilEsporte(
        substantivo="campeão",
        substantivo_plural="campeões",
    ),
}

#: Para todo jogo que nao declarou perfil. Sem metrica: chutar as do Dota faria
#: a tela pedir ouro por minuto de um jogo de cartas.
PADRAO = PerfilEsporte(substantivo="personagem", substantivo_plural="personagens")


def perfil(jogo: str) -> PerfilEsporte:
    return VOCABULARIO.get(jogo, PADRAO)
