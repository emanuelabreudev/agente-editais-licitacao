"""Avaliação: métricas RAGAS, acurácia por campo, comparação e custo."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from edital_agent.ui import dados, tema
from edital_agent.ui.execucao import ROTULOS_CAMPO

st.title("Avaliação RAGAS")
st.caption(
    "Faithfulness e Answer Correctness conforme Es et al. (2023), taxa de alucinação, "
    "acurácia contra o ground truth do PNCP e IC 95% por bootstrap (2.000 reamostragens)."
)

if dados.aviso_sem_dados():
    st.stop()

alvos = dados.alvos_disponiveis()
if not alvos:
    st.warning(
        "Nenhuma avaliação encontrada. Rode `make smoke` (offline) ou "
        "`make avaliar` (LLM real).",
        icon=":material/analytics:",
    )
    st.stop()

metas = dados.config()["avaliacao"]
alvos_agente = [a for a in alvos if a.startswith("agente")]
alvo = st.selectbox(
    "Execução avaliada", alvos, format_func=lambda a: dados.EXECUTORES[a],
    index=alvos.index(alvos_agente[0]) if alvos_agente else 0,
)
aval = dados.avaliacao(alvo)
resumo, por_edital = aval["resumo"], aval["por_edital"]
e_agente = alvo.startswith("agente")

if alvo == "agente_mock":
    st.info(
        "Smoke test offline (MockLLM + juiz heurístico): valida a instrumentação "
        "ponta a ponta, mas **não** mede o agente com LLM.",
        icon=":material/science:",
    )

st.caption(
    f"n = {resumo['n_editais']} editais"
    + (f" · juiz: {resumo.get('juiz')}" if e_agente else "")
)


def _ic(metrica: str) -> str:
    m = resumo.get(metrica)
    if not m or m["media"] is None:
        return "—"
    ic = m["ic95_bootstrap"]
    if not ic:
        return tema.formatar_pct(m["media"])
    return f"IC95 {tema.formatar_pct(ic[0])}–{tema.formatar_pct(ic[1])}"


def _tile(coluna, rotulo: str, metrica: str, meta: float | None, maior_melhor=True):
    m = resumo.get(metrica)
    valor = m["media"] if m else None
    with coluna:
        st.metric(rotulo, tema.formatar_pct(valor), help=_ic(metrica))
        if valor is None or meta is None:
            return
        atingiu = valor >= meta if maior_melhor else valor <= meta
        st.badge(
            f"meta {'≥' if maior_melhor else '≤'} {meta:.0%}",
            color="green" if atingiu else "red",
            icon=":material/check:" if atingiu else ":material/close:",
        )
        if m["desvio_padrao"]:
            st.caption(f"desvio-padrão {m['desvio_padrao']:.3f}")


# ------------------------------------------------------------------ métricas
if e_agente:
    st.subheader("Métricas da pergunta de pesquisa")
    col = st.columns(4)
    _tile(col[0], "Faithfulness", "faithfulness", metas["meta_faithfulness"])
    _tile(col[1], "Answer Correctness", "answer_correctness",
          metas["meta_answer_correctness"])
    _tile(col[2], "Taxa de alucinação", "taxa_alucinacao",
          metas["meta_taxa_alucinacao"], maior_melhor=False)
    _tile(col[3], "Citações válidas", "proporcao_citacoes_validas", None)

    with st.expander("Decomposição e variantes restritas ao texto disponível"):
        col2 = st.columns(4)
        _tile(col2[0], "Faithfulness (críticos)", "faithfulness_criticos", None)
        _tile(col2[1], "AC · F1 factual", "answer_correctness_f1", None)
        _tile(col2[2], "AC · similaridade semântica",
              "answer_correctness_similaridade", None)
        _tile(col2[3], "AC · campos disponíveis no texto",
              "answer_correctness_disponivel", None)
        st.caption(
            "Answer Correctness = 0,75 · F1 factual + 0,25 · similaridade semântica "
            "(pesos padrão do RAGAS). A variante *disponíveis no texto* exclui campos "
            "cujo valor oficial não aparece no documento publicado."
        )
else:
    st.subheader("Acurácia do baseline")
    col = st.columns(3)
    _tile(col[0], "Campos críticos", "acuracia_criticos", metas["meta_precisao_baseline"])
    _tile(col[1], "Críticos disponíveis no texto", "acuracia_criticos_disponiveis",
          metas["meta_precisao_baseline"])
    m_lat = resumo.get("latencia_s", {})
    col[2].metric("Latência média", f"{m_lat.get('media', 0):.3f} s")

st.divider()

# ------------------------------------------------- acurácia por campo (comparação)
st.subheader("Acurácia por campo vs. ground truth")

linhas = []
for a in alvos:
    resumo_a = dados.avaliacao(a)["resumo"]
    for campo, info in resumo_a["acuracia_por_campo"].items():
        if info["acuracia"] is None:
            continue
        linhas.append(
            {
                "campo": ROTULOS_CAMPO.get(campo, campo),
                "extrator": dados.EXECUTORES[a],
                "acurácia": info["acuracia"],
            }
        )
df_campos = pd.DataFrame(linhas)
if not df_campos.empty:
    st.altair_chart(
        tema.barras_agrupadas(
            df_campos, "acurácia", "campo", "extrator",
            titulo="Acurácia por campo (todos os editais)",
            rotulo_valor="acurácia",
        ),
        use_container_width=True,
    )
    st.caption(
        "Campos categóricos (modalidade, critério) são fáceis para regras; prazo e valor "
        "concentram os erros — a lacuna que motiva a abordagem RAG."
    )

st.divider()

# --------------------------------------------------------------- por edital
st.subheader("Resultados por edital")

registros = {r["id_edital"]: r for r in dados.benchmark()}
linhas_edital = []
for e in por_edital:
    reg = registros.get(e["id_edital"], {})
    gt = reg.get("ground_truth", {})
    linha = {
        "edital": f"{reg.get('municipio', '?')}/{gt.get('uf', '?')}",
        "modalidade": gt.get("modalidade", "—"),
    }
    if e_agente:
        linha |= {
            "faithfulness": e["faithfulness"],
            "answer correctness": e["answer_correctness"],
            "alucinação": e["taxa_alucinacao"],
            "citações válidas": e["proporcao_citacoes_validas"],
            "custo (US$)": e.get("uso", {}).get("custo_usd"),
            "iterações": e.get("iteracoes"),
        }
    linha |= {
        "acurácia críticos": e["acuracia_criticos"],
        "críticos disponíveis": e.get("acuracia_criticos_disponiveis"),
        "latência (s)": e["latencia_s"],
    }
    linhas_edital.append(linha)

df_edital = pd.DataFrame(linhas_edital)
config_colunas = {
    c: st.column_config.NumberColumn(format="%.2f")
    for c in ("faithfulness", "answer correctness", "alucinação", "citações válidas",
              "acurácia críticos", "críticos disponíveis")
    if c in df_edital
}
if "custo (US$)" in df_edital:
    config_colunas["custo (US$)"] = st.column_config.NumberColumn(format="$ %.4f")
if "latência (s)" in df_edital:
    config_colunas["latência (s)"] = st.column_config.NumberColumn(format="%.2f")

st.dataframe(df_edital, use_container_width=True, hide_index=True,
             column_config=config_colunas)

if e_agente and "faithfulness" in df_edital:
    st.altair_chart(
        tema.barras_horizontais(
            df_edital.sort_values("faithfulness", ascending=False)[["edital", "faithfulness"]],
            "faithfulness", "edital",
            "Faithfulness por edital", rotulo_valor="faithfulness",
            formato=".2f", altura_barra=24,
        ),
        use_container_width=True,
    )

# ----------------------------------------------------------------- custo total
if e_agente:
    custo_total = sum((e.get("uso", {}).get("custo_usd") or 0) for e in por_edital)
    tokens = sum((e.get("uso", {}).get("tokens_entrada") or 0) for e in por_edital)
    latencia = sum((e.get("latencia_s") or 0) for e in por_edital)
    col = st.columns(4)
    col[0].metric("Custo total do benchmark", f"US$ {custo_total:.4f}")
    col[1].metric("Custo médio por edital", f"US$ {custo_total / max(1, len(por_edital)):.4f}")
    col[2].metric("Tokens de entrada", f"{tokens:,}".replace(",", "."))
    col[3].metric("Latência total", f"{latencia:.0f} s")
    if resumo.get("custo_juiz"):
        st.caption(
            f"Custo do juiz LLM na avaliação: "
            f"US$ {resumo['custo_juiz']['custo_usd']:.4f} "
            f"({resumo['custo_juiz']['chamadas']} chamadas)"
        )

st.download_button(
    "Baixar avaliação completa (JSON)",
    json.dumps(aval, ensure_ascii=False, indent=2).encode("utf-8"),
    f"avaliacao_{alvo}.json",
    "application/json",
    icon=":material/download:",
)
