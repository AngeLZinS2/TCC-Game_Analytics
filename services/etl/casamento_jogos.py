"""Casa o MESMO jogo entre catalogos de lojas diferentes, pelo nome.

Existe para o cruzamento Xbox -> Steam do "Resumo por IA": a Xbox Store nao
publica texto de avaliacao (so nota agregada - ver `xbox_collector.py`), mas
um jogo multiplataforma como "Grand Theft Auto V" pode ja ter resumo pronto
do lado Steam. O problema e que a mesma franquia quase nunca tem o MESMO
texto nas duas lojas: "Grand Theft Auto V Enhanced (PC)" (Xbox) vs
"Grand Theft Auto V" (Steam) - sem normalizar, nenhum cruzamento bateria.

Funcao pura sobre string: nada de rede, nada de banco.
"""

from __future__ import annotations

import re
import unicodedata

#: Preciso tirar antes do NFKD: ele decompoe "™"/"®" em letras ("TM"/"R"),
#: que sobreviveriam grudadas na palavra de trocadilho ("horizon5tm").
_MARCA = re.compile(r"[™®©]")
_PARENTESES = re.compile(r"\([^)]*\)|\[[^\]]*\]")

#: Sufixos de edicao/plataforma que uma loja acrescenta e a outra nao. Remover
#: os DEPOIS dos parenteses pega o que vem sem parenteses tambem
#: ("... Definitive Edition").
_EDICOES = re.compile(
    r"(?i)\b("
    r"enhanced|remastered|remake|definitive|game of the year|goty|premium|"
    r"deluxe|ultimate|complete|standard|gold|legendary|anniversary|special|"
    r"director'?s cut|edition"
    r")\b"
)
_PONTUACAO = re.compile(r"[:\-–—'\",.!?]")
_ESPACOS = re.compile(r"\s+")


def normalizar_titulo(nome: str) -> str:
    """Reduz um titulo ao "nome nu" - sem edicao, plataforma, pontuacao ou
    acento - pra comparar a mesma franquia entre Xbox e Steam.

    So compara IGUAL apos normalizar (nunca por substring/token): um match
    parcial arriscaria colar o resumo de um jogo errado no outro - pior que
    nao ter cruzamento nenhum.
    """
    if not nome:
        return ""
    texto = _MARCA.sub(" ", nome)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = _PARENTESES.sub(" ", texto)
    texto = _EDICOES.sub(" ", texto)
    texto = _PONTUACAO.sub(" ", texto)
    texto = _ESPACOS.sub(" ", texto).strip().lower()
    return texto
