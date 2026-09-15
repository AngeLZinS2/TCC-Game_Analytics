"""Contrato da verificacao de ID token do Firebase - sobretudo a tolerancia
de relogio (`leeway`), adicionada por um bug visto ao vivo: o container do
Docker Desktop/WSL2 as vezes atrasa alguns segundos depois do host dormir, e
um token recem-emitido (`iat` = agora) chega "no futuro" pro relogio do
container - `ImmatureSignatureError` sem essa tolerancia (Fase 35).

Sem chave real do Firebase pra assinar um token de teste, a verificacao usa
um par de chaves RSA proprio: `_cliente_jwks` e trocado por um dublê que
devolve a chave publica de teste, e o token e assinado com a privada
correspondente - o mesmo golpe de dublê que `test_usuario.py` usa pra nao
depender de um ID token real.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from services import autenticacao
from services.autenticacao import TokenInvalido, verificar_token_firebase

PROJECT_ID = "playdb-teste"


@pytest.fixture(scope="module")
def par_de_chaves():
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return privada, privada.public_key()


@pytest.fixture
def com_jwks_de_teste(par_de_chaves, monkeypatch: pytest.MonkeyPatch):
    _, publica = par_de_chaves

    class _ChaveFalsa:
        key = publica

    class _ClienteFalso:
        def get_signing_key_from_jwt(self, token: str) -> _ChaveFalsa:
            return _ChaveFalsa()

    monkeypatch.setattr(autenticacao, "_cliente_jwks", lambda *a, **k: _ClienteFalso())


def _token(par_de_chaves, **claims_extra):
    privada, _ = par_de_chaves
    agora = int(time.time())
    claims = {
        "sub": "uid-teste-autenticacao",
        "email": "teste@playdb.local",
        "aud": PROJECT_ID,
        "iss": f"https://securetoken.google.com/{PROJECT_ID}",
        "iat": agora,
        "exp": agora + 3600,
        **claims_extra,
    }
    return jwt.encode(claims, privada, algorithm="RS256")


def test_token_valido_devolve_claims(par_de_chaves, com_jwks_de_teste):
    claims = verificar_token_firebase(_token(par_de_chaves), PROJECT_ID)
    assert claims["sub"] == "uid-teste-autenticacao"


def test_token_com_iat_levemente_no_futuro_ainda_passa(par_de_chaves, com_jwks_de_teste):
    # Relogio do container alguns segundos atras do real - dentro do leeway de 60s.
    agora = int(time.time())
    token = _token(par_de_chaves, iat=agora + 30, exp=agora + 30 + 3600)
    claims = verificar_token_firebase(token, PROJECT_ID)
    assert claims["sub"] == "uid-teste-autenticacao"


def test_token_com_iat_muito_no_futuro_e_rejeitado(par_de_chaves, com_jwks_de_teste):
    agora = int(time.time())
    token = _token(par_de_chaves, iat=agora + 200, exp=agora + 200 + 3600)
    with pytest.raises(TokenInvalido):
        verificar_token_firebase(token, PROJECT_ID)


def test_token_expirado_e_rejeitado(par_de_chaves, com_jwks_de_teste):
    agora = int(time.time())
    token = _token(par_de_chaves, iat=agora - 7200, exp=agora - 3600)
    with pytest.raises(TokenInvalido):
        verificar_token_firebase(token, PROJECT_ID)


def test_token_de_outro_projeto_e_rejeitado(par_de_chaves, com_jwks_de_teste):
    token = _token(par_de_chaves, aud="outro-projeto")
    with pytest.raises(TokenInvalido):
        verificar_token_firebase(token, PROJECT_ID)
