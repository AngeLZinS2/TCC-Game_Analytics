"""Favoritos por conta: jogos (Steam/Xbox) e times de esports.

Sao duas listas independentes, cada uma com seu proprio par
favoritar/desfavoritar/listar. A listagem sempre devolve o favorito ja
enriquecido (preco/promocao/noticia pro jogo, proxima partida pro time) -
o frontend nao faz uma segunda chamada por item.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from controllers.routers.usuario import UsuarioAtual, exigir_usuario
from models.models import (
    AgendaPartida,
    DimEquipe,
    DimJogo,
    DimJogoSteam,
    DimJogoXbox,
    FatoSnapshotJogoSteam,
    FatoSnapshotJogoXbox,
    NoticiaJogoSteam,
    UsuarioEquipeFavorita,
    UsuarioJogoFavorito,
)
from models.session import get_db
from views.schemas import (
    EntradaFavoritarEquipe,
    EntradaFavoritarJogo,
    EquipeFavorita,
    JogoFavorito,
    ProximaPartidaFavorita,
)

router = APIRouter(prefix="/api/usuario/favoritos", tags=["favoritos"])


# ---------------------------------------------------------------------------
# Jogos
# ---------------------------------------------------------------------------


@router.post("/jogos", status_code=204)
def favoritar_jogo(
    entrada: EntradaFavoritarJogo,
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> None:
    ja_existe = sessao.execute(
        select(UsuarioJogoFavorito).where(
            UsuarioJogoFavorito.id_usuario == usuario.id_usuario,
            UsuarioJogoFavorito.fonte == entrada.fonte,
            UsuarioJogoFavorito.jogo_id == entrada.jogo_id,
        )
    ).scalar_one_or_none()
    if ja_existe is None:
        sessao.add(
            UsuarioJogoFavorito(
                id_usuario=usuario.id_usuario,
                fonte=entrada.fonte,
                jogo_id=entrada.jogo_id,
                criado_em=datetime.now(timezone.utc),
            )
        )
        sessao.commit()


@router.delete("/jogos/{fonte}/{jogo_id}", status_code=204)
def desfavoritar_jogo(
    fonte: str,
    jogo_id: str,
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> None:
    favorito = sessao.execute(
        select(UsuarioJogoFavorito).where(
            UsuarioJogoFavorito.id_usuario == usuario.id_usuario,
            UsuarioJogoFavorito.fonte == fonte,
            UsuarioJogoFavorito.jogo_id == jogo_id,
        )
    ).scalar_one_or_none()
    if favorito is None:
        raise HTTPException(status_code=404, detail="favorito nao encontrado")
    sessao.delete(favorito)
    sessao.commit()


def _jogo_favorito_steam(sessao: Session, jogo_id: str) -> JogoFavorito | None:
    try:
        app_id = int(jogo_id)
    except ValueError:
        return None

    jogo = sessao.get(DimJogoSteam, app_id)
    if jogo is None:
        return None

    snapshot = sessao.execute(
        select(FatoSnapshotJogoSteam)
        .where(FatoSnapshotJogoSteam.app_id == app_id)
        .order_by(FatoSnapshotJogoSteam.janela_coleta.desc())
        .limit(1)
    ).scalar_one_or_none()

    noticia = sessao.execute(
        select(NoticiaJogoSteam)
        .where(NoticiaJogoSteam.app_id == app_id)
        .order_by(NoticiaJogoSteam.publicado_em.desc())
        .limit(1)
    ).scalar_one_or_none()

    desconto = snapshot.desconto_percentual if snapshot else None

    return JogoFavorito(
        fonte="steam",
        jogo_id=jogo_id,
        nome=jogo.nome,
        imagem=None,  # Steam: a URL sai do app_id direto no frontend (CapaJogo).
        preco_atual=(snapshot.preco_no_momento if snapshot else None) or jogo.preco_atual,
        preco_normal=None,
        desconto_percentual=desconto,
        moeda=(snapshot.moeda if snapshot else None) or jogo.moeda,
        gratuito=jogo.gratuito,
        promocao_ativa=bool(desconto and desconto > 0),
        ultima_noticia_titulo=noticia.titulo if noticia else None,
        ultima_noticia_url=noticia.url if noticia else None,
        ultima_noticia_em=noticia.publicado_em if noticia else None,
    )


def _jogo_favorito_xbox(sessao: Session, jogo_id: str) -> JogoFavorito | None:
    jogo = sessao.get(DimJogoXbox, jogo_id)
    if jogo is None:
        return None

    snapshot = sessao.execute(
        select(FatoSnapshotJogoXbox)
        .where(FatoSnapshotJogoXbox.product_id == jogo_id)
        .order_by(FatoSnapshotJogoXbox.janela_coleta.desc())
        .limit(1)
    ).scalar_one_or_none()

    preco_atual = (snapshot.preco_no_momento if snapshot else None) or jogo.preco_atual
    preco_normal = (snapshot.preco_normal if snapshot else None) or jogo.preco_normal
    desconto = (snapshot.desconto_percentual if snapshot else None) or jogo.desconto_percentual

    return JogoFavorito(
        fonte="xbox",
        jogo_id=jogo_id,
        nome=jogo.nome,
        imagem=jogo.imagem_capa or jogo.imagem_header,
        preco_atual=preco_atual,
        preco_normal=preco_normal,
        desconto_percentual=desconto,
        moeda=(snapshot.moeda if snapshot else None),
        gratuito=None,
        promocao_ativa=bool(desconto and desconto > 0),
    )


@router.get("/jogos", response_model=list[JogoFavorito])
def listar_jogos_favoritos(
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> list[JogoFavorito]:
    favoritos = sessao.execute(
        select(UsuarioJogoFavorito)
        .where(UsuarioJogoFavorito.id_usuario == usuario.id_usuario)
        .order_by(UsuarioJogoFavorito.criado_em.desc())
    ).scalars().all()

    resultado: list[JogoFavorito] = []
    for favorito in favoritos:
        enriquecido = (
            _jogo_favorito_steam(sessao, favorito.jogo_id)
            if favorito.fonte == "steam"
            else _jogo_favorito_xbox(sessao, favorito.jogo_id)
        )
        # Jogo pode ter saido do catalogo coletado - o favorito continua
        # existindo, so nao aparece na lista ate voltar a ser coletado.
        if enriquecido is not None:
            resultado.append(enriquecido)
    return resultado


# ---------------------------------------------------------------------------
# Equipes
# ---------------------------------------------------------------------------


@router.post("/equipes", status_code=204)
def favoritar_equipe(
    entrada: EntradaFavoritarEquipe,
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> None:
    equipe = sessao.get(DimEquipe, entrada.id_equipe)
    if equipe is None:
        raise HTTPException(status_code=404, detail="equipe nao encontrada")

    ja_existe = sessao.execute(
        select(UsuarioEquipeFavorita).where(
            UsuarioEquipeFavorita.id_usuario == usuario.id_usuario,
            UsuarioEquipeFavorita.id_equipe == entrada.id_equipe,
        )
    ).scalar_one_or_none()
    if ja_existe is None:
        sessao.add(
            UsuarioEquipeFavorita(
                id_usuario=usuario.id_usuario,
                id_equipe=entrada.id_equipe,
                criado_em=datetime.now(timezone.utc),
            )
        )
        sessao.commit()


@router.delete("/equipes/{id_equipe}", status_code=204)
def desfavoritar_equipe(
    id_equipe: int,
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> None:
    favorito = sessao.execute(
        select(UsuarioEquipeFavorita).where(
            UsuarioEquipeFavorita.id_usuario == usuario.id_usuario,
            UsuarioEquipeFavorita.id_equipe == id_equipe,
        )
    ).scalar_one_or_none()
    if favorito is None:
        raise HTTPException(status_code=404, detail="favorito nao encontrado")
    sessao.delete(favorito)
    sessao.commit()


@router.get("/equipes", response_model=list[EquipeFavorita])
def listar_equipes_favoritas(
    usuario: UsuarioAtual = Depends(exigir_usuario),
    sessao: Session = Depends(get_db),
) -> list[EquipeFavorita]:
    linhas = sessao.execute(
        select(UsuarioEquipeFavorita, DimEquipe, DimJogo)
        .join(DimEquipe, DimEquipe.id_equipe == UsuarioEquipeFavorita.id_equipe)
        .join(DimJogo, DimJogo.id_jogo == DimEquipe.id_jogo)
        .where(UsuarioEquipeFavorita.id_usuario == usuario.id_usuario)
        .order_by(UsuarioEquipeFavorita.criado_em.desc())
    ).all()

    agora = datetime.now(timezone.utc)
    resultado: list[EquipeFavorita] = []
    for _favorito, equipe, jogo in linhas:
        proxima = sessao.execute(
            select(AgendaPartida)
            .where(
                or_(
                    AgendaPartida.id_equipe_a == equipe.id_equipe,
                    AgendaPartida.id_equipe_b == equipe.id_equipe,
                ),
                AgendaPartida.inicio_previsto >= agora,
                AgendaPartida.vitoria_a.is_(None),
            )
            .order_by(AgendaPartida.inicio_previsto.asc())
            .limit(1)
        ).scalar_one_or_none()

        proxima_partida = None
        if proxima is not None:
            adversario = (
                proxima.equipe_b_nome
                if proxima.id_equipe_a == equipe.id_equipe
                else proxima.equipe_a_nome
            )
            proxima_partida = ProximaPartidaFavorita(
                id_externo=proxima.id_externo,
                adversario_nome=adversario,
                inicio_previsto=proxima.inicio_previsto,
                torneio=proxima.torneio,
            )

        resultado.append(
            EquipeFavorita(
                id_equipe=equipe.id_equipe,
                nome=equipe.nome,
                tag=equipe.tag,
                logo_url=equipe.logo_url,
                jogo_codigo=jogo.codigo,
                proxima_partida=proxima_partida,
            )
        )
    return resultado
