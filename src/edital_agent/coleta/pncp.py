"""Cliente das APIs públicas do PNCP (Portal Nacional de Contratações Públicas).

APIs usadas (públicas, sem autenticação — Lei 12.527/2011):
  - Consulta de contratações por data de publicação:
      GET https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao
  - Arquivos de uma compra (edital e anexos):
      GET https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos
  - Itens de uma compra (critério de julgamento, orçamento sigiloso):
      GET https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_CONSULTA = "https://pncp.gov.br/api/consulta/v1"
BASE_PNCP_API = "https://pncp.gov.br/pncp-api/v1"

MODALIDADES = {
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
    8: "Dispensa",
    9: "Inexigibilidade",
}


@dataclass
class Contratacao:
    """Metadados oficiais de uma contratação no PNCP (fonte de ground truth)."""

    numero_controle_pncp: str
    cnpj: str
    ano: int
    sequencial: int
    orgao: str
    uf: str
    municipio: str
    modalidade_id: int
    modalidade_nome: str
    objeto: str
    valor_total_estimado: float | None
    data_abertura_proposta: str | None
    data_encerramento_proposta: str | None
    situacao: str
    criterio_julgamento: str | None = None
    orcamento_sigiloso: bool = False
    bruto: dict[str, Any] = field(default_factory=dict)

    @property
    def id_edital(self) -> str:
        """Identificador de arquivo seguro derivado do numeroControlePNCP."""
        return self.numero_controle_pncp.replace("/", "-")

    @classmethod
    def de_json(cls, item: dict[str, Any]) -> "Contratacao":
        orgao_ent = item.get("orgaoEntidade") or {}
        unidade = item.get("unidadeOrgao") or {}
        return cls(
            numero_controle_pncp=item["numeroControlePNCP"],
            cnpj=orgao_ent.get("cnpj", ""),
            ano=item["anoCompra"],
            sequencial=item["sequencialCompra"],
            orgao=orgao_ent.get("razaoSocial", ""),
            uf=unidade.get("ufSigla", ""),
            municipio=unidade.get("municipioNome", ""),
            modalidade_id=item["modalidadeId"],
            modalidade_nome=item.get("modalidadeNome", ""),
            objeto=item.get("objetoCompra", ""),
            valor_total_estimado=item.get("valorTotalEstimado"),
            data_abertura_proposta=item.get("dataAberturaProposta"),
            data_encerramento_proposta=item.get("dataEncerramentoProposta"),
            situacao=item.get("situacaoCompraNome", ""),
            bruto=item,
        )


class PNCPClient:
    """Cliente HTTP com retry simples para as APIs públicas do PNCP."""

    def __init__(self, timeout_s: float = 60.0, max_tentativas: int = 3):
        self._http = httpx.Client(
            timeout=timeout_s,
            follow_redirects=True,
            headers={"accept": "*/*", "user-agent": "edital-agent/0.1 (uso academico)"},
        )
        self.max_tentativas = max_tentativas

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        ultima_exc: Exception | None = None
        for tentativa in range(self.max_tentativas):
            try:
                resp = self._http.get(url, params=params)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                ultima_exc = exc
                espera = 2**tentativa
                logger.warning("Falha em %s (%s); nova tentativa em %ss", url, exc, espera)
                time.sleep(espera)
        raise RuntimeError(f"Falha após {self.max_tentativas} tentativas: {url}") from ultima_exc

    def buscar_contratacoes(
        self,
        data_inicial: str,
        data_final: str,
        codigo_modalidade: int,
        pagina: int = 1,
        tamanho_pagina: int = 50,
    ) -> dict[str, Any]:
        """Busca contratações publicadas na janela [data_inicial, data_final] (AAAAMMDD)."""
        resp = self._get(
            f"{BASE_CONSULTA}/contratacoes/publicacao",
            params={
                "dataInicial": data_inicial,
                "dataFinal": data_final,
                "codigoModalidadeContratacao": codigo_modalidade,
                "pagina": pagina,
                "tamanhoPagina": max(10, tamanho_pagina),
            },
        )
        if resp.status_code == 204:
            return {"data": [], "totalRegistros": 0, "totalPaginas": 0}
        resp.raise_for_status()
        return resp.json()

    def listar_arquivos(self, cnpj: str, ano: int, sequencial: int) -> list[dict[str, Any]]:
        resp = self._get(f"{BASE_PNCP_API}/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos")
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json()

    def listar_itens(self, cnpj: str, ano: int, sequencial: int) -> list[dict[str, Any]]:
        resp = self._get(
            f"{BASE_PNCP_API}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens",
            params={"pagina": 1, "tamanhoPagina": 50},
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json()

    def baixar_arquivo(self, url: str, destino: Path) -> dict[str, Any]:
        """Baixa um documento e devolve metadados (tamanho, sha256, content-type)."""
        resp = self._get(url)
        resp.raise_for_status()
        conteudo = resp.content
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        return {
            "url": url,
            "bytes": len(conteudo),
            "sha256": hashlib.sha256(conteudo).hexdigest(),
            "content_type": resp.headers.get("content-type", ""),
        }

    def fechar(self) -> None:
        self._http.close()


def enriquecer_com_itens(cliente: PNCPClient, contratacao: Contratacao) -> None:
    """Preenche critério de julgamento e orçamento sigiloso a partir dos itens."""
    try:
        itens = cliente.listar_itens(contratacao.cnpj, contratacao.ano, contratacao.sequencial)
    except Exception as exc:  # itens são complemento; falha não bloqueia a coleta
        logger.warning("Itens indisponíveis para %s: %s", contratacao.numero_controle_pncp, exc)
        return
    criterios = Counter(
        i.get("criterioJulgamentoNome") for i in itens if i.get("criterioJulgamentoNome")
    )
    if criterios:
        contratacao.criterio_julgamento = criterios.most_common(1)[0][0]
    contratacao.orcamento_sigiloso = any(i.get("orcamentoSigiloso") for i in itens)
    if contratacao.orcamento_sigiloso:
        # Orçamento sigiloso: ausência de valor é indisponibilidade, não erro do modelo
        contratacao.valor_total_estimado = None


def escolher_arquivo_edital(arquivos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Escolhe o documento principal (Edital ou Aviso de Contratação Direta)."""
    ativos = [a for a in arquivos if a.get("statusAtivo", True)]
    for tipo in ("Edital", "Aviso de Contratação Direta"):
        candidatos = [a for a in ativos if a.get("tipoDocumentoNome") == tipo]
        if candidatos:
            return candidatos[0]
    return ativos[0] if ativos else None


def url_download_arquivo(arquivo: dict[str, Any]) -> str:
    """URL canônica de download na porta 443.

    O campo `url` retornado pela API embute portas altas (ex.: :40566) que
    frequentemente estouram timeout; o mesmo recurso responde na porta padrão.
    """
    return (
        f"{BASE_PNCP_API}/orgaos/{arquivo['cnpj']}/compras/"
        f"{arquivo['anoCompra']}/{arquivo['sequencialCompra']}/arquivos/"
        f"{arquivo['sequencialDocumento']}"
    )


def salvar_benchmark(contratacoes: list[Contratacao], caminho: Path) -> None:
    """Serializa o ground truth (metadados oficiais do PNCP) do benchmark."""
    registros = []
    for c in contratacoes:
        registros.append(
            {
                "id_edital": c.id_edital,
                "numero_controle_pncp": c.numero_controle_pncp,
                "ground_truth": {
                    "prazo_entrega_proposta": c.data_encerramento_proposta,
                    "valor_estimado": c.valor_total_estimado,
                    "modalidade": c.modalidade_nome,
                    "objeto": c.objeto,
                    "orgao_responsavel": c.orgao,
                    "uf": c.uf,
                    "criterio_julgamento": c.criterio_julgamento,
                },
                "orcamento_sigiloso": c.orcamento_sigiloso,
                "municipio": c.municipio,
                "situacao": c.situacao,
                "fonte": "PNCP - API pública de consulta (metadados oficiais)",
            }
        )
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8"
    )
