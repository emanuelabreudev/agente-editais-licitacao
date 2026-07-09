"""Extração estruturada: rodar o agente ou o baseline e auditar as evidências."""

from __future__ import annotations

import streamlit as st

from edital_agent.ui import dados, execucao

st.title("Extração estruturada")
st.caption(
    "Roda o extrator sobre um edital do benchmark e exibe cada campo com sua "
    "evidência: chunk de origem, citação literal e validação da citação."
)

if dados.aviso_sem_dados():
    st.stop()

indexados = dados.editais_indexados()
ids = [r["id_edital"] for r in dados.benchmark()]

esq, dir_ = st.columns([3, 2])
with esq:
    id_edital = st.selectbox(
        "Edital", ids, format_func=lambda i: dados.rotulo_edital(dados.registro(i))
    )
with dir_:
    tipo, modelo = execucao.seletor_executor()

registro = dados.registro(id_edital)
gt = registro["ground_truth"]
pode_rodar = tipo == "baseline" or (
    id_edital in indexados and (modelo == "mock" or dados.chave_api_configurada())
)

col_a, col_b = st.columns([1, 3])
with col_a:
    rodar = st.button(
        "Executar extração", type="primary", disabled=not pode_rodar,
        icon=":material/play_arrow:", use_container_width=True,
    )
with col_b:
    salvo = dados.resultado_extracao(
        "baseline" if tipo == "baseline"
        else ("agente_mock" if modelo == "mock" else "agente"),
        id_edital,
    )
    if salvo:
        st.caption("Há um resultado salvo do pipeline para esta combinação (exibido abaixo).")

if tipo == "agente" and id_edital not in indexados:
    st.error("Edital não indexado. Rode `make indexar`.", icon=":material/error:")

chave_estado = f"extracao::{id_edital}::{tipo}::{modelo}"
if rodar:
    with st.spinner("Executando…", show_time=True):
        try:
            if tipo == "baseline":
                resultado = execucao.executar_baseline(dados.texto_edital(id_edital), id_edital)
            else:
                resultado = execucao.executar_agente(
                    dados.indice(id_edital), id_edital, modelo,
                    dados.config()["llm"]["max_iteracoes_agente"],
                )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Falha na extração: {exc}", icon=":material/error:")
            st.stop()
    st.session_state[chave_estado] = resultado
    st.toast("Extração concluída", icon=":material/check_circle:")

resultado = st.session_state.get(chave_estado) or salvo
if resultado is None:
    st.info(
        "Clique em **Executar extração** para rodar agora, ou selecione uma combinação "
        "já processada pelo pipeline.",
        icon=":material/touch_app:",
    )
    st.stop()

st.divider()

agente = execucao.e_agente(resultado)
if agente:
    execucao.renderizar_custo(resultado)
    st.divider()

st.subheader("Campos extraídos")
df = execucao.tabela_campos(resultado, ground_truth=gt)
execucao.renderizar_tabela(df)

acertos = df[df["acerto"].isin(["sim", "não"])] if "acerto" in df else df.iloc[:0]
if not acertos.empty:
    n_ok = (acertos["acerto"] == "sim").sum()
    st.caption(
        f"{n_ok}/{len(acertos)} campos conferem com o ground truth do PNCP "
        "(abstenções corretas — orçamento sigiloso — não entram na conta)."
    )

if agente:
    st.divider()
    st.subheader("Rastreabilidade de evidências")
    st.caption(
        "Cada campo cita o chunk de origem e um trecho literal; a citação é conferida "
        "contra os trechos que o agente de fato recuperou."
    )
    execucao.renderizar_evidencias(resultado)

    with st.expander("Trace das chamadas de ferramenta", icon=":material/timeline:"):
        execucao.renderizar_trace(resultado)

    with st.expander(
        f"Trechos recuperados ({len(resultado.get('contextos', []))})",
        icon=":material/inventory_2:",
    ):
        for ctx in resultado.get("contextos", []):
            st.markdown(f"`{ctx['chunk_id']}` · {ctx['secao'][:80]}")
else:
    st.divider()
    st.caption(
        "O baseline por regex não produz evidências rastreáveis — é essa a lacuna "
        "que o agente RAG endereça."
    )

execucao.botao_download(
    resultado, id_edital, "baseline" if not agente else f"agente_{modelo}"
)
