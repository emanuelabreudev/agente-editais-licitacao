"""Schema da extração estruturada com rastreabilidade de evidências.

Cada campo carrega: valor, ids dos chunks que o sustentam (evidência), citação
literal e confiança — requisito central da proposta (rastreabilidade completa
entre cada campo extraído e sua evidência documental).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

CAMPOS = (
    "prazo_entrega_proposta",
    "valor_estimado",
    "modalidade",
    "objeto",
    "orgao_responsavel",
    "uf",
    "criterio_julgamento",
    "prazo_execucao",
)
CAMPOS_CRITICOS = ("prazo_entrega_proposta", "valor_estimado", "modalidade")


class CampoExtraido(BaseModel):
    valor: Any = None
    chunks_evidencia: list[str] = Field(default_factory=list)
    citacao: str | None = None
    confianca: float = 0.0
    evidencia_valida: bool | None = None  # preenchido no pós-processamento


class ExtracaoEdital(BaseModel):
    prazo_entrega_proposta: CampoExtraido = Field(default_factory=CampoExtraido)
    valor_estimado: CampoExtraido = Field(default_factory=CampoExtraido)
    modalidade: CampoExtraido = Field(default_factory=CampoExtraido)
    objeto: CampoExtraido = Field(default_factory=CampoExtraido)
    orgao_responsavel: CampoExtraido = Field(default_factory=CampoExtraido)
    uf: CampoExtraido = Field(default_factory=CampoExtraido)
    criterio_julgamento: CampoExtraido = Field(default_factory=CampoExtraido)
    prazo_execucao: CampoExtraido = Field(default_factory=CampoExtraido)

    def campo(self, nome: str) -> CampoExtraido:
        return getattr(self, nome)

    def valores(self) -> dict[str, Any]:
        return {nome: self.campo(nome).valor for nome in CAMPOS}


def _schema_campo(descricao: str, tipo_valor: dict) -> dict:
    return {
        "type": "object",
        "description": descricao,
        "properties": {
            "valor": {**tipo_valor, "description": "Valor extraído; null se ausente no edital."},
            "chunks_evidencia": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ids dos chunks (ex.: 'xxx#c0012') que sustentam o valor.",
            },
            "citacao": {
                "type": ["string", "null"],
                "description": "Trecho literal e curto (<=200 chars) copiado do chunk citado.",
            },
            "confianca": {
                "type": "number",
                "description": "Confiança de 0 a 1.",
            },
        },
        "required": ["valor", "chunks_evidencia", "citacao", "confianca"],
        "additionalProperties": False,
    }


def schema_ferramenta_extracao() -> dict:
    """JSON Schema (strict) da ferramenta final `registrar_extracao`."""
    props = {
        "prazo_entrega_proposta": _schema_campo(
            "Data limite para entrega/encerramento de recebimento das propostas.",
            {"type": ["string", "null"]},
        ),
        "valor_estimado": _schema_campo(
            "Valor total estimado da contratação em reais (número, sem 'R$').",
            {"type": ["number", "null"]},
        ),
        "modalidade": _schema_campo(
            "Modalidade da licitação.",
            {
                "type": ["string", "null"],
                "enum": [
                    "pregao eletronico", "pregao presencial", "concorrencia",
                    "dispensa", "inexigibilidade", "leilao", "concurso",
                    "credenciamento", None,
                ],
            },
        ),
        "objeto": _schema_campo("Descrição do objeto da licitação.", {"type": ["string", "null"]}),
        "orgao_responsavel": _schema_campo(
            "Órgão/entidade licitante.", {"type": ["string", "null"]}
        ),
        "uf": _schema_campo(
            "Sigla da unidade federativa do órgão (ex.: SP).", {"type": ["string", "null"]}
        ),
        "criterio_julgamento": _schema_campo(
            "Critério de julgamento.",
            {
                "type": ["string", "null"],
                "enum": [
                    "menor preco", "maior desconto", "tecnica e preco",
                    "melhor tecnica", "maior lance", "maior retorno economico", None,
                ],
            },
        ),
        "prazo_execucao": _schema_campo(
            "Prazo de execução/vigência do contrato (ex.: '12 meses').",
            {"type": ["string", "null"]},
        ),
    }
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }
