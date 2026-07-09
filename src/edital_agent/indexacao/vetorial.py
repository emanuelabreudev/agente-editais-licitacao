"""Indexação vetorial com FAISS + embeddings multilíngues (fastembed/ONNX).

Um índice por edital: data/indices/<id_edital>/{index.faiss, chunks.json}.
A busca usa produto interno sobre vetores normalizados (similaridade de cosseno).

O embedder é injetável para permitir testes offline (ver FakeEmbedder em tests/).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

import numpy as np

from .chunking import Chunk

logger = logging.getLogger(__name__)

MODELO_PADRAO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    def embed(self, textos: list[str]) -> np.ndarray: ...


class FastEmbedEmbedder:
    """Embeddings multilíngues via fastembed (ONNX, CPU, sem torch)."""

    _instancias: dict[str, "FastEmbedEmbedder"] = {}

    def __init__(self, modelo: str = MODELO_PADRAO):
        from fastembed import TextEmbedding

        self.modelo = modelo
        self._model = TextEmbedding(model_name=modelo)

    @classmethod
    def compartilhado(cls, modelo: str = MODELO_PADRAO) -> "FastEmbedEmbedder":
        """Reaproveita a instância (o carregamento do modelo ONNX é caro)."""
        if modelo not in cls._instancias:
            cls._instancias[modelo] = cls(modelo)
        return cls._instancias[modelo]

    def embed(self, textos: list[str]) -> np.ndarray:
        vetores = np.array(list(self._model.embed(textos)), dtype=np.float32)
        normas = np.linalg.norm(vetores, axis=1, keepdims=True)
        return vetores / np.clip(normas, 1e-12, None)


class IndiceVetorial:
    """Índice FAISS de chunks de um edital, com persistência em disco."""

    def __init__(self, chunks: list[Chunk], embedder: Embedder, indice=None):
        import faiss

        self.chunks = chunks
        self.embedder = embedder
        self._por_id = {c.id: i for i, c in enumerate(chunks)}
        if indice is not None:
            self.indice = indice
        else:
            vetores = embedder.embed([c.texto for c in chunks])
            self.indice = faiss.IndexFlatIP(vetores.shape[1])
            self.indice.add(vetores)

    def buscar(self, consulta: str, top_k: int = 5) -> list[tuple[Chunk, float]]:
        vetor = self.embedder.embed([consulta])
        top_k = min(top_k, len(self.chunks))
        scores, indices = self.indice.search(vetor, top_k)
        return [
            (self.chunks[i], float(s))
            for i, s in zip(indices[0], scores[0])
            if i >= 0
        ]

    def obter_chunk(self, chunk_id: str, janela: int = 0) -> list[Chunk]:
        """Devolve o chunk pedido e, opcionalmente, os vizinhos (contexto)."""
        if chunk_id not in self._por_id:
            return []
        i = self._por_id[chunk_id]
        ini, fim = max(0, i - janela), min(len(self.chunks), i + janela + 1)
        return self.chunks[ini:fim]

    def salvar(self, diretorio: Path) -> None:
        import faiss

        diretorio.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.indice, str(diretorio / "index.faiss"))
        dados = [
            {
                "id": c.id,
                "texto": c.texto,
                "secao": c.secao,
                "posicao": c.posicao,
                "id_edital": c.id_edital,
            }
            for c in self.chunks
        ]
        (diretorio / "chunks.json").write_text(
            json.dumps(dados, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def carregar(cls, diretorio: Path, embedder: Embedder) -> "IndiceVetorial":
        import faiss

        indice = faiss.read_index(str(diretorio / "index.faiss"))
        dados = json.loads((diretorio / "chunks.json").read_text(encoding="utf-8"))
        chunks = [Chunk(**d) for d in dados]
        return cls(chunks, embedder, indice=indice)
