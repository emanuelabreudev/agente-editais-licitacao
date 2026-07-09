"""Etapa 2 — Extração de texto dos documentos baixados (pypdf + OCR fallback).

Resolve ZIPs (edital + anexos), extrai texto página a página e registra o
método usado (pypdf | pypdf+ocr) e avisos (páginas escaneadas sem OCR etc.).

Uso: python scripts/02_processar.py
"""

from __future__ import annotations

import json
import logging
import sys

from edital_agent.avaliacao.juiz import verificar_gt_no_texto
from edital_agent.config import (
    DIR_BENCHMARK, DIR_PROCESSADOS, DIR_RAW, carregar_config, garantir_diretorios,
)
from edital_agent.extracao.pdf import extrair_texto, resolver_documento

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("processar")


def processar(config: dict) -> int:
    cfg = config["extracao"]
    max_paginas = config["coleta"].get("max_paginas_pdf")
    benchmark = json.loads((DIR_BENCHMARK / "benchmark.json").read_text(encoding="utf-8"))
    metadados: dict[str, dict] = {}
    falhas = 0

    for registro in benchmark:
        id_edital = registro["id_edital"]
        origem = DIR_RAW / f"{id_edital}.bin"
        if not origem.exists():
            logger.warning("Documento ausente: %s (rode 01_coletar.py)", origem.name)
            falhas += 1
            continue
        try:
            pdf = resolver_documento(origem)
            resultado = extrair_texto(
                pdf,
                min_chars_por_pagina=cfg["min_chars_por_pagina"],
                ocr_dpi=cfg["ocr_dpi"],
                max_paginas=max_paginas,
            )
        except Exception as exc:
            logger.error("Falha ao processar %s: %s", id_edital, exc)
            falhas += 1
            continue
        (DIR_PROCESSADOS / f"{id_edital}.txt").write_text(resultado.texto, encoding="utf-8")
        # anota quais campos do ground truth são verificáveis no texto baixado
        registro["gt_presente_no_texto"] = verificar_gt_no_texto(
            registro["ground_truth"], resultado.texto
        )
        metadados[id_edital] = {
            "n_paginas": resultado.n_paginas,
            "n_paginas_ocr": resultado.n_paginas_ocr,
            "metodo": resultado.metodo,
            "caracteres": resultado.caracteres,
            "avisos": resultado.avisos,
        }
        logger.info(
            "%s: %d págs, %d chars, método=%s%s",
            id_edital, resultado.n_paginas, resultado.caracteres, resultado.metodo,
            f" avisos={resultado.avisos}" if resultado.avisos else "",
        )

    (DIR_PROCESSADOS / "extracao_meta.json").write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DIR_BENCHMARK / "benchmark.json").write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Processados %d/%d documentos", len(metadados), len(benchmark))
    return 0 if metadados and falhas == 0 else (0 if metadados else 1)


if __name__ == "__main__":
    garantir_diretorios()
    sys.exit(processar(carregar_config()))
