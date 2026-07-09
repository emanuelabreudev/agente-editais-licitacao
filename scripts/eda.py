"""EDA do benchmark: composição da amostra, valores, tamanho dos documentos.

Gera figuras (relatorio/figuras/) e estatísticas (relatorio/resultados/eda.json).
Estilo: hue único para magnitude (sem paleta arco-íris), grid recessivo,
rótulos diretos nas barras — paleta de referência validada do guia de dataviz.
"""

from __future__ import annotations

import json
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from edital_agent.config import (
    DIR_BENCHMARK, DIR_FIGURAS, DIR_INDICES, DIR_PROCESSADOS, DIR_RESULTADOS,
    garantir_diretorios,
)

# Paleta de referência (dataviz) — modo claro
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
AZUL = "#2a78d6"       # hue sequencial padrão (magnitude)
AZUL_CLARO = "#9ec5f4"  # passo 200 da rampa (destaque secundário)

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.edgecolor": BASELINE,
        "font.family": "sans-serif",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
    }
)


def _preparar_eixo(ax, eixo_grid: str = "x"):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    if eixo_grid == "x":
        ax.spines["bottom"].set_visible(False)
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
    else:
        ax.spines["left"].set_visible(False)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)


def _barras_horizontais(rotulos, valores, titulo, arquivo, xlabel="editais",
                        fmt=lambda v: f"{v:g}"):
    fig, ax = plt.subplots(figsize=(7, 0.5 * len(rotulos) + 1.6), dpi=150)
    y = np.arange(len(rotulos))
    ax.barh(y, valores, height=0.62, color=AZUL, zorder=2)
    ax.set_yticks(y, rotulos)
    ax.invert_yaxis()
    _preparar_eixo(ax, "x")
    vmax = max(valores)
    for yi, v in zip(y, valores):
        ax.text(v + vmax * 0.015, yi, fmt(v), va="center", ha="left",
                color=INK_2, fontsize=9)
    ax.set_xlim(0, vmax * 1.12)
    ax.set_xlabel(xlabel, color=MUTED)
    ax.set_title(titulo, pad=12)
    fig.tight_layout()
    fig.savefig(DIR_FIGURAS / arquivo, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    garantir_diretorios()
    benchmark = json.loads((DIR_BENCHMARK / "benchmark.json").read_text(encoding="utf-8"))
    meta = json.loads((DIR_PROCESSADOS / "extracao_meta.json").read_text(encoding="utf-8"))
    caminho_idx = DIR_INDICES / "estatisticas.json"
    stats_idx = (
        json.loads(caminho_idx.read_text(encoding="utf-8")) if caminho_idx.exists() else {}
    )

    # ---------------------------------------------------------- composição
    modalidades = Counter(r["ground_truth"]["modalidade"] for r in benchmark)
    ufs = Counter(r["ground_truth"]["uf"] for r in benchmark)
    _barras_horizontais(
        list(modalidades.keys()), list(modalidades.values()),
        "Editais do benchmark por modalidade", "modalidades.png",
    )
    _barras_horizontais(
        [uf for uf, _ in ufs.most_common()], [n for _, n in ufs.most_common()],
        "Editais do benchmark por UF", "ufs.png",
    )

    # ------------------------------------------------------------- valores
    com_valor = sorted(
        (
            (r["ground_truth"]["valor_estimado"], r["municipio"])
            for r in benchmark
            if r["ground_truth"]["valor_estimado"]
        ),
        reverse=True,
    )
    n_sigilosos = sum(1 for r in benchmark if r["ground_truth"]["valor_estimado"] is None)
    fig, ax = plt.subplots(figsize=(7, 0.42 * len(com_valor) + 1.8), dpi=150)
    y = np.arange(len(com_valor))
    valores = [v for v, _ in com_valor]
    # dot plot (não barras): em escala log, comprimento de barra deixa de ser
    # proporcional ao valor — pontos + rótulos diretos evitam a distorção
    ax.hlines(y, xmin=min(valores) * 0.5, xmax=valores, color=GRID,
              linewidth=1.0, zorder=1)
    ax.plot(valores, y, "o", color=AZUL, markersize=8, zorder=2)
    ax.set_yticks(y, [m for _, m in com_valor])
    ax.invert_yaxis()
    ax.set_xscale("log")
    _preparar_eixo(ax, "x")
    for yi, v in zip(y, valores):
        ax.text(v * 1.35, yi, f"R$ {v:,.0f}".replace(",", "."), va="center",
                ha="left", color=INK_2, fontsize=8)
    ax.set_xlim(min(valores) * 0.5, max(valores) * 20)
    ax.set_xlabel("valor estimado (R$, escala log)", color=MUTED)
    ax.set_title(
        f"Valor estimado por edital — {n_sigilosos} caso(s) com orçamento sigiloso/ausente",
        pad=12,
    )
    fig.tight_layout()
    fig.savefig(DIR_FIGURAS / "valores.png", bbox_inches="tight")
    plt.close(fig)

    # ------------------------------------------------- tamanho dos documentos
    tamanhos = sorted(
        ((m["caracteres"] / 1000, id_e) for id_e, m in meta.items()), reverse=True
    )
    _barras_horizontais(
        [i[-11:] for _, i in tamanhos], [round(t, 1) for t, _ in tamanhos],
        "Tamanho do texto extraído por edital (mil caracteres)",
        "documentos.png", xlabel="mil caracteres",
        fmt=lambda v: f"{v:g}k",
    )

    # ------------------------------------------------------------ resumo JSON
    chars = [m["caracteres"] for m in meta.values()]
    paginas = [m["n_paginas"] for m in meta.values() if m["n_paginas"]]
    gt_texto = [r.get("gt_presente_no_texto", {}) for r in benchmark]
    disponibilidade = {
        campo: (
            sum(1 for g in gt_texto if g.get(campo)) /
            max(1, sum(1 for g in gt_texto if campo in g))
        )
        for campo in ("prazo_entrega_proposta", "valor_estimado", "modalidade",
                      "objeto", "orgao_responsavel", "uf", "criterio_julgamento")
    }
    resumo = {
        "n_editais": len(benchmark),
        "modalidades": dict(modalidades),
        "ufs": dict(ufs),
        "orcamento_sigiloso_ou_ausente": n_sigilosos,
        "paginas": {"media": float(np.mean(paginas)), "mediana": float(np.median(paginas)),
                    "max": int(np.max(paginas))},
        "caracteres": {"media": float(np.mean(chars)), "mediana": float(np.median(chars)),
                       "min": int(np.min(chars)), "max": int(np.max(chars))},
        "metodos_extracao": dict(Counter(m["metodo"] for m in meta.values())),
        "chunks": {
            "total": sum(s["n_chunks"] for s in stats_idx.values()),
            "por_edital_media": (
                float(np.mean([s["n_chunks"] for s in stats_idx.values()]))
                if stats_idx else None
            ),
        },
        "gt_verificavel_no_texto_pct": {k: round(v, 3) for k, v in disponibilidade.items()},
    }
    (DIR_RESULTADOS / "eda.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
