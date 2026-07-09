"""Métricas RAGAS implementadas conforme as definições de Es et al. (2023).

RAGAS — Retrieval Augmented Generation Assessment (arXiv:2309.15217):

  * Faithfulness: a resposta é decomposta em afirmações atômicas; um juiz decide
    quantas são inferíveis dos contextos recuperados.
        F = |afirmações sustentadas| / |afirmações|
    Aqui a decomposição é determinística (uma afirmação por campo preenchido),
    o que torna a métrica reprodutível para extração estruturada.

  * Answer Correctness: combinação ponderada de similaridade factual (F1 sobre
    afirmações TP/FP/FN em relação ao ground truth) e similaridade semântica
    (cosseno de embeddings), com pesos padrão 0,75/0,25 (idênticos ao RAGAS).

A implementação é própria (sem a biblioteca `ragas`) para funcionar com o LLM
juiz da Anthropic e com juiz heurístico offline, mantendo as definições.

  * Taxa de alucinação: complemento do Faithfulness — fração dos campos
    preenchidos cujo valor NÃO é sustentado pelos contextos recuperados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..normalizacao import (
    moeda_para_float,
    normalizar_criterio,
    normalizar_data,
    normalizar_modalidade,
    normalizar_texto,
)
from .juiz import Afirmacao, Juiz, gerar_afirmacoes

# Campos com ground truth oficial (metadados PNCP). prazo_execucao não tem GT.
CAMPOS_COM_GT = (
    "prazo_entrega_proposta",
    "valor_estimado",
    "modalidade",
    "objeto",
    "orgao_responsavel",
    "uf",
    "criterio_julgamento",
)
CAMPOS_CRITICOS = ("prazo_entrega_proposta", "valor_estimado", "modalidade")

PESO_F1 = 0.75
PESO_SIMILARIDADE = 0.25


# --------------------------------------------------------------- comparadores
def comparar_campo(
    campo: str, extraido: Any, esperado: Any, tolerancia_valor_pct: float = 0.5
) -> bool | None:
    """Compara valor extraído vs. ground truth com normalização por tipo.

    Devolve None quando ambos são nulos (abstenção correta — fora do F1).
    """
    if extraido is None and esperado is None:
        return None
    if extraido is None or esperado is None:
        return False
    if campo == "prazo_entrega_proposta":
        return normalizar_data(str(extraido)) == normalizar_data(str(esperado))
    if campo == "valor_estimado":
        a, b = moeda_para_float(extraido), moeda_para_float(esperado)
        if a is None or b is None:
            return False
        return abs(a - b) / max(abs(b), 1e-9) <= tolerancia_valor_pct / 100
    if campo == "modalidade":
        return normalizar_modalidade(str(extraido)) == normalizar_modalidade(str(esperado))
    if campo == "criterio_julgamento":
        return normalizar_criterio(str(extraido)) == normalizar_criterio(str(esperado))
    if campo == "uf":
        return str(extraido).strip().upper() == str(esperado).strip().upper()
    # objeto / orgao_responsavel: sobreposição de tokens (Jaccard relaxado)
    ta = set(normalizar_texto(str(extraido)).split())
    tb = set(normalizar_texto(str(esperado)).split())
    if not ta or not tb:
        return False
    intersecao = len(ta & tb)
    return intersecao / min(len(ta), len(tb)) >= 0.5


# ------------------------------------------------------------------- métricas
@dataclass
class ResultadoFaithfulness:
    total: int
    sustentadas: int
    por_campo: dict[str, bool] = field(default_factory=dict)

    @property
    def valor(self) -> float | None:
        if self.total == 0:
            return None
        return self.sustentadas / self.total

    @property
    def taxa_alucinacao(self) -> float | None:
        if self.total == 0:
            return None
        return 1.0 - (self.sustentadas / self.total)


def faithfulness(
    valores_extraidos: dict[str, Any],
    contextos: list[str],
    juiz: Juiz,
    campos: tuple[str, ...] | None = None,
) -> ResultadoFaithfulness:
    """Faithfulness RAGAS: fração das afirmações sustentadas pelos contextos."""
    afirmacoes: list[Afirmacao] = gerar_afirmacoes(valores_extraidos)
    if campos is not None:
        afirmacoes = [a for a in afirmacoes if a.campo in campos]
    if not contextos:
        return ResultadoFaithfulness(
            total=len(afirmacoes),
            sustentadas=0,
            por_campo={a.campo: False for a in afirmacoes},
        )
    por_campo: dict[str, bool] = {}
    for afirmacao in afirmacoes:
        por_campo[afirmacao.campo] = juiz.verificar(afirmacao, contextos)
    return ResultadoFaithfulness(
        total=len(afirmacoes),
        sustentadas=sum(por_campo.values()),
        por_campo=por_campo,
    )


@dataclass
class ResultadoCorrectness:
    f1_factual: float
    similaridade_semantica: float
    tp: int
    fp: int
    fn: int
    por_campo: dict[str, bool | None] = field(default_factory=dict)

    @property
    def valor(self) -> float:
        return PESO_F1 * self.f1_factual + PESO_SIMILARIDADE * self.similaridade_semantica


def _texto_para_similaridade(valores: dict[str, Any], campos: tuple[str, ...]) -> str:
    partes = []
    for campo in campos:
        v = valores.get(campo)
        if v is not None:
            partes.append(f"{campo.replace('_', ' ')}: {v}")
    return "; ".join(partes) or "nenhuma informação extraída"


def answer_correctness(
    valores_extraidos: dict[str, Any],
    ground_truth: dict[str, Any],
    embedder,
    campos: tuple[str, ...] = CAMPOS_CRITICOS,
    tolerancia_valor_pct: float = 0.5,
) -> ResultadoCorrectness:
    """Answer Correctness RAGAS: 0,75·F1_factual + 0,25·similaridade_semântica."""
    tp = fp = fn = 0
    por_campo: dict[str, bool | None] = {}
    for campo in campos:
        extraido = valores_extraidos.get(campo)
        esperado = ground_truth.get(campo)
        resultado = comparar_campo(campo, extraido, esperado, tolerancia_valor_pct)
        por_campo[campo] = resultado
        if resultado is None:  # abstenção correta (ex.: orçamento sigiloso)
            continue
        if resultado:
            tp += 1
        elif extraido is not None and esperado is not None:
            fp += 1  # extraiu valor errado: penaliza precisão e cobertura
            fn += 1
        elif extraido is not None:
            fp += 1
        else:
            fn += 1
    f1 = (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) > 0 else 1.0

    texto_resposta = _texto_para_similaridade(valores_extraidos, campos)
    texto_gt = _texto_para_similaridade(ground_truth, campos)
    vetores = embedder.embed([texto_resposta, texto_gt])
    sim = float(np.dot(vetores[0], vetores[1]))
    sim = max(0.0, min(1.0, sim))

    return ResultadoCorrectness(
        f1_factual=f1,
        similaridade_semantica=sim,
        tp=tp,
        fp=fp,
        fn=fn,
        por_campo=por_campo,
    )
