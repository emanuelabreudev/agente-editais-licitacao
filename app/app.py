"""Interface do Agente Autônomo para Análise de Editais de Licitação.

Execução:  streamlit run app/app.py     (ou `make app`)
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "src") not in sys.path:  # funciona mesmo sem `pip install -e .`
    sys.path.insert(0, str(RAIZ / "src"))

st.set_page_config(
    page_title="Agente de Editais de Licitação",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

from edital_agent.ui import dados, tema  # noqa: E402

tema.estilo_global()

with st.sidebar:
    st.title("📄 Agente de Editais")
    st.caption(
        "Extração estruturada de editais de licitação (PNCP) com RAG, "
        "rastreabilidade de evidências e avaliação RAGAS."
    )

paginas = [
    st.Page("paginas/dashboard.py", title="Visão geral", icon=":material/dashboard:",
            default=True),
    st.Page("paginas/editais.py", title="Editais", icon=":material/description:"),
    st.Page("paginas/busca.py", title="Busca semântica", icon=":material/search:"),
    st.Page("paginas/extracao.py", title="Extração", icon=":material/smart_toy:"),
    st.Page("paginas/avaliacao.py", title="Avaliação RAGAS", icon=":material/bar_chart:"),
    st.Page("paginas/novo_edital.py", title="Analisar novo edital",
            icon=":material/upload_file:"),
    st.Page("paginas/sobre.py", title="Sobre o projeto", icon=":material/info:"),
]

dados.barra_lateral_chave()
st.navigation(paginas).run()
