"""Sobre: pergunta de pesquisa, arquitetura, reprodutibilidade e ética."""

from __future__ import annotations

import streamlit as st

from edital_agent.ui import dados

st.title("Sobre o projeto")

st.markdown(
    """
### Pergunta de pesquisa

> Em que medida um agente autônomo baseado em **RAG** consegue extrair campos críticos
> (**prazo**, **valor estimado**, **modalidade**) de editais de licitação com
> **Faithfulness ≥ 0,85** e **Answer Correctness ≥ 0,80** (métricas RAGAS), usando o
> próprio texto do edital como referência, com **taxa de alucinação ≤ 10%**?

**Baseline comparativo**: extração por regex sobre o texto integral (meta de referência
de 80% de acurácia nos campos críticos).
"""
)

st.divider()
st.subheader("Arquitetura")
st.code(
    """PNCP (APIs públicas)
  │ 01_coletar    metadados oficiais → ground truth · download + SHA256
  ▼
data/raw/*.bin (PDF · DOCX · ZIP)
  │ 02_processar  pypdf + fallback OCR (Tesseract) + DOCX
  ▼
data/processed/*.txt
  │ 03_indexar    chunking semântico por seções (overlap) + FAISS (embeddings multilíngues)
  ▼
data/indices/<edital>/
  ├── AGENTE single-agent com tool use ──┐  buscar_trechos · ler_trecho · registrar_extracao
  └── BASELINE regex sobre o texto ──────┤
                                          ▼  04_extrair
        extração estruturada + evidências (chunk_id, citação literal, confiança)
                                          │  05_avaliar
                                          ▼
     RAGAS (Faithfulness, Answer Correctness) · taxa de alucinação
     acurácia por campo · custo/latência · IC bootstrap 95%""",
    language="text",
)

st.divider()
esq, dir_ = st.columns(2)

with esq:
    st.subheader("Controle de alucinação")
    st.markdown(
        """
1. **No prompt e no schema** — todo campo preenchido deve citar o `chunk_id` de origem e
   um trecho **literal**; o pós-processamento confere a citação contra os chunks que o
   agente de fato recuperou (`evidencia_valida`).
2. **Na métrica** — o *Faithfulness* decompõe a extração em afirmações atômicas e um juiz
   (LLM ou heurístico) decide se cada uma é inferível dos contextos recuperados. A **taxa
   de alucinação** é o complemento.
        """
    )
    st.subheader("Campos extraídos")
    st.markdown(
        """
| Campo | Tipo | Crítico |
|---|---|---|
| prazo_entrega_proposta | data | ✅ |
| valor_estimado | monetário | ✅ |
| modalidade | categórico | ✅ |
| objeto | texto | — |
| orgao_responsavel | texto | — |
| uf | categórico | — |
| criterio_julgamento | categórico | — |
| prazo_execucao | duração | — |
        """
    )

with dir_:
    st.subheader("Dados, ética e licença")
    st.markdown(
        """
- **Fonte**: Portal Nacional de Contratações Públicas (PNCP), APIs públicas sem
  autenticação — dados abertos pela **Lei 12.527/2011** (LAI).
- **Sem PII**: os documentos são atos administrativos públicos; não há anonimização
  necessária.
- **Ground truth**: metadados oficiais da contratação (fonte primária do governo).
- O sistema é **apoio à triagem** — não substitui análise jurídica ou profissional.
- Código sob licença MIT.
        """
    )

    st.subheader("Reprodutibilidade")
    st.code(
        """make setup              # venv + dependências fixadas
make test               # suíte offline (embedder fake, LLM mock)
make pipeline-offline   # coleta → processa → indexa → baseline → avalia → EDA
make smoke              # agente (mock) + avaliação, sem chave de API
make tudo               # pipeline completo com o agente real
make app                # esta interface""",
        language="bash",
    )
    st.caption(
        "Dependências fixadas, seeds fixas (bootstrap = 42), snapshot de coleta com SHA256 "
        "e CI executando a suíte a cada push."
    )

st.divider()
st.subheader("Estado do ambiente")
col = st.columns(4)
col[0].metric("Editais no benchmark", len(dados.benchmark()))
col[1].metric("Índices FAISS", len(dados.editais_indexados()))
col[2].metric("Avaliações prontas", len(dados.alvos_disponiveis()))
col[3].metric(
    "Chave Anthropic",
    "configurada" if dados.chave_api_configurada() else "ausente",
)

from edital_agent.extracao.pdf import ocr_disponivel  # noqa: E402

if not ocr_disponivel():
    st.info(
        "OCR indisponível: instale `tesseract-ocr`, `tesseract-ocr-por` e `poppler-utils` "
        "para processar PDFs escaneados.",
        icon=":material/document_scanner:",
    )

st.divider()
st.caption(
    "Referências: Es et al. (2023) *RAGAS: Automated Evaluation of Retrieval Augmented "
    "Generation*, arXiv:2309.15217 · Lewis et al. (2020) *Retrieval-Augmented Generation "
    "for Knowledge-Intensive NLP Tasks*, NeurIPS · Lei 14.133/2021 · Lei 12.527/2011."
)
