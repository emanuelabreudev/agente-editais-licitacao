"""Juízes de verificação de afirmações contra contextos recuperados (NLI).

O Faithfulness do RAGAS exige decidir, para cada afirmação da resposta, se ela é
inferível dos chunks recuperados. Implementações:
  - JuizLLM: veredito por LLM (usado na avaliação real);
  - JuizHeuristico: casamento normalizado (datas/valores/categorias) — usado em
    testes/CI e no smoke test offline, sem custo de API.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from ..normalizacao import (
    extrair_data,
    moeda_para_float,
    normalizar_criterio,
    normalizar_data,
    normalizar_modalidade,
    normalizar_texto,
)

logger = logging.getLogger(__name__)


@dataclass
class Afirmacao:
    """Afirmação atômica derivada de um campo extraído."""

    campo: str
    valor: Any
    texto_nl: str  # forma em linguagem natural, usada pelo juiz LLM


class Juiz(Protocol):
    def verificar(self, afirmacao: Afirmacao, contextos: list[str]) -> bool: ...


PROMPT_JUIZ = """Você é um verificador rigoroso. Dada uma AFIRMAÇÃO sobre um edital de licitação \
e TRECHOS literais desse edital, responda se a afirmação pode ser diretamente inferida dos \
trechos (mesmo com formatação diferente de datas/valores, ex.: '06/07/2026' equivale a \
'2026-07-06').

Responda SOMENTE com uma palavra: 'sim' se a afirmação é sustentada pelos trechos, 'nao' caso \
contrário. Se os trechos não contêm a informação, responda 'nao'."""


class JuizLLM:
    """Veredito de suporte via LLM (avaliação real das métricas RAGAS)."""

    def __init__(self, llm):
        self.llm = llm

    def verificar(self, afirmacao: Afirmacao, contextos: list[str]) -> bool:
        contexto = "\n\n---\n\n".join(contextos)[:60000]
        mensagem = (
            f"TRECHOS DO EDITAL:\n{contexto}\n\n"
            f"AFIRMAÇÃO: {afirmacao.texto_nl}\n\n"
            "A afirmação é diretamente inferível dos trechos? Responda 'sim' ou 'nao'."
        )
        resposta = self.llm.criar_mensagem(
            system=PROMPT_JUIZ, messages=[{"role": "user", "content": mensagem}]
        )
        veredito = normalizar_texto(resposta.texto)
        return bool(re.match(r"^\s*sim\b", veredito))


class JuizHeuristico:
    """Casamento normalizado por tipo de campo (determinístico, offline)."""

    def verificar(self, afirmacao: Afirmacao, contextos: list[str]) -> bool:
        texto = "\n".join(contextos)
        if afirmacao.valor is None:
            return True
        campo, valor = afirmacao.campo, afirmacao.valor
        if campo in ("prazo_entrega_proposta",):
            alvo = normalizar_data(str(valor))
            if alvo is None:
                return False
            datas = {
                normalizar_data(m.group(0))
                for m in re.finditer(
                    r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4}",
                    texto,
                    re.IGNORECASE,
                )
            }
            return alvo in datas
        if campo == "valor_estimado":
            alvo = moeda_para_float(str(valor))
            if alvo is None:
                return False
            for m in re.finditer(r"R\$\s*[\d\.\s]{1,15},\d{2}", texto):
                candidato = moeda_para_float(m.group(0))
                if candidato and abs(candidato - alvo) / max(alvo, 1e-9) < 0.005:
                    return True
            return False
        if campo == "modalidade":
            return normalizar_modalidade(str(valor)) == normalizar_modalidade(texto[:20000]) or (
                normalizar_modalidade(str(valor)) or ""
            ) in normalizar_texto(texto)
        if campo == "criterio_julgamento":
            return (normalizar_criterio(str(valor)) or "") in normalizar_texto(texto)
        if campo == "uf":
            v = str(valor).upper().strip()
            return bool(re.search(rf"\b{re.escape(v)}\b", texto))
        # campos textuais (objeto, orgao, prazo_execucao): sobreposição de tokens
        tokens = [t for t in normalizar_texto(str(valor)).split() if len(t) > 3]
        if not tokens:
            return False
        texto_norm = normalizar_texto(texto)
        presentes = sum(1 for t in tokens if t in texto_norm)
        return presentes / len(tokens) >= 0.6


TEMPLATES_AFIRMACAO = {
    "prazo_entrega_proposta": "A data limite para entrega das propostas é {v}.",
    "valor_estimado": "O valor total estimado da contratação é R$ {v}.",
    "modalidade": "A modalidade da licitação é {v}.",
    "objeto": "O objeto da licitação é: {v}.",
    "orgao_responsavel": "O órgão responsável pela licitação é {v}.",
    "uf": "O órgão licitante está localizado na UF {v}.",
    "criterio_julgamento": "O critério de julgamento é {v}.",
    "prazo_execucao": "O prazo de execução/vigência do contrato é {v}.",
}


def verificar_gt_no_texto(ground_truth: dict[str, Any], texto: str) -> dict[str, bool]:
    """Verifica quais campos do ground truth (metadados PNCP) constam no texto.

    Alguns órgãos publicam no PNCP apenas documentos resumidos (ex.: relação de
    itens); campos oficiais podem não aparecer no texto baixado. Essa anotação
    permite avaliar o extrator apenas sobre informação de fato disponível.
    """
    juiz = JuizHeuristico()
    verificacao: dict[str, bool] = {}
    for campo, valor in ground_truth.items():
        if valor is None or campo not in TEMPLATES_AFIRMACAO:
            continue
        afirmacao = Afirmacao(campo=campo, valor=valor,
                              texto_nl=TEMPLATES_AFIRMACAO[campo].format(v=valor))
        verificacao[campo] = juiz.verificar(afirmacao, [texto])
    return verificacao


def gerar_afirmacoes(valores: dict[str, Any]) -> list[Afirmacao]:
    """Decompõe a extração em afirmações atômicas (uma por campo preenchido)."""
    afirmacoes = []
    for campo, valor in valores.items():
        if valor is None or campo not in TEMPLATES_AFIRMACAO:
            continue
        afirmacoes.append(
            Afirmacao(
                campo=campo,
                valor=valor,
                texto_nl=TEMPLATES_AFIRMACAO[campo].format(v=valor),
            )
        )
    return afirmacoes
