"""Execução de extratores a partir da interface e renderização das evidências."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from ..agente.agente import AgenteEdital
from ..agente.schema import CAMPOS, CAMPOS_CRITICOS
from ..avaliacao.ragas_metrics import comparar_campo
from ..baseline.regex_extractor import extrair_por_regex
from ..indexacao.vetorial import IndiceVetorial
from ..llm.cliente import criar_llm
from . import dados, tema

ROTULOS_CAMPO = {
    "prazo_entrega_proposta": "Prazo p/ entrega de propostas",
    "valor_estimado": "Valor estimado",
    "modalidade": "Modalidade",
    "objeto": "Objeto",
    "orgao_responsavel": "Órgão responsável",
    "uf": "UF",
    "criterio_julgamento": "Critério de julgamento",
    "prazo_execucao": "Prazo de execução",
}


def executar_agente(
    indice: IndiceVetorial, id_edital: str, modelo: str, max_iteracoes: int
) -> dict[str, Any]:
    """Roda o loop agêntico e devolve o resultado serializado."""
    llm = criar_llm(modelo, max_tokens=dados.config()["llm"]["max_tokens"])
    agente = AgenteEdital(llm, indice, max_iteracoes=max_iteracoes)
    return agente.executar(id_edital).como_dict()


def executar_baseline(texto: str, id_edital: str) -> dict[str, Any]:
    import time

    inicio = time.monotonic()
    extracao = extrair_por_regex(texto)
    return {
        "id_edital": id_edital,
        "extracao": extracao.como_dict(),
        "latencia_s": round(time.monotonic() - inicio, 4),
        "executor": "baseline_regex",
    }


def _valores(resultado: dict[str, Any]) -> dict[str, Any]:
    """Normaliza a saída de agente (campos com evidência) e baseline (valores)."""
    extracao = resultado["extracao"]
    primeiro = next(iter(extracao.values()), None)
    if isinstance(primeiro, dict):  # agente
        return {c: extracao[c]["valor"] for c in extracao}
    return dict(extracao)  # baseline


def e_agente(resultado: dict[str, Any]) -> bool:
    primeiro = next(iter(resultado["extracao"].values()), None)
    return isinstance(primeiro, dict)


def tabela_campos(
    resultado: dict[str, Any], ground_truth: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Tabela dos 8 campos com valor, confiança, evidência e acerto vs. GT."""
    valores = _valores(resultado)
    agente = e_agente(resultado)
    tolerancia = dados.config()["avaliacao"]["tolerancia_valor_pct"]

    linhas = []
    for campo in CAMPOS:
        valor = valores.get(campo)
        linha: dict[str, Any] = {
            "campo": ROTULOS_CAMPO[campo],
            "crítico": campo in CAMPOS_CRITICOS,
            "valor extraído": "—" if valor is None else str(valor),
        }
        if agente:
            info = resultado["extracao"][campo]
            linha["confiança"] = info.get("confianca")
            linha["evidência"] = ", ".join(
                c.split("#")[-1] for c in info.get("chunks_evidencia", [])
            ) or "—"
            valida = info.get("evidencia_valida")
            linha["citação válida"] = (
                "—" if valida is None else ("sim" if valida else "não")
            )
        if ground_truth is not None:
            esperado = ground_truth.get(campo)
            linha["ground truth"] = "—" if esperado is None else str(esperado)
            if campo in ground_truth:
                acerto = comparar_campo(campo, valor, esperado, tolerancia)
                linha["acerto"] = (
                    "abstenção correta" if acerto is None else ("sim" if acerto else "não")
                )
            else:
                linha["acerto"] = "sem GT"
        linhas.append(linha)
    return pd.DataFrame(linhas)


def renderizar_tabela(df: pd.DataFrame) -> None:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "crítico": st.column_config.CheckboxColumn(width="small"),
            "confiança": st.column_config.ProgressColumn(
                format="%.2f", min_value=0.0, max_value=1.0, width="small"
            ),
            "valor extraído": st.column_config.TextColumn(width="medium"),
            "ground truth": st.column_config.TextColumn(width="medium"),
        },
    )


def renderizar_evidencias(resultado: dict[str, Any]) -> None:
    """Para cada campo preenchido: citação literal destacada no chunk de origem."""
    contextos = {c["chunk_id"]: c for c in resultado.get("contextos", [])}
    extracao = resultado["extracao"]
    algum = False
    for campo in CAMPOS:
        info = extracao[campo]
        if info["valor"] is None:
            continue
        algum = True
        valida = info.get("evidencia_valida")
        icone = (
            ":material/verified:" if valida
            else (":material/report:" if valida is False else ":material/help:")
        )
        with st.expander(
            f"{ROTULOS_CAMPO[campo]} · {info['valor']}", icon=icone
        ):
            if info.get("citacao"):
                st.markdown(f"> {info['citacao']}")
            if valida is False:
                st.warning(
                    "A citação não foi confirmada nos trechos recuperados — "
                    "candidata a alucinação.",
                    icon=":material/warning:",
                )
            ids = info.get("chunks_evidencia") or []
            if not ids:
                st.caption("Nenhum chunk citado.")
            for chunk_id in ids:
                ctx = contextos.get(chunk_id)
                if ctx is None:
                    st.caption(f"Chunk `{chunk_id}` não consta nos trechos recuperados.")
                    continue
                tema.cartao_trecho(
                    ctx["secao"], ctx["texto"], chunk_id, destaque=info.get("citacao")
                )
    if not algum:
        st.info("Nenhum campo foi preenchido.", icon=":material/info:")


def renderizar_custo(resultado: dict[str, Any]) -> None:
    uso = resultado.get("uso", {})
    col = st.columns(5)
    col[0].metric("Iterações", resultado.get("iteracoes", "—"))
    col[1].metric("Chamadas ao LLM", uso.get("chamadas", "—"))
    col[2].metric(
        "Tokens (entrada/saída)",
        f"{uso.get('tokens_entrada', 0):,}/{uso.get('tokens_saida', 0):,}".replace(",", "."),
    )
    col[3].metric("Custo estimado", f"US$ {uso.get('custo_usd', 0):.4f}")
    col[4].metric("Latência", f"{resultado.get('latencia_s', 0):.1f} s")
    if uso.get("modelo") == "mock":
        st.caption(
            "MockLLM: custo zero e resultados heurísticos — valida o pipeline, "
            "não mede o agente real."
        )


def renderizar_trace(resultado: dict[str, Any]) -> None:
    trace = resultado.get("trace", [])
    if not trace:
        st.caption("Sem trace de ferramentas.")
        return
    for passo in trace:
        entrada = passo.get("entrada") or {}
        descricao = entrada.get("consulta") or entrada.get("chunk_id") or "—"
        icone = ":material/error:" if passo.get("erro") else ":material/check:"
        st.markdown(
            f"{icone} **iteração {passo['iteracao']}** · `{passo['ferramenta']}` — {descricao}"
        )


def botao_download(resultado: dict[str, Any], id_edital: str, sufixo: str) -> None:
    st.download_button(
        "Baixar resultado (JSON)",
        json.dumps(resultado, ensure_ascii=False, indent=2).encode("utf-8"),
        f"{id_edital}_{sufixo}.json",
        "application/json",
        icon=":material/download:",
    )


def seletor_executor(chave: str = "executor") -> tuple[str, str]:
    """Devolve (tipo, modelo). tipo ∈ {baseline, agente}."""
    opcoes = {
        "Baseline (regex)": ("baseline", ""),
        "Agente RAG · MockLLM (offline)": ("agente", "mock"),
        "Agente RAG · LLM Anthropic": ("agente", dados.config()["llm"]["modelo"]),
    }
    escolha = st.radio(
        "Extrator", list(opcoes), key=chave, horizontal=True,
    )
    tipo, modelo = opcoes[escolha]
    if tipo == "agente" and modelo != "mock":
        if not dados.chave_api_configurada():
            st.warning(
                "Informe a `ANTHROPIC_API_KEY` na barra lateral para usar o LLM real.",
                icon=":material/key_off:",
            )
        else:
            modelo = st.selectbox(
                "Modelo",
                ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
                help="Custo por edital cresce com a capacidade do modelo.",
            )
    return tipo, modelo
