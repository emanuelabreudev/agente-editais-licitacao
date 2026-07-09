"""Playground de busca semântica (a ferramenta `buscar_trechos` do agente)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from edital_agent.ui import dados, tema

st.title("Busca semântica")
st.caption(
    "Consulta o índice FAISS de um edital — exatamente a ferramenta `buscar_trechos` "
    "que o agente usa para recuperar evidências."
)

if dados.aviso_sem_dados():
    st.stop()

indexados = dados.editais_indexados()
if not indexados:
    st.info("Nenhum índice encontrado. Rode `make indexar`.", icon=":material/info:")
    st.stop()

ids = [r["id_edital"] for r in dados.benchmark() if r["id_edital"] in indexados]
esq, dir_ = st.columns([3, 1])
with esq:
    id_edital = st.selectbox(
        "Edital", ids, format_func=lambda i: dados.rotulo_edital(dados.registro(i))
    )
with dir_:
    top_k = st.slider("Trechos (top-k)", 1, 10, 5)

PRESETS = {
    "Prazo das propostas": "data limite para entrega e encerramento do recebimento das propostas",
    "Valor estimado": "valor total estimado da contratação",
    "Modalidade": "modalidade da licitação pregão eletrônico concorrência",
    "Critério de julgamento": "critério de julgamento menor preço",
    "Habilitação": "documentos exigidos para habilitação jurídica e fiscal",
    "Prazo de execução": "prazo de execução e vigência do contrato",
    "Sanções": "penalidades multa e sanções administrativas",
}

escolha = st.pills(
    "Consultas de exemplo", list(PRESETS), selection_mode="single",
    label_visibility="collapsed",
)
consulta = st.text_input(
    "Consulta",
    value=PRESETS.get(escolha, ""),
    placeholder="ex.: garantia contratual exigida do licitante vencedor",
    icon=":material/search:",
)

if not consulta:
    st.info("Escolha uma consulta de exemplo ou escreva a sua.", icon=":material/lightbulb:")
    st.stop()

indice = dados.indice(id_edital)
resultados = indice.buscar(consulta, top_k=top_k)

if not resultados:
    st.warning("Nenhum trecho recuperado.", icon=":material/search_off:")
    st.stop()

st.markdown(f"##### {len(resultados)} trecho(s) recuperado(s)")

df_scores = pd.DataFrame(
    [
        {"chunk": chunk.id.split("#")[-1], "similaridade": score}
        for chunk, score in resultados
    ]
)
st.altair_chart(
    tema.barras_horizontais(
        df_scores, "similaridade", "chunk", "Similaridade de cosseno por trecho",
        rotulo_valor="similaridade", formato=".3f", altura_barra=26,
    ),
    use_container_width=True,
)

mostrar_vizinhos = st.toggle(
    "Expandir contexto (chunks vizinhos)",
    help="Equivale à ferramenta `ler_trecho` do agente, com janela ±1.",
)

for chunk, score in resultados:
    if mostrar_vizinhos:
        vizinhos = indice.obter_chunk(chunk.id, janela=1)
        texto = "\n\n[…]\n\n".join(v.texto for v in vizinhos)
        tema.cartao_trecho(
            f"{chunk.secao}  ·  {len(vizinhos)} chunks", texto, chunk.id, score
        )
    else:
        tema.cartao_trecho(chunk.secao, chunk.texto, chunk.id, score)
