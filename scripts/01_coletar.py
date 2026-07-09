"""Etapa 1 — Coleta de editais no PNCP e construção do ground truth.

Amostra editais publicados na janela configurada, com diversidade de
modalidade, UF e órgão (mitigação do risco de amostra homogênea — seção 2.4).
Baixa o documento principal (Edital / Aviso de Contratação Direta), registra
SHA256 (data card) e salva os metadados oficiais como ground truth.

Uso: python scripts/01_coletar.py [--n-editais 16]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from edital_agent.coleta import pncp
from edital_agent.config import DIR_BENCHMARK, DIR_RAW, carregar_config, garantir_diretorios

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("coleta")


def coletar(config: dict, n_editais: int | None = None) -> int:
    cfg = config["coleta"]
    alvo = n_editais or cfg["n_editais"]
    cliente = pncp.PNCPClient(timeout_s=cfg["timeout_s"])
    selecionados: list[pncp.Contratacao] = []
    documentos: dict[str, dict] = {}
    por_uf: dict[str, int] = {}
    por_modalidade: dict[int, int] = {}

    try:
        for modalidade in cfg["modalidades"]:
            if len(selecionados) >= alvo:
                break
            pagina = 1
            while (
                por_modalidade.get(modalidade, 0) < cfg["max_por_modalidade"]
                and len(selecionados) < alvo
                and pagina <= 4
            ):
                resposta = cliente.buscar_contratacoes(
                    cfg["data_inicial"], cfg["data_final"], modalidade,
                    pagina=pagina, tamanho_pagina=50,
                )
                itens = resposta.get("data", [])
                if not itens:
                    break
                for item in itens:
                    if (
                        len(selecionados) >= alvo
                        or por_modalidade.get(modalidade, 0) >= cfg["max_por_modalidade"]
                    ):
                        break
                    contratacao = pncp.Contratacao.de_json(item)
                    if por_uf.get(contratacao.uf, 0) >= cfg["max_por_uf"]:
                        continue
                    if any(
                        s.numero_controle_pncp == contratacao.numero_controle_pncp
                        for s in selecionados
                    ):
                        continue
                    doc = _baixar_documento(cliente, contratacao)
                    if doc is None:
                        continue
                    pncp.enriquecer_com_itens(cliente, contratacao)
                    selecionados.append(contratacao)
                    documentos[contratacao.id_edital] = doc
                    por_uf[contratacao.uf] = por_uf.get(contratacao.uf, 0) + 1
                    por_modalidade[modalidade] = por_modalidade.get(modalidade, 0) + 1
                    logger.info(
                        "[%d/%d] %s | %s | %s-%s | R$ %s",
                        len(selecionados), alvo, contratacao.numero_controle_pncp,
                        contratacao.modalidade_nome, contratacao.municipio, contratacao.uf,
                        contratacao.valor_total_estimado,
                    )
                pagina += 1
    finally:
        cliente.fechar()

    if not selecionados:
        logger.error("Nenhum edital coletado — verifique a janela de datas/conexão.")
        return 1

    pncp.salvar_benchmark(selecionados, DIR_BENCHMARK / "benchmark.json")
    (DIR_BENCHMARK / "documentos.json").write_text(
        json.dumps(documentos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "Coletados %d editais | modalidades: %s | UFs: %s",
        len(selecionados), dict(por_modalidade), dict(por_uf),
    )
    return 0


def _baixar_documento(cliente: pncp.PNCPClient, c: pncp.Contratacao) -> dict | None:
    """Baixa o documento principal; devolve metadados ou None se inviável."""
    try:
        arquivos = cliente.listar_arquivos(c.cnpj, c.ano, c.sequencial)
        escolhido = pncp.escolher_arquivo_edital(arquivos)
        if escolhido is None:
            return None
        destino = DIR_RAW / f"{c.id_edital}.bin"
        meta = cliente.baixar_arquivo(pncp.url_download_arquivo(escolhido), destino)
        if meta["bytes"] < 10_000:  # provavelmente não é o edital completo
            destino.unlink(missing_ok=True)
            return None
        meta.update(
            {
                "titulo": escolhido.get("titulo"),
                "tipo_documento": escolhido.get("tipoDocumentoNome"),
                "arquivo_local": destino.name,
            }
        )
        return meta
    except Exception as exc:
        logger.warning("Documento indisponível para %s: %s", c.numero_controle_pncp, exc)
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-editais", type=int, default=None)
    args = parser.parse_args()
    garantir_diretorios()
    sys.exit(coletar(carregar_config(), args.n_editais))
