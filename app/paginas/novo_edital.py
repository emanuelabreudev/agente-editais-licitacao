"""Analisar um edital novo: upload de arquivo ou busca direta no PNCP."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import streamlit as st

from edital_agent.coleta import pncp
from edital_agent.extracao.pdf import extrair_texto, ocr_disponivel, resolver_documento
from edital_agent.indexacao.chunking import dividir_em_chunks
from edital_agent.indexacao.vetorial import IndiceVetorial
from edital_agent.ui import dados, execucao, tema

st.title("Analisar novo edital")
st.caption(
    "Pipeline completo sob demanda: extração de texto → chunking → índice vetorial → "
    "extração estruturada. Nada é gravado no benchmark."
)

PADRAO_CONTROLE = re.compile(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$")


def _preparar_indice(caminho: Path, id_edital: str, cfg: dict):
    documento = resolver_documento(caminho)
    resultado = extrair_texto(
        documento,
        min_chars_por_pagina=cfg["extracao"]["min_chars_por_pagina"],
        ocr_dpi=cfg["extracao"]["ocr_dpi"],
        max_paginas=cfg["coleta"].get("max_paginas_pdf"),
    )
    if not resultado.texto.strip():
        raise ValueError(
            "Nenhum texto extraído. O PDF é escaneado e o OCR está "
            + ("indisponível." if not ocr_disponivel() else "falhou.")
        )
    chunks = dividir_em_chunks(
        resultado.texto, id_edital=id_edital,
        tamanho=cfg["indexacao"]["tamanho_chunk"], overlap=cfg["indexacao"]["overlap"],
    )
    indice = IndiceVetorial(chunks, dados.embedder())
    return resultado, indice


def _baixar_do_pncp(cnpj: str, ano: int, sequencial: int, destino: Path) -> dict:
    cliente = pncp.PNCPClient(timeout_s=dados.config()["coleta"]["timeout_s"])
    try:
        arquivos = cliente.listar_arquivos(cnpj, ano, sequencial)
        escolhido = pncp.escolher_arquivo_edital(arquivos)
        if escolhido is None:
            raise ValueError("A contratação não possui documentos ativos no PNCP.")
        meta = cliente.baixar_arquivo(pncp.url_download_arquivo(escolhido), destino)
        meta["titulo"] = escolhido.get("titulo")
        meta["tipo_documento"] = escolhido.get("tipoDocumentoNome")
        return meta
    finally:
        cliente.fechar()


cfg = dados.config()
aba_upload, aba_pncp = st.tabs(["Enviar arquivo", "Buscar no PNCP"])

fonte = None  # (caminho, id_edital, rotulo)

with aba_upload:
    enviado = st.file_uploader(
        "Edital em PDF, DOCX ou ZIP", type=["pdf", "docx", "zip"],
        help="O arquivo é processado em memória/tmp e descartado ao fim da sessão.",
    )
    if enviado is not None:
        temporario = Path(tempfile.gettempdir()) / f"edital_ui_{enviado.name}"
        temporario.write_bytes(enviado.getvalue())
        fonte = (temporario, Path(enviado.name).stem[:40], enviado.name)
        st.success(
            f"{enviado.name} · {len(enviado.getvalue()) / 1024:.0f} KB",
            icon=":material/description:",
        )

with aba_pncp:
    st.caption(
        "Informe o número de controle PNCP da contratação "
        "(formato `CNPJ-1-SEQUENCIAL/ANO`, visível na página da contratação)."
    )
    numero = st.text_input(
        "Número de controle PNCP", placeholder="88201298000149-1-000679/2026",
        icon=":material/tag:",
    )
    if numero:
        casamento = PADRAO_CONTROLE.match(numero.strip())
        if not casamento:
            st.error("Formato inválido. Ex.: `88201298000149-1-000679/2026`.",
                     icon=":material/error:")
        elif st.button("Baixar do PNCP", icon=":material/cloud_download:"):
            cnpj, _, sequencial, ano = casamento.groups()
            destino = Path(tempfile.gettempdir()) / f"pncp_{cnpj}_{ano}_{int(sequencial)}.bin"
            with st.spinner("Baixando documento do PNCP…", show_time=True):
                try:
                    meta = _baixar_do_pncp(cnpj, int(ano), int(sequencial), destino)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Falha ao baixar: {exc}", icon=":material/error:")
                    st.stop()
            st.session_state["pncp_fonte"] = (
                str(destino), numero.strip().replace("/", "-"), meta.get("titulo", numero)
            )
            st.success(
                f"{meta.get('tipo_documento')} · {meta['bytes'] / 1024:.0f} KB · "
                f"SHA256 `{meta['sha256'][:16]}…`",
                icon=":material/check_circle:",
            )
    if "pncp_fonte" in st.session_state and fonte is None:
        caminho, id_e, rotulo = st.session_state["pncp_fonte"]
        fonte = (Path(caminho), id_e, rotulo)

if fonte is None:
    st.info(
        "Envie um arquivo ou informe um número de controle PNCP para começar.",
        icon=":material/upload_file:",
    )
    st.stop()

caminho, id_edital, rotulo = fonte
st.divider()
st.subheader(f"Documento: {rotulo}")

tipo, modelo = execucao.seletor_executor(chave="executor_novo")
pode_rodar = tipo == "baseline" or modelo == "mock" or dados.chave_api_configurada()

if not st.button(
    "Analisar edital", type="primary", disabled=not pode_rodar, icon=":material/play_arrow:"
):
    st.stop()

# ------------------------------------------------------------------- pipeline
progresso = st.status("Processando o edital…", expanded=True)
try:
    with progresso:
        st.write("Extraindo texto (pypdf / DOCX / OCR)…")
        resultado_extracao, indice = _preparar_indice(caminho, id_edital, cfg)
        st.write(
            f"{resultado_extracao.caracteres:,} caracteres · "
            f"{resultado_extracao.n_paginas} páginas · método `{resultado_extracao.metodo}`"
            .replace(",", ".")
        )
        for aviso in resultado_extracao.avisos:
            st.warning(aviso, icon=":material/warning:")
        st.write(f"Indexando {len(indice.chunks)} chunks no FAISS…")

        if tipo == "baseline":
            st.write("Executando baseline por regex…")
            resultado = execucao.executar_baseline(resultado_extracao.texto, id_edital)
        else:
            st.write(f"Executando agente RAG (`{modelo}`)…")
            resultado = execucao.executar_agente(
                indice, id_edital, modelo, cfg["llm"]["max_iteracoes_agente"]
            )
    progresso.update(label="Análise concluída", state="complete", expanded=False)
except Exception as exc:  # noqa: BLE001
    progresso.update(label="Falha na análise", state="error")
    st.error(str(exc), icon=":material/error:")
    st.stop()

st.session_state["indice_novo"] = indice

# -------------------------------------------------------------------- saída
agente = execucao.e_agente(resultado)
if agente:
    execucao.renderizar_custo(resultado)
    st.divider()

st.subheader("Campos extraídos")
st.caption(
    "Edital fora do benchmark: não há ground truth oficial para conferir — a auditoria "
    "aqui é feita pelas evidências citadas."
)
execucao.renderizar_tabela(execucao.tabela_campos(resultado))

if agente:
    st.divider()
    st.subheader("Rastreabilidade de evidências")
    execucao.renderizar_evidencias(resultado)
    with st.expander("Trace das chamadas de ferramenta", icon=":material/timeline:"):
        execucao.renderizar_trace(resultado)

st.divider()
with st.expander("Consultar o índice deste edital", icon=":material/search:"):
    consulta = st.text_input(
        "Busca semântica no documento recém-analisado",
        placeholder="ex.: exigências de qualificação técnica",
    )
    if consulta:
        for chunk, score in indice.buscar(consulta, top_k=4):
            tema.cartao_trecho(chunk.secao, chunk.texto, chunk.id, score)

execucao.botao_download(resultado, id_edital, "novo")
