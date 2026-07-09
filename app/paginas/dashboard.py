"""Visão geral: composição do benchmark, metas da pesquisa e EDA."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from edital_agent.ui import dados, tema

st.title("Visão geral")
st.caption(
    "Benchmark piloto de editais coletados das APIs públicas do PNCP "
    "(Lei 12.527/2011), com ground truth vindo dos metadados oficiais."
)

if dados.aviso_sem_dados():
    st.stop()

bench = dados.benchmark()
resumo_eda = dados.eda()
stats_idx = dados.estatisticas_indice()
metas = dados.config()["avaliacao"]

# ------------------------------------------------------------------ hero tiles
col = st.columns(5)
col[0].metric("Editais", len(bench))
col[1].metric("Modalidades", len({r["ground_truth"]["modalidade"] for r in bench}))
col[2].metric("UFs", len({r["ground_truth"]["uf"] for r in bench}))
col[3].metric(
    "Chunks indexados",
    f"{sum(s['n_chunks'] for s in stats_idx.values()):,}".replace(",", "."),
)
paginas = resumo_eda.get("paginas", {})
col[4].metric(
    "Páginas (mediana)",
    f"{paginas.get('mediana', 0):.0f}" if paginas else "—",
    help=f"máx. {paginas.get('max', '—')} páginas" if paginas else None,
)

st.divider()

# ------------------------------------------------------- metas vs. resultados
st.subheader("Metas da pergunta de pesquisa")
st.caption(
    "Faithfulness ≥ 0,85 · Answer Correctness ≥ 0,80 · taxa de alucinação ≤ 0,10 "
    "nos campos críticos (prazo, valor estimado, modalidade)."
)

alvos = dados.alvos_disponiveis()
alvo_agente = "agente" if "agente" in alvos else ("agente_mock" if "agente_mock" in alvos else None)
aval_agente = dados.avaliacao(alvo_agente) if alvo_agente else None
aval_baseline = dados.avaliacao("baseline")

if alvo_agente == "agente_mock":
    st.info(
        "Nenhuma execução do agente com LLM real encontrada — exibindo o **smoke test "
        "offline (MockLLM)**, que valida o pipeline mas não mede o agente real. "
        "Rode `make agente && make avaliar` com uma chave da Anthropic.",
        icon=":material/science:",
    )


def _tile(coluna, rotulo: str, valor: float | None, meta: float, maior_melhor: bool = True):
    with coluna:
        st.metric(rotulo, tema.formatar_pct(valor))
        if valor is None:
            st.caption("sem dados")
            return
        atingiu = valor >= meta if maior_melhor else valor <= meta
        sinal = "≥" if maior_melhor else "≤"
        st.badge(
            f"meta {sinal} {meta:.0%} · {'atingida' if atingiu else 'não atingida'}",
            color="green" if atingiu else "red",
            icon=":material/check:" if atingiu else ":material/close:",
        )


def _media(aval: dict | None, metrica: str) -> float | None:
    if not aval or metrica not in aval["resumo"]:
        return None
    return aval["resumo"][metrica]["media"]


colunas = st.columns(4)
_tile(colunas[0], "Faithfulness", _media(aval_agente, "faithfulness"),
      metas["meta_faithfulness"])
_tile(colunas[1], "Answer Correctness", _media(aval_agente, "answer_correctness"),
      metas["meta_answer_correctness"])
_tile(colunas[2], "Taxa de alucinação", _media(aval_agente, "taxa_alucinacao"),
      metas["meta_taxa_alucinacao"], maior_melhor=False)
_tile(colunas[3], "Acurácia críticos (baseline)",
      _media(aval_baseline, "acuracia_criticos"), metas["meta_precisao_baseline"])

if alvo_agente:
    st.caption(
        f"Fonte: `{dados.EXECUTORES[alvo_agente]}` · baseline regex sobre o texto integral. "
        "Detalhes e intervalos de confiança em **Avaliação RAGAS**."
    )

st.divider()

# --------------------------------------------------------------------- EDA
st.subheader("Composição da amostra")

esq, dir_ = st.columns(2)
with esq:
    modalidades = (
        pd.Series([r["ground_truth"]["modalidade"] for r in bench])
        .value_counts()
        .rename_axis("modalidade")
        .reset_index(name="editais")
    )
    st.altair_chart(
        tema.barras_horizontais(
            modalidades, "editais", "modalidade", "Editais por modalidade",
            rotulo_valor="editais",
        ),
        use_container_width=True,
    )
with dir_:
    ufs = (
        pd.Series([r["ground_truth"]["uf"] for r in bench])
        .value_counts()
        .rename_axis("uf")
        .reset_index(name="editais")
    )
    st.altair_chart(
        tema.barras_horizontais(
            ufs, "editais", "uf", "Editais por UF", rotulo_valor="editais",
        ),
        use_container_width=True,
    )

com_valor = pd.DataFrame(
    [
        {
            "edital": f"{r['municipio']}/{r['ground_truth']['uf']}",
            "valor": r["ground_truth"]["valor_estimado"],
        }
        for r in bench
        if r["ground_truth"]["valor_estimado"]
    ]
).sort_values("valor", ascending=False)
n_sigiloso = sum(1 for r in bench if r["ground_truth"]["valor_estimado"] is None)

st.altair_chart(
    tema.pontos_log(
        com_valor, "valor", "edital",
        titulo=f"Valor estimado por edital (escala log) — "
               f"{n_sigiloso} caso(s) com orçamento sigiloso/ausente",
        rotulo_valor="valor estimado (R$)",
    ),
    use_container_width=True,
)

st.divider()

# -------------------------------------------- disponibilidade do GT no texto
st.subheader("Ground truth verificável no texto do documento")
st.caption(
    "Alguns órgãos publicam no PNCP apenas documentos resumidos. A fração abaixo é o "
    "**teto de qualquer extrator** — as métricas também são reportadas restritas a "
    "estes campos."
)
disponibilidade = resumo_eda.get("gt_verificavel_no_texto_pct", {})
if disponibilidade:
    df_disp = pd.DataFrame(
        [{"campo": k.replace("_", " "), "fração": v} for k, v in disponibilidade.items()]
    ).sort_values("fração", ascending=False)
    st.altair_chart(
        tema.barras_horizontais(
            df_disp, "fração", "campo",
            "Fração dos editais em que o valor oficial aparece no texto",
            rotulo_valor="fração dos editais", formato=".0%",
        ),
        use_container_width=True,
    )

with st.expander("Como o pipeline funciona"):
    st.markdown(
        """
| Etapa | O que faz | Módulo |
|---|---|---|
| **1. Coleta** | APIs públicas do PNCP: metadados (ground truth) + download do edital, com SHA256 | `coleta/pncp.py` |
| **2. Extração** | pypdf, DOCX e ZIP; fallback de OCR (Tesseract) em páginas escaneadas | `extracao/pdf.py` |
| **3. Indexação** | Chunking semântico por seções (overlap) + FAISS com embeddings multilíngues | `indexacao/` |
| **4. Agente** | Single-agent com *tool use*: busca semântica, leitura de trechos e extração estruturada (schema estrito) | `agente/agente.py` |
| **5. Baseline** | Extração por regex sobre o texto integral (abordagem por regras) | `baseline/regex_extractor.py` |
| **6. Avaliação** | RAGAS (Faithfulness, Answer Correctness), taxa de alucinação, custo/latência, IC bootstrap | `avaliacao/` |
"""
    )
