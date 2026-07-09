"""Carregadores com cache para a interface (dados do benchmark, índices, LLM)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import streamlit as st

from ..config import (
    DIR_BENCHMARK,
    DIR_INDICES,
    DIR_PROCESSADOS,
    DIR_RESULTADOS,
    carregar_config,
)
from ..indexacao.vetorial import FastEmbedEmbedder, IndiceVetorial

EXECUTORES = {
    "baseline": "Baseline (regex)",
    "agente_mock": "Agente RAG (MockLLM, offline)",
    "agente": "Agente RAG (LLM Anthropic)",
}


@st.cache_data(show_spinner=False)
def config() -> dict[str, Any]:
    return carregar_config()


@st.cache_data(show_spinner=False)
def benchmark() -> list[dict[str, Any]]:
    caminho = DIR_BENCHMARK / "benchmark.json"
    if not caminho.exists():
        return []
    return json.loads(caminho.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def documentos() -> dict[str, dict]:
    caminho = DIR_BENCHMARK / "documentos.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


@st.cache_data(show_spinner=False)
def meta_extracao() -> dict[str, dict]:
    caminho = DIR_PROCESSADOS / "extracao_meta.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


@st.cache_data(show_spinner=False)
def estatisticas_indice() -> dict[str, dict]:
    caminho = DIR_INDICES / "estatisticas.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


@st.cache_data(show_spinner=False)
def eda() -> dict[str, Any]:
    caminho = DIR_RESULTADOS / "eda.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


@st.cache_data(show_spinner=False)
def texto_edital(id_edital: str) -> str:
    caminho = DIR_PROCESSADOS / f"{id_edital}.txt"
    return caminho.read_text(encoding="utf-8") if caminho.exists() else ""


@st.cache_data(show_spinner=False)
def avaliacao(alvo: str) -> dict[str, Any] | None:
    caminho = DIR_RESULTADOS / f"avaliacao_{alvo}.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


@st.cache_data(show_spinner=False)
def resultado_extracao(alvo: str, id_edital: str) -> dict[str, Any] | None:
    caminho = DIR_RESULTADOS / alvo / f"{id_edital}.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def alvos_disponiveis() -> list[str]:
    return [a for a in EXECUTORES if (DIR_RESULTADOS / f"avaliacao_{a}.json").exists()]


def editais_indexados() -> set[str]:
    if not DIR_INDICES.exists():
        return set()
    return {d.name for d in DIR_INDICES.iterdir() if (d / "index.faiss").exists()}


@st.cache_resource(show_spinner="Carregando modelo de embeddings (só na 1ª vez)…")
def embedder() -> FastEmbedEmbedder:
    return FastEmbedEmbedder.compartilhado(config()["indexacao"]["modelo_embedding"])


@st.cache_resource(show_spinner="Carregando índice vetorial…")
def indice(id_edital: str) -> IndiceVetorial:
    return IndiceVetorial.carregar(DIR_INDICES / id_edital, embedder())


def registro(id_edital: str) -> dict[str, Any] | None:
    return next((r for r in benchmark() if r["id_edital"] == id_edital), None)


def rotulo_edital(registro: dict[str, Any]) -> str:
    gt = registro["ground_truth"]
    objeto = (gt.get("objeto") or "")[:58]
    return f"{registro['municipio']}/{gt['uf']} · {gt['modalidade']} · {objeto}…"


def chave_api_configurada() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def barra_lateral_chave() -> None:
    """Campo para informar a chave da Anthropic (só nesta sessão, não persistida)."""
    with st.sidebar:
        st.divider()
        if chave_api_configurada():
            st.success("Chave da Anthropic detectada", icon=":material/key:")
            return
        st.caption(
            "O agente com LLM real precisa de uma chave da Anthropic. "
            "Sem ela, use o modo **MockLLM** (offline)."
        )
        chave = st.text_input(
            "ANTHROPIC_API_KEY", type="password", placeholder="sk-ant-…",
            help="Usada apenas nesta sessão; não é gravada em disco.",
        )
        if chave:
            os.environ["ANTHROPIC_API_KEY"] = chave.strip()
            st.rerun()


def aviso_sem_dados() -> bool:
    """Mostra instrução se o benchmark ainda não foi gerado. True se faltar dado."""
    if benchmark():
        return False
    st.warning(
        "Benchmark ainda não construído. Rode o pipeline antes de usar a interface:",
        icon=":material/database_off:",
    )
    st.code("make setup\nmake pipeline-offline", language="bash")
    return True
