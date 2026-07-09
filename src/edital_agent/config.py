"""Carregamento de configuração (configs/config.yaml + variáveis de ambiente).

Sobrescrita por ambiente: EDITAL_AGENT_<SECAO>_<CHAVE>, ex.:
    EDITAL_AGENT_LLM_MODELO=claude-haiku-4-5
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
DIR_CONFIG = RAIZ_PROJETO / "configs"
DIR_DADOS = RAIZ_PROJETO / "data"
DIR_RAW = DIR_DADOS / "raw"
DIR_PROCESSADOS = DIR_DADOS / "processed"
DIR_BENCHMARK = DIR_DADOS / "benchmark"
DIR_INDICES = DIR_DADOS / "indices"
DIR_RESULTADOS = RAIZ_PROJETO / "relatorio" / "resultados"
DIR_FIGURAS = RAIZ_PROJETO / "relatorio" / "figuras"


def _sobrescrever_por_ambiente(config: dict[str, Any]) -> dict[str, Any]:
    for secao, chaves in config.items():
        if not isinstance(chaves, dict):
            continue
        for chave, valor in chaves.items():
            env = os.environ.get(f"EDITAL_AGENT_{secao.upper()}_{chave.upper()}")
            if env is None:
                continue
            if isinstance(valor, bool):
                chaves[chave] = env.lower() in ("1", "true", "sim")
            elif isinstance(valor, int):
                chaves[chave] = int(env)
            elif isinstance(valor, float):
                chaves[chave] = float(env)
            else:
                chaves[chave] = env
    return config


def carregar_config(caminho: Path | None = None) -> dict[str, Any]:
    caminho = caminho or (DIR_CONFIG / "config.yaml")
    with open(caminho, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return _sobrescrever_por_ambiente(config)


def garantir_diretorios() -> None:
    for d in (DIR_RAW, DIR_PROCESSADOS, DIR_BENCHMARK, DIR_INDICES, DIR_RESULTADOS, DIR_FIGURAS):
        d.mkdir(parents=True, exist_ok=True)
