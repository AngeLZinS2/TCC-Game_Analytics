"""Verificacao de ID token do Firebase Authentication.

O backend nunca ve senha nenhuma - quem autentica e-mail/senha e cria a conta
e o Firebase, no navegador. O que chega aqui e um JWT assinado (RS256) que o
SDK do Firebase anexa em cada requisicao; verificar a assinatura contra o JWKS
publico do Google (`PyJWKClient`, com cache proprio) e suficiente pra confiar
no `sub` (uid) e no `email` sem precisar do pacote `firebase-admin` nem de uma
service account no servidor.

Referencia do formato do token:
https://firebase.google.com/docs/auth/admin/verify-id-tokens
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

_JWKS_URL = (
    "https://www.googleapis.com/service_accounts/v1/jwk/"
    "securetoken@system.gserviceaccount.com"
)


class TokenInvalido(Exception):
    """Token ausente, expirado, mal assinado ou de outro projeto Firebase."""


@lru_cache(maxsize=1)
def _cliente_jwks(lifespan_segundos: int) -> PyJWKClient:
    return PyJWKClient(_JWKS_URL, cache_keys=True, lifespan=lifespan_segundos)


def verificar_token_firebase(
    token: str, project_id: str, cache_segundos: int = 3600
) -> dict[str, Any]:
    """Verifica assinatura, emissor e audiencia; devolve as claims do token.

    `sub` e o uid estavel da conta; `email`/`name` sao os que o Firebase
    carimbou no token na hora do login (podem faltar se a conta nao tiver).
    """
    try:
        chave = _cliente_jwks(cache_segundos).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            chave.key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"https://securetoken.google.com/{project_id}",
        )
    except Exception as exc:  # noqa: BLE001 - qualquer falha de verificacao vira 401
        raise TokenInvalido(f"{type(exc).__name__}: {exc}") from exc

    if not claims.get("sub"):
        raise TokenInvalido("token sem 'sub'")

    return claims
