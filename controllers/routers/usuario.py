"""Conta de usuario (Firebase Auth) - perfil e historico do assistente.

Quem autentica e-mail/senha e cria a conta e o Firebase, no navegador; o
backend so verifica o ID token (`services/autenticacao.py`) e mantem um
perfil local minimo (`dim_usuario`), criado sob demanda na primeira
requisicao autenticada - nao ha rota de "cadastro" aqui.

`exigir_usuario` e importado por `assistente.py` pra proteger `/perguntar`
com a mesma conta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from config import get_settings
from models.models import DimUsuario, FatoPerguntaAssistente
from models.session import get_db, session_scope
from services.autenticacao import TokenInvalido, verificar_token_firebase
from services.cifra import CifraIndisponivel, cifrar, decifrar, mascarar
from views.schemas import (
    EntradaAvaliarPergunta,
    EntradaChaveIA,
    EntradaHistoricoAssistente,
    PerfilUsuario,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/usuario", tags=["usuario"])


@dataclass(frozen=True)
class UsuarioAtual:
    id_usuario: int
    firebase_uid: str
    email: str | None
    nome_exibicao: str | None


def exigir_usuario(authorization: str | None = Header(default=None)) -> UsuarioAtual:
    """Dependencia do FastAPI - verifica o token e garante o perfil local.

    Upsert numa transacao propria (`session_scope`), separada da sessao do
    handler que chama isto: o mesmo padrao de `registrar_busca` em
    `telemetria.py` - a escrita nao deve depender do resto da requisicao.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="login necessario")

    try:
        claims = verificar_token_firebase(
            authorization.removeprefix("Bearer ").strip(),
            get_settings().firebase_project_id,
            get_settings().firebase_jwks_cache_segundos,
        )
    except TokenInvalido as exc:
        raise HTTPException(status_code=401, detail="sessao invalida ou expirada") from exc

    uid = str(claims["sub"])
    email = claims.get("email")
    nome = claims.get("name")
    agora = datetime.now(timezone.utc)

    with session_scope() as sessao:
        usuario = sessao.execute(
            select(DimUsuario).where(DimUsuario.firebase_uid == uid)
        ).scalar_one_or_none()

        if usuario is None:
            usuario = DimUsuario(
                firebase_uid=uid,
                email=email,
                nome_exibicao=nome,
                criado_em=agora,
                ultimo_acesso=agora,
            )
            sessao.add(usuario)
            sessao.flush()
        else:
            usuario.ultimo_acesso = agora
            if email:
                usuario.email = email
            if nome:
                usuario.nome_exibicao = nome

        return UsuarioAtual(
            id_usuario=usuario.id_usuario,
            firebase_uid=usuario.firebase_uid,
            email=usuario.email,
            nome_exibicao=usuario.nome_exibicao,
        )


@router.get("/perfil", response_model=PerfilUsuario)
def perfil(
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> PerfilUsuario:
    criado_em, chave_cifrada, provedor, modelo = sessao.execute(
        select(
            DimUsuario.criado_em,
            DimUsuario.chave_ia_cifrada,
            DimUsuario.chave_ia_provedor,
            DimUsuario.chave_ia_modelo,
        ).where(DimUsuario.id_usuario == usuario.id_usuario)
    ).one()

    total = sessao.execute(
        select(func.count())
        .select_from(FatoPerguntaAssistente)
        .where(FatoPerguntaAssistente.id_usuario == usuario.id_usuario)
    ).scalar_one()

    chave_mascarada = None
    if chave_cifrada:
        chave_texto = decifrar(chave_cifrada)
        if chave_texto:
            chave_mascarada = mascarar(chave_texto)

    return PerfilUsuario(
        email=usuario.email,
        nome_exibicao=usuario.nome_exibicao,
        membro_desde=criado_em,
        total_perguntas_assistente=total,
        tem_chave_ia_propria=bool(chave_cifrada),
        chave_ia_mascarada=chave_mascarada,
        chave_ia_provedor=provedor if chave_cifrada else None,
        chave_ia_modelo=modelo if chave_cifrada else None,
    )


@router.put("/chave-ia", status_code=204)
def salvar_chave_ia(
    entrada: EntradaChaveIA,
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> None:
    """Cadastra/troca a chave de IA da propria conta (OpenRouter, Anthropic
    ou Google).

    Nao testa a chave contra o provedor aqui - so guarda cifrada. Uma chave
    invalida so aparece na proxima pergunta ao assistente, com o mesmo erro
    que a chave compartilhada ja mostra quando o provedor recusa.
    """
    try:
        cifrada = cifrar(entrada.chave.strip())
    except CifraIndisponivel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    sessao.execute(
        update(DimUsuario)
        .where(DimUsuario.id_usuario == usuario.id_usuario)
        .values(
            chave_ia_cifrada=cifrada,
            chave_ia_provedor=entrada.provedor,
            chave_ia_modelo=(entrada.modelo.strip() if entrada.modelo else None) or None,
        )
    )
    sessao.commit()


@router.delete("/chave-ia", status_code=204)
def remover_chave_ia(
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> None:
    sessao.execute(
        update(DimUsuario)
        .where(DimUsuario.id_usuario == usuario.id_usuario)
        .values(chave_ia_cifrada=None, chave_ia_provedor=None, chave_ia_modelo=None)
    )
    sessao.commit()


@router.get("/historico-assistente", response_model=list[EntradaHistoricoAssistente])
def historico_assistente(
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> list[EntradaHistoricoAssistente]:
    linhas = sessao.execute(
        select(FatoPerguntaAssistente)
        .where(FatoPerguntaAssistente.id_usuario == usuario.id_usuario)
        .order_by(FatoPerguntaAssistente.criado_em.desc())
        .limit(50)
    ).scalars().all()

    return [
        EntradaHistoricoAssistente(id=l.id, pergunta=l.pergunta, em=l.criado_em, util=l.util)
        for l in linhas
    ]


@router.patch("/historico-assistente/{id_pergunta}", status_code=204)
def avaliar_pergunta(
    id_pergunta: int,
    entrada: EntradaAvaliarPergunta,
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> None:
    resultado = sessao.execute(
        update(FatoPerguntaAssistente)
        .where(
            FatoPerguntaAssistente.id == id_pergunta,
            FatoPerguntaAssistente.id_usuario == usuario.id_usuario,
        )
        .values(util=entrada.util)
    )
    if resultado.rowcount == 0:
        raise HTTPException(status_code=404, detail="pergunta nao encontrada")
    sessao.commit()


@router.delete("/historico-assistente", status_code=204)
def limpar_historico(
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> None:
    sessao.execute(
        delete(FatoPerguntaAssistente).where(
            FatoPerguntaAssistente.id_usuario == usuario.id_usuario
        )
    )
    sessao.commit()
