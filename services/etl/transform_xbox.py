"""Normalizacao dos payloads da Xbox Store / Game Pass.

Funcao pura sobre dicionarios: nada de rede, nada de banco. E o ponto frouxo
do dominio Xbox - os endpoints da Microsoft nao sao documentados e mudam sem
aviso - por isso tem teste de fixture em `tests/`.

Duas fontes:
- `catalog.gamepass.com/sigls/v2` -> a lista de `product_id`s no Game Pass.
- `displaycatalog.mp.microsoft.com/v7.0/products` -> a ficha de cada jogo.

**Onde mora o preco de balcao.** Cada jogo tem varias `Availability`. A de
venda e a que tem `"Purchase"` em `Actions`, moeda igual a do mercado e
`ListPrice > 0`. As varias `Availability` de `ListPrice: 0.0` em BRL com
`RemediationRequired: true` sao concessoes do Game Pass / EA Play - nao o
preco de balcao. As de USD com `"License"` sao licencas do Game Pass. Se nao
sobra nenhuma de venda, o jogo so e vendido via Game Pass no BR: `preco` fica
nulo, mas ele ainda entra na vitrine (com o selo do GP).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from pydantic import BaseModel, Field

from services.collectors.base import RawRecord

logger = logging.getLogger(__name__)

FONTE = "xbox"
ENDPOINT_GAMEPASS = "gamepass-sigl"
ENDPOINT_PRODUTOS = "displaycatalog-products"

#: Pagina da loja. `product_id` no final resolve para o slug certo sozinho.
_URL_LOJA = "https://www.xbox.com/pt-BR/games/store/-/{product_id}"

#: Traducao dos generos da Microsoft (`Properties.Categories`) para pt-BR. O
#: que nao estiver aqui passa como veio - a lista da loja e grande e muda.
_GENEROS = {
    "Action & adventure": "Ação e aventura",
    "Card & board": "Cartas e tabuleiro",
    "Classics": "Clássicos",
    "Educational": "Educativo",
    "Family & kids": "Família e crianças",
    "Fighting": "Luta",
    "Music": "Música",
    "Other": "Outros",
    "Platformer": "Plataforma",
    "Puzzle & trivia": "Quebra-cabeça",
    "Racing & flying": "Corrida e voo",
    "Role playing": "RPG",
    "Shooter": "Tiro",
    "Simulation": "Simulação",
    "Sports": "Esportes",
    "Strategy": "Estratégia",
    "Word": "Palavras",
}

#: Ordem de preferencia da arte larga do topo.
_ARTE_HEADER = ("SuperHeroArt", "TitledHeroArt", "BrandedKeyArt")
#: Ordem de preferencia da arte quadrada da lista.
_ARTE_CAPA = ("Poster", "BoxArt", "FeaturePromotionalSquareArt", "Logo")

#: Recursos da loja (`Properties.Attributes`) ja traduzidos. So os que dizem
#: algo ao jogador - `XboxLive`, `XPA`, `XblPresence`, `BroadcastSupport` e cia.
#: sao ruido de infraestrutura e ficam de fora (nao estao no mapa).
_RECURSOS = {
    # video / audio
    "Capability4k": "4K",
    "CapabilityHDR": "HDR",
    "CapabilityVRR": "VRR",
    "CapabilityXboxEnhanced": "Xbox One X Enhanced",
    "60fps": "60 FPS",
    "120fps": "120 FPS",
    "Capability60fps": "60 FPS",
    "Capability120fps": "120 FPS",
    "DolbyAtmos": "Dolby Atmos",
    "DolbyVision": "Dolby Vision",
    "DTSX": "DTS:X",
    "SpatialSound": "Áudio espacial",
    "RayTracing": "Ray tracing",
    # modos de jogo
    "SinglePlayer": "Um jogador",
    "CoopSupportLocal": "Co-op local",
    "CoopSupportOnline": "Co-op online",
    "XblLocalCoop": "Co-op local",
    "XblOnlineCoop": "Co-op online",
    "XblCrossPlatformCoop": "Co-op cross-platform",
    "LocalMultiplayer": "Multi-jogador local",
    "OnlineMultiplayerWithGold": "Multi-jogador online",
    "XblLocalMultiPlayer": "Multi-jogador local",
    "XblOnlineMultiPlayer": "Multi-jogador online",
    "XblCrossPlatformMultiPlayer": "Multiplayer cross-platform",
    "XboxLiveCrossGenMP": "Multiplayer entre gerações",
    "SharedSplitScreen": "Tela dividida",
    # plataforma / entrega
    "ConsoleGen9Optimized": "Otimizado p/ Series X|S",
    "ConsoleGen9Enhanced": "Melhorado p/ Series X|S",
    "ConsoleCrossGen": "Smart Delivery",
    "CrossBuy": "Cross-buy",
    "XblCloudSaves": "Saves na nuvem",
    "CloudGaming": "Jogo na nuvem",
    "ConsoleKeyboardMouse": "Teclado e mouse (console)",
    "NativeKbmSupport": "Teclado e mouse",
    "PcGamePad": "Suporte a controle",
    "PCGamePad": "Suporte a controle",
    "WindowsMixedReality": "Realidade virtual",
    "TouchInput": "Toque",
}

#: Descritores de conteudo, o codigo cru -> texto. Best-effort: o que nao
#: estiver aqui cai para o proprio codigo sem prefixo.
_DESCRITORES = {
    "DJCTQ:Vio": "Violência",
    "DJCTQ:ExtVio": "Violência extrema",
    "DJCTQ:FanVio": "Violência fantasiosa",
    "DJCTQ:LigAniVio": "Violência",
    "DJCTQ:VioExt": "Violência extrema",
    "DJCTQ:SexCon": "Conteúdo sexual",
    "DJCTQ:Sex": "Sexo",
    "DJCTQ:Nud": "Nudez",
    "DJCTQ:Dru": "Drogas",
    "DJCTQ:LegDru": "Drogas lícitas",
    "DJCTQ:IllDru": "Drogas ilícitas",
    "DJCTQ:IleDru": "Drogas ilícitas",
    "DJCTQ:InaLan": "Linguagem imprópria",
    "DJCTQ:Fea": "Medo",
    "DJCTQ:ImpCon": "Conteúdo impactante",
    "DJCTQ:SenThem": "Temas sensíveis",
    "DJCTQ:Cri": "Crime",
    "DJCTQ:Dis": "Discriminação",
    "DJCTQ:Gam": "Jogos de azar",
    "ESRB:Vio": "Violência",
    "ESRB:StrVio": "Violência intensa",
    "ESRB:Blo": "Sangue",
    "ESRB:BloGore": "Sangue e mutilação",
    "ESRB:StrLan": "Linguagem forte",
    "ESRB:Lan": "Linguagem",
    "ESRB:SexThemes": "Temas sexuais",
    "ESRB:SexCon": "Conteúdo sexual",
    "ESRB:Nud": "Nudez",
    "ESRB:UseAlc": "Álcool",
    "ESRB:UseDrugs": "Drogas",
    "ESRB:AlcTobDru": "Álcool, tabaco e drogas",
    "ESRB:SimGam": "Simulação de apostas",
    "ESRB:InGamePurch": "Compras no jogo",
    "ESRB:InGamPur": "Compras no jogo",
}

#: Ordem de preferencia do sistema de classificacao (Brasil primeiro).
_SISTEMAS_CLASSIFICACAO = ("DJCTQ", "ESRB", "PEGI", "IARC", "Microsoft")


# ---------------------------------------------------------------------------
# Modelos normalizados
# ---------------------------------------------------------------------------


class JogoXbox(BaseModel):
    """Linha da dimensao `dim_jogo_xbox`."""

    product_id: str
    nome: str
    tipo: str | None = None
    desenvolvedora: str | None = None
    publicadora: str | None = None
    data_lancamento: date | None = None
    data_lancamento_texto: str | None = None
    generos: list[str] = Field(default_factory=list)
    gratuito: bool | None = None
    preco_atual: Decimal | None = None
    preco_normal: Decimal | None = None
    moeda: str | None = None
    desconto_percentual: int | None = None
    faixa_etaria: int | None = None
    imagem_header: str | None = None
    imagem_capa: str | None = None
    url_loja: str | None = None
    descricao: str | None = None
    nota: Decimal | None = None
    numero_avaliacoes: int | None = None
    nota_recente: Decimal | None = None
    recursos: list[str] = Field(default_factory=list)
    tem_conquistas: bool | None = None
    classificacao_etaria: str | None = None
    descritores_conteudo: list[str] = Field(default_factory=list)
    midias: list[dict] = Field(default_factory=list)
    no_game_pass: bool | None = None


class SnapshotXbox(BaseModel):
    """Linha de `fato_snapshot_jogo_xbox` - preco, GP e nota no tempo."""

    product_id: str
    janela_coleta: datetime
    data_coleta: datetime
    preco_no_momento: Decimal | None = None
    preco_normal: Decimal | None = None
    moeda: str | None = None
    desconto_percentual: int | None = None
    no_game_pass: bool | None = None
    nota: Decimal | None = None
    numero_avaliacoes: int | None = None
    nota_recente: Decimal | None = None


class ResultadoXbox(BaseModel):
    jogos: list[JogoXbox] = Field(default_factory=list)
    snapshots: list[SnapshotXbox] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.jogos)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def truncar_janela(momento: datetime, minutos: int) -> datetime:
    """Alinha um instante ao inicio da janela de coleta (chave de idempotencia)."""
    if minutos <= 0:
        raise ValueError("minutos deve ser positivo")
    momento = momento.astimezone(timezone.utc)
    inicio_do_dia = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    decorridos = int((momento - inicio_do_dia).total_seconds() // 60)
    return inicio_do_dia + timedelta(minutes=(decorridos // minutos) * minutos)


def _decimal(valor: Any) -> Decimal | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _data(valor: Any) -> tuple[date | None, str | None]:
    """`OriginalReleaseDate` -> (date, None) ou (None, texto) se nao parseia."""
    if not isinstance(valor, str) or not valor:
        return None, None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).date(), None
    except ValueError:
        return None, valor[:64]


def _https(uri: Any) -> str | None:
    """`//store-images...` (protocolo relativo) -> `https://...`."""
    if not isinstance(uri, str) or not uri:
        return None
    return f"https:{uri}" if uri.startswith("//") else uri


def _imagem(imagens: list[dict], ordem: tuple[str, ...]) -> str | None:
    por_proposito = {
        img.get("ImagePurpose"): img.get("Uri")
        for img in imagens
        if isinstance(img, dict) and img.get("Uri")
    }
    for proposito in ordem:
        alvo = _https(por_proposito.get(proposito))
        if alvo:
            return alvo
    return None


def _notas(mercado: dict) -> tuple[Decimal | None, int | None, Decimal | None]:
    """(nota, numero_avaliacoes, nota_recente) do `MarketProperties.UsageData`.

    A Store agrega por janela: `AllTime` e a nota "oficial", `7Days` diz se
    esta subindo ou caindo. Sem avaliacao nenhuma (`RatingCount` 0/ausente) nao
    ha sinal - devolve nulo em vez de fingir um "0.0".
    """
    usos = {
        u.get("AggregateTimeSpan"): u
        for u in (mercado.get("UsageData") or [])
        if isinstance(u, dict)
    }
    todo_periodo = usos.get("AllTime") or {}
    contagem = _inteiro(todo_periodo.get("RatingCount"))
    if not contagem:
        return None, None, None
    nota = _decimal(todo_periodo.get("AverageRating"))
    # `7Days` vem com `AverageRating: 0.0` quando nao houve avaliacao recente -
    # isso e "sem dado", nao "nota zero".
    semana = usos.get("7Days") or {}
    recente = (
        _decimal(semana.get("AverageRating"))
        if _inteiro(semana.get("RatingCount"))
        else None
    )
    return nota, contagem, recente


def _recursos(propriedades: dict) -> tuple[list[str], bool | None]:
    """(recursos traduzidos, tem_conquistas) de `Properties.Attributes`."""
    atributos = propriedades.get("Attributes")
    if not isinstance(atributos, list):
        return [], None
    nomes = [
        a["Name"]
        for a in atributos
        if isinstance(a, dict) and isinstance(a.get("Name"), str)
    ]
    if not nomes:
        return [], None
    traduzidos: list[str] = []
    for nome in nomes:
        rotulo = _RECURSOS.get(nome)
        if rotulo and rotulo not in traduzidos:
            traduzidos.append(rotulo)
    return traduzidos, "XblAchievements" in nomes


def _classificacao(mercado: dict) -> tuple[str | None, list[str]]:
    """(classificacao_etaria, descritores) preferindo a DJCTQ (Brasil)."""
    avaliacoes = mercado.get("ContentRatings")
    if not isinstance(avaliacoes, list):
        return None, []
    por_sistema = {
        a.get("RatingSystem"): a for a in avaliacoes if isinstance(a, dict)
    }
    escolhida = None
    for sistema in _SISTEMAS_CLASSIFICACAO:
        if sistema in por_sistema:
            escolhida = por_sistema[sistema]
            break
    if escolhida is None and avaliacoes:
        escolhida = avaliacoes[0] if isinstance(avaliacoes[0], dict) else None
    if not escolhida:
        return None, []

    faixa = None
    rating_id = escolhida.get("RatingId")
    if isinstance(rating_id, str) and rating_id:
        faixa = rating_id.split(":")[-1]

    # So os descritores que sabemos nomear - um codigo cru ("ImpCon") na tela
    # nao diz nada. Dedup preservando a ordem.
    vistos: list[str] = []
    for codigo in escolhida.get("RatingDescriptors") or []:
        if not isinstance(codigo, str):
            continue
        rotulo = _DESCRITORES.get(codigo)
        if rotulo and rotulo not in vistos:
            vistos.append(rotulo)
    return faixa, vistos


def _midias(local: dict) -> list[dict]:
    """Trailers e capturas da ficha, para o carrossel da tela de detalhe.

    Mesma forma que a galeria da Steam (`{tipo, url, cartaz, titulo}`), para
    reusar o `CarrosselMidia`: trailer primeiro, capturas depois.

    O trailer vem de `CMSVideos` (nao `Videos`, que a Store deixou de povoar) -
    e o campo `HLS` de cada item e um `.m3u8`, o mesmo formato dos trailers da
    Steam, entao o player HLS ja existente toca sem mudanca. `Videos` (mp4
    direto) some com `fieldsTemplate=Details`; o coletor pede a resposta sem
    template justamente para o `CMSVideos` vir junto.
    """
    videos: list[dict] = []
    for video in local.get("CMSVideos") or []:
        if not isinstance(video, dict):
            continue
        url = video.get("HLS") or video.get("DASH")
        if not isinstance(url, str) or not url:
            continue
        videos.append(
            {
                "tipo": "video",
                "url": url,
                "cartaz": _https((video.get("PreviewImage") or {}).get("Uri")) or "",
                "titulo": video.get("Caption") or "Trailer",
            }
        )

    imagens: list[dict] = []
    vistos: set[str] = set()
    for img in local.get("Images") or []:
        if not isinstance(img, dict) or img.get("ImagePurpose") != "Screenshot":
            continue
        url = _https(img.get("Uri"))
        if url and url not in vistos:
            vistos.add(url)
            imagens.append({"tipo": "imagem", "url": url, "cartaz": "", "titulo": ""})
        if len(imagens) >= 12:
            break

    return videos + imagens


def _generos(propriedades: dict) -> list[str]:
    brutos = propriedades.get("Categories")
    if not isinstance(brutos, list):
        um = propriedades.get("Category")
        brutos = [um] if um else []
    vistos: list[str] = []
    for bruto in brutos:
        if not isinstance(bruto, str) or not bruto:
            continue
        nome = _GENEROS.get(bruto, bruto)
        if nome not in vistos:
            vistos.append(nome)
    return vistos


def _preco_de_balcao(
    disponibilidades: list[dict], moeda_mercado: str
) -> tuple[Decimal | None, Decimal | None, int | None, bool]:
    """(preco, preco_normal, desconto_%, gratuito) da SKU `full`.

    Percorre so as `Availability` de venda: `"Purchase"` em `Actions`, sem
    `RemediationRequired` e na moeda do mercado. Entre elas, a de menor
    `ListPrice` e o preco atual; o `MSRP` dela e o preco cheio.
    """
    candidatas: list[tuple[Decimal, Decimal]] = []  # (list, msrp)
    tem_venda_gratis = False

    for dsa in disponibilidades:
        if not isinstance(dsa, dict):
            continue
        sku = dsa.get("Sku") or {}
        if sku.get("SkuType") not in (None, "full"):
            continue
        for av in dsa.get("Availabilities") or []:
            if not isinstance(av, dict):
                continue
            acoes = av.get("Actions") or []
            if "Purchase" not in acoes or av.get("RemediationRequired"):
                continue
            preco = (av.get("OrderManagementData") or {}).get("Price") or {}
            if preco.get("CurrencyCode") != moeda_mercado:
                continue
            lista = _decimal(preco.get("ListPrice"))
            msrp = _decimal(preco.get("MSRP")) or lista
            if lista is None:
                continue
            if lista == 0 and (msrp or 0) == 0:
                tem_venda_gratis = True
                continue
            candidatas.append((lista, msrp if msrp is not None else lista))

    if not candidatas:
        # Nenhuma venda paga. `gratuito` so e True se havia venda a custo zero.
        return None, None, None, tem_venda_gratis

    lista, msrp = min(candidatas, key=lambda c: c[0])
    desconto = None
    if msrp and msrp > lista:
        desconto = int(round((1 - (lista / msrp)) * 100))
    return lista, msrp, desconto, False


def _um_jogo(produto: dict, moeda_mercado: str, ids_game_pass: set[str]) -> JogoXbox | None:
    product_id = produto.get("ProductId")
    if not isinstance(product_id, str) or not product_id:
        return None

    locais = produto.get("LocalizedProperties") or []
    local = locais[0] if locais and isinstance(locais[0], dict) else {}
    nome = local.get("ProductTitle") or local.get("SortTitle")
    if not nome:
        return None

    mercado = (produto.get("MarketProperties") or [{}])[0]
    if not isinstance(mercado, dict):
        mercado = {}
    data, data_texto = _data(mercado.get("OriginalReleaseDate"))

    preco, preco_normal, desconto, gratuito = _preco_de_balcao(
        produto.get("DisplaySkuAvailabilities") or [], moeda_mercado
    )

    propriedades = produto.get("Properties") or {}
    nota, num_avaliacoes, nota_recente = _notas(mercado)
    recursos, tem_conquistas = _recursos(propriedades)
    faixa_classificacao, descritores = _classificacao(mercado)

    return JogoXbox(
        product_id=product_id,
        nome=nome,
        tipo=produto.get("ProductType"),
        desenvolvedora=(local.get("DeveloperName") or None),
        publicadora=(local.get("PublisherName") or None),
        data_lancamento=data,
        data_lancamento_texto=data_texto,
        generos=_generos(propriedades),
        gratuito=gratuito or None,
        preco_atual=preco,
        preco_normal=preco_normal,
        moeda=(moeda_mercado if preco is not None else None),
        desconto_percentual=desconto,
        faixa_etaria=_inteiro(mercado.get("MinimumUserAge")),
        imagem_header=_imagem(local.get("Images") or [], _ARTE_HEADER),
        imagem_capa=_imagem(local.get("Images") or [], _ARTE_CAPA),
        url_loja=_URL_LOJA.format(product_id=product_id),
        descricao=(local.get("ShortDescription") or None),
        nota=nota,
        numero_avaliacoes=num_avaliacoes,
        nota_recente=nota_recente,
        recursos=recursos,
        tem_conquistas=tem_conquistas,
        classificacao_etaria=faixa_classificacao,
        descritores_conteudo=descritores,
        midias=_midias(local),
        no_game_pass=product_id in ids_game_pass,
    )


def _inteiro(valor: Any) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _ids_do_game_pass(registros: Iterable[RawRecord]) -> set[str]:
    ids: set[str] = set()
    for registro in registros:
        if registro.endpoint != ENDPOINT_GAMEPASS:
            continue
        payload = registro.payload
        if not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.add(item["id"])
    return ids


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


def transformar(
    registros: Iterable[RawRecord],
    *,
    moeda_mercado: str = "BRL",
    janela_minutos: int = 360,
) -> ResultadoXbox:
    """RawRecord's das duas fontes -> `ResultadoXbox` (dimensao + snapshots).

    `ids_game_pass` sai dos proprios registros (`ENDPOINT_GAMEPASS`); o preco e
    a ficha vem do `ENDPOINT_PRODUTOS`. Um produto sem `ProductId` ou sem nome
    e descartado silenciosamente - a fonte as vezes devolve entradas vazias.
    """
    registros = list(registros)
    ids_game_pass = _ids_do_game_pass(registros)

    agora = datetime.now(timezone.utc)
    janela = truncar_janela(agora, janela_minutos)

    jogos: dict[str, JogoXbox] = {}
    for registro in registros:
        if registro.fonte != FONTE or registro.endpoint != ENDPOINT_PRODUTOS:
            continue
        payload = registro.payload
        produtos = payload.get("Products") if isinstance(payload, dict) else None
        if not isinstance(produtos, list):
            continue
        for produto in produtos:
            if not isinstance(produto, dict):
                continue
            jogo = _um_jogo(produto, moeda_mercado, ids_game_pass)
            if jogo is not None:
                jogos[jogo.product_id] = jogo

    snapshots = [
        SnapshotXbox(
            product_id=jogo.product_id,
            janela_coleta=janela,
            data_coleta=agora,
            preco_no_momento=jogo.preco_atual,
            preco_normal=jogo.preco_normal,
            moeda=jogo.moeda,
            desconto_percentual=jogo.desconto_percentual,
            no_game_pass=jogo.no_game_pass,
            nota=jogo.nota,
            numero_avaliacoes=jogo.numero_avaliacoes,
            nota_recente=jogo.nota_recente,
        )
        for jogo in jogos.values()
    ]

    return ResultadoXbox(jogos=list(jogos.values()), snapshots=snapshots)
