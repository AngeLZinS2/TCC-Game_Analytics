"""O que os modelos do projeto compartilham.

Este modulo ja foi o catalogo das tres familias que disputavam a previsao por
minuto - linear, bagging e boosting. Aquele comparativo saiu do projeto junto
das telas que o mostravam, e com ele o `CATALOGO`, a `Definicao` e o
`por_chave`, que nao tinham mais quem os chamasse.

Sobrou a semente, e ela sobrou por um motivo que nao depende de nenhum modelo em
particular: os dois treinos que restaram (`ml/sentimento.py` e `ml/confronto.py`)
precisam usar a MESMA, senao "semente fixa" vira uma frase sem consequencia.
Cada modulo tem seu proprio catalogo de modelos, porque as familias que fazem
sentido para texto nao sao as que fazem sentido para confronto entre equipes -
mas a reprodutibilidade e uma so.
"""

from __future__ import annotations

#: Semente unica do projeto. Com ela o treino e reproduzivel - a monografia pode
#: citar um numero e alguem consegue chegar nele de novo.
SEMENTE = 42
