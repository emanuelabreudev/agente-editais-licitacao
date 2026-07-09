"""Explorador de editais: metadados oficiais, documento, texto e chunks."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from edital_agent.ui import dados, tema

st.title("Editais do benchmark")

if dados.aviso_sem_dados():
    st.stop()

bench = dados.benchmark()
docs = dados.documentos()
metas_extracao = dados.meta_extracao()
stats_idx = dados.estatisticas_indice()

visao = st.segmented_control(
    "Visão", ["Tabela", "Detalhe do edital"], default="Tabela", label_visibility="collapsed"
)

# ------------------------------------------------------------------- tabela
if visao == "Tabela":
    linhas = []
    for r in bench:
        gt = r["ground_truth"]
        m = metas_extracao.get(r["id_edital"], {})
        linhas.append(
            {
                "id": r["id_edital"],
                "órgão": gt["orgao_responsavel"],
                "UF": gt["uf"],
                "modalidade": gt["modalidade"],
                "valor estimado": gt["valor_estimado"],
                "prazo propostas": gt["prazo_entrega_proposta"],
                "critério": gt["criterio_julgamento"],
                "páginas": m.get("n_paginas"),
                "caracteres": m.get("caracteres"),
                "extração": m.get("metodo"),
                "chunks": stats_idx.get(r["id_edital"], {}).get("n_chunks"),
                "objeto": gt["objeto"],
            }
        )
    df = pd.DataFrame(linhas)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "valor estimado": st.column_config.NumberColumn(format="R$ %.2f"),
            "caracteres": st.column_config.NumberColumn(format="%d"),
            "objeto": st.column_config.TextColumn(width="large"),
            "id": st.column_config.TextColumn(width="medium"),
        },
    )
    st.download_button(
        "Baixar benchmark (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        "benchmark.csv",
        "text/csv",
        icon=":material/download:",
    )
    st.caption(
        "Ground truth = metadados oficiais da contratação no PNCP. "
        "Hashes SHA256 dos documentos em `data/data_card.md`."
    )
    st.stop()

# ------------------------------------------------------------------ detalhe
ids = [r["id_edital"] for r in bench]
id_edital = st.selectbox(
    "Edital",
    ids,
    format_func=lambda i: dados.rotulo_edital(dados.registro(i)),
)
registro = dados.registro(id_edital)
gt = registro["ground_truth"]
doc = docs.get(id_edital, {})
meta = metas_extracao.get(id_edital, {})

st.subheader(gt["orgao_responsavel"] or registro["municipio"])
st.caption(f"`{registro['numero_controle_pncp']}` · {registro['situacao']}")

col = st.columns(4)
col[0].metric("Modalidade", gt["modalidade"])
col[1].metric("Valor estimado", tema.formatar_moeda(gt["valor_estimado"]))
col[2].metric("Prazo p/ propostas", (gt["prazo_entrega_proposta"] or "—")[:16].replace("T", " "))
col[3].metric("Critério de julgamento", gt["criterio_julgamento"] or "—")

st.markdown(f"**Objeto** · {gt['objeto']}")

esq, dir_ = st.columns([3, 2])

with esq:
    st.markdown("##### Documento")
    st.markdown(
        f"""
- **Título**: {doc.get('titulo', '—')}
- **Tipo**: {doc.get('tipo_documento', '—')}
- **Tamanho**: {doc.get('bytes', 0) / 1024:.0f} KB · **SHA256**: `{doc.get('sha256', '')[:20]}…`
- **Páginas**: {meta.get('n_paginas', '—')} · **Caracteres extraídos**: {meta.get('caracteres', 0):,}
- **Método de extração**: `{meta.get('metodo', '—')}`
  {f"(OCR em {meta['n_paginas_ocr']} página(s))" if meta.get('n_paginas_ocr') else ""}
- **Chunks indexados**: {stats_idx.get(id_edital, {}).get('n_chunks', '—')}
        """.replace(",", ".")
    )
    for aviso in meta.get("avisos", []):
        st.warning(aviso, icon=":material/warning:")

with dir_:
    st.markdown("##### Ground truth verificável no texto")
    st.caption("Campos oficiais que aparecem no documento publicado.")
    presente = registro.get("gt_presente_no_texto", {})
    if not presente:
        st.caption("Não anotado (rode `make processar`).")
    for campo, ok in presente.items():
        st.markdown(
            f"{':material/check_circle:' if ok else ':material/cancel:'} "
            f"{campo.replace('_', ' ')} "
            f"{'' if ok else '— ausente no texto'}"
        )

st.divider()

texto = dados.texto_edital(id_edital)
aba_texto, aba_chunks = st.tabs(["Texto extraído", "Chunks"])

with aba_texto:
    busca = st.text_input(
        "Localizar no texto", placeholder="ex.: encerramento das propostas",
        icon=":material/search:",
    )
    if busca:
        ocorrencias = [
            i for i in range(len(texto)) if texto.lower().startswith(busca.lower(), i)
        ]
        st.caption(f"{len(ocorrencias)} ocorrência(s)")
        for pos in ocorrencias[:8]:
            trecho = texto[max(0, pos - 220): pos + 260]
            tema.cartao_trecho(
                f"posição {pos:,}".replace(",", "."), trecho,
                f"{id_edital}@{pos}", destaque=busca,
            )
        if not ocorrencias:
            st.info("Nenhuma ocorrência.", icon=":material/search_off:")
    else:
        st.text_area("Conteúdo", texto[:120_000], height=420, label_visibility="collapsed")
        if len(texto) > 120_000:
            st.caption(f"Exibindo 120.000 de {len(texto):,} caracteres.".replace(",", "."))

with aba_chunks:
    if id_edital not in dados.editais_indexados():
        st.info("Edital ainda não indexado. Rode `make indexar`.", icon=":material/info:")
    else:
        indice = dados.indice(id_edital)
        st.caption(
            f"{len(indice.chunks)} chunks · "
            f"{len({c.secao for c in indice.chunks})} seções distintas · "
            f"{sum(len(c.texto) for c in indice.chunks) // len(indice.chunks)} caracteres/chunk"
        )
        secoes = (
            pd.Series([c.secao for c in indice.chunks])
            .value_counts()
            .head(15)
            .rename_axis("seção")
            .reset_index(name="chunks")
        )
        st.altair_chart(
            tema.barras_horizontais(
                secoes, "chunks", "seção", "Seções com mais chunks (top 15)",
                rotulo_valor="chunks",
            ),
            use_container_width=True,
        )
        indice_chunk = st.number_input(
            "Inspecionar chunk nº", 0, len(indice.chunks) - 1, 0, step=1
        )
        chunk = indice.chunks[int(indice_chunk)]
        tema.cartao_trecho(chunk.secao, chunk.texto, chunk.id)
