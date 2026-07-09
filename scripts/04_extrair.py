"""Etapa 4 — Extração: agente RAG (LLM) e/ou baseline regex.

Uso:
  python scripts/04_extrair.py --executor baseline
  python scripts/04_extrair.py --executor agente                # LLM real (ANTHROPIC_API_KEY)
  python scripts/04_extrair.py --executor agente --modelo mock  # smoke test offline
  python scripts/04_extrair.py --executor ambos

Resultados: relatorio/resultados/{agente|agente_mock|baseline}/<id_edital>.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from edital_agent.agente.agente import AgenteEdital
from edital_agent.baseline.regex_extractor import extrair_por_regex
from edital_agent.config import (
    DIR_BENCHMARK, DIR_INDICES, DIR_PROCESSADOS, DIR_RESULTADOS,
    carregar_config, garantir_diretorios,
)
from edital_agent.indexacao.vetorial import FastEmbedEmbedder, IndiceVetorial
from edital_agent.llm.cliente import criar_llm

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("extrair")


def _ids_benchmark() -> list[str]:
    benchmark = json.loads((DIR_BENCHMARK / "benchmark.json").read_text(encoding="utf-8"))
    return [r["id_edital"] for r in benchmark]


def rodar_baseline() -> int:
    destino = DIR_RESULTADOS / "baseline"
    destino.mkdir(parents=True, exist_ok=True)
    ok = 0
    for id_edital in _ids_benchmark():
        caminho = DIR_PROCESSADOS / f"{id_edital}.txt"
        if not caminho.exists():
            logger.warning("Texto ausente para %s", id_edital)
            continue
        texto = caminho.read_text(encoding="utf-8")
        inicio = time.monotonic()
        extracao = extrair_por_regex(texto)
        latencia = time.monotonic() - inicio
        (destino / f"{id_edital}.json").write_text(
            json.dumps(
                {
                    "id_edital": id_edital,
                    "extracao": extracao.como_dict(),
                    "latencia_s": round(latencia, 4),
                    "executor": "baseline_regex",
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        ok += 1
    logger.info("Baseline concluído para %d editais", ok)
    return 0 if ok else 1


def rodar_agente(config: dict, modelo: str | None) -> int:
    cfg_llm = config["llm"]
    cfg_idx = config["indexacao"]
    modelo = modelo or cfg_llm["modelo"]
    sufixo = "_mock" if modelo == "mock" else ""
    destino = DIR_RESULTADOS / f"agente{sufixo}"
    destino.mkdir(parents=True, exist_ok=True)
    embedder = FastEmbedEmbedder.compartilhado(cfg_idx["modelo_embedding"])

    ok = 0
    for id_edital in _ids_benchmark():
        dir_indice = DIR_INDICES / id_edital
        if not dir_indice.exists():
            logger.warning("Índice ausente para %s (rode 03_indexar.py)", id_edital)
            continue
        indice = IndiceVetorial.carregar(dir_indice, embedder)
        llm = criar_llm(modelo, max_tokens=cfg_llm["max_tokens"])  # 1 instância/edital p/ custo
        agente = AgenteEdital(llm, indice, max_iteracoes=cfg_llm["max_iteracoes_agente"])
        logger.info("Agente (%s) analisando %s ...", modelo, id_edital)
        try:
            resultado = agente.executar(id_edital)
        except Exception:
            logger.exception("Agente falhou em %s", id_edital)
            continue
        (destino / f"{id_edital}.json").write_text(
            json.dumps(resultado.como_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        preenchidos = sum(
            1 for v in resultado.extracao.valores().values() if v is not None
        )
        logger.info(
            "%s: %d/8 campos, %d iterações, %.1fs, US$ %.4f",
            id_edital, preenchidos, resultado.iteracoes, resultado.latencia_s,
            resultado.uso.get("custo_usd", 0.0),
        )
        ok += 1
    logger.info("Agente concluído para %d editais (resultados em %s)", ok, destino)
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor", choices=["agente", "baseline", "ambos"], default="ambos")
    parser.add_argument("--modelo", default=None,
                        help="Id do modelo Anthropic ou 'mock' (offline)")
    args = parser.parse_args()
    garantir_diretorios()
    config = carregar_config()
    status = 0
    if args.executor in ("baseline", "ambos"):
        status |= rodar_baseline()
    if args.executor in ("agente", "ambos"):
        status |= rodar_agente(config, args.modelo)
    sys.exit(status)
