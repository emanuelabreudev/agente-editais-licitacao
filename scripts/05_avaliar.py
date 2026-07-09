"""Etapa 5 — Avaliação RAGAS + acurácia + custo, com IC bootstrap.

Uso:
  python scripts/05_avaliar.py --alvo agente --juiz llm          # avaliação real
  python scripts/05_avaliar.py --alvo agente_mock --juiz heuristico  # offline
  python scripts/05_avaliar.py --alvo baseline

Saídas: relatorio/resultados/avaliacao_<alvo>.json e resumo_<alvo>.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from edital_agent.avaliacao.avaliar import (
    agregar, avaliar_execucao_agente, avaliar_execucao_baseline,
    salvar_json, tabela_markdown_resumo,
)
from edital_agent.avaliacao.juiz import JuizHeuristico, JuizLLM
from edital_agent.config import DIR_BENCHMARK, DIR_RESULTADOS, carregar_config, garantir_diretorios
from edital_agent.indexacao.vetorial import FastEmbedEmbedder
from edital_agent.llm.cliente import criar_llm

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("avaliar")

METRICAS_AGENTE = (
    "faithfulness", "faithfulness_criticos", "taxa_alucinacao",
    "answer_correctness", "answer_correctness_disponivel",
    "answer_correctness_f1", "answer_correctness_similaridade",
    "acuracia_criticos", "acuracia_criticos_disponiveis",
    "proporcao_citacoes_validas", "latencia_s",
)
METRICAS_BASELINE = ("acuracia_criticos", "acuracia_criticos_disponiveis", "latencia_s")


def _carregar_benchmark() -> dict[str, dict]:
    benchmark = json.loads((DIR_BENCHMARK / "benchmark.json").read_text(encoding="utf-8"))
    return {r["id_edital"]: r for r in benchmark}


def avaliar(alvo: str, nome_juiz: str, modelo_juiz: str | None, config: dict) -> int:
    registros = _carregar_benchmark()
    dir_resultados = DIR_RESULTADOS / alvo
    arquivos = sorted(dir_resultados.glob("*.json"))
    if not arquivos:
        logger.error("Sem resultados em %s (rode 04_extrair.py)", dir_resultados)
        return 1

    cfg_aval = config["avaliacao"]
    tolerancia = cfg_aval["tolerancia_valor_pct"]
    e_agente = alvo.startswith("agente")

    if e_agente:
        if nome_juiz == "llm":
            llm_juiz = criar_llm(modelo_juiz or config["llm"]["modelo_juiz"],
                                 max_tokens=config["llm"]["max_tokens"])
            juiz = JuizLLM(llm_juiz)
        else:
            llm_juiz = None
            juiz = JuizHeuristico()
        embedder = FastEmbedEmbedder.compartilhado(config["indexacao"]["modelo_embedding"])

    por_edital = []
    for arquivo in arquivos:
        resultado = json.loads(arquivo.read_text(encoding="utf-8"))
        id_edital = resultado["id_edital"]
        if id_edital not in registros:
            logger.warning("Sem ground truth para %s; ignorado", id_edital)
            continue
        registro = registros[id_edital]
        gt = registro["ground_truth"]
        gt_no_texto = registro.get("gt_presente_no_texto")
        if e_agente:
            aval = avaliar_execucao_agente(
                resultado, gt, juiz, embedder,
                tolerancia_valor_pct=tolerancia, gt_no_texto=gt_no_texto,
            )
        else:
            aval = avaliar_execucao_baseline(
                resultado, gt, tolerancia_valor_pct=tolerancia, gt_no_texto=gt_no_texto
            )
        por_edital.append(aval)

    metricas = METRICAS_AGENTE if e_agente else METRICAS_BASELINE
    resumo = agregar(por_edital, metricas, n_bootstrap=cfg_aval["bootstrap_amostras"])
    resumo["alvo"] = alvo
    resumo["juiz"] = nome_juiz if e_agente else None
    if e_agente and nome_juiz == "llm" and llm_juiz is not None:
        resumo["custo_juiz"] = llm_juiz.uso.como_dict()

    saida = {"resumo": resumo, "por_edital": por_edital}
    salvar_json(saida, DIR_RESULTADOS / f"avaliacao_{alvo}.json")

    # tabela markdown comparativa (usa baseline se já avaliado)
    resumo_baseline = None
    caminho_baseline = DIR_RESULTADOS / "avaliacao_baseline.json"
    if caminho_baseline.exists():
        resumo_baseline = json.loads(caminho_baseline.read_text(encoding="utf-8"))["resumo"]
    tabela = tabela_markdown_resumo(
        resumo if e_agente else None,
        resumo if not e_agente else (resumo_baseline or {}),
        cfg_aval,
    )
    (DIR_RESULTADOS / f"resumo_{alvo}.md").write_text(tabela + "\n", encoding="utf-8")

    logger.info("Avaliação de '%s' (%d editais):", alvo, resumo["n_editais"])
    for metrica in metricas:
        m = resumo[metrica]
        if m["media"] is not None:
            ic = m["ic95_bootstrap"]
            ic_txt = f" IC95=[{ic[0]:.3f}, {ic[1]:.3f}]" if ic else ""
            logger.info("  %s: %.3f ± %s%s", metrica, m["media"],
                        f"{m['desvio_padrao']:.3f}" if m["desvio_padrao"] else "n/a", ic_txt)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alvo", default="agente",
                        help="agente | agente_mock | baseline")
    parser.add_argument("--juiz", choices=["llm", "heuristico"], default="llm")
    parser.add_argument("--modelo-juiz", default=None)
    args = parser.parse_args()
    garantir_diretorios()
    sys.exit(avaliar(args.alvo, args.juiz, args.modelo_juiz, carregar_config()))
