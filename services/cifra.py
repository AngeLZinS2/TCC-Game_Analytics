"""Cifra simetrica (Fernet) para segredo que o backend precisa LER de volta.

Diferente de senha (que so se compara por hash, nunca se le), a chave de IA
da propria conta (`dim_usuario.openrouter_api_key_cifrada`) precisa voltar a
texto puro na hora de montar o header `Authorization` da chamada ao
OpenRouter - por isso cifra, nao hash. `CHAVE_CIFRA_SECRETS` e o segredo
mestre: perde-lo torna toda chave ja guardada irrecuperavel (a pessoa
cadastra de novo), mas nunca expoe as chaves de ninguem se o banco vazar
sozinho.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from config import get_settings


class CifraIndisponivel(RuntimeError):
    """CHAVE_CIFRA_SECRETS nao configurada."""


@lru_cache(maxsize=1)
def _fernet(chave: str) -> Fernet:
    return Fernet(chave.encode())


def _cliente() -> Fernet:
    chave = get_settings().chave_cifra_secrets
    if not chave:
        raise CifraIndisponivel(
            "CHAVE_CIFRA_SECRETS nao configurada - gere uma com "
            "Fernet.generate_key() e defina no .env."
        )
    return _fernet(chave)


def cifrar(texto: str) -> str:
    return _cliente().encrypt(texto.encode()).decode()


def decifrar(texto_cifrado: str) -> str | None:
    """`None` quando o valor nao decifra (chave mestra trocada, dado
    corrompido) - melhor esforco: cai pro comportamento de "sem chave
    propria" em vez de derrubar a requisicao."""
    try:
        return _cliente().decrypt(texto_cifrado.encode()).decode()
    except InvalidToken:
        return None


def mascarar(texto: str) -> str:
    """Os ultimos 4 caracteres, pra confirmar visualmente qual chave esta
    cadastrada sem nunca reexibir o valor inteiro."""
    if len(texto) <= 4:
        return "••••"
    return f"••••{texto[-4:]}"
