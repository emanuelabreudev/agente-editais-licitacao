"""Fixtures compartilhadas — tudo offline (sem rede, sem modelos de embedding)."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest


class FakeEmbedder:
    """Embedder determinístico por hashing de tokens (para testes/CI).

    Não captura semântica real, mas garante que textos iguais/parecidos tenham
    vetores próximos, o suficiente para exercitar FAISS e as métricas.
    """

    dim = 64

    def embed(self, textos: list[str]) -> np.ndarray:
        vetores = np.zeros((len(textos), self.dim), dtype=np.float32)
        for i, texto in enumerate(textos):
            for token in texto.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vetores[i, h % self.dim] += 1.0
        normas = np.linalg.norm(vetores, axis=1, keepdims=True)
        return vetores / np.clip(normas, 1e-12, None)


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


EDITAL_SINTETICO = """
PREFEITURA MUNICIPAL DE EXEMPLO - SP
PREGÃO ELETRÔNICO Nº 12/2026
PROCESSO ADMINISTRATIVO 100/2026

1. DO OBJETO
1.1. A presente licitação tem por objeto a aquisição de material escolar para a
rede municipal de ensino, conforme especificações do Termo de Referência.

2. DO VALOR ESTIMADO
2.1. O valor total estimado da contratação é de R$ 150.000,00 (cento e
cinquenta mil reais).

3. DAS PROPOSTAS
3.1. O encerramento do recebimento das propostas ocorrerá em 20/08/2026 às 09:00,
horário de Brasília.
3.2. A abertura da sessão pública ocorrerá em 20/08/2026 às 09:30.

4. DO JULGAMENTO
4.1. O critério de julgamento será o menor preço por item.

5. DO PRAZO DE EXECUÇÃO
5.1. O prazo de entrega dos materiais será de 30 (trinta) dias corridos.
"""
