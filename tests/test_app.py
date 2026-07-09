"""Smoke test da interface: cada página renderiza sem exceção.

Usa o AppTest do Streamlit, que executa os scripts de página de verdade
(sem navegador). Páginas que dependem dos índices FAISS são puladas quando
o pipeline ainda não foi executado.
"""

from __future__ import annotations

import pytest

from edital_agent.config import DIR_BENCHMARK, DIR_INDICES

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

TEM_BENCHMARK = (DIR_BENCHMARK / "benchmark.json").exists()
TEM_INDICES = DIR_INDICES.exists() and any(DIR_INDICES.glob("*/index.faiss"))

precisa_benchmark = pytest.mark.skipif(
    not TEM_BENCHMARK, reason="benchmark não construído (rode `make pipeline-offline`)"
)
precisa_indices = pytest.mark.skipif(
    not TEM_INDICES, reason="índices FAISS ausentes (rode `make indexar`)"
)


def _rodar(caminho: str) -> "AppTest":
    app = AppTest.from_file(caminho, default_timeout=120)
    app.run()
    return app


@pytest.mark.parametrize(
    "pagina",
    ["app/paginas/dashboard.py", "app/paginas/editais.py", "app/paginas/avaliacao.py",
     "app/paginas/extracao.py", "app/paginas/sobre.py", "app/paginas/novo_edital.py"],
)
@precisa_benchmark
def test_pagina_renderiza_sem_excecao(pagina: str):
    app = _rodar(pagina)
    assert not app.exception, [e.value for e in app.exception]


@precisa_benchmark
def test_dashboard_mostra_metricas():
    app = _rodar("app/paginas/dashboard.py")
    rotulos = [m.label for m in app.metric]
    assert "Editais" in rotulos and "UFs" in rotulos


@precisa_indices
@precisa_benchmark
def test_busca_semantica_retorna_trechos():
    app = _rodar("app/paginas/busca.py")
    assert not app.exception, [e.value for e in app.exception]
    # sem consulta, a página orienta o usuário em vez de quebrar
    app.text_input[0].set_value("valor total estimado da contratação").run()
    assert not app.exception, [e.value for e in app.exception]
    assert any("trecho(s) recuperado(s)" in m.value for m in app.markdown)
