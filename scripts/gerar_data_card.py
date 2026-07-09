"""Gera data/data_card.md a partir dos metadados de coleta (origem, licença, SHA256).

Uso: python scripts/gerar_data_card.py  (após 01_coletar.py e 02_processar.py)
"""

from __future__ import annotations

import json
from datetime import date

from edital_agent.config import DIR_BENCHMARK, DIR_DADOS, DIR_PROCESSADOS


def main() -> None:
    benchmark = json.loads((DIR_BENCHMARK / "benchmark.json").read_text(encoding="utf-8"))
    documentos = json.loads((DIR_BENCHMARK / "documentos.json").read_text(encoding="utf-8"))
    caminho_meta = DIR_PROCESSADOS / "extracao_meta.json"
    meta = json.loads(caminho_meta.read_text(encoding="utf-8")) if caminho_meta.exists() else {}

    linhas = [
        "# Data Card — Benchmark piloto de editais (PNCP)",
        "",
        f"Gerado automaticamente em {date.today().isoformat()} por `scripts/gerar_data_card.py`.",
        "",
        "## Origem e licença",
        "",
        "- **Fonte**: Portal Nacional de Contratações Públicas (PNCP) — APIs públicas de",
        "  consulta (`https://pncp.gov.br/api/consulta/v1`) e de documentos",
        "  (`https://pncp.gov.br/pncp-api/v1`), sem autenticação.",
        "- **Licença**: dados públicos e abertos (Lei de Acesso à Informação — Lei 12.527/2011).",
        "- **Janela de coleta**: publicações de 01/06/2026 a 15/06/2026 (snapshot estático).",
        "- **PII**: os documentos são atos administrativos públicos; não há dados pessoais",
        "  sensíveis nem necessidade de anonimização.",
        "",
        "## Composição da amostra",
        "",
        f"- **Nº de editais**: {len(benchmark)}",
        f"- **Modalidades**: "
        + ", ".join(sorted({r['ground_truth']['modalidade'] for r in benchmark})),
        f"- **UFs**: " + ", ".join(sorted({r['ground_truth']['uf'] for r in benchmark})),
        f"- **Orçamento sigiloso/ausente**: "
        + str(sum(1 for r in benchmark if r["ground_truth"]["valor_estimado"] is None))
        + " caso(s) (tratados como indisponibilidade, não erro do modelo)",
        "",
        "## Ground truth",
        "",
        "Os campos-alvo vêm dos **metadados oficiais** da contratação no PNCP",
        "(`dataEncerramentoProposta`, `valorTotalEstimado`, `modalidadeNome`,",
        "`objetoCompra`, `razaoSocial`, `ufSigla`, `criterioJulgamentoNome` dos itens).",
        "O campo `gt_presente_no_texto` em `benchmark.json` indica, por campo, se o valor",
        "oficial é verificável no texto do documento baixado (alguns órgãos publicam no",
        "PNCP apenas documentos resumidos).",
        "",
        "## Documentos (rastreabilidade)",
        "",
        "PDFs/DOCX brutos ficam em `data/raw/` (fora do versionamento); para reproduzir,",
        "rode `make coletar` e confira os hashes abaixo.",
        "",
        "| id_edital | documento | tipo | bytes | método extração | SHA256 |",
        "|---|---|---|---|---|---|",
    ]
    for registro in benchmark:
        id_e = registro["id_edital"]
        doc = documentos.get(id_e, {})
        m = meta.get(id_e, {})
        linhas.append(
            f"| {id_e} | {str(doc.get('titulo', ''))[:40]} | {doc.get('tipo_documento', '')} "
            f"| {doc.get('bytes', '')} | {m.get('metodo', '')} | `{doc.get('sha256', '')[:16]}…` |"
        )
    linhas += [
        "",
        "Hashes completos em `data/benchmark/documentos.json`.",
        "",
        "## Vieses e limitações conhecidos",
        "",
        "- Amostra piloto (n=16) concentrada em uma janela de 2 semanas de 2026;",
        "  modalidades de menor volume (inexigibilidade) podem não aparecer.",
        "- Municípios pequenos publicam avisos de dispensa muito curtos (1 página);",
        "  campos oficiais podem não constar no documento (ver `gt_presente_no_texto`).",
        "- PDFs escaneados dependem de OCR (Tesseract); sem os binários instalados as",
        "  páginas de imagem ficam vazias e são reportadas em `extracao_meta.json`.",
    ]
    (DIR_DADOS / "data_card.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"Data card gerado em {DIR_DADOS / 'data_card.md'}")


if __name__ == "__main__":
    main()
