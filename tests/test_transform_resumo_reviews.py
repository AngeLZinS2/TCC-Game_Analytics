"""Testes do parser do resumo de avaliacoes por IA (Groq).

Sem rede e sem banco: `transformar` sobre RawRecord's com a resposta crua
(formato chat/completions) montada na mao. O que se protege e a tolerancia
do parser a um modelo gratis que nao segue o formato pedido 100% das vezes.
"""

from __future__ import annotations

from services.collectors.base import RawRecord
from services.etl.transform_resumo_reviews import (
    ENDPOINT_CHAT,
    FONTE,
    _extrair_secoes,
    transformar,
)

APP = 1245620


def _reg(app_id: int, conteudo: str, modelo: str = "llama-3.3-70b-versatile", total: int = 10):
    return RawRecord(
        fonte=FONTE,
        endpoint=ENDPOINT_CHAT,
        identificador=str(app_id),
        payload={
            "groq_response": {
                "model": modelo,
                "choices": [{"message": {"role": "assistant", "content": conteudo}}],
            },
            "amostra": {"total": total},
        },
    )


FORMATO_OK = (
    "RESUMO: Jogadores elogiam o combate fluido e a trilha sonora, mas "
    "reclamam de bugs recorrentes no multiplayer.\n"
    "POSITIVOS:\n"
    "- Combate rapido e responsivo\n"
    "- Trilha sonora marcante\n"
    "- Boa curva de progressao\n"
    "NEGATIVOS:\n"
    "- Bugs frequentes no modo online\n"
    "- Otimizacao fraca em PCs mais fracos\n"
)


def test_extrair_secoes_formato_padrao():
    resumo, positivos, negativos = _extrair_secoes(FORMATO_OK)
    assert resumo.startswith("Jogadores elogiam")
    assert positivos == [
        "Combate rapido e responsivo",
        "Trilha sonora marcante",
        "Boa curva de progressao",
    ]
    assert negativos == [
        "Bugs frequentes no modo online",
        "Otimizacao fraca em PCs mais fracos",
    ]


def test_extrair_secoes_tolera_markdown_negrito():
    bruto = (
        "**RESUMO:** Recepcao mista, com elogios ao visual.\n"
        "**POSITIVOS:**\n"
        "- Visual caprichado\n"
        "**NEGATIVOS:**\n"
        "- Preco alto\n"
    )
    resumo, positivos, negativos = _extrair_secoes(bruto)
    assert resumo == "Recepcao mista, com elogios ao visual."
    assert positivos == ["Visual caprichado"]
    assert negativos == ["Preco alto"]


def test_extrair_secoes_sem_marcador_vira_resumo_inteiro():
    bruto = "O jogo agrada bastante, com poucas reclamacoes registradas."
    resumo, positivos, negativos = _extrair_secoes(bruto)
    assert resumo == bruto
    assert positivos == []
    assert negativos == []


def test_extrair_secoes_sem_negativos_nao_quebra():
    bruto = "RESUMO: Unanimidade positiva.\nPOSITIVOS:\n- Otimo em tudo\n"
    resumo, positivos, negativos = _extrair_secoes(bruto)
    assert resumo == "Unanimidade positiva."
    assert positivos == ["Otimo em tudo"]
    assert negativos == []


def test_extrair_secoes_teto_de_bullets():
    bullets = "\n".join(f"- ponto {i}" for i in range(10))
    bruto = f"RESUMO: teste\nPOSITIVOS:\n{bullets}\n"
    _, positivos, _ = _extrair_secoes(bruto)
    assert len(positivos) == 6


def test_transformar_monta_resumo_completo():
    resultado = transformar([_reg(APP, FORMATO_OK, total=14)])
    assert resultado.total == 1
    item = resultado.resumos[0]
    assert item.app_id == APP
    assert item.modelo == "llama-3.3-70b-versatile"
    assert item.avaliacoes_usadas == 14
    assert len(item.positivos) == 3
    assert len(item.negativos) == 2


def test_transformar_ignora_outras_fontes():
    reg = RawRecord(fonte="itad", endpoint=ENDPOINT_CHAT, identificador="1", payload={})
    assert transformar([reg]).total == 0


def test_transformar_ignora_outro_endpoint():
    reg = RawRecord(fonte=FONTE, endpoint="lookup", identificador=str(APP), payload={})
    assert transformar([reg]).total == 0


def test_transformar_resposta_sem_conteudo_e_descartada():
    reg = _reg(APP, "")
    assert transformar([reg]).total == 0


def test_transformar_identificador_invalido_e_ignorado():
    reg = RawRecord(
        fonte=FONTE,
        endpoint=ENDPOINT_CHAT,
        identificador="nao-e-um-app-id",
        payload={"groq_response": {"choices": [{"message": {"content": "RESUMO: x"}}]}},
    )
    assert transformar([reg]).total == 0
