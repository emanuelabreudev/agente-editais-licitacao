"""Orquestração da avaliação: por edital, por campo e agregados com IC bootstrap.

Produz, para agente e baseline:
  - Faithfulness e Answer Correctness (RAGAS) por edital e agregados [agente];
  - taxa de alucinação [agente];
  - acurácia por campo vs. ground truth do PNCP [ambos];
  - custo (tokens/USD) e latência por edital [ambos];
  - intervalos de confiança (bootstrap percentil, 95%) sobre os editais.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .juiz import Juiz
from .ragas_metrics import (
    CAMPOS_COM_GT,
    CAMPOS_CRITICOS,
    answer_correctness,
    comparar_campo,
    faithfulness,
)

TODOS_CAMPOS = CAMPOS_COM_GT + ("prazo_execucao",)


def bootstrap_ic(
    valores: list[float], n_amostras: int = 2000, alpha: float = 0.05, seed: int = 42
) -> tuple[float, float] | None:
    """IC percentil por bootstrap sobre a média (amostra = editais)."""
    dados = np.array([v for v in valores if v is not None], dtype=float)
    if len(dados) < 2:
        return None
    rng = np.random.default_rng(seed)
    medias = rng.choice(dados, size=(n_amostras, len(dados)), replace=True).mean(axis=1)
    return (
        float(np.percentile(medias, 100 * alpha / 2)),
        float(np.percentile(medias, 100 * (1 - alpha / 2))),
    )


def _acuracia_por_campo(
    valores: dict[str, Any], gt: dict[str, Any], tolerancia: float
) -> dict[str, bool | None]:
    return {
        campo: comparar_campo(campo, valores.get(campo), gt.get(campo), tolerancia)
        for campo in CAMPOS_COM_GT
    }


def _campos_disponiveis(
    gt_no_texto: dict[str, bool] | None, gt: dict[str, Any]
) -> tuple[str, ...]:
    """Campos críticos avaliáveis: GT nulo (abstenção) ou GT verificado no texto."""
    if gt_no_texto is None:
        return CAMPOS_CRITICOS
    return tuple(
        c for c in CAMPOS_CRITICOS if gt.get(c) is None or gt_no_texto.get(c, False)
    )


def avaliar_execucao_agente(
    resultado: dict[str, Any],
    gt: dict[str, Any],
    juiz: Juiz,
    embedder,
    tolerancia_valor_pct: float = 0.5,
    gt_no_texto: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Avalia a saída de um agente (ResultadoAgente serializado) para um edital."""
    extracao = resultado["extracao"]
    valores = {campo: extracao[campo]["valor"] for campo in extracao}
    contextos = [c["texto"] for c in resultado.get("contextos", [])]

    ff_todos = faithfulness(valores, contextos, juiz)
    ff_criticos = faithfulness(valores, contextos, juiz, campos=CAMPOS_CRITICOS)
    ac = answer_correctness(
        valores, gt, embedder, campos=CAMPOS_CRITICOS, tolerancia_valor_pct=tolerancia_valor_pct
    )
    disponiveis = _campos_disponiveis(gt_no_texto, gt)
    ac_disponivel = (
        answer_correctness(
            valores, gt, embedder, campos=disponiveis,
            tolerancia_valor_pct=tolerancia_valor_pct,
        )
        if disponiveis
        else None
    )
    acuracia = _acuracia_por_campo(valores, gt, tolerancia_valor_pct)
    citacoes_validas = [
        extracao[campo].get("evidencia_valida")
        for campo in extracao
        if extracao[campo]["valor"] is not None
    ]
    return {
        "id_edital": resultado["id_edital"],
        "faithfulness": ff_todos.valor,
        "faithfulness_criticos": ff_criticos.valor,
        "faithfulness_por_campo": ff_todos.por_campo,
        "taxa_alucinacao": ff_todos.taxa_alucinacao,
        "answer_correctness": ac.valor,
        "answer_correctness_f1": ac.f1_factual,
        "answer_correctness_similaridade": ac.similaridade_semantica,
        "answer_correctness_disponivel": ac_disponivel.valor if ac_disponivel else None,
        "campos_criticos_disponiveis": list(disponiveis),
        "acuracia_por_campo": acuracia,
        "acuracia_criticos": _media_bool([acuracia[c] for c in CAMPOS_CRITICOS]),
        "acuracia_criticos_disponiveis": _media_bool(
            [acuracia[c] for c in disponiveis]
        ),
        "proporcao_citacoes_validas": _media_bool(citacoes_validas),
        "campos_preenchidos": sum(1 for v in valores.values() if v is not None),
        "iteracoes": resultado.get("iteracoes"),
        "uso": resultado.get("uso", {}),
        "latencia_s": resultado.get("latencia_s"),
    }


def avaliar_execucao_baseline(
    resultado: dict[str, Any],
    gt: dict[str, Any],
    tolerancia_valor_pct: float = 0.5,
    gt_no_texto: dict[str, bool] | None = None,
) -> dict[str, Any]:
    valores = resultado["extracao"]
    acuracia = _acuracia_por_campo(valores, gt, tolerancia_valor_pct)
    disponiveis = _campos_disponiveis(gt_no_texto, gt)
    return {
        "id_edital": resultado["id_edital"],
        "acuracia_por_campo": acuracia,
        "acuracia_criticos": _media_bool([acuracia[c] for c in CAMPOS_CRITICOS]),
        "acuracia_criticos_disponiveis": _media_bool([acuracia[c] for c in disponiveis]),
        "campos_preenchidos": sum(1 for v in valores.values() if v is not None),
        "latencia_s": resultado.get("latencia_s"),
    }


def _media_bool(valores: list[bool | None]) -> float | None:
    validos = [v for v in valores if v is not None]
    if not validos:
        return None
    return sum(validos) / len(validos)


def _media(valores: list[float | None]) -> float | None:
    validos = [v for v in valores if v is not None]
    return float(np.mean(validos)) if validos else None


def _desvio(valores: list[float | None]) -> float | None:
    validos = [v for v in valores if v is not None]
    return float(np.std(validos, ddof=1)) if len(validos) > 1 else None


def agregar(
    por_edital: list[dict[str, Any]],
    metricas: tuple[str, ...],
    n_bootstrap: int = 2000,
) -> dict[str, Any]:
    """Agrega métricas por edital: média, desvio-padrão e IC bootstrap 95%."""
    resumo: dict[str, Any] = {"n_editais": len(por_edital)}
    for metrica in metricas:
        valores = [e.get(metrica) for e in por_edital]
        resumo[metrica] = {
            "media": _media(valores),
            "desvio_padrao": _desvio(valores),
            "ic95_bootstrap": bootstrap_ic(valores, n_amostras=n_bootstrap),
            "n_validos": sum(1 for v in valores if v is not None),
        }
    # acurácia agregada por campo
    por_campo: dict[str, Any] = {}
    for campo in CAMPOS_COM_GT:
        valores_campo = [
            e["acuracia_por_campo"].get(campo)
            for e in por_edital
            if "acuracia_por_campo" in e
        ]
        por_campo[campo] = {
            "acuracia": _media_bool(valores_campo),
            "n_avaliados": sum(1 for v in valores_campo if v is not None),
        }
    resumo["acuracia_por_campo"] = por_campo
    return resumo


def salvar_json(dados: Any, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def formatar_pct(v: float | None) -> str:
    return f"{100 * v:.1f}%" if v is not None else "—"


def tabela_markdown_resumo(
    resumo_agente: dict[str, Any] | None,
    resumo_baseline: dict[str, Any],
    metas: dict[str, float],
) -> str:
    """Tabela comparativa em Markdown para o relatório/README."""
    linhas = [
        "| Métrica | Meta | Agente RAG | Baseline regex |",
        "|---|---|---|---|",
    ]

    def celula(resumo: dict | None, metrica: str) -> str:
        if not resumo or metrica not in resumo or resumo[metrica]["media"] is None:
            return "—"
        m = resumo[metrica]
        ic = m["ic95_bootstrap"]
        ic_txt = f" (IC95 {formatar_pct(ic[0])}–{formatar_pct(ic[1])})" if ic else ""
        return f"{formatar_pct(m['media'])}{ic_txt}"

    linhas.append(
        f"| Faithfulness (RAGAS) | ≥ {metas['meta_faithfulness']:.2f} | "
        f"{celula(resumo_agente, 'faithfulness')} | n/a |"
    )
    linhas.append(
        f"| Answer Correctness (RAGAS, campos críticos) | ≥ {metas['meta_answer_correctness']:.2f} | "
        f"{celula(resumo_agente, 'answer_correctness')} | n/a |"
    )
    linhas.append(
        f"| Taxa de alucinação | ≤ {metas['meta_taxa_alucinacao']:.2f} | "
        f"{celula(resumo_agente, 'taxa_alucinacao')} | n/a |"
    )
    linhas.append(
        f"| Acurácia campos críticos | ≥ {metas['meta_precisao_baseline']:.2f} (baseline) | "
        f"{celula(resumo_agente, 'acuracia_criticos')} | {celula(resumo_baseline, 'acuracia_criticos')} |"
    )
    return "\n".join(linhas)
