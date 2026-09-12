"""Os modelos que a pessoa pode escolher ao cadastrar a propria chave de IA.

Existe porque o campo de modelo era texto livre: quem quisesse trocar o modelo
precisava saber de cabeca que a Anthropic no OpenRouter e
`anthropic/claude-sonnet-5` e que na API direta e `claude-sonnet-5`. Um typo
ali nao da erro de digitacao - da "modelo nao encontrado" na hora da pergunta,
muito depois, parecendo chave invalida.

A lista do OpenRouter e BUSCADA AO VIVO (a API publica `/models`, sem chave):
sao 400+ modelos e a lista muda toda semana, entao qualquer copia nossa
nasceria velha. O que fazemos com ela e curar - `:batch` fora (nao serve para
pergunta interativa), familias principais primeiro, teto por familia - para o
`<select>` continuar navegavel.

Anthropic e Google diretos ficam em lista fixa: a API delas exige a chave DA
PESSOA para listar modelos, e nos nao temos (nem queremos ter) essa chave em
texto puro aqui. A tela mantem "Outro - digitar o ID" para nao travar quem
quer um modelo recem-lancado.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

URL_MODELOS_OPENROUTER = "https://openrouter.ai/api/v1/models"

#: A lista muda de semana em semana, nao de minuto em minuto.
_TTL_CACHE_S = 3600
_cache: dict[str, Any] = {"em": 0.0, "itens": []}

#: Familias que entram na lista curada, na ordem em que aparecem no select.
FAMILIAS = (
    ("anthropic/", "Anthropic (Claude)"),
    ("google/", "Google (Gemini)"),
    ("openai/", "OpenAI"),
    ("deepseek/", "DeepSeek"),
    ("meta-llama/", "Meta (Llama)"),
    ("qwen/", "Qwen"),
    ("mistralai/", "Mistral"),
    ("x-ai/", "xAI (Grok)"),
)

#: Teto por familia. Sem ele o select teria 284 opcoes so das familias grandes.
MAX_POR_FAMILIA = 8


@dataclass
class ModeloIA:
    id: str
    nome: str
    #: O `<optgroup>` onde a opcao entra.
    grupo: str
    gratuito: bool = False


#: Fallback do OpenRouter quando a API nao responde - so o essencial, para a
#: tela nunca ficar com o select vazio.
MODELOS_OPENROUTER_FALLBACK = (
    ModeloIA("anthropic/claude-sonnet-5", "Claude Sonnet 5", "Anthropic (Claude)"),
    ModeloIA("google/gemini-3.8-flash", "Gemini 3.8 Flash", "Google (Gemini)"),
    ModeloIA("openai/gpt-6-astra", "GPT-6 Astra", "OpenAI"),
)

#: Ids da API DIRETA da Anthropic (nao levam prefixo `anthropic/`).
MODELOS_ANTHROPIC = (
    ModeloIA("claude-opus-5", "Claude Opus 5 (mais capaz)", "Anthropic (Claude)"),
    ModeloIA("claude-sonnet-5", "Claude Sonnet 5 (equilibrado)", "Anthropic (Claude)"),
    ModeloIA("claude-fable-5-1", "Claude Fable 5.1", "Anthropic (Claude)"),
    ModeloIA(
        "claude-haiku-4-5-20251001", "Claude Haiku 4.5 (mais rápido)", "Anthropic (Claude)"
    ),
)

#: Ids da API direta do Google (Generative Language API).
MODELOS_GOOGLE = (
    ModeloIA("gemini-3.8-flash", "Gemini 3.8 Flash (rápido)", "Google (Gemini)"),
    ModeloIA("gemini-3.5-flash", "Gemini 3.5 Flash", "Google (Gemini)"),
    ModeloIA("gemini-2.5-pro", "Gemini 2.5 Pro (mais capaz)", "Google (Gemini)"),
    ModeloIA("gemini-2.5-flash", "Gemini 2.5 Flash", "Google (Gemini)"),
)


def _nome_curto(modelo: dict[str, Any]) -> str:
    """"Anthropic: Claude Sonnet 5" -> "Claude Sonnet 5".

    O prefixo da familia ja e o `<optgroup>` e o "(free)" do fim ja e o selo
    de gratuito da propria opcao; repetir os dois em cada linha so gasta a
    largura do select ("Ling 3.0 Flash VL (free) - gratis").
    """
    nome = (modelo.get("name") or modelo.get("id") or "").strip()
    if ": " in nome:
        nome = nome.split(": ", 1)[1]
    return nome.removesuffix("(free)").strip()


def _openrouter_ao_vivo() -> list[ModeloIA]:
    agora = time.monotonic()
    if agora - float(_cache["em"]) < _TTL_CACHE_S and _cache["itens"]:
        return list(_cache["itens"])

    try:
        resposta = requests.get(URL_MODELOS_OPENROUTER, timeout=10)
        resposta.raise_for_status()
        dados = (resposta.json() or {}).get("data") or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("lista de modelos do OpenRouter indisponivel: %s", exc)
        return list(_cache["itens"]) or list(MODELOS_OPENROUTER_FALLBACK)

    # `:batch` e assincrono (a resposta vem depois, por outro caminho) - nao
    # serve para uma pergunta que espera resposta na tela.
    uteis = [
        modelo
        for modelo in dados
        if isinstance(modelo.get("id"), str) and ":batch" not in modelo["id"]
    ]

    curados: list[ModeloIA] = [
        ModeloIA(modelo["id"], _nome_curto(modelo), "Gratuitos", gratuito=True)
        for modelo in uteis
        if modelo["id"].endswith(":free")
    ]

    for prefixo, grupo in FAMILIAS:
        da_familia = [
            ModeloIA(modelo["id"], _nome_curto(modelo), grupo)
            for modelo in uteis
            if modelo["id"].startswith(prefixo) and not modelo["id"].endswith(":free")
        ]
        curados.extend(da_familia[:MAX_POR_FAMILIA])

    if curados:
        _cache["em"] = agora
        _cache["itens"] = curados
    return curados or list(MODELOS_OPENROUTER_FALLBACK)


def listar(provedor: str) -> list[ModeloIA]:
    """Os modelos oferecidos para aquele provedor, ja na ordem do select."""
    if provedor == "anthropic":
        return list(MODELOS_ANTHROPIC)
    if provedor == "google":
        return list(MODELOS_GOOGLE)
    return _openrouter_ao_vivo()


def catalogo() -> dict[str, list[ModeloIA]]:
    """Os tres provedores de uma vez - a tela carrega isso uma vez so."""
    return {
        "openrouter": listar("openrouter"),
        "anthropic": listar("anthropic"),
        "google": listar("google"),
    }
