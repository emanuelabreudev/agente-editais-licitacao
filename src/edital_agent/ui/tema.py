"""Paleta e helpers de gráfico (Altair) para a interface.

Paleta de referência validada (contraste + separação para daltonismo), com passos
próprios para claro e escuro — não é um "flip" automático. Um único hue para
magnitude; hues categóricos em ordem fixa, nunca cíclica.
"""

from __future__ import annotations

from typing import Any

import altair as alt
import streamlit as st

CLARO = {
    "superficie": "#fcfcfb",
    "tinta": "#0b0b0b",
    "tinta_2": "#52514e",
    "suave": "#898781",
    "grade": "#e1e0d9",
    "eixo": "#c3c2b7",
    "serie_1": "#2a78d6",  # azul — hue sequencial padrão
    "serie_2": "#1baf7a",  # aqua
    "serie_3": "#eda100",  # amarelo
    "serie_4": "#4a3aa7",  # violeta
    "bom": "#0ca30c",
    "atencao": "#fab219",
    "critico": "#d03b3b",
    "azul_claro": "#9ec5f4",
}

ESCURO = {
    "superficie": "#1a1a19",
    "tinta": "#ffffff",
    "tinta_2": "#c3c2b7",
    "suave": "#898781",
    "grade": "#2c2c2a",
    "eixo": "#383835",
    "serie_1": "#3987e5",
    "serie_2": "#199e70",
    "serie_3": "#c98500",
    "serie_4": "#9085e9",
    "bom": "#0ca30c",
    "atencao": "#fab219",
    "critico": "#d03b3b",
    "azul_claro": "#184f95",
}


def modo_escuro() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def paleta() -> dict[str, str]:
    return ESCURO if modo_escuro() else CLARO


def cor(nome: str) -> str:
    return paleta()[nome]


def _config(chart: alt.Chart) -> alt.Chart:
    p = paleta()
    return (
        chart.configure_view(strokeWidth=0)
        .configure_axis(
            grid=True,
            gridColor=p["grade"],
            gridWidth=0.8,
            domainColor=p["eixo"],
            tickColor=p["eixo"],
            labelColor=p["suave"],
            titleColor=p["tinta_2"],
            labelFontSize=11,
            titleFontSize=11,
            titleFontWeight="normal",
        )
        .configure_legend(
            labelColor=p["tinta_2"], titleColor=p["tinta_2"], symbolType="square"
        )
        .configure_title(color=p["tinta"], fontSize=13, anchor="start")
    )


def barras_horizontais(
    df,
    campo_valor: str,
    campo_categoria: str,
    titulo: str = "",
    rotulo_valor: str = "",
    formato: str = ",.0f",
    altura_barra: int = 30,
    cor_barra: str | None = None,
) -> alt.Chart:
    """Barras horizontais com rótulos diretos e tooltip (camada de hover)."""
    p = paleta()
    n = max(1, len(df))
    base = alt.Chart(df).encode(
        y=alt.Y(f"{campo_categoria}:N", sort="-x", title=None,
                axis=alt.Axis(labelLimit=220)),
        x=alt.X(f"{campo_valor}:Q", title=rotulo_valor or None),
        tooltip=[
            alt.Tooltip(f"{campo_categoria}:N", title="item"),
            alt.Tooltip(f"{campo_valor}:Q", title=rotulo_valor or "valor", format=formato),
        ],
    )
    barras = base.mark_bar(
        color=cor_barra or p["serie_1"], cornerRadiusEnd=4, height=altura_barra * 0.62
    )
    rotulos = base.mark_text(
        align="left", dx=6, color=p["tinta_2"], fontSize=11
    ).encode(text=alt.Text(f"{campo_valor}:Q", format=formato))
    return _config(
        (barras + rotulos).properties(height=altura_barra * n + 24, title=titulo)
    )


def barras_agrupadas(
    df,
    campo_valor: str,
    campo_categoria: str,
    campo_serie: str,
    titulo: str = "",
    rotulo_valor: str = "",
    formato: str = ".0%",
) -> alt.Chart:
    """Duas ou mais séries lado a lado — legenda sempre presente + tooltip."""
    p = paleta()
    series = sorted(df[campo_serie].unique())
    cores = [p["serie_1"], p["serie_2"], p["serie_3"], p["serie_4"]][: len(series)]
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            y=alt.Y(f"{campo_categoria}:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=220)),
            x=alt.X(f"{campo_valor}:Q", title=rotulo_valor or None,
                    axis=alt.Axis(format=formato)),
            yOffset=alt.YOffset(f"{campo_serie}:N", sort=series),
            color=alt.Color(
                f"{campo_serie}:N",
                scale=alt.Scale(domain=series, range=cores),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip(f"{campo_categoria}:N", title="campo"),
                alt.Tooltip(f"{campo_serie}:N", title="extrator"),
                alt.Tooltip(f"{campo_valor}:Q", title="acurácia", format=formato),
            ],
        )
        .properties(height=42 * df[campo_categoria].nunique() + 40, title=titulo)
    )
    return _config(chart)


def pontos_log(
    df, campo_valor: str, campo_categoria: str, titulo: str = "", rotulo_valor: str = ""
) -> alt.Chart:
    """Dot plot em escala log — comprimento de barra distorce em log."""
    p = paleta()
    base = alt.Chart(df).encode(
        y=alt.Y(f"{campo_categoria}:N", sort="-x", title=None,
                axis=alt.Axis(labelLimit=200)),
        x=alt.X(
            f"{campo_valor}:Q",
            scale=alt.Scale(type="log"),
            title=rotulo_valor or None,
        ),
        tooltip=[
            alt.Tooltip(f"{campo_categoria}:N", title="edital"),
            alt.Tooltip(f"{campo_valor}:Q", title="valor (R$)", format=",.2f"),
        ],
    )
    regua = base.mark_rule(color=p["grade"], strokeWidth=1)
    pontos = base.mark_point(
        filled=True, size=110, color=p["serie_1"], stroke=p["superficie"], strokeWidth=2
    )
    return _config((regua + pontos).properties(height=30 * len(df) + 30, title=titulo))


def barra_progresso_meta(valor: float | None, meta: float, maior_melhor: bool = True) -> str:
    """Rótulo textual do status frente à meta (nunca só cor — sempre com texto)."""
    if valor is None:
        return "sem dados"
    atingiu = valor >= meta if maior_melhor else valor <= meta
    return "atingiu a meta" if atingiu else "abaixo da meta"


def estilo_global() -> None:
    """CSS mínimo: tipografia tabular em métricas e cartões de evidência."""
    p = paleta()
    st.markdown(
        f"""
        <style>
          div[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}
          .cartao {{
            border: 1px solid {p['grade']};
            border-radius: 10px;
            padding: 0.85rem 1rem;
            margin-bottom: 0.6rem;
            background: transparent;
          }}
          .cartao-cabecalho {{
            display: flex; justify-content: space-between; align-items: baseline;
            gap: 0.75rem; margin-bottom: 0.35rem;
          }}
          .cartao-secao {{
            color: {p['tinta_2']}; font-size: 0.82rem; font-weight: 600;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
          }}
          .cartao-score {{
            color: {p['suave']}; font-size: 0.78rem; font-variant-numeric: tabular-nums;
            white-space: nowrap;
          }}
          .cartao-texto {{
            color: {p['tinta_2']}; font-size: 0.86rem; line-height: 1.5;
            white-space: pre-wrap; max-height: 11rem; overflow-y: auto;
          }}
          .cartao-texto mark {{
            background: {p['azul_claro']}; color: {p['tinta']};
            padding: 0 2px; border-radius: 2px;
          }}
          .rodape-chunk {{ color: {p['suave']}; font-size: 0.74rem; margin-top: 0.4rem; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def cartao_trecho(
    secao: str, texto: str, chunk_id: str, score: float | None = None,
    destaque: str | None = None,
) -> None:
    """Cartão de um chunk recuperado, com destaque opcional da citação."""
    import html
    import re

    corpo = html.escape(texto)
    if destaque:
        alvo = html.escape(destaque.strip())
        if alvo:
            corpo = re.sub(
                re.escape(alvo), lambda m: f"<mark>{m.group(0)}</mark>", corpo, flags=re.I
            )
    score_txt = f"similaridade {score:.3f}" if score is not None else ""
    st.markdown(
        f"""<div class="cartao">
          <div class="cartao-cabecalho">
            <span class="cartao-secao">{html.escape(secao[:90])}</span>
            <span class="cartao-score">{score_txt}</span>
          </div>
          <div class="cartao-texto">{corpo}</div>
          <div class="rodape-chunk">chunk <code>{html.escape(chunk_id)}</code></div>
        </div>""",
        unsafe_allow_html=True,
    )


def formatar_moeda(valor: Any) -> str:
    if valor is None:
        return "—"
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    except (TypeError, ValueError):
        return str(valor)


def formatar_pct(valor: float | None, casas: int = 1) -> str:
    return f"{100 * valor:.{casas}f}%" if valor is not None else "—"
