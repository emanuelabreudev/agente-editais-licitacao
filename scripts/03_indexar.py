"""Etapa 3 — Chunking semântico e indexação vetorial (FAISS) por edital.

Uso: python scripts/03_indexar.py
"""

from __future__ import annotations

import json
import logging
import sys

from edital_agent.config import (
    DIR_INDICES, DIR_PROCESSADOS, carregar_config, garantir_diretorios,
)
from edital_agent.indexacao.chunking import dividir_em_chunks
from edital_agent.indexacao.vetorial import FastEmbedEmbedder, IndiceVetorial

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("indexar")


def indexar(config: dict) -> int:
    cfg = config["indexacao"]
    embedder = FastEmbedEmbedder.compartilhado(cfg["modelo_embedding"])
    textos = sorted(DIR_PROCESSADOS.glob("*.txt"))
    if not textos:
        logger.error("Nenhum texto em %s (rode 02_processar.py)", DIR_PROCESSADOS)
        return 1

    estatisticas: dict[str, dict] = {}
    for caminho in textos:
        id_edital = caminho.stem
        texto = caminho.read_text(encoding="utf-8")
        chunks = dividir_em_chunks(
            texto, id_edital=id_edital, tamanho=cfg["tamanho_chunk"], overlap=cfg["overlap"]
        )
        if not chunks:
            logger.warning("Sem chunks para %s (texto vazio?)", id_edital)
            continue
        indice = IndiceVetorial(chunks, embedder)
        indice.salvar(DIR_INDICES / id_edital)
        estatisticas[id_edital] = {
            "n_chunks": len(chunks),
            "chars_medio": round(sum(len(c.texto) for c in chunks) / len(chunks)),
            "n_secoes": len({c.secao for c in chunks}),
        }
        logger.info("%s: %d chunks, %d seções", id_edital, len(chunks),
                    estatisticas[id_edital]["n_secoes"])

    (DIR_INDICES / "estatisticas.json").write_text(
        json.dumps(estatisticas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if estatisticas else 1


if __name__ == "__main__":
    garantir_diretorios()
    sys.exit(indexar(carregar_config()))
